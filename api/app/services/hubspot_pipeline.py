"""Shared query service for the Pipeline surface (S18 §2).

Every page that shows HubSpot-sourced deals reads through this service:

- ``/pipeline`` (SPA)                   → :func:`list_pipeline_deals`
- ``/command`` pipeline card (SPA)      → :func:`list_pipeline_deals`
- SOW upload deal picker (SPA)          → :func:`search_pipeline_deals`
- SOW board "Not linked" pill           → :func:`is_hubspot_linked`

Filters on ``opportunity.source = 'hubspot' AND archived_at IS NULL`` for
every list view. Closed-lost stays visible under a separate tab so the
caller filters by ``stage_label`` when it wants only open deals.

The service never contacts HubSpot at read time — every column comes from
the cache populated by :mod:`app.services.hubspot_intake`. The nightly
reconcile keeps the cache honest.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User


@dataclass(frozen=True)
class LinkedSow:
    sow_id: uuid.UUID
    created_at: datetime


@dataclass(frozen=True)
class PipelineDeal:
    opportunity_id: uuid.UUID
    hubspot_deal_id: str | None
    name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    stage: str | None
    stage_label: str | None
    amount: Decimal | None
    owner_id: uuid.UUID | None
    owner_email: str | None
    owner_name: str | None
    close_date: date | None
    hubspot_last_seen_at: datetime | None
    linked_sows: tuple[LinkedSow, ...] = field(default_factory=tuple)


CLOSED_LOST_LABELS: frozenset[str] = frozenset({"closedlost", "closed lost", "closed-lost"})


def _is_closed_lost(stage: str | None, stage_label: str | None) -> bool:
    for candidate in (stage, stage_label):
        if candidate and candidate.strip().lower() in CLOSED_LOST_LABELS:
            return True
    return False


async def _collect_linked_sows(
    session: AsyncSession, opportunity_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[LinkedSow, ...]]:
    if not opportunity_ids:
        return {}
    stmt = (
        select(Sow.id, Sow.opportunity_id, Sow.created_at)
        .where(Sow.opportunity_id.in_(opportunity_ids))
        .where(Sow.archived_at.is_(None))
        .order_by(Sow.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    grouped: dict[uuid.UUID, list[LinkedSow]] = {}
    for sow_id, opp_id, created_at in rows:
        grouped.setdefault(opp_id, []).append(LinkedSow(sow_id=sow_id, created_at=created_at))
    return {opp_id: tuple(v) for opp_id, v in grouped.items()}


def _base_query():
    """Every Pipeline read starts here — HubSpot-sourced, non-archived."""

    return (
        select(Opportunity, Client, User)
        .join(Client, Client.id == Opportunity.client_id, isouter=True)
        .join(User, User.id == Opportunity.owner_id, isouter=True)
        .where(Opportunity.source == "hubspot")
        .where(Opportunity.archived_at.is_(None))
    )


def _row_to_deal(
    opp: Opportunity, client: Client | None, owner: User | None,
    linked: tuple[LinkedSow, ...],
) -> PipelineDeal:
    return PipelineDeal(
        opportunity_id=opp.id,
        hubspot_deal_id=opp.hubspot_deal_id,
        name=opp.stage_label or opp.sales_stage or opp.hubspot_deal_id,
        client_id=client.id if client else None,
        client_name=client.name if client else None,
        stage=opp.sales_stage,
        stage_label=opp.stage_label,
        amount=opp.amount,
        owner_id=owner.id if owner else None,
        owner_email=owner.email if owner else None,
        owner_name=owner.name if owner else None,
        close_date=opp.close_date,
        hubspot_last_seen_at=opp.hubspot_last_seen_at,
        linked_sows=linked,
    )


async def list_pipeline_deals(
    session: AsyncSession,
    *,
    include_closed_lost: bool = False,
    page: int = 1,
    size: int = 50,
) -> tuple[list[PipelineDeal], int, int]:
    """Return (rows, total_open, total_closed_lost) for the Pipeline UI."""

    # Split counts so the tab labels are honest without a second round trip.
    count_stmt = (
        select(Opportunity.stage_label, Opportunity.sales_stage, func.count(Opportunity.id))
        .where(Opportunity.source == "hubspot")
        .where(Opportunity.archived_at.is_(None))
        .group_by(Opportunity.stage_label, Opportunity.sales_stage)
    )
    total_open = 0
    total_closed_lost = 0
    for stage_label, stage, count in (await session.execute(count_stmt)).all():
        if _is_closed_lost(stage, stage_label):
            total_closed_lost += count
        else:
            total_open += count

    stmt = _base_query()
    if not include_closed_lost:
        lowered = func.lower(func.coalesce(Opportunity.stage_label, Opportunity.sales_stage, ""))
        stmt = stmt.where(~lowered.in_([s for s in CLOSED_LOST_LABELS]))
    # NULLS LAST portable ordering: primary key = "date is null" so nulls sink.
    stmt = stmt.order_by(
        Opportunity.close_date.is_(None).asc(),
        Opportunity.close_date.asc(),
        Opportunity.id.asc(),
    )
    stmt = stmt.offset(max(0, (page - 1) * size)).limit(size)

    ids: list[uuid.UUID] = []
    rows: list[tuple[Opportunity, Client | None, User | None]] = []
    for opp, client, owner in (await session.execute(stmt)).all():
        ids.append(opp.id)
        rows.append((opp, client, owner))
    linked = await _collect_linked_sows(session, ids)

    deals = [_row_to_deal(opp, client, owner, linked.get(opp.id, ())) for opp, client, owner in rows]
    return deals, total_open, total_closed_lost


async def get_pipeline_deal(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> PipelineDeal | None:
    stmt = _base_query().where(Opportunity.id == opportunity_id)
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    opp, client, owner = row
    linked = await _collect_linked_sows(session, [opp.id])
    return _row_to_deal(opp, client, owner, linked.get(opp.id, ()))


async def search_pipeline_deals(
    session: AsyncSession, *, q: str, limit: int = 10
) -> list[PipelineDeal]:
    """SOW-upload picker feed. Matches deal id, stage label, or client name."""

    query = (q or "").strip()
    if not query:
        return []
    like = f"%{query.lower()}%"
    stmt = (
        _base_query()
        .where(
            or_(
                func.lower(func.coalesce(Opportunity.hubspot_deal_id, "")).like(like),
                func.lower(func.coalesce(Opportunity.stage_label, "")).like(like),
                func.lower(func.coalesce(Client.name, "")).like(like),
            )
        )
        .order_by(Opportunity.close_date.is_(None).asc(), Opportunity.close_date.asc())
        .limit(limit)
    )
    ids: list[uuid.UUID] = []
    rows: list[tuple[Opportunity, Client | None, User | None]] = []
    for opp, client, owner in (await session.execute(stmt)).all():
        ids.append(opp.id)
        rows.append((opp, client, owner))
    linked = await _collect_linked_sows(session, ids)
    return [_row_to_deal(opp, client, owner, linked.get(opp.id, ())) for opp, client, owner in rows]


async def is_hubspot_linked(session: AsyncSession, opportunity_id: uuid.UUID) -> bool:
    """SOW board uses this to decide whether to render the 'Not linked' pill."""

    stmt = (
        select(Opportunity.id)
        .where(Opportunity.id == opportunity_id)
        .where(Opportunity.hubspot_deal_id.is_not(None))
        .where(Opportunity.archived_at.is_(None))
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None
