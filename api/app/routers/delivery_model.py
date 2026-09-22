"""Delivery Model Builder API (S3 E6).

Router stays thin — all logic lives in
:mod:`app.services.delivery_model` (and the ratified :mod:`app.gm`
library it wraps).

Endpoints:

* ``POST /delivery-model/preview`` — pure compute preview, no persist.
  Every keystroke in the Builder hits this (debounced client-side).
* ``POST /delivery-model/{opportunity_id}/versions`` — Save. Creates one
  immutable ``gm_model`` + N ``resource_line`` + M ``cost_line`` rows +
  a ``gm_model.created`` audit row in one transaction.
* ``GET /delivery-model/{opportunity_id}`` — latest version + rows +
  computed numbers + warnings.
* ``GET /delivery-model/{opportunity_id}/versions`` — list all versions
  for the opportunity (summary only).
* ``GET /delivery-model/versions/{gm_model_id}/xlsx`` — Excel export
  numbers match the compute response for the same inputs (blueprint §7).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.models.opportunity import Opportunity
from app.services.delivery_model import (
    DeliveryModelInputError,
    build_compute_response,
    build_xlsx,
    capacity_conflicts,
    compute_live,
    create_gm_model_version,
    delete_template,
    hr_lead_time_warnings,
    latest_gm_model_for,
    latest_gm_model_for as _latest,  # noqa: F401 (kept for clarity)
    list_gm_models_for,
    list_templates,
    load_gm_model,
    parse_gm_model_payload,
    reorder_phases,
    save_as_template,
    seed_from_template,
    serialize_gm_model,
    serialize_template,
    serialize_warnings,
    summarize_gm_model,
)
from app.services.gm_sandbox import SandboxInputError
from app.services.redact import redact_costs

# Sales/Marketing never see cost bands (story: 403). CEO reads dashboards.
_PREVIEW_ROLES = ("Delivery", "Presales", "Finance", "SystemAdmin")
_WRITE_ROLES = ("Delivery", "SystemAdmin")
_READ_ROLES = (
    "Delivery",
    "Presales",
    "Finance",
    "HR",
    "SystemAdmin",
    "CEO",
    "Legal",
)

router = APIRouter(prefix="/delivery-model", tags=["delivery-model"])


class PreviewRequest(BaseModel):
    engagement_type: str
    inputs: dict[str, Any] = Field(default_factory=dict)


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


async def _load_opportunity(session: AsyncSession, opportunity_id: uuid.UUID) -> Opportunity:
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found")
    return opp


@router.post("/preview")
async def preview_endpoint(
    body: PreviewRequest,
    _user: AuthUser = Depends(require_role(*_PREVIEW_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pure compute preview + capacity / HR warnings. Never writes."""

    try:
        payload = parse_gm_model_payload(
            {
                "engagement_type": body.engagement_type,
                "resource_lines": body.inputs.get("resource_lines", []),
                "cost_lines": body.inputs.get("cost_lines", []),
                "sow_version_id": body.inputs.get("sow_version_id"),
                "delivery_pattern": body.inputs.get("delivery_pattern"),
                "contingency_pct": body.inputs.get("contingency_pct"),
                "warranty_days": body.inputs.get("warranty_days"),
                "total_price": body.inputs.get("total_price"),
            }
        )
        # Templates like fixed_price / assessment / managed_service also carry
        # top-level revenue/price fields; forward them verbatim.
        extra: dict[str, Any] = {}
        for key in (
            "total_price",
            "revenue_us",
            "revenue_india",
            "deliverable",
            "monthly_fee_us",
            "monthly_fee_india",
            "term_months",
            "revenue_cap",
            "replacement_obligation",
        ):
            if key in body.inputs:
                extra[key] = body.inputs[key]
        result = compute_live(payload, extra_inputs=extra)
    except (DeliveryModelInputError, SandboxInputError) as exc:
        raise _bad_request(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc

    capacity = await capacity_conflicts(session, payload.resource_lines)
    hr = hr_lead_time_warnings(payload.resource_lines)
    return redact_costs({
        "engagement_type": payload.engagement_type,
        "computed": build_compute_response(result),
        "warnings": {
            "capacity": serialize_warnings(capacity),
            "hr": serialize_warnings(hr),
        },
    }, set(_user.groups))


@router.post("/{opportunity_id}/versions", status_code=201)
async def create_version_endpoint(
    opportunity_id: uuid.UUID,
    body: dict[str, Any],
    actor: AuthUser = Depends(require_role(*_WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Persist one immutable GM model version + its child rows + audit."""

    await _load_opportunity(session, opportunity_id)
    try:
        payload = parse_gm_model_payload(body)
    except (DeliveryModelInputError, SandboxInputError) as exc:
        raise _bad_request(exc) from exc

    try:
        model = await create_gm_model_version(
            session,
            opportunity_id=opportunity_id,
            actor_id=actor.id,
            payload=payload,
        )
    except DeliveryModelInputError as exc:
        raise _bad_request(exc) from exc

    # Compute + serialize the resulting model for the save-response.
    try:
        from app.services.delivery_model import _extra_inputs_for_model, _model_to_payload
        result = compute_live(_model_to_payload(model), extra_inputs=_extra_inputs_for_model(model))
    except (DeliveryModelInputError, SandboxInputError):
        # Persisted rows are fine even if compute rejects (e.g. missing
        # cost that the payload chose to leave null) — surface the shape
        # without the ``computed`` field.
        return redact_costs(
            {"gm_model": serialize_gm_model(model)}, set(actor.groups)
        )

    capacity = await capacity_conflicts(
        session, payload.resource_lines, exclude_gm_model_id=model.id
    )
    hr = hr_lead_time_warnings(payload.resource_lines)
    response = {
        "gm_model": serialize_gm_model(model, result=result),
        "warnings": {
            "capacity": serialize_warnings(capacity),
            "hr": serialize_warnings(hr),
        },
    }
    # S7 B: strip cost fields for readers without a cost-authorized role.
    # _WRITE_ROLES already restricts to Delivery/SystemAdmin, both allowed
    # so this is a defence-in-depth pass rather than the main enforcement.
    return redact_costs(response, set(actor.groups))


# --- S7 wave 2: templates (declared before ``/{opportunity_id}`` so the
# literal ``/templates`` path matches BEFORE FastAPI tries to parse
# "templates" as a UUID) ---------------------------------------------------


class SaveTemplateRequest(BaseModel):
    gm_model_id: uuid.UUID
    name: str


@router.post("/templates", status_code=201)
async def save_template_endpoint(
    body: SaveTemplateRequest,
    actor: AuthUser = Depends(require_role(*_WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Save an existing GM model version as a reusable template."""

    try:
        tpl = await save_as_template(
            session,
            actor_id=actor.id,
            gm_model_id=body.gm_model_id,
            name=body.name,
        )
    except DeliveryModelInputError as exc:
        raise _bad_request(exc) from exc
    return {"template": serialize_template(tpl)}


# Templates are shape-only (no cost values). Presales sees them so they
# can pick one when starting a new opportunity from the Adviser flow.
_TEMPLATE_READ_ROLES = ("Delivery", "Presales", "SystemAdmin", "Finance")


@router.get("/templates")
async def list_templates_endpoint(
    engagement_type: str | None = None,
    _user: AuthUser = Depends(require_role(*_TEMPLATE_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    tpls = await list_templates(session, engagement_type=engagement_type)
    return {"items": [serialize_template(t) for t in tpls]}


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template_endpoint(
    template_id: uuid.UUID,
    actor: AuthUser = Depends(require_role(*_WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        await delete_template(session, template_id=template_id, actor_id=actor.id)
    except DeliveryModelInputError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)


@router.get("/versions/{gm_model_id}/xlsx")
async def export_version_endpoint(
    gm_model_id: uuid.UUID,
    _user: AuthUser = Depends(require_role("Delivery", "Finance", "HR", "SystemAdmin", "CEO")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Excel export. Numbers must match the compute response for the same
    inputs (story AC: "download matches the GM sandbox numbers exactly")."""

    try:
        model = await load_gm_model(session, gm_model_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="gm_model not found") from exc

    from app.services.delivery_model import (
        _extra_inputs_for_model,
        _model_to_payload,
    )

    payload = _model_to_payload(model)
    try:
        result = compute_live(payload, extra_inputs=_extra_inputs_for_model(model))
    except (DeliveryModelInputError, SandboxInputError) as exc:
        raise _bad_request(exc) from exc
    response_body = build_compute_response(result)
    xlsx = build_xlsx(model, result, response_body)
    filename = f"gm_model_{gm_model_id}.xlsx"
    return Response(
        content=xlsx,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"content-disposition": f'attachment; filename="{filename}"'},
    )


# --- S7 wave 2: phase reorder + seed-from-template (opportunity-scoped) --


class ReorderPhasesRequest(BaseModel):
    ordered_phase_ids: list[uuid.UUID]


@router.patch("/{opportunity_id}/phases/reorder")
async def reorder_phases_endpoint(
    opportunity_id: uuid.UUID,
    body: ReorderPhasesRequest,
    actor: AuthUser = Depends(require_role(*_WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reorder phases for the latest gm_model on this opportunity."""

    await _load_opportunity(session, opportunity_id)
    model = await latest_gm_model_for(session, opportunity_id)
    if model is None:
        raise HTTPException(status_code=404, detail="no gm_model for opportunity")

    try:
        phases = await reorder_phases(
            session,
            gm_model_id=model.id,
            ordered_phase_ids=body.ordered_phase_ids,
            actor_id=actor.id,
        )
    except DeliveryModelInputError as exc:
        raise _bad_request(exc) from exc

    return {
        "phases": [
            {"id": str(p.id), "name": p.name, "order": p.order} for p in phases
        ]
    }


@router.post("/{opportunity_id}/from-template/{template_id}", status_code=201)
async def seed_from_template_endpoint(
    opportunity_id: uuid.UUID,
    template_id: uuid.UUID,
    actor: AuthUser = Depends(require_role(*_WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Seed a fresh gm_model draft on the opportunity from a template."""

    await _load_opportunity(session, opportunity_id)
    try:
        model = await seed_from_template(
            session,
            opportunity_id=opportunity_id,
            template_id=template_id,
            actor_id=actor.id,
        )
    except DeliveryModelInputError as exc:
        raise _bad_request(exc) from exc

    return redact_costs(
        {"gm_model": serialize_gm_model(model)}, set(actor.groups)
    )


@router.get("/{opportunity_id}")
async def get_latest_endpoint(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Latest version for an opportunity with computed numbers."""

    await _load_opportunity(session, opportunity_id)
    model = await latest_gm_model_for(session, opportunity_id)
    if model is None:
        return {"gm_model": None}

    from app.services.delivery_model import (  # local import — same package
        _extra_inputs_for_model,
        _model_to_payload,
    )

    payload = _model_to_payload(model)
    try:
        result = compute_live(payload, extra_inputs=_extra_inputs_for_model(model))
        capacity = await capacity_conflicts(
            session, payload.resource_lines, exclude_gm_model_id=model.id
        )
        hr = hr_lead_time_warnings(payload.resource_lines)
        response = {
            "gm_model": serialize_gm_model(model, result=result),
            "warnings": {
                "capacity": serialize_warnings(capacity),
                "hr": serialize_warnings(hr),
            },
        }
    except (DeliveryModelInputError, SandboxInputError):
        response = {"gm_model": serialize_gm_model(model)}
    # S7 B: strip cost keys for Legal / Presales readers.
    return redact_costs(response, set(user.groups))


@router.get("/{opportunity_id}/versions")
async def list_versions_endpoint(
    opportunity_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await _load_opportunity(session, opportunity_id)
    models = await list_gm_models_for(session, opportunity_id)
    return {"items": [summarize_gm_model(m) for m in models]}

