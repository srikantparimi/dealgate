"""Deals API — S1-E2.

Endpoints:

- `GET  /deals`         — paginated, row-level filtered list.
- `GET  /deals/{id}`    — deal detail (intake + coverage + tasks + audit).
- `PATCH /deals/{id}`   — mutate owner, engagement_type, next_client_action,
                          next_client_date. Emits audit events.

Governance status is not auto-advanced here — the S2 workflow module owns
transitions. When `engagement_type` becomes non-null we leave `Intake` in
place; only workflow may promote it.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.services.deals import (
    DealListFilters,
    build_deal_count_query,
    build_deal_list_query,
    can_mutate_deal,
    coverage_state_summary,
    get_client_name,
    is_leader,
    latest_gm_model_summary,
)

router = APIRouter(prefix="/deals", tags=["deals"])

# --- schemas ---------------------------------------------------------------


class DealRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hubspot_deal_id: str
    owner_id: uuid.UUID | None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    engagement_type: str | None
    sales_stage: str | None
    governance_status: str
    next_client_action: str | None
    next_client_date: date | None
    coverage_state: str


class DealListResponse(BaseModel):
    items: list[DealRow]
    page: int
    size: int
    total: int


class TaskRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subject: str
    status: str
    due_date: date | None
    escalation_level: int


class AuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ts: datetime
    actor_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class DealDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hubspot_deal_id: str
    owner_id: uuid.UUID | None
    client_id: uuid.UUID | None = None
    client_name: str | None = None
    engagement_type: str | None
    sales_stage: str | None
    governance_status: str
    next_client_action: str | None
    next_client_date: date | None
    coverage_state: str
    tasks: list[TaskRow]
    audit: list[AuditRow]
    # S3 E6: compact summary of the latest gm_model for the deal, or None.
    # The Delivery Model Builder pulls the full payload from
    # /delivery-model/{opportunity_id}; this field lets the deal card
    # render an "existing model" chip + "open builder" affordance without
    # a second request.
    gm_model: dict[str, Any] | None = None


class DealPatch(BaseModel):
    # `None` means "not provided"; to clear a field, the client sends null
    # inside an explicit `set_` object — kept out of scope for Sprint 1.
    owner_id: uuid.UUID | None = None
    engagement_type: str | None = Field(default=None, max_length=64)
    next_client_action: str | None = Field(default=None, max_length=255)
    next_client_date: date | None = None


# --- helpers ---------------------------------------------------------------


async def _load_opportunity(session: AsyncSession, deal_id: uuid.UUID) -> Opportunity:
    opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == deal_id))
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")
    return opp


async def _access_or_403(session: AsyncSession, user: AuthUser, opp: Opportunity) -> None:
    if is_leader(user):
        return
    if opp.owner_id is not None and opp.owner_id == user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")


async def _row_for(session: AsyncSession, opp: Opportunity) -> DealRow:
    coverage = await coverage_state_summary(session, client_id=opp.client_id)
    client_name = await get_client_name(session, opp.client_id)
    return DealRow(
        id=opp.id,
        hubspot_deal_id=opp.hubspot_deal_id,
        owner_id=opp.owner_id,
        client_id=opp.client_id,
        client_name=client_name,
        engagement_type=opp.engagement_type,
        sales_stage=opp.sales_stage,
        governance_status=opp.governance_status,
        next_client_action=opp.next_client_action,
        next_client_date=opp.next_client_date,
        coverage_state=coverage,
    )


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=DealListResponse)
async def list_deals(
    owner: str | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    stage: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DealListResponse:
    filters = DealListFilters(owner=owner, status=status_, stage=stage, page=page, size=size)
    rows = (await session.execute(build_deal_list_query(user, filters))).scalars().all()
    total = (await session.execute(build_deal_count_query(user, filters))).scalar_one()
    items = [await _row_for(session, opp) for opp in rows]
    return DealListResponse(items=items, page=page, size=size, total=int(total))


async def _build_detail(session: AsyncSession, opp: Opportunity) -> DealDetail:
    tasks = (
        await session.execute(
            select(Task).where(Task.owner_id == opp.owner_id).order_by(Task.due_date.asc())
        )
    ).scalars().all() if opp.owner_id else []

    audit_rows = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity == "opportunity", AuditEvent.entity_id == str(opp.id))
            .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
            .limit(10)
        )
    ).scalars().all()

    coverage = await coverage_state_summary(session, client_id=opp.client_id)
    client_name = await get_client_name(session, opp.client_id)
    gm_model_summary = await latest_gm_model_summary(session, opp.id)

    return DealDetail(
        id=opp.id,
        hubspot_deal_id=opp.hubspot_deal_id,
        owner_id=opp.owner_id,
        client_id=opp.client_id,
        client_name=client_name,
        engagement_type=opp.engagement_type,
        sales_stage=opp.sales_stage,
        governance_status=opp.governance_status,
        next_client_action=opp.next_client_action,
        next_client_date=opp.next_client_date,
        coverage_state=coverage,
        tasks=[TaskRow.model_validate(t) for t in tasks],
        audit=[AuditRow.model_validate(a) for a in audit_rows],
        gm_model=gm_model_summary,
    )


@router.get("/{deal_id}", response_model=DealDetail)
async def get_deal(
    deal_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DealDetail:
    opp = await _load_opportunity(session, deal_id)
    await _access_or_403(session, user, opp)
    return await _build_detail(session, opp)


_TRACKED_FIELDS: tuple[str, ...] = (
    "owner_id",
    "engagement_type",
    "next_client_action",
    "next_client_date",
)

_AUDIT_ACTION_BY_FIELD: dict[str, str] = {
    "owner_id": "opportunity.owner_changed",
    "engagement_type": "opportunity.engagement_type_set",
    "next_client_action": "opportunity.next_action_updated",
    "next_client_date": "opportunity.next_action_updated",
}


def _serialize(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, date, datetime)):
        return str(value)
    return value


@router.patch("/{deal_id}", response_model=DealDetail)
async def patch_deal(
    deal_id: uuid.UUID,
    patch: DealPatch,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> DealDetail:
    opp = await _load_opportunity(session, deal_id)
    if not can_mutate_deal(user, opp):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")

    # Extract only fields the client actually included (unset -> ignore).
    provided = patch.model_dump(exclude_unset=True)
    if not provided:
        # No-op patch. Return the deal as-is; do not emit audit events.
        return await _build_detail(session, opp)

    # Compute diff per tracked field and audit each change independently
    # so the audit stream is easy to read and filter later.
    for field_name in _TRACKED_FIELDS:
        if field_name not in provided:
            continue
        old_value = getattr(opp, field_name)
        new_value = provided[field_name]
        if old_value == new_value:
            continue
        setattr(opp, field_name, new_value)
        await append_audit(
            session,
            actor_id=user.id,
            action=_AUDIT_ACTION_BY_FIELD[field_name],
            entity="opportunity",
            entity_id=str(opp.id),
            before={field_name: _serialize(old_value)},
            after={field_name: _serialize(new_value)},
        )

    # Governance status stays `Intake` when engagement_type is null (S2 workflow
    # owns advancement). If engagement_type became non-null we still do not
    # promote here — workflow module writes the transition + audit row.

    await session.commit()
    await session.refresh(opp)

    return await _build_detail(session, opp)
