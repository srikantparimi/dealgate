"""Deal query builder + coverage helper.

Row-level access:

- Leader roles (Finance, Legal, CEO, SystemAdmin, Delivery, HR, SalesLeader,
  Marketing leader roles as they land) see every deal.
- Everyone else sees only the deals they own.

Coverage state:

  S2 E3 wired ``opportunity.client_id`` and moved the pure ``coverage_state``
  logic into :mod:`app.services.clients`. The helper here loads the client's
  agreements (via its legal entities) and delegates. When a deal has no
  ``client_id`` yet (pre-migration backfill) we return ``"No client linked"``
  so the UI never fabricates state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.auth import AuthUser
from app.models.client import Agreement, Client, LegalEntity
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.services.clients import coverage_state as _coverage_state

# Roles that can see every deal (build-guide §3 leader roles + admin).
LEADER_ROLES: frozenset[str] = frozenset(
    {
        "Finance",
        "Legal",
        "CEO",
        "SystemAdmin",
        "Delivery",
        "HR",
        "SalesLeader",
    }
)

# Roles that can mutate a deal's owner / next action when they own the row
# (Sales) or when they are a Sales leader / admin.
SALES_MUTATE_ROLES: frozenset[str] = frozenset({"Sales", "SalesLeader", "SystemAdmin"})


def is_leader(user: AuthUser) -> bool:
    return any(role in LEADER_ROLES for role in user.groups)


def can_mutate_deal(user: AuthUser, opp: Opportunity) -> bool:
    """Owner, SalesLeader or SystemAdmin may mutate; nobody else.

    Note: Sales who do not own the row cannot mutate it — the story is
    explicit that only the owner or a Sales leader may change owner / next
    action.
    """

    if "SystemAdmin" in user.groups or "SalesLeader" in user.groups:
        return True
    if opp.owner_id is not None and opp.owner_id == user.id:
        return True
    return False


@dataclass(frozen=True)
class DealListFilters:
    owner: str | None = None  # "me", a user-id string, or None
    status: str | None = None  # governance_status
    stage: str | None = None  # sales_stage
    page: int = 1
    size: int = 25


def _apply_access(stmt: Select, user: AuthUser) -> Select:
    if is_leader(user):
        return stmt
    return stmt.where(Opportunity.owner_id == user.id)


def _apply_owner_filter(
    stmt: Select, user: AuthUser, owner: str | None
) -> Select:
    if owner is None:
        return stmt
    if owner == "me":
        return stmt.where(Opportunity.owner_id == user.id)
    try:
        owner_uuid = uuid.UUID(owner)
    except ValueError:
        # Unparseable owner filter yields an empty result rather than 500.
        return stmt.where(_never())
    return stmt.where(Opportunity.owner_id == owner_uuid)


def _never() -> ColumnElement[bool]:
    # False literal that SQLAlchemy renders as a real predicate.
    return Opportunity.id != Opportunity.id


def build_deal_list_query(user: AuthUser, filters: DealListFilters) -> Select:
    """Build the paginated list query with row-level access + optional filters."""

    stmt = select(Opportunity)
    stmt = _apply_access(stmt, user)
    stmt = _apply_owner_filter(stmt, user, filters.owner)
    if filters.status:
        stmt = stmt.where(Opportunity.governance_status == filters.status)
    if filters.stage:
        stmt = stmt.where(Opportunity.sales_stage == filters.stage)
    # Default sort: next_client_date ASC NULLS LAST. Portable across SQLite
    # (which has no explicit NULLS LAST) via a computed key.
    null_key = Opportunity.next_client_date.is_(None)
    stmt = stmt.order_by(null_key.asc(), Opportunity.next_client_date.asc(), Opportunity.id.asc())
    offset = max(0, (filters.page - 1) * filters.size)
    stmt = stmt.offset(offset).limit(filters.size)
    return stmt


def build_deal_count_query(user: AuthUser, filters: DealListFilters) -> Select:
    """Row count matching the same access + filter rules (page/size ignored)."""

    from sqlalchemy import func

    stmt = select(func.count(Opportunity.id))
    stmt = _apply_access(stmt, user)
    stmt = _apply_owner_filter(stmt, user, filters.owner)
    if filters.status:
        stmt = stmt.where(Opportunity.governance_status == filters.status)
    if filters.stage:
        stmt = stmt.where(Opportunity.sales_stage == filters.stage)
    return stmt


async def coverage_state_summary(
    session: AsyncSession, client_id: uuid.UUID | None, today: date | None = None
) -> str:
    """Return a short human string for the deal's coverage state.

    Delegates to the pure :func:`app.services.clients.coverage_state` after
    loading the client's agreements. See that function for the label set.
    """

    if client_id is None:
        return "No client linked"

    entity_ids = (
        await session.execute(
            select(LegalEntity.id).where(LegalEntity.client_id == client_id)
        )
    ).scalars().all()
    agreements: list[Agreement] = []
    if entity_ids:
        agreements = list(
            (
                await session.execute(
                    select(Agreement).where(Agreement.legal_entity_id.in_(entity_ids))
                )
            ).scalars()
        )
    return _coverage_state(agreements, today=today)


async def get_client_name(session: AsyncSession, client_id: uuid.UUID | None) -> str | None:
    """Look up the client name for a deal row. ``None`` when unlinked."""

    if client_id is None:
        return None
    row = (
        await session.execute(select(Client.name).where(Client.id == client_id))
    ).scalar_one_or_none()
    return row


async def latest_gm_model_summary(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> dict | None:
    """Compact summary of the newest ``gm_model`` for a deal, if any.

    Kept as a thin joined lookup so ``GET /deals/{id}`` can render the "GM
    model" card without pulling the full builder payload. The Builder page
    calls the dedicated ``/delivery-model/{opportunity_id}`` endpoint for
    resource_lines + cost_lines + computed numbers.
    """

    stmt = (
        select(GmModel)
        .where(GmModel.opportunity_id == opportunity_id)
        .order_by(GmModel.created_at.desc(), GmModel.id.desc())
        .limit(1)
    )
    model = (await session.execute(stmt)).scalar_one_or_none()
    if model is None:
        return None
    return {
        "id": str(model.id),
        "engagement_type": model.engagement_type,
        "delivery_pattern": model.delivery_pattern,
        "revenue_us": (format(model.revenue_us, "f") if model.revenue_us is not None else None),
        "revenue_india": (
            format(model.revenue_india, "f") if model.revenue_india is not None else None
        ),
        "created_at": model.created_at.isoformat() if model.created_at else None,
    }
