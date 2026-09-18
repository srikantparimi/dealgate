"""S6 E9 actuals CSV import endpoints.

Finance/SystemAdmin only (:data:`app.services.actuals_import.ACTUALS_ROLES`).
Business logic lives in :mod:`app.services.actuals_import`; this router
handles role-gating, shape conversion and error mapping (patterned on
:mod:`app.routers.legacy`).

Endpoints:

- ``POST /actuals/import`` — multipart CSV upload; returns the batch.
- ``GET  /actuals/batches`` — paginated list.
- ``GET  /actuals/batches/{id}`` — single-batch detail (with errors).
- ``GET  /actuals/gm-model/{gm_model_id}?period_month=YYYY-MM`` —
  aggregated actual GM for the period.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.actual import ActualImportBatch
from app.services.actuals_import import (
    ACTUALS_ROLES,
    ActualsImportError,
    actual_gm_for,
    assert_role,
    import_csv,
)

router = APIRouter(prefix="/actuals", tags=["actuals"])


# --- role helper ---------------------------------------------------------


async def _finance_user(
    user: AuthUser = Depends(current_user),
) -> AuthUser:
    assert_role(user.groups)
    return user


# --- schemas -------------------------------------------------------------


class ActualBatchRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    uploaded_by: uuid.UUID
    status: str
    row_count: int
    errors: list[dict[str, Any]] | None = None


class ActualBatchListResponse(BaseModel):
    items: list[ActualBatchRow]
    page: int
    size: int
    total: int


class ActualGmResponse(BaseModel):
    gm_model_id: uuid.UUID
    period_month: date
    revenue: str
    cost_us: str
    cost_india: str
    gm_us: str | None
    gm_india: str | None


# --- helpers -------------------------------------------------------------


def _batch_row(batch: ActualImportBatch) -> ActualBatchRow:
    return ActualBatchRow(
        id=batch.id,
        uploaded_by=batch.uploaded_by,
        status=batch.status,
        row_count=batch.row_count,
        errors=batch.errors,
    )


# --- endpoints -----------------------------------------------------------


@router.post("/import", response_model=ActualBatchRow, status_code=201)
async def import_actuals(
    file: UploadFile = File(..., alias="file"),
    actor: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ActualBatchRow:
    payload = await file.read()
    try:
        batch = await import_csv(session, actor_id=actor.id, csv_bytes=payload)
    except ActualsImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc
    return _batch_row(batch)


@router.get("/batches", response_model=ActualBatchListResponse)
async def list_batches(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    _user: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ActualBatchListResponse:
    total = (
        await session.execute(select(func.count(ActualImportBatch.id)))
    ).scalar_one()
    rows = list(
        (
            await session.execute(
                select(ActualImportBatch)
                .order_by(ActualImportBatch.uploaded_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        )
        .scalars()
        .all()
    )
    return ActualBatchListResponse(
        items=[_batch_row(r) for r in rows], page=page, size=size, total=int(total)
    )


@router.get("/batches/{batch_id}", response_model=ActualBatchRow)
async def get_batch(
    batch_id: uuid.UUID,
    _user: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ActualBatchRow:
    row = (
        await session.execute(
            select(ActualImportBatch).where(ActualImportBatch.id == batch_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="batch not found"
        )
    return _batch_row(row)


@router.get("/gm-model/{gm_model_id}", response_model=ActualGmResponse)
async def get_actual_gm(
    gm_model_id: uuid.UUID,
    period_month: str = Query(..., description="YYYY-MM"),
    _user: AuthUser = Depends(_finance_user),
    session: AsyncSession = Depends(get_session),
) -> ActualGmResponse:
    parsed = _parse_period(period_month)
    snap = await actual_gm_for(
        session, gm_model_id=gm_model_id, period_month=parsed
    )
    return ActualGmResponse(
        gm_model_id=gm_model_id,
        period_month=parsed,
        revenue=str(snap.revenue),
        cost_us=str(snap.cost_us),
        cost_india=str(snap.cost_india),
        gm_us=str(snap.gm_us) if snap.gm_us is not None else None,
        gm_india=str(snap.gm_india) if snap.gm_india is not None else None,
    )


def _parse_period(v: str) -> date:
    s = (v or "").strip()
    if len(s) != 7 or s[4] != "-":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"period_month must be YYYY-MM: got {v!r}",
        )
    try:
        return date(int(s[0:4]), int(s[5:7]), 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"period_month must be YYYY-MM: {exc}",
        ) from exc


__all__ = ["router", "ACTUALS_ROLES"]
