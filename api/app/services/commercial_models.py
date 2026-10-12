"""Versioned commercial storage; all monetary calculation stays in app.gm."""

from __future__ import annotations

import uuid
import os
from typing import Any

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, null, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.commercial import ComponentSchedule, HybridPricing, PricingComponent
from app.gm.commercial_adapter import compute_commercial
from app.gm.engine import GmOutcome
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.policy import active_policy

COMPONENT = TypeAdapter(PricingComponent)
SCHEDULE = TypeAdapter(ComponentSchedule)
OUTCOME = TypeAdapter(GmOutcome)


class CommercialInputError(ValueError):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


def _no_floats(value: Any) -> None:
    if isinstance(value, float):
        raise CommercialInputError("Decimal quantities and money must be strings, never floats")
    if isinstance(value, dict):
        for item in value.values():
            _no_floats(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _no_floats(item)


def _no_discarded_fields(raw: Any, canonical: Any, path: str = "component") -> None:
    # Dataclass union parsing selects a typed profile; reject any input it would discard.
    if isinstance(raw, dict):
        if not isinstance(canonical, dict) or raw.keys() - canonical.keys():
            raise CommercialInputError(f"Unknown or incompatible fields at {path}")
        for key, value in raw.items():
            _no_discarded_fields(value, canonical[key], f"{path}.{key}")
    elif isinstance(raw, list):
        if not isinstance(canonical, list) or len(raw) != len(canonical):
            raise CommercialInputError(f"Incompatible entries at {path}")
        for index, value in enumerate(raw):
            _no_discarded_fields(value, canonical[index], f"{path}[{index}]")


def parse_component(raw: dict) -> PricingComponent:
    _no_floats(raw)
    try:
        component = COMPONENT.validate_python(raw)
    except ValidationError as exc:
        raise CommercialInputError(str(exc)) from exc
    _no_discarded_fields(raw, COMPONENT.dump_python(component, mode="json"))
    return component


def _bind_source(component: PricingComponent, sow: SowVersion, policy_version: str) -> None:
    if component.source_id != str(sow.sow_id) or component.source_version != str(sow.id):
        raise CommercialInputError("Commercial component must reference this exact SOW/version")
    if component.policy_version != policy_version:
        raise CommercialInputError("Policy changed; refresh and confirm the current policy", 409)
    if isinstance(component.pricing, HybridPricing):
        for child in component.pricing.components:
            _bind_source(child, sow, policy_version)


async def save_commercial_model(
    session: AsyncSession, *, opportunity_id: uuid.UUID, actor_id: uuid.UUID,
    sow_version_id: uuid.UUID, expected_gm_model_id: uuid.UUID | None,
    inputs: dict, change_reason: str,
) -> GmModel:
    from app.services.delivery_model import load_gm_model
    from app.services.approvals import active_package_for, void_on_change

    if not change_reason.strip():
        raise CommercialInputError("A written commercial confirmation/change reason is required")
    component = parse_component(inputs)
    opp = await session.scalar(select(Opportunity).where(
        Opportunity.id == opportunity_id).with_for_update())
    if opp is None:
        raise CommercialInputError("Opportunity not found", 404)
    sow = await session.scalar(select(SowVersion).join(Sow).where(
        SowVersion.id == sow_version_id, Sow.opportunity_id == opportunity_id,
        SowVersion.discarded_at.is_(None), SowVersion.superseded_by.is_(None)))
    if sow is None:
        raise CommercialInputError("Current SOW version not found for this opportunity", 409)
    from app.models.approval import ApprovalPackage
    from app.models.signed_sow import SignedSowUpload
    signed_basis = await session.scalar(select(ApprovalPackage.id).where(
        ApprovalPackage.sow_version_id == sow.id,
        or_(ApprovalPackage.status == "released", ApprovalPackage.id.in_(
            select(SignedSowUpload.package_id).where(SignedSowUpload.verify_status == "verified"))),
    ).limit(1))
    if signed_basis:
        raise CommercialInputError("Signed financial basis is immutable; create a separate amendment SOW version", 409)
    current = await session.scalar(select(GmModel).where(
        GmModel.opportunity_id == opportunity_id, GmModel.sow_id == sow.sow_id,
    ).order_by(GmModel.version.desc(), GmModel.created_at.desc()).limit(1))
    if (current.id if current else None) != expected_gm_model_id:
        raise CommercialInputError("GM version changed; refresh before saving", 409)
    policy = await active_policy(session)
    policy_version = str(policy.id) if policy.id else "blueprint-defaults-v1"
    _bind_source(component, sow, policy_version)
    result = compute_commercial(component, us_floor=policy.us_floor, india_floor=policy.india_floor)
    outcome, schedule = result.gm_outcome, result.commercial_schedule

    # Saving the staffing plan is the user's confirmation of its contract
    # window. Keep the still-draft SOW terms aligned so the following Confirm
    # SOW screen opens with the same dates instead of asking for them again.
    # Submitted SOW versions remain immutable and are never rewritten here.
    if sow.confirmed_at is None:
        from app.services.sow_extract import confirm_field

        for field_name, value in (
            ("term_start", component.service_start),
            ("term_end", component.service_end),
        ):
            if value is not None:
                await confirm_field(
                    session,
                    actor_id=actor_id,
                    sow_version_id=sow.id,
                    field_name=field_name,
                    value=value.isoformat(),
                )

    snapshot = {
        "schema_version": "commercial-model-v1",
        "tenant_id": os.environ.get("DEALGATE_TENANT_ID"),
        "environment": os.environ.get("DEALGATE_ENV", "local"),
        "policy": {"version": policy_version, "us_floor": str(policy.us_floor),
                   "india_floor": str(policy.india_floor), "fx_convention": policy.fx_convention},
        "schedule": SCHEDULE.dump_python(schedule, mode="json"),
        "outcome": OUTCOME.dump_python(outcome, mode="json"),
        "change_reason": change_reason.strip(),
    }
    version = await session.scalar(select(func.max(GmModel.version)).where(
        GmModel.opportunity_id == opportunity_id)) or 0
    model = GmModel(
        id=uuid.uuid4(), opportunity_id=opportunity_id, sow_id=sow.sow_id,
        sow_version_id=sow.id, engagement_type=component.profile,
        currency=component.currency or "", created_by=actor_id, version=version + 1,
        direct_costs_reviewed=component.costs_confirmed,
        commercial_inputs=COMPONENT.dump_python(component, mode="json"), commercial_snapshot=snapshot,
        revenue_us=result.revenue_us if result.complete else null(),
        revenue_india=result.revenue_india if result.complete else null(),
    )
    session.add(model)
    await session.flush()
    await append_audit(session, actor_id=actor_id, action="gm_model.created", entity="gm_model",
                       entity_id=str(model.id), before=None,
                       after={"opportunity_id": str(opportunity_id), "sow_version_id": str(sow.id),
                              "version": model.version, "profile": component.profile,
                              "policy_version": policy_version, "change_reason": change_reason.strip(),
                              "calculation_version": schedule.calculation_version,
                              "status": outcome.status})
    package = await active_package_for(session, opportunity_id)
    # An amendment draft must not invalidate a signed/released contract.
    if package and package.sow_version_id == sow.id and package.status != "released":
        from app.models.signed_sow import SignedSowUpload
        signed = await session.scalar(select(SignedSowUpload.id).where(
            SignedSowUpload.package_id == package.id, SignedSowUpload.verify_status == "verified"))
        if not signed:
            await void_on_change(session, opportunity_id=opportunity_id, actor_id=actor_id,
                                 reason=f"commercial model changed (new version {model.id})")
    await session.commit()
    return await load_gm_model(session, model.id)
