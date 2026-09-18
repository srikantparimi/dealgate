"""Admin rate cards API — S2 E4.

Router stays thin: read gates for Finance/Delivery/HR/SystemAdmin, write
gate for Finance/SystemAdmin. All validation + audit lives in
``app.services.rate_cards``. PATCH is deliberately 409 — rate card rows
are immutable versions, and Finance re-publishes to change bands.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.rate_cards import (
    RateCardRowInput,
    _sanity_warnings,
    _validate_row,
    active_rate_card,
    get_rate_card,
    list_rate_cards,
    publish_rate_card,
)

READ_ROLES = ("Finance", "Delivery", "HR", "SystemAdmin")
WRITE_ROLES = ("Finance", "SystemAdmin")

router = APIRouter(prefix="/admin/rate-cards", tags=["admin"])


# --- schemas ---------------------------------------------------------------


class RateCardRowSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | None = None
    role: str = Field(min_length=1, max_length=128)
    seniority: str = Field(min_length=1, max_length=64)
    location: str
    cost_low: Decimal
    cost_base: Decimal
    cost_high: Decimal


class RateCardVersionSummary(BaseModel):
    id: uuid.UUID
    effective_from: date
    published_at: datetime
    published_by: uuid.UUID | None
    notes: str | None
    row_count: int
    is_active: bool = False


class RateCardVersionDetail(RateCardVersionSummary):
    rows: list[RateCardRowSchema]


class RateCardListResponse(BaseModel):
    items: list[RateCardVersionSummary]
    active_id: uuid.UUID | None


class PublishRateCardRequest(BaseModel):
    effective_from: date
    notes: str | None = Field(default=None, max_length=1024)
    rows: list[RateCardRowSchema] = Field(min_length=1)
    confirm: bool = False


class PublishRateCardResponse(BaseModel):
    version: RateCardVersionDetail
    warnings: list[str] = Field(default_factory=list)


# --- helpers ---------------------------------------------------------------


def _to_input(row: RateCardRowSchema) -> RateCardRowInput:
    return RateCardRowInput(
        role=row.role,
        seniority=row.seniority,
        location=row.location,
        cost_low=row.cost_low,
        cost_base=row.cost_base,
        cost_high=row.cost_high,
    )


def _summary(version, *, active_id: uuid.UUID | None) -> RateCardVersionSummary:
    return RateCardVersionSummary(
        id=version.id,
        effective_from=version.effective_from,
        published_at=version.published_at,
        published_by=version.published_by,
        notes=version.notes,
        row_count=len(version.rows),
        is_active=(active_id is not None and version.id == active_id),
    )


def _detail(version, *, active_id: uuid.UUID | None) -> RateCardVersionDetail:
    return RateCardVersionDetail(
        id=version.id,
        effective_from=version.effective_from,
        published_at=version.published_at,
        published_by=version.published_by,
        notes=version.notes,
        row_count=len(version.rows),
        is_active=(active_id is not None and version.id == active_id),
        rows=[RateCardRowSchema.model_validate(r) for r in version.rows],
    )


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=RateCardListResponse)
async def list_rate_cards_endpoint(
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> RateCardListResponse:
    versions = await list_rate_cards(session)
    active = await active_rate_card(session)
    active_id = active.id if active is not None else None
    return RateCardListResponse(
        items=[_summary(v, active_id=active_id) for v in versions],
        active_id=active_id,
    )


@router.get("/{version_id}", response_model=RateCardVersionDetail)
async def get_rate_card_endpoint(
    version_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> RateCardVersionDetail:
    version = await get_rate_card(session, version_id)
    active = await active_rate_card(session)
    active_id = active.id if active is not None else None
    return _detail(version, active_id=active_id)


@router.post("", response_model=PublishRateCardResponse, status_code=201)
async def publish_rate_card_endpoint(
    body: PublishRateCardRequest,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> PublishRateCardResponse:
    inputs = [_to_input(r) for r in body.rows]

    # Run hard validation first (422) so an invalid row can never be masked
    # by the 400 sanity-warning path below.
    for idx, row in enumerate(inputs):
        _validate_row(row, idx)

    # Sanity warnings — surface before write when confirm=False so the UI
    # can prompt Finance to re-check obvious keystroke slips.
    warnings = _sanity_warnings(inputs)
    if warnings and not body.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "cost band(s) below sanity floor — retry with confirm=true",
                "warnings": warnings,
            },
        )

    version = await publish_rate_card(
        session,
        actor_id=actor.id,
        rows=inputs,
        effective_from=body.effective_from,
        notes=body.notes,
    )
    active = await active_rate_card(session)
    active_id = active.id if active is not None else None
    return PublishRateCardResponse(
        version=_detail(version, active_id=active_id),
        warnings=warnings,
    )


@router.patch("/{version_id}")
async def patch_rate_card_endpoint(
    version_id: uuid.UUID,  # noqa: ARG001 — accepted for URL shape, always rejected.
    _user: AuthUser = Depends(require_role(*WRITE_ROLES)),
) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="rate card versions are immutable — publish a new version instead",
    )
