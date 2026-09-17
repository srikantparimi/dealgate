"""Deal query builder + coverage helper for S1-E2.

Row-level access:

- Leader roles (Finance, Legal, CEO, SystemAdmin, Delivery, HR, SalesLeader,
  Marketing leader roles as they land) see every deal.
- Everyone else sees only the deals they own.

Coverage state:

  The Sprint 1 `opportunity` table has no `client_id` column yet (see
  `docs/questions.md`). Until that link exists, the coverage helper accepts an
  optional `client_id` and returns a summary string derived from the client's
  agreements (NDA + MSA). Callers that cannot resolve a client get
  "No client linked" so the UI shows a real, non-fabricated state.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from app.auth import AuthUser
from app.models.client import Agreement, LegalEntity
from app.models.opportunity import Opportunity

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

    Rules (Sprint 1 minimum):

    - No client linked                → "No client linked"
    - No agreements at all            → "NDA missing, MSA missing"
    - Missing NDA or MSA              → "NDA missing" / "MSA missing"
    - Any agreement expired          → "NDA expired" / "MSA expired"
    - Both present, none expired      → "Complete"
    """

    if client_id is None:
        return "No client linked"

    today = today or date.today()
    entities = (
        await session.execute(
            select(LegalEntity.id).where(LegalEntity.client_id == client_id)
        )
    ).scalars().all()
    if not entities:
        return "NDA missing, MSA missing"

    agreements = (
        await session.execute(
            select(Agreement).where(Agreement.legal_entity_id.in_(entities))
        )
    ).scalars().all()

    return _summarize_agreements(agreements, today)


def _summarize_agreements(agreements: Iterable[Agreement], today: date) -> str:
    parts: list[str] = []
    for kind in ("NDA", "MSA"):
        matching = [a for a in agreements if a.kind == kind]
        if not matching:
            parts.append(f"{kind} missing")
            continue
        # Pick the freshest agreement (max expiry, then max effective).
        matching.sort(
            key=lambda a: (
                a.expiry_date or date.min,
                a.effective_date or date.min,
            ),
            reverse=True,
        )
        latest = matching[0]
        if latest.expiry_date is not None and latest.expiry_date < today:
            parts.append(f"{kind} expired")
    return "Complete" if not parts else ", ".join(parts)
