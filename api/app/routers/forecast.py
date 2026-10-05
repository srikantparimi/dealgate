"""S6 E9 — weekly forecast update router.

Thin router. Role-gate + delegate to :mod:`app.services.forecast`. Every
state change flows through the service so the audit + notification chain
lives in one place (CLAUDE.md rule 5).

Endpoints:

- ``POST /forecast/{gm_model_id}`` — write a new immutable snapshot for
  the current ISO week. Delivery / SystemAdmin only.
- ``GET  /forecast/{gm_model_id}/latest`` — the latest snapshot, or 204.
- ``GET  /forecast/{gm_model_id}/history`` — trend data
  (Delivery / HR / Finance / CEO / SystemAdmin).
"""

from __future__ import annotations

import uuid
from typing import Any
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.forecast import (
    ForecastError,
    forecast_history,
    latest_forecast,
    serialize,
    update_forecast,
)
from app.services import forecast_plans
from app.services.redact import redact_costs
from app.services.commercial_models import CommercialInputError


router = APIRouter(prefix="/forecast", tags=["forecast"])


# ---- role gates ---------------------------------------------------------

_READ_ROLES: frozenset[str] = frozenset(
    {"Delivery", "HR", "Finance", "CEO", "SystemAdmin"}
)
_WRITE_ROLES: frozenset[str] = frozenset({"Delivery", "SystemAdmin"})


def _has_any(user: AuthUser, roles: frozenset[str]) -> bool:
    return any(g in roles for g in user.groups)


async def _require_read(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not _has_any(user, _READ_ROLES):
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


async def _require_write(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not _has_any(user, _WRITE_ROLES):
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


def _wrap(exc: ForecastError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---- schemas ------------------------------------------------------------


class ForecastLineInput(BaseModel):
    resource_line_id: uuid.UUID
    remaining_hours: str = Field(..., max_length=32)


class ForecastUpdateBody(BaseModel):
    lines: list[ForecastLineInput] = Field(default_factory=list)


class ForecastHistoryResponse(BaseModel):
    items: list[dict[str, Any]]


# ---- endpoints ----------------------------------------------------------


def _planning_response(value, user):
    # Forecast planning cost/GM is entitlement-controlled independently of demand.
    if not set(user.groups) & forecast_plans.ORG_READ:
        def strip(item):
            if isinstance(item, dict):
                return {key: strip(value) for key, value in item.items()
                        if key not in {"cost", "known_cost", "unavoidable_cost", "gm", "cost_complete",
                                       "commercial_inputs", "commercial_snapshot"}}
            if isinstance(item, list):
                return [strip(value) for value in item]
            return item
        value = strip(value)
    return jsonable_encoder(redact_costs(value, set(user.groups)), custom_encoder={Decimal: lambda value: format(value, "f")})


@router.post("/plans", status_code=201)
async def create_plan(body: forecast_plans.PlanInput, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from app.services.user_provisioning import ensure_user
    await ensure_user(session, user)
    try:
        row = await forecast_plans.save_plan(session, actor=user, body=body)
    except CommercialInputError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"id": str(row.plan_id), "version_id": str(row.id), "version": row.version}


@router.post("/plans/{plan_id}/versions", status_code=201)
async def revise_plan(plan_id: uuid.UUID, body: forecast_plans.PlanInput, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        row = await forecast_plans.save_plan(session, actor=user, body=body, plan_id=plan_id)
    except CommercialInputError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"id": str(row.plan_id), "version_id": str(row.id), "version": row.version}


@router.get("/plans")
async def plans(account_id: uuid.UUID | None = None, page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=200),
                user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    rows = await forecast_plans.list_plans(session, actor=user, account_id=account_id)
    return _planning_response({"items": rows[(page - 1) * size:page * size], "total": len(rows), "page": page, "size": size}, user)


@router.post("/plans/{plan_id}/assumptions", status_code=201)
async def revise_assumptions(plan_id: uuid.UUID, body: forecast_plans.AssumptionsInput,
                             user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        row = await forecast_plans.revise_assumptions(session, actor=user, plan_id=plan_id, body=body)
    except CommercialInputError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"id": str(row.plan_id), "version_id": str(row.id), "version": row.version}


@router.post("/plans/{plan_id}/commercial", status_code=201)
async def revise_commercial_plan(plan_id: uuid.UUID, body: forecast_plans.CommercialRevisionInput,
                                 user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from dataclasses import replace
    from app.services.user_provisioning import ensure_user
    if not set(user.groups) & forecast_plans.PLAN_WRITE:
        raise HTTPException(403, "Delivery or Finance planning permission required")
    canonical = await ensure_user(session, user)
    identity = canonical.id
    # Release identity/audit locks before taking the plan revision lock.
    await session.commit()
    try:
        row = await forecast_plans.revise_commercial(session, actor=replace(user, id=identity), plan_id=plan_id, body=body)
    except CommercialInputError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"id": str(row.plan_id), "version_id": str(row.id), "version": row.version}


@router.get("/outlook")
async def company_outlook(account_id: uuid.UUID | None = None, scenario: str = "expected", future_quarters: int = 2,
                          as_of: datetime | None = None, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        view = await forecast_plans.outlook(session, actor=user, account_id=account_id, as_of=as_of,
                                           scenario=scenario, future_quarters=future_quarters)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _planning_response(view, user)


class ConversionBody(BaseModel):
    gm_model_id: uuid.UUID
    expected_version_id: uuid.UUID
    scope_fraction: str
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/plans/{plan_id}/conversions", status_code=201)
async def convert_scope(plan_id: uuid.UUID, body: ConversionBody, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    try:
        row = await forecast_plans.link_conversion(session, actor=user, plan_id=plan_id, **body.model_dump())
    except ArithmeticError as exc:
        raise HTTPException(422, "Invalid scope fraction") from exc
    return {"id": str(row.id), "plan_id": str(row.plan_id), "gm_model_id": str(row.gm_model_id), "scope_fraction": str(row.scope_fraction)}


@router.post("/{gm_model_id}")
async def post_forecast(
    gm_model_id: uuid.UUID,
    body: ForecastUpdateBody,
    user: AuthUser = Depends(_require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    payload_lines = [
        {
            "resource_line_id": str(line.resource_line_id),
            "remaining_hours": line.remaining_hours,
        }
        for line in body.lines
    ]
    try:
        row = await update_forecast(
            session,
            actor=user,
            gm_model_id=gm_model_id,
            lines=payload_lines,
        )
    except ForecastError as exc:
        raise _wrap(exc) from exc
    return serialize(row)


@router.get("/{gm_model_id}/latest")
async def get_latest(
    gm_model_id: uuid.UUID,
    _user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any] | None:
    row = await latest_forecast(session, gm_model_id)
    return serialize(row) if row is not None else None


@router.get("/{gm_model_id}/history")
async def get_history(
    gm_model_id: uuid.UUID,
    limit: int = Query(default=52, ge=1, le=260),
    _user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> ForecastHistoryResponse:
    rows = await forecast_history(session, gm_model_id, limit=limit)
    return ForecastHistoryResponse(items=[serialize(r) for r in rows])
