"""S5 E9 — renewals inbox + detail + PATCH API (Agent Y2).

Thin router. Role-gate + delegate to :mod:`app.services.renewals`. All
state changes go through the service so the audit + notification chain
lives in one place (CLAUDE.md rule 5).

Endpoints:

- ``GET  /renewals``            — list (any governance role).
- ``GET  /renewals/{id}``       — detail.
- ``PATCH /renewals/{id}``      — update outcome_summary + status +
  replacement_sow_version_id (account owner of the opportunity, or
  SystemAdmin).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.opportunity import Opportunity
from app.services.renewals import (
    RENEWAL_STATUSES,
    RenewalError,
    list_renewals,
    load_renewal,
    patch_renewal,
    serialize_renewal,
)


router = APIRouter(prefix="/renewals", tags=["renewals"])


# ---- role gates ---------------------------------------------------------

# Every governance role reads renewals. The write role is enforced per row
# (opportunity account owner) — the constant just gates the inbox link.
_READ_ROLES: frozenset[str] = frozenset(
    {
        "Sales",
        "SalesLeader",
        "Delivery",
        "HR",
        "Finance",
        "Legal",
        "CEO",
        "SystemAdmin",
    }
)


def _has_any(user: AuthUser, roles: frozenset[str]) -> bool:
    return any(g in roles for g in user.groups)


async def _require_read(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not _has_any(user, _READ_ROLES):
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


async def _load_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    row = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return row


# ---- schemas ------------------------------------------------------------


class RenewalRow(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    term_end: str
    trigger_date: str
    status: str
    outcome_summary: str | None = None
    replacement_sow_version_id: uuid.UUID | None = None
    opened_at: str | None = None
    updated_at: str | None = None
    days_until_end: int
    hubspot_deal_id: str | None = None
    owner_id: uuid.UUID | None = None
    client_id: uuid.UUID | None = None


class RenewalListResponse(BaseModel):
    items: list[dict[str, Any]]
    page: int
    size: int
    total: int


class RenewalPatch(BaseModel):
    outcome_summary: str | None = Field(default=None, max_length=4000)
    status: str | None = Field(default=None, max_length=16)
    replacement_sow_version_id: uuid.UUID | None = None


def _wrap(exc: RenewalError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---- endpoints ----------------------------------------------------------


@router.get("", response_model=RenewalListResponse)
async def list_endpoint(
    status_: str | None = Query(default=None, alias="status"),
    owner: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> RenewalListResponse:
    owner_id: uuid.UUID | None = None
    if owner:
        if owner == "me":
            owner_id = user.id
        else:
            try:
                owner_id = uuid.UUID(owner)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422, detail="owner must be 'me' or a uuid"
                ) from exc
    if status_ is not None and status_ not in RENEWAL_STATUSES:
        raise HTTPException(status_code=422, detail=f"unknown status: {status_!r}")

    try:
        rows, total = await list_renewals(
            session, status_=status_, owner_id=owner_id, page=page, size=size
        )
    except RenewalError as exc:
        raise _wrap(exc) from exc
    return RenewalListResponse(
        items=[serialize_renewal(r, o) for (r, o) in rows],
        page=page,
        size=size,
        total=total,
    )


@router.get("/{renewal_id}")
async def get_endpoint(
    renewal_id: uuid.UUID,
    _user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        renewal = await load_renewal(session, renewal_id)
    except RenewalError as exc:
        raise _wrap(exc) from exc
    opp = await _load_opportunity(session, renewal.opportunity_id)
    return serialize_renewal(renewal, opp)


@router.patch("/{renewal_id}")
async def patch_endpoint(
    renewal_id: uuid.UUID,
    body: RenewalPatch,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        renewal = await load_renewal(session, renewal_id)
    except RenewalError as exc:
        raise _wrap(exc) from exc

    opp = await _load_opportunity(session, renewal.opportunity_id)

    # SystemAdmin or the deal's account owner.
    if "SystemAdmin" not in user.groups:
        if opp.owner_id is None or opp.owner_id != user.id:
            raise HTTPException(
                status_code=403,
                detail="only the account owner or SystemAdmin may edit this renewal",
            )

    provided = body.model_dump(exclude_unset=True)
    summary_provided = "outcome_summary" in provided
    try:
        updated = await patch_renewal(
            session,
            renewal=renewal,
            actor_id=user.id,
            outcome_summary=provided.get("outcome_summary"),
            to_status=provided.get("status"),
            replacement_sow_version_id=provided.get("replacement_sow_version_id"),
            _summary_provided=summary_provided,
        )
    except RenewalError as exc:
        raise _wrap(exc) from exc

    await session.commit()
    await session.refresh(updated)
    return serialize_renewal(updated, opp)
