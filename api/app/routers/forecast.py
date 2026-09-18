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

from fastapi import APIRouter, Depends, HTTPException, Query
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
