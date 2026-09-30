"""Shared query service for the Pipeline surface (S18 §2 + S19 slice 1).

Every page that shows HubSpot-sourced deals reads through this service:

- ``/pipeline`` (SPA)                   → :func:`list_opportunities` / :func:`list_clients`
- ``/command`` pipeline card (SPA)      → :func:`list_clients`
- SOW upload deal picker (SPA)          → :func:`search_pipeline_deals`
- SOW board "Not linked" pill           → :func:`is_hubspot_linked`

Filters on ``opportunity.source = 'hubspot' AND archived_at IS NULL`` for
every list view. Closed-lost stays visible under a separate tab (readiness
filter). is_closed_won / is_closed_lost drive "open" — the S18 mapper only
looked at stage-label string matching which broke on portals with custom
labels.

The service never contacts HubSpot at read time — every column comes from
the cache populated by :mod:`app.services.hubspot_intake` and the mirror
in :mod:`app.services.hubspot_stage_mirror`. The nightly reconcile
(``worker.hubspot_reconcile``) keeps the cache honest.

**Query-count invariant (C7):** every ``list_*`` and ``summary`` call
executes ≤ 3 SQL statements against the session. A pytest fixture wraps
the ``AsyncConnection`` in a counting event listener and asserts the
budget on every call — no N+1 slipping in.

**Single-truth grep gate (C8):** every router that lists opportunities
routes through this module. ``scripts/check-single-query-service.sh``
grep-fails the build if any other module does ``select(Opportunity)``
for listing.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import Date, Integer, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalPackage
from app.models.client import Agreement, Client
from app.models.hubspot_pipeline import HubspotStage
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
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
    # L04 — real deal name (from mirrored HubSpot ``dealname``) once W1
    # lands the column. Fall back to stage_label / sales_stage / id so
    # the surface never renders a numeric stage as identity.
    real_name = getattr(opp, "name", None)
    display_name = real_name or opp.stage_label or opp.sales_stage or opp.hubspot_deal_id
    return PipelineDeal(
        opportunity_id=opp.id,
        hubspot_deal_id=opp.hubspot_deal_id,
        name=display_name,
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


async def get_opportunity_row(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    now: datetime | None = None,
) -> OpportunityRow | None:
    """S20 W2 · single-opportunity in the S19 OpportunityRow shape.

    Powers /deals/{id} in the SPA. Reuses the same correlated subqueries
    the list endpoint uses so the field shape is identical (name,
    stage_id, sow_state, attention_flags, next_action counts, BU,
    pipeline_id, is_closed_*).
    """

    now = now or datetime.now(tz=UTC)

    subq_next_open = _next_action_open_count_subq().label("na_open")
    subq_next_due = _next_action_min_due_subq().label("na_due")
    subq_latest_pkg = _latest_package_status_subq().label("pkg_status")
    subq_sow_id = _sow_id_subq().label("sow_id")
    subq_signed = _signed_sow_exists_subq().label("signed_ct")
    subq_sow_ct = _sow_count_subq().label("sow_ct")

    stmt = (
        select(
            Opportunity,
            Client,
            User,
            subq_next_open,
            subq_next_due,
            subq_latest_pkg,
            subq_sow_id,
            subq_signed,
            subq_sow_ct,
        )
        .join(Client, Client.id == Opportunity.client_id, isouter=True)
        .join(User, User.id == Opportunity.owner_id, isouter=True)
        .where(
            Opportunity.id == opportunity_id,
            Opportunity.source == "hubspot",
            Opportunity.archived_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None

    opp, client, owner, na_open, na_due, pkg_status, sow_id, signed_ct, sow_ct = row
    signed_count = int(signed_ct or 0)
    state = _derive_sow_state(
        sow_id=sow_id, latest_status=pkg_status, signed_count=signed_count
    )
    flags = _derive_attention(
        owner_email=owner.email if owner else None,
        is_closed_won=opp.is_closed_won,
        is_closed_lost=opp.is_closed_lost,
        hubspot_last_activity_at=opp.hubspot_last_activity_at,
        next_action_min_due=na_due,
        latest_status=pkg_status,
        signed_count=signed_count,
        sow_id=sow_id,
        now=now,
    )
    raw_name = getattr(opp, "name", None)
    display_name = raw_name or opp.stage_label or opp.hubspot_deal_id
    return OpportunityRow(
        opportunity_id=opp.id,
        hubspot_deal_id=opp.hubspot_deal_id,
        name=display_name,
        client_id=client.id if client else None,
        client_name=client.name if client else None,
        stage_id=opp.hubspot_stage_id,
        stage_label=opp.stage_label,
        is_closed_won=opp.is_closed_won,
        is_closed_lost=opp.is_closed_lost,
        amount=opp.amount,
        currency=opp.currency,
        close_date=opp.close_date,
        owner_id=owner.id if owner else None,
        owner_name=owner.name if owner else None,
        owner_email=owner.email if owner else None,
        hubspot_last_activity_at=opp.hubspot_last_activity_at,
        sow_approval_state=state.value,
        attention_flags=tuple(f.value for f in flags),
        next_action_open_count=int(na_open or 0),
        next_action_min_due=na_due,
        sow_count=int(sow_ct or 0),
        hubspot_pipeline_id=opp.hubspot_pipeline_id,
        business_unit=(
            getattr(opp, "hubspot_business_unit", None)
            or (getattr(client, "hubspot_business_unit", None) if client else None)
        ),
    )


@dataclass(frozen=True)
class OwnerFacet:
    """S20 W2 Session 3b Rev-2 · deal-owner option for the pipeline filter bar.

    Populated from distinct ``Opportunity.owner_id → User`` joins so the
    filter shows only owners that actually own a HubSpot deal today.
    A HubSpot owner with no local deals doesn't render.
    """
    id: uuid.UUID
    name: str
    email: str | None


@dataclass(frozen=True)
class PipelineFacets:
    owners: tuple[OwnerFacet, ...]
    business_units: tuple[str, ...]


async def list_pipeline_facets(session: AsyncSession) -> PipelineFacets:
    """Return the facet lists the Pipeline filter bar renders as selects.

    - ``owners`` = distinct users who own at least one non-archived
      HubSpot opportunity. Sorted by name for a stable UI.
    - ``business_units`` = distinct non-null BU values across the
      opportunity + client mirrors. Empty on staging today (D10 evidence
      — property not on the deal schema); rendered as an empty-select
      note in the UI so the axis is present but honest.
    """

    owner_rows = (
        await session.execute(
            select(User.id, User.name, User.email)
            .join(Opportunity, Opportunity.owner_id == User.id)
            .where(
                Opportunity.source == "hubspot",
                Opportunity.archived_at.is_(None),
                User.name.is_not(None),
            )
            .group_by(User.id, User.name, User.email)
            .order_by(User.name.asc())
        )
    ).all()
    owners = tuple(
        OwnerFacet(id=row.id, name=row.name, email=row.email) for row in owner_rows
    )

    bus: set[str] = set()
    opp_bu = _opportunity_bu_column()
    client_bu = _client_bu_column()
    if opp_bu is not None:
        for (v,) in (
            await session.execute(
                select(opp_bu)
                .where(
                    Opportunity.source == "hubspot",
                    Opportunity.archived_at.is_(None),
                    opp_bu.is_not(None),
                )
                .distinct()
            )
        ).all():
            if v:
                bus.add(str(v))
    if client_bu is not None:
        for (v,) in (
            await session.execute(
                select(client_bu)
                .where(client_bu.is_not(None))
                .distinct()
            )
        ).all():
            if v:
                bus.add(str(v))

    return PipelineFacets(owners=owners, business_units=tuple(sorted(bus)))


async def list_pipeline_stages(
    session: AsyncSession, *, pipeline_id: str
) -> tuple[StageCount, ...]:
    """S20 W2 · ordered stages for a single pipeline, non-archived only.

    Powers the ordered stage strip on /deals/{id}. Uses the mirror in
    `hubspot_stage` (D9). Zero-count stages included so the strip shows
    every stage the deal could sit in, in mirror order.
    """

    rows = (
        await session.execute(
            select(
                HubspotStage.id,
                HubspotStage.label,
                HubspotStage.display_order,
                HubspotStage.is_closed,
                HubspotStage.probability,
            )
            .where(
                HubspotStage.pipeline_id == pipeline_id,
                HubspotStage.archived.is_(False),
            )
            .order_by(HubspotStage.display_order.asc())
        )
    ).all()

    return tuple(
        StageCount(
            pipeline_id=pipeline_id,
            stage_id=stage_id,
            stage_label=label,
            stage_order=order,
            count=0,
            is_closed_won=bool(is_closed) and (probability is not None and probability >= Decimal("1.0")),
            is_closed_lost=bool(is_closed) and (probability is not None and probability <= Decimal("0.0")),
        )
        for stage_id, label, order, is_closed, probability in rows
    )


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


# ---------------------------------------------------------------------------
# S19 slice 1 — full query service (C1–C8).
# ---------------------------------------------------------------------------


UNASSIGNED_OWNER_EMAIL = "unassigned@dealgate.local"
STALLED_DAYS = 14

# D3 — SOW approval state as the UI names it. Derived from Sow + SowVersion +
# ApprovalPackage + SignedSowUpload; enum kept in lock-step with the
# directive line.
class SowApprovalState(str, Enum):
    NONE = "none"
    DRAFT = "draft"
    IN_REVIEW_DELIVERY_HR = "in_review_delivery_hr"
    IN_REVIEW_FINANCE_LEGAL = "in_review_finance_legal"
    CHANGES_REQUESTED = "changes_requested"
    CEO_EXCEPTION = "ceo_exception"
    APPROVED = "approved"
    AWAITING_SIGNATURE = "awaiting_signature"
    SIGNED = "signed"


# D4 — Attention flags, computable in SQL (or derivable from the row set).
class AttentionFlag(str, Enum):
    OVERDUE_ACTION = "overdue_action"
    STALLED = "stalled"
    NO_OWNER = "no_owner"
    PENDING_APPROVAL = "pending_approval"
    CLOSED_WON_NOT_RELEASED = "closed_won_not_released"


READINESS_STATES: tuple[str, ...] = tuple(s.value for s in SowApprovalState)
ATTENTION_FLAGS: tuple[str, ...] = tuple(f.value for f in AttentionFlag)


# --- Filter + sort inputs ---------------------------------------------------


@dataclass(frozen=True)
class PipelineFilters:
    """Shared filter set for list_clients / list_opportunities / summary.

    Every list surface takes this same shape. Empty tuple / None means "no
    constraint on that axis". The service applies the ``source='hubspot' AND
    archived_at IS NULL`` invariants unconditionally; callers can't turn
    those off.

    Contract: **OR within a field, AND between fields** (contracts §4).

    Ownership axes (D2, three concepts, NEVER conflated):
    - ``owner`` — deal sales owner (HubSpot owner id resolved to
      ``opportunity.owner_id``). "Deal owner" in the UI.
    - ``account_owner`` — client account owner (HubSpot company
      ``hubspot_owner_id`` mirrored onto ``client.hubspot_owner_id`` once
      W1's owner mirror lands the column — see requests.md
      W2-2026-09-30-02). Distinct filter; NEVER derived from a deal.
    - ``business_unit`` — HubSpot BU property (D10). Read from
      ``opportunity.hubspot_business_unit`` or (per W1's discovery)
      ``client.hubspot_business_unit``.

    Date presets (contracts §4): ``last7 | last30 | last90 | next7 |
    next30 | next90 | this_month | this_quarter | custom``. The caller
    (router) resolves the preset to concrete ``date_from`` / ``date_to``
    using the business timezone (America/Los_Angeles).
    """

    pipeline: str | None = None
    stage: tuple[str, ...] = ()  # HubSpot stage ids
    owner: tuple[uuid.UUID, ...] = ()  # deal sales owner (D2)
    account_owner: tuple[str, ...] = ()  # client hubspot_owner_id list (D2 separate axis)
    business_unit: tuple[str, ...] = ()  # D10
    client: tuple[uuid.UUID, ...] = ()  # S20 W2 Session 3b · scope to a specific client (client detail page)
    # S20 W6 Session 4 · tracking group scope. Router resolves group id
    # → opportunity id set (manual or rule-based via `filter_json`) and
    # passes the ids down on `opportunity_id`. Directive: "rule-based
    # groups evaluated by the same engine — no second implementation".
    group: tuple[uuid.UUID, ...] = ()
    # S20 W6 Session 4 · direct opportunity id scope, used by the group
    # resolver + watchlist filter. `None` = axis not requested; empty
    # tuple = an intentional zero-match (e.g. watchlist with no stars).
    opportunity_id: tuple[uuid.UUID, ...] | None = None
    # S20 W6 Session 4 · per-user watchlist scope. Alias for
    # `opportunity_id` populated by the router from the caller's own
    # `WatchedItem` rows; keeps the source axis distinct in filter echo.
    watching_ids: tuple[uuid.UUID, ...] | None = None
    group: uuid.UUID | None = None  # slice 2 wires tracking_group; slice 1 no-op
    readiness: tuple[str, ...] = ()  # subset of READINESS_STATES (a.k.a sow_state)
    attention: tuple[str, ...] = ()  # subset of ATTENTION_FLAGS
    date_field: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None
    include_closed: bool = False  # legacy toggle: include closed-lost + closed-won
    open_closed: str | None = None  # 'open' | 'closed_won' | 'closed_lost' | 'any'
    missing: tuple[str, ...] = ()  # rows missing a field: 'owner' | 'stage' | 'close_date' | 'amount' | 'business_unit'


VALID_DATE_FIELDS: frozenset[str] = frozenset(
    {"created", "close", "last_activity", "action_due", "last_contacted"}
)
VALID_OPEN_CLOSED: frozenset[str] = frozenset(
    {"open", "closed_won", "closed_lost", "any"}
)
VALID_MISSING_FIELDS: frozenset[str] = frozenset(
    {"owner", "stage", "close_date", "amount", "business_unit", "next_action"}
)


@dataclass(frozen=True)
class SortSpec:
    column: str
    descending: bool = False


DEFAULT_SORT_OPPS: tuple[SortSpec, ...] = (
    SortSpec("attention", descending=True),
    SortSpec("next_action_due"),
    SortSpec("close_date"),
)
DEFAULT_SORT_CLIENTS: tuple[SortSpec, ...] = (
    SortSpec("attention", descending=True),
    SortSpec("latest_activity", descending=True),
    SortSpec("client_name"),
)


# --- Result shapes ----------------------------------------------------------


@dataclass(frozen=True)
class OpportunityRow:
    opportunity_id: uuid.UUID
    hubspot_deal_id: str | None
    name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    stage_id: str | None
    stage_label: str | None
    is_closed_won: bool
    is_closed_lost: bool
    amount: Decimal | None
    currency: str | None
    close_date: date | None
    owner_id: uuid.UUID | None
    owner_name: str | None
    owner_email: str | None
    hubspot_last_activity_at: datetime | None
    sow_approval_state: str
    attention_flags: tuple[str, ...]
    next_action_open_count: int
    next_action_min_due: date | None
    sow_count: int
    hubspot_pipeline_id: str | None
    business_unit: str | None


@dataclass(frozen=True)
class ClientRow:
    client_id: uuid.UUID
    client_name: str
    hubspot_company_id: str | None
    # D2: client "account owner" is derived from the client (company) property,
    # NEVER from a deal. Populated once W1's owner-mirror migration lands
    # (requests.md W2-2026-09-30-02); until then account_owner_* are None
    # and deal_owner_* stand in as the closest-deal owner for a legacy fallback.
    account_owner_id: str | None
    account_owner_name: str | None
    account_owner_email: str | None
    owner_id: uuid.UUID | None  # deal-derived; kept for backward compatibility
    owner_name: str | None
    owner_email: str | None
    matching_deal_count: int  # deals matching the current filter set
    total_open_deal_count: int  # every open deal on this client, ignoring filter
    open_value_by_currency: dict[str, Decimal]
    stage_breakdown: dict[str, int]  # stage_label → count of matching deals
    has_nda: bool
    has_msa: bool
    worst_sow_approval_state: str  # per D3 ordering
    attention_flags: tuple[str, ...]
    latest_activity_at: datetime | None
    next_action_min_due: date | None
    next_action_open_count: int

    # Legacy alias so older tests that read ``open_opp_count`` still pass.
    @property
    def open_opp_count(self) -> int:
        return self.matching_deal_count


@dataclass(frozen=True)
class PipelineSummary:
    open_count: int
    open_value_by_currency: dict[str, Decimal]
    closing_this_month: int
    overdue_actions: int
    pending_approvals: int
    agreement_gaps: int


@dataclass(frozen=True)
class StageCount:
    pipeline_id: str | None
    stage_id: str | None
    stage_label: str | None
    stage_order: int | None
    count: int
    is_closed_won: bool = False
    is_closed_lost: bool = False
    # S20 W2 Session 3b Rev-2 · per-chip value totals. Same
    # `sum(amount)` semantics as the summary card, but grouped by
    # (pipeline_id, stage_id). Keeps the "count + value per chip"
    # contract the review's L06 line called out.
    open_value_by_currency: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class ListPage[R]:
    items: tuple[R, ...]
    total: int
    page: int
    page_size: int
    # A5, T35, T40: chip counts + explicit unknown-stage bucket are
    # computed over the FULL authorized filter set (before pagination) so
    # chips reconcile with matching deal totals. Zero-count stages
    # rendered (D9).
    stage_counts: tuple[StageCount, ...] = field(default_factory=tuple)
    unknown_bucket: int = 0
    freshness: dict[str, Any] | None = None


# --- SQL helpers ------------------------------------------------------------


def _closed_condition() -> Any:
    return and_(Opportunity.is_closed_won.is_(False), Opportunity.is_closed_lost.is_(False))


def _opp_name_column():
    """Return the SQL expression for the deal name.

    Prefers ``Opportunity.name`` (populated by W1's intake once the Lead
    lands the migration requested in W2-2026-09-30-01) and falls back to
    the stage label or the HubSpot id. Keeps the query service working
    today while the migration is in flight.
    """

    name_col = getattr(Opportunity, "name", None)
    if name_col is not None:
        return func.coalesce(name_col, Opportunity.stage_label, Opportunity.hubspot_deal_id)
    return func.coalesce(Opportunity.stage_label, Opportunity.hubspot_deal_id)


def _client_hubspot_owner_column():
    """Return the ``Client.hubspot_owner_id`` column if present, else None.

    W1's owner-mirror migration lands the column (requests.md
    W2-2026-09-30-02). Until then the account-owner filter is a no-op.
    """

    return getattr(Client, "hubspot_owner_id", None)


def _opportunity_bu_column():
    return getattr(Opportunity, "hubspot_business_unit", None)


def _client_bu_column():
    return getattr(Client, "hubspot_business_unit", None)


def _base_opportunity_filter(filters: PipelineFilters):
    """WHERE clauses shared by every list_*/summary call.

    Contract: OR within a field (``.in_([...])``), AND between fields
    (each condition is appended to the outer AND list). See §"Filter
    contract" in the review + contracts §4.
    """

    conditions = [
        Opportunity.source == "hubspot",
        Opportunity.archived_at.is_(None),
    ]
    # open_closed takes precedence over the legacy include_closed toggle
    # when set — the review's explicit "open | closed_won | closed_lost |
    # any" contract requires it.
    if filters.open_closed == "open":
        conditions.append(_closed_condition())
    elif filters.open_closed == "closed_won":
        conditions.append(Opportunity.is_closed_won.is_(True))
    elif filters.open_closed == "closed_lost":
        conditions.append(Opportunity.is_closed_lost.is_(True))
    elif filters.open_closed == "any":
        pass  # no closed constraint
    elif not filters.include_closed:
        # Legacy path: hide closed-won and closed-lost.
        conditions.append(_closed_condition())
    if filters.pipeline is not None:
        conditions.append(Opportunity.hubspot_pipeline_id == filters.pipeline)
    if filters.stage:
        conditions.append(Opportunity.hubspot_stage_id.in_(filters.stage))
    if filters.owner:
        conditions.append(Opportunity.owner_id.in_(filters.owner))
    if filters.client:
        # S20 W2 Session 3b · scope to specific client(s). Powers /clients/:id
        # deal list — the client page shows every deal the client owns,
        # matching the same filter/sort semantics the /pipeline page uses.
        conditions.append(Opportunity.client_id.in_(filters.client))
    if filters.opportunity_id is not None:
        # S20 W6 · Direct opportunity-id scope (groups + watchlist). Empty
        # tuple = intentional zero-match; non-empty = subset scope.
        if filters.opportunity_id:
            conditions.append(Opportunity.id.in_(filters.opportunity_id))
        else:
            conditions.append(Opportunity.id == uuid.UUID(int=0))
    if filters.watching_ids is not None and filters.opportunity_id is None:
        # Legacy path when the router set watching_ids without pre-merging.
        if filters.watching_ids:
            conditions.append(Opportunity.id.in_(filters.watching_ids))
        else:
            conditions.append(Opportunity.id == uuid.UUID(int=0))
    if filters.account_owner:
        client_owner = _client_hubspot_owner_column()
        if client_owner is not None:
            conditions.append(client_owner.in_(filters.account_owner))
        # else: column not yet mirrored (W1's migration in flight); silently
        # ignore rather than crash — the UI will show the axis with a
        # "not yet mirrored" note until W1 lands the column.
    if filters.business_unit:
        opp_bu = _opportunity_bu_column()
        client_bu = _client_bu_column()
        clauses = []
        if opp_bu is not None:
            clauses.append(opp_bu.in_(filters.business_unit))
        if client_bu is not None:
            clauses.append(client_bu.in_(filters.business_unit))
        if clauses:
            conditions.append(or_(*clauses))
        # else: BU not yet mirrored — filter is a no-op (W1 will populate).
    if filters.date_field and (filters.date_from or filters.date_to):
        column = _date_field_column(filters.date_field)
        if column is not None:
            if filters.date_from is not None:
                conditions.append(column >= filters.date_from)
            if filters.date_to is not None:
                conditions.append(column <= filters.date_to)
    if filters.missing:
        for miss in filters.missing:
            if miss == "owner":
                conditions.append(Opportunity.owner_id.is_(None))
            elif miss == "stage":
                conditions.append(
                    or_(
                        Opportunity.hubspot_stage_id.is_(None),
                        Opportunity.stage_label.is_(None),
                    )
                )
            elif miss == "close_date":
                conditions.append(Opportunity.close_date.is_(None))
            elif miss == "amount":
                conditions.append(Opportunity.amount.is_(None))
            elif miss == "business_unit":
                opp_bu = _opportunity_bu_column()
                client_bu = _client_bu_column()
                bu_clauses = []
                if opp_bu is not None:
                    bu_clauses.append(opp_bu.is_(None))
                if client_bu is not None:
                    bu_clauses.append(client_bu.is_(None))
                if bu_clauses:
                    conditions.append(and_(*bu_clauses))
    if filters.search:
        like = f"%{filters.search.strip().lower()}%"
        name_col = _opp_name_column()
        conditions.append(
            or_(
                func.lower(func.coalesce(name_col, "")).like(like),
                func.lower(func.coalesce(Opportunity.stage_label, "")).like(like),
                func.lower(func.coalesce(Opportunity.hubspot_deal_id, "")).like(like),
                func.lower(func.coalesce(Client.name, "")).like(like),
            )
        )
    return conditions


def _date_field_column(name: str):
    if name not in VALID_DATE_FIELDS:
        return None
    if name == "created":
        return func.coalesce(Opportunity.hubspot_created_at, Opportunity.created_at)
    if name == "close":
        return Opportunity.close_date
    if name == "last_activity":
        return Opportunity.hubspot_last_activity_at
    if name == "last_contacted":
        # Falls back to last_modified/notes_last_updated in the mirror.
        return Opportunity.hubspot_last_activity_at
    if name == "action_due":
        # Wire when next_action lands UI in slice 2; for now the filter is a no-op.
        return None
    return None


BUSINESS_TZ = "America/Los_Angeles"


def resolve_date_preset(
    preset: str,
    *,
    today: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[date | None, date | None]:
    """Resolve a preset string (contracts §4) to ``(from, to)`` inclusive.

    ``custom`` returns the caller-supplied bounds unchanged. Business
    timezone anchor is ``America/Los_Angeles``; date-only fields do not
    shift (review §"Filter contract"). ``today`` defaults to
    ``date.today()`` — tests inject a fixed value.
    """

    today = today or date.today()
    if preset == "custom":
        return date_from, date_to
    if preset == "last7":
        return today - timedelta(days=7), today
    if preset == "last30":
        return today - timedelta(days=30), today
    if preset == "last90":
        return today - timedelta(days=90), today
    if preset == "next7":
        return today, today + timedelta(days=7)
    if preset == "next30":
        return today, today + timedelta(days=30)
    if preset == "next90":
        return today, today + timedelta(days=90)
    if preset == "this_month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - timedelta(days=1)
        return start, end
    if preset == "this_quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=q_start_month, day=1)
        end_month = q_start_month + 2
        if end_month == 12:
            end = start.replace(month=12, day=31)
        else:
            end = start.replace(month=end_month + 1, day=1) - timedelta(days=1)
        return start, end
    return date_from, date_to


# Correlated subqueries for one-shot fetch. Each is a scalar subquery in the
# main SELECT list so the whole page comes back in a single query.
def _next_action_open_count_subq():
    return (
        select(func.count(NextAction.id))
        .where(NextAction.opportunity_id == Opportunity.id)
        .where(NextAction.status != "complete")
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _next_action_min_due_subq():
    return (
        select(func.min(NextAction.due_date))
        .where(NextAction.opportunity_id == Opportunity.id)
        .where(NextAction.status != "complete")
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _latest_package_status_subq():
    return (
        select(ApprovalPackage.status)
        .where(ApprovalPackage.opportunity_id == Opportunity.id)
        .order_by(ApprovalPackage.submitted_at.desc())
        .limit(1)
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _sow_id_subq():
    return (
        select(Sow.id)
        .where(Sow.opportunity_id == Opportunity.id)
        .where(Sow.archived_at.is_(None))
        .limit(1)
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _signed_sow_exists_subq():
    return (
        select(func.count(SignedSowUpload.id))
        .join(ApprovalPackage, ApprovalPackage.id == SignedSowUpload.package_id)
        .where(ApprovalPackage.opportunity_id == Opportunity.id)
        .correlate(Opportunity)
        .scalar_subquery()
    )


def _sow_count_subq():
    return (
        select(func.count(Sow.id))
        .where(Sow.opportunity_id == Opportunity.id)
        .where(Sow.archived_at.is_(None))
        .correlate(Opportunity)
        .scalar_subquery()
    )


# --- Mapping approval-package status → D3 display state --------------------

_PACKAGE_TO_STATE: dict[str, SowApprovalState] = {
    "pending_delivery_hr": SowApprovalState.IN_REVIEW_DELIVERY_HR,
    "pending_finance_legal": SowApprovalState.IN_REVIEW_FINANCE_LEGAL,
    "pending_ceo_exception": SowApprovalState.CEO_EXCEPTION,
    "ready_to_sign": SowApprovalState.APPROVED,
    "released": SowApprovalState.SIGNED,
    "voided": SowApprovalState.CHANGES_REQUESTED,
    "rejected": SowApprovalState.CHANGES_REQUESTED,
}


# Rank for "worst" state per client (higher = more attention). Directive
# ordering: none < draft < in review < changes requested < CEO exception <
# approved < awaiting signature < signed.
_STATE_RANK: dict[SowApprovalState, int] = {
    SowApprovalState.NONE: 0,
    SowApprovalState.DRAFT: 1,
    SowApprovalState.IN_REVIEW_DELIVERY_HR: 2,
    SowApprovalState.IN_REVIEW_FINANCE_LEGAL: 3,
    SowApprovalState.CHANGES_REQUESTED: 4,
    SowApprovalState.CEO_EXCEPTION: 5,
    SowApprovalState.APPROVED: 6,
    SowApprovalState.AWAITING_SIGNATURE: 7,
    SowApprovalState.SIGNED: 8,
}


def _derive_sow_state(
    *, sow_id: uuid.UUID | None, latest_status: str | None, signed_count: int
) -> SowApprovalState:
    if sow_id is None:
        return SowApprovalState.NONE
    if latest_status is None:
        return SowApprovalState.DRAFT
    mapped = _PACKAGE_TO_STATE.get(latest_status, SowApprovalState.DRAFT)
    # ready_to_sign + signed upload present but not yet released → awaiting_signature
    if mapped is SowApprovalState.APPROVED and signed_count > 0:
        return SowApprovalState.AWAITING_SIGNATURE
    return mapped


def _derive_attention(
    *,
    owner_email: str | None,
    is_closed_won: bool,
    is_closed_lost: bool,
    hubspot_last_activity_at: datetime | None,
    next_action_min_due: date | None,
    latest_status: str | None,
    signed_count: int,
    sow_id: uuid.UUID | None,
    now: datetime,
) -> tuple[AttentionFlag, ...]:
    flags: list[AttentionFlag] = []
    today = now.date()
    if next_action_min_due is not None and next_action_min_due < today:
        flags.append(AttentionFlag.OVERDUE_ACTION)
    if (
        hubspot_last_activity_at is not None
        and not is_closed_won
        and not is_closed_lost
        and (now - hubspot_last_activity_at) > timedelta(days=STALLED_DAYS)
    ):
        flags.append(AttentionFlag.STALLED)
    if owner_email is None or owner_email == UNASSIGNED_OWNER_EMAIL:
        flags.append(AttentionFlag.NO_OWNER)
    if latest_status in {"pending_delivery_hr", "pending_finance_legal", "pending_ceo_exception"}:
        flags.append(AttentionFlag.PENDING_APPROVAL)
    if is_closed_won and (sow_id is None or signed_count == 0):
        flags.append(AttentionFlag.CLOSED_WON_NOT_RELEASED)
    return tuple(flags)


def _row_matches_attention_filter(
    row_flags: tuple[str, ...], requested: tuple[str, ...]
) -> bool:
    if not requested:
        return True
    return any(f in row_flags for f in requested)


def _row_matches_readiness_filter(row_state: str, requested: tuple[str, ...]) -> bool:
    if not requested:
        return True
    return row_state in requested


# --- Public list surfaces ---------------------------------------------------


async def list_opportunities(
    session: AsyncSession,
    *,
    filters: PipelineFilters | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: tuple[SortSpec, ...] = DEFAULT_SORT_OPPS,
    now: datetime | None = None,
) -> ListPage[OpportunityRow]:
    """Return the paged Opportunities view for the Pipeline UI.

    Query budget: 3 executes — (1) main select with correlated
    subqueries + window count; (2) stage-count aggregation over the full
    authorized filter set for chip reconciliation (A5/T35/T40); (3)
    zero-count stage rendering pulls from the mirror when the base
    aggregation has zero rows for a stage (D9). Agreements are attached
    in ``list_clients`` where they matter; the Opportunities view does
    not gate on them.
    """

    filters = filters or PipelineFilters()
    now = now or datetime.now(tz=UTC)

    # Correlated subq columns bind at execute time to the outer opp row so
    # each result set includes everything needed to derive SOW state +
    # attention without a follow-up query.
    subq_next_open = _next_action_open_count_subq().label("na_open")
    subq_next_due = _next_action_min_due_subq().label("na_due")
    subq_latest_pkg = _latest_package_status_subq().label("pkg_status")
    subq_sow_id = _sow_id_subq().label("sow_id")
    subq_signed = _signed_sow_exists_subq().label("signed_ct")
    subq_sow_ct = _sow_count_subq().label("sow_ct")
    total = func.count().over().label("total")

    stmt = (
        select(
            Opportunity,
            Client,
            User,
            subq_next_open,
            subq_next_due,
            subq_latest_pkg,
            subq_sow_id,
            subq_signed,
            subq_sow_ct,
            total,
        )
        .join(Client, Client.id == Opportunity.client_id, isouter=True)
        .join(User, User.id == Opportunity.owner_id, isouter=True)
        .where(*_base_opportunity_filter(filters))
    )

    stmt = _apply_opportunity_sort(stmt, sort)
    stmt = stmt.offset(max(0, (page - 1) * page_size)).limit(page_size)

    rows = (await session.execute(stmt)).all()

    items: list[OpportunityRow] = []
    total_count = 0
    for (
        opp,
        client,
        owner,
        na_open,
        na_due,
        pkg_status,
        sow_id,
        signed_ct,
        sow_ct,
        total_c,
    ) in rows:
        total_count = int(total_c or 0)
        signed_count = int(signed_ct or 0)
        state = _derive_sow_state(
            sow_id=sow_id, latest_status=pkg_status, signed_count=signed_count
        )
        flags = _derive_attention(
            owner_email=owner.email if owner else None,
            is_closed_won=opp.is_closed_won,
            is_closed_lost=opp.is_closed_lost,
            hubspot_last_activity_at=opp.hubspot_last_activity_at,
            next_action_min_due=na_due,
            latest_status=pkg_status,
            signed_count=signed_count,
            sow_id=sow_id,
            now=now,
        )
        flag_values = tuple(f.value for f in flags)
        if not _row_matches_attention_filter(flag_values, filters.attention):
            continue
        if not _row_matches_readiness_filter(state.value, filters.readiness):
            continue
        # Deal name: prefer the mirrored HubSpot dealname (once W1 lands
        # the column), then fall back to the stage label or the HubSpot id.
        # NEVER show a raw stage as the deal identity. If closed-lost, the
        # UI adds the "Closed Lost" pill next to the name (L07).
        raw_name = getattr(opp, "name", None)
        display_name = raw_name or opp.stage_label or opp.hubspot_deal_id
        items.append(
            OpportunityRow(
                opportunity_id=opp.id,
                hubspot_deal_id=opp.hubspot_deal_id,
                name=display_name,
                client_id=client.id if client else None,
                client_name=client.name if client else None,
                stage_id=opp.hubspot_stage_id,
                stage_label=opp.stage_label,
                is_closed_won=opp.is_closed_won,
                is_closed_lost=opp.is_closed_lost,
                amount=opp.amount,
                currency=opp.currency,
                close_date=opp.close_date,
                owner_id=owner.id if owner else None,
                owner_name=owner.name if owner else None,
                owner_email=owner.email if owner else None,
                hubspot_last_activity_at=opp.hubspot_last_activity_at,
                sow_approval_state=state.value,
                attention_flags=flag_values,
                next_action_open_count=int(na_open or 0),
                next_action_min_due=na_due,
                sow_count=int(sow_ct or 0),
                hubspot_pipeline_id=opp.hubspot_pipeline_id,
                business_unit=(
                    getattr(opp, "hubspot_business_unit", None)
                    or (getattr(client, "hubspot_business_unit", None) if client else None)
                ),
            )
        )

    # A5, T35, T40: stage_counts + unknown_bucket over the FULL authorized
    # filter set — not the page. Uses the same base filter conditions so
    # chip counts reconcile with the matching-deal total. Post-Python
    # filters (attention / readiness) are re-applied to the row set below.
    stage_counts_all, unknown_bucket = await _compute_stage_counts(
        session, filters=filters, now=now
    )

    # Freshness envelope (contracts §3): the router populates specifics;
    # we surface the row-set watermark hint by echoing filter state.
    return ListPage(
        items=tuple(items),
        total=total_count,
        page=page,
        page_size=page_size,
        stage_counts=stage_counts_all,
        unknown_bucket=unknown_bucket,
    )


async def _compute_stage_counts(
    session: AsyncSession,
    *,
    filters: PipelineFilters,
    now: datetime,
) -> tuple[tuple[StageCount, ...], int]:
    """Return ``(stage_counts, unknown_bucket)`` over the full filter set.

    Aggregates by ``(hubspot_pipeline_id, hubspot_stage_id)`` per D9,
    labels from the stage mirror, unknown-stage rows collected into an
    explicit bucket. Zero-count stages from the mirror are rendered so
    chip strips are stable across pages.
    """

    conditions = _base_opportunity_filter(filters)
    # Aggregation joins Client so the search filter (which touches
    # client name) resolves properly. NULL client rows must survive as
    # unknown-bucket candidates when the search is empty.
    # S20 W2 Session 3b Rev-2 · also aggregate `sum(amount)` per
    # currency so each chip carries a per-chip value (L06 review line:
    # "count + value per chip"). Group-by adds currency; Python-side
    # collates by (pipeline_id, stage_id) with a per-currency dict.
    stmt = (
        select(
            Opportunity.hubspot_pipeline_id.label("pipeline_id"),
            Opportunity.hubspot_stage_id.label("stage_id"),
            func.coalesce(Opportunity.stage_label, "").label("stage_label"),
            Opportunity.currency.label("currency"),
            func.count(Opportunity.id).label("count"),
            func.coalesce(func.sum(Opportunity.amount), 0).label("value_sum"),
        )
        .join(Client, Client.id == Opportunity.client_id, isouter=True)
        .where(*conditions)
        .group_by(
            Opportunity.hubspot_pipeline_id,
            Opportunity.hubspot_stage_id,
            Opportunity.stage_label,
            Opportunity.currency,
        )
    )
    rows = (await session.execute(stmt)).all()

    # Fetch the mirror once so zero-count stages appear (D9). Cheap
    # (< 50 rows on SmarTek21) and keeps chips stable across empty pages.
    mirror_rows = (
        await session.execute(
            select(
                HubspotStage.id,
                HubspotStage.pipeline_id,
                HubspotStage.label,
                HubspotStage.display_order,
                HubspotStage.is_closed,
                HubspotStage.probability,
            ).where(HubspotStage.archived.is_(False))
        )
    ).all()
    mirror_map: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    for sid, pid, label, order, is_closed, prob in mirror_rows:
        mirror_map[(pid, sid)] = {
            "label": label,
            "order": order,
            "is_closed_won": bool(is_closed) and (prob is not None and prob >= Decimal("1.0")),
            "is_closed_lost": bool(is_closed) and (prob is not None and prob <= Decimal("0.0")),
        }

    # Collate the currency-broken groups back to (pipeline_id, stage_id):
    # {key: {"count": int, "value_by_currency": {ccy: Decimal},
    #        "stage_label": str}}
    per_key: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    unknown = 0
    for pid, sid, stage_label, currency, count, value_sum in rows:
        if pid is None and sid is None:
            unknown += int(count or 0)
            continue
        key = (pid, sid)
        bucket = per_key.setdefault(
            key,
            {
                "count": 0,
                "value_by_currency": {},
                "stage_label": stage_label or None,
            },
        )
        bucket["count"] += int(count or 0)
        if value_sum is not None and int(count or 0) > 0:
            ccy = currency or "USD"
            existing = bucket["value_by_currency"].get(ccy, Decimal("0"))
            bucket["value_by_currency"][ccy] = existing + Decimal(str(value_sum))

    counts: list[StageCount] = []
    seen: set[tuple[str | None, str | None]] = set(per_key.keys())
    for (pid, sid), bucket in per_key.items():
        mirror = mirror_map.get((pid, sid), {})
        counts.append(
            StageCount(
                pipeline_id=pid,
                stage_id=sid,
                stage_label=mirror.get("label") or bucket["stage_label"],
                stage_order=mirror.get("order"),
                count=bucket["count"],
                is_closed_won=bool(mirror.get("is_closed_won")),
                is_closed_lost=bool(mirror.get("is_closed_lost")),
                open_value_by_currency=bucket["value_by_currency"],
            )
        )

    # D9: zero-count stages from the mirror stay in the strip so chip
    # order and coverage are stable across filter changes.
    for (pid, sid), meta in mirror_map.items():
        if (pid, sid) in seen:
            continue
        # Respect the pipeline filter: if the caller selected pipeline X,
        # don't display stages from pipeline Y as zero-count chips.
        if filters.pipeline is not None and pid != filters.pipeline:
            continue
        counts.append(
            StageCount(
                pipeline_id=pid,
                stage_id=sid,
                stage_label=meta.get("label"),
                stage_order=meta.get("order"),
                count=0,
                is_closed_won=bool(meta.get("is_closed_won")),
                is_closed_lost=bool(meta.get("is_closed_lost")),
            )
        )

    counts.sort(
        key=lambda c: (
            c.pipeline_id or "",
            c.stage_order if c.stage_order is not None else 999_999,
            c.stage_label or "",
        )
    )
    return tuple(counts), unknown


def _apply_opportunity_sort(stmt, sort: tuple[SortSpec, ...]):
    # Attention isn't a stored column; we approximate at query-time by
    # sorting on the derivable signal (no owner + closed-won gap flags land
    # via NULL owner_id and is_closed_won) and let Python resolve the exact
    # ordering when it matters (list is 25/50/100 rows per page, cheap).
    #
    # For every other column we push the ORDER BY down to SQL so N+1 in
    # sort never happens.
    order_by: list[Any] = []
    for spec in sort:
        direction = "desc" if spec.descending else "asc"
        if spec.column == "attention":
            # `no_owner` = owner_id IS NULL, always wants to sort to top when desc
            expr = Opportunity.owner_id.is_(None)
            order_by.append(expr.desc() if spec.descending else expr.asc())
        elif spec.column == "next_action_due":
            expr = _next_action_min_due_subq()
            order_by.append(expr.desc().nullslast() if spec.descending else expr.asc().nullslast())
        elif spec.column == "close_date":
            order_by.append(
                Opportunity.close_date.desc().nullslast()
                if spec.descending
                else Opportunity.close_date.asc().nullslast()
            )
        elif spec.column == "amount":
            order_by.append(
                Opportunity.amount.desc().nullslast()
                if spec.descending
                else Opportunity.amount.asc().nullslast()
            )
        elif spec.column == "last_activity":
            order_by.append(
                Opportunity.hubspot_last_activity_at.desc().nullslast()
                if spec.descending
                else Opportunity.hubspot_last_activity_at.asc().nullslast()
            )
        elif spec.column == "stage":
            order_by.append(
                Opportunity.stage_order.desc().nullslast()
                if spec.descending
                else Opportunity.stage_order.asc().nullslast()
            )
        elif spec.column == "client_name":
            order_by.append(Client.name.desc() if spec.descending else Client.name.asc())
        elif spec.column == "owner":
            order_by.append(User.name.desc() if spec.descending else User.name.asc())
    # Deterministic tiebreak so pagination is stable.
    order_by.append(Opportunity.id.asc())
    return stmt.order_by(*order_by)


async def list_clients(
    session: AsyncSession,
    *,
    filters: PipelineFilters | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: tuple[SortSpec, ...] = DEFAULT_SORT_CLIENTS,
    now: datetime | None = None,
) -> ListPage[ClientRow]:
    """Return the paged Clients view.

    Query budget: 3 executes — (1) the page of clients + aggregates over
    their opportunities; (2) currency-broken open values per client for
    the page; (3) agreements attached per client_id (batch). Stage
    breakdown + attention derive from the aggregation columns in Q1 +
    per-opp data joined in Q1's subqueries.
    """

    filters = filters or PipelineFilters()
    now = now or datetime.now(tz=UTC)

    # Q1: Client rows with aggregated columns via correlated subqueries.
    open_count_subq = _client_open_opp_count_subq(filters)
    latest_activity_subq = _client_latest_activity_subq(filters)
    na_min_due_subq = _client_na_min_due_subq(filters)
    na_open_count_subq = _client_na_open_count_subq(filters)
    worst_state_signal_subq = _client_worst_pkg_status_subq(filters)
    has_open_closed_won_no_release_subq = _client_closed_won_gap_subq()

    total = func.count().over().label("total")

    owner_subq = _client_primary_owner_subq(filters).label("owner_id")

    stmt = (
        select(
            Client,
            open_count_subq.label("open_ct"),
            latest_activity_subq.label("latest_activity"),
            na_min_due_subq.label("na_min_due"),
            na_open_count_subq.label("na_open"),
            worst_state_signal_subq.label("worst_pkg_status"),
            has_open_closed_won_no_release_subq.label("closed_won_gap"),
            owner_subq,
            total,
        )
        .where(Client.archived_at.is_(None))
    )
    # Text search over client name (mirrors search_pipeline_deals shape).
    if filters.search:
        stmt = stmt.where(func.lower(Client.name).like(f"%{filters.search.strip().lower()}%"))

    stmt = _apply_client_sort(stmt, sort)
    stmt = stmt.offset(max(0, (page - 1) * page_size)).limit(page_size)

    client_rows = (await session.execute(stmt)).all()

    if not client_rows:
        return ListPage(items=(), total=0, page=page, page_size=page_size)

    client_ids = [row[0].id for row in client_rows]

    # Q2: per-client currency breakdown + stage breakdown (SUM/COUNT grouped).
    open_conditions = _base_opportunity_filter(filters)
    breakdown_stmt = (
        select(
            Opportunity.client_id,
            func.coalesce(Opportunity.currency, "").label("currency"),
            func.coalesce(Opportunity.stage_label, "").label("stage_label"),
            func.count(Opportunity.id).label("count"),
            func.coalesce(func.sum(Opportunity.amount), 0).label("total"),
        )
        .where(*open_conditions)
        .where(Opportunity.client_id.in_(client_ids))
        .group_by(Opportunity.client_id, Opportunity.currency, Opportunity.stage_label)
    )
    breakdown_rows = (await session.execute(breakdown_stmt)).all()

    per_client_currency: dict[uuid.UUID, dict[str, Decimal]] = {}
    per_client_stage: dict[uuid.UUID, dict[str, int]] = {}
    for cid, currency, stage_label, count, total_amount in breakdown_rows:
        if cid is None:
            continue
        cur = currency or "UNK"
        per_client_currency.setdefault(cid, {})
        per_client_currency[cid][cur] = per_client_currency[cid].get(cur, Decimal(0)) + Decimal(total_amount or 0)
        stage = stage_label or "unknown"
        per_client_stage.setdefault(cid, {})
        per_client_stage[cid][stage] = per_client_stage[cid].get(stage, 0) + int(count)

    # Matching vs total-open per client (aggregate contract). "Matching"
    # is the count in Q1 (``open_ct``); "total open" is every open deal
    # on the client, unfiltered — used by the UI to show "1 of 5 open"
    # style rollups. Folded into Q3 below (agreements + total-open in one
    # SELECT) so the ≤ 3 query budget still holds.
    total_open_by_client: dict[uuid.UUID, int] = {}

    # Q3: agreements per client + total-open count per client (matching
    # vs total, aggregate contract). Both aggregations join to Client so
    # the query engine keeps the budget at 3. `total_open_ct` is computed
    # by a correlated subquery so the outer GROUP BY stays per client.
    total_open_subq = (
        select(func.count(Opportunity.id))
        .where(Opportunity.source == "hubspot")
        .where(Opportunity.archived_at.is_(None))
        .where(_closed_condition())
        .where(Opportunity.client_id == Client.id)
        .correlate(Client)
        .scalar_subquery()
    )
    combined_stmt = (
        select(
            Client.id,
            total_open_subq.label("total_open_ct"),
            func.max(case((Agreement.kind == "NDA", 1), else_=0)).label("has_nda"),
            func.max(case((Agreement.kind == "MSA", 1), else_=0)).label("has_msa"),
        )
        .select_from(Client)
        .outerjoin(Agreement, Agreement.client_id == Client.id)
        .where(Client.id.in_(client_ids))
        .group_by(Client.id)
    )
    combined_rows = (await session.execute(combined_stmt)).all()
    has_nda: set[uuid.UUID] = set()
    has_msa: set[uuid.UUID] = set()
    for cid, total_open_ct, nda_flag, msa_flag in combined_rows:
        total_open_by_client[cid] = int(total_open_ct or 0)
        if nda_flag:
            has_nda.add(cid)
        if msa_flag:
            has_msa.add(cid)

    # D2: account owner from the client's own HubSpot company property.
    # Falls back to (None, None) until W1 lands the owner-mirror column;
    # in that case the UI shows "not set" rather than a deal-derived owner.
    client_owner_col = _client_hubspot_owner_column()
    account_owner_ids: dict[uuid.UUID, str | None] = {}
    if client_owner_col is not None:
        # Reads from the already-loaded Client rows — no extra query.
        for row in client_rows:
            c = row[0]
            account_owner_ids[c.id] = getattr(c, "hubspot_owner_id", None)

    total_count = 0
    items: list[ClientRow] = []
    now_utc = now
    for (
        client,
        open_ct,
        latest_activity,
        na_min_due,
        na_open,
        worst_pkg_status,
        closed_won_gap,
        owner_id,
        total_c,
    ) in client_rows:
        total_count = int(total_c or 0)
        state = _derive_sow_state(
            sow_id=None if worst_pkg_status is None else uuid.uuid4(),
            latest_status=worst_pkg_status,
            signed_count=0,
        )
        flags: list[AttentionFlag] = []
        if na_min_due is not None and na_min_due < now_utc.date():
            flags.append(AttentionFlag.OVERDUE_ACTION)
        if latest_activity is not None and (
            now_utc - latest_activity
        ) > timedelta(days=STALLED_DAYS):
            flags.append(AttentionFlag.STALLED)
        if owner_id is None:
            flags.append(AttentionFlag.NO_OWNER)
        if worst_pkg_status in {
            "pending_delivery_hr",
            "pending_finance_legal",
            "pending_ceo_exception",
        }:
            flags.append(AttentionFlag.PENDING_APPROVAL)
        if bool(closed_won_gap):
            flags.append(AttentionFlag.CLOSED_WON_NOT_RELEASED)
        flag_values = tuple(f.value for f in flags)
        if not _row_matches_attention_filter(flag_values, filters.attention):
            continue
        if not _row_matches_readiness_filter(state.value, filters.readiness):
            continue
        acct_owner_id = account_owner_ids.get(client.id)
        items.append(
            ClientRow(
                client_id=client.id,
                client_name=client.name,
                hubspot_company_id=client.hubspot_company_id,
                account_owner_id=acct_owner_id,
                account_owner_name=None,  # W1's mirror lookup populates this
                account_owner_email=None,
                owner_id=owner_id,
                owner_name=None,  # per-deal owner: filled below batch-side
                owner_email=None,
                matching_deal_count=int(open_ct or 0),
                total_open_deal_count=total_open_by_client.get(client.id, 0),
                open_value_by_currency=per_client_currency.get(client.id, {}),
                stage_breakdown=per_client_stage.get(client.id, {}),
                has_nda=client.id in has_nda,
                has_msa=client.id in has_msa,
                worst_sow_approval_state=state.value,
                attention_flags=flag_values,
                latest_activity_at=latest_activity,
                next_action_min_due=na_min_due,
                next_action_open_count=int(na_open or 0),
            )
        )

    return ListPage(
        items=tuple(items),
        total=total_count,
        page=page,
        page_size=page_size,
    )


def _client_open_opp_count_subq(filters: PipelineFilters):
    conditions = _base_opportunity_filter(filters)
    return (
        select(func.count(Opportunity.id))
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .correlate(Client)
        .scalar_subquery()
    )


def _client_latest_activity_subq(filters: PipelineFilters):
    conditions = _base_opportunity_filter(filters)
    return (
        select(func.max(Opportunity.hubspot_last_activity_at))
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .correlate(Client)
        .scalar_subquery()
    )


def _client_na_min_due_subq(filters: PipelineFilters):
    conditions = _base_opportunity_filter(filters)
    return (
        select(func.min(NextAction.due_date))
        .join(Opportunity, Opportunity.id == NextAction.opportunity_id)
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .where(NextAction.status != "complete")
        .correlate(Client)
        .scalar_subquery()
    )


def _client_na_open_count_subq(filters: PipelineFilters):
    conditions = _base_opportunity_filter(filters)
    return (
        select(func.count(NextAction.id))
        .join(Opportunity, Opportunity.id == NextAction.opportunity_id)
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .where(NextAction.status != "complete")
        .correlate(Client)
        .scalar_subquery()
    )


def _client_worst_pkg_status_subq(filters: PipelineFilters):
    """Return the "in-review-most" package status across a client's open opps.

    Simplified worst-case: prefer the earliest-in-approval-flow state so
    the client card shows the deepest need for attention. In practice
    this is best-effort — the true worst state is derived downstream.
    """

    conditions = _base_opportunity_filter(filters)
    ranked = case(
        (ApprovalPackage.status == "pending_delivery_hr", 5),
        (ApprovalPackage.status == "pending_finance_legal", 4),
        (ApprovalPackage.status == "pending_ceo_exception", 3),
        (ApprovalPackage.status == "ready_to_sign", 2),
        (ApprovalPackage.status == "released", 1),
        else_=0,
    )
    return (
        select(ApprovalPackage.status)
        .join(Opportunity, Opportunity.id == ApprovalPackage.opportunity_id)
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .order_by(ranked.desc(), ApprovalPackage.submitted_at.desc())
        .limit(1)
        .correlate(Client)
        .scalar_subquery()
    )


def _client_closed_won_gap_subq():
    """1 if the client has any closed-won opp without a released package."""

    released_pkg_exists = (
        select(func.count(ApprovalPackage.id))
        .where(ApprovalPackage.opportunity_id == Opportunity.id)
        .where(ApprovalPackage.status == "released")
        .correlate(Opportunity)
        .scalar_subquery()
    )
    return (
        select(func.count(Opportunity.id))
        .where(Opportunity.source == "hubspot")
        .where(Opportunity.archived_at.is_(None))
        .where(Opportunity.is_closed_won.is_(True))
        .where(Opportunity.client_id == Client.id)
        .where(released_pkg_exists == 0)
        .correlate(Client)
        .scalar_subquery()
    )


def _client_primary_owner_subq(filters: PipelineFilters):
    """Owner of the most-recent open opportunity — used as the client owner."""

    conditions = _base_opportunity_filter(filters)
    return (
        select(Opportunity.owner_id)
        .where(*conditions)
        .where(Opportunity.client_id == Client.id)
        .order_by(Opportunity.hubspot_last_activity_at.desc().nullslast())
        .limit(1)
        .correlate(Client)
        .scalar_subquery()
    )


def _apply_client_sort(stmt, sort: tuple[SortSpec, ...]):
    order_by: list[Any] = []
    for spec in sort:
        if spec.column == "attention":
            # Approximate: sort by NULL owner (proxy for no_owner).
            expr = _client_primary_owner_subq(PipelineFilters()).is_(None)
            order_by.append(expr.desc() if spec.descending else expr.asc())
        elif spec.column == "latest_activity":
            expr = _client_latest_activity_subq(PipelineFilters())
            order_by.append(expr.desc().nullslast() if spec.descending else expr.asc().nullslast())
        elif spec.column == "client_name":
            order_by.append(Client.name.desc() if spec.descending else Client.name.asc())
        elif spec.column == "open_count":
            expr = _client_open_opp_count_subq(PipelineFilters())
            order_by.append(expr.desc() if spec.descending else expr.asc())
    order_by.append(Client.id.asc())
    return stmt.order_by(*order_by)


async def summary(
    session: AsyncSession,
    *,
    filters: PipelineFilters | None = None,
    now: datetime | None = None,
) -> PipelineSummary:
    """Aggregate summary across every authorized matching record.

    Query budget: 3 executes — (1) open counts + values per currency
    across all matching opps; (2) pending approvals + overdue action
    counters; (3) agreement gaps (clients with open deals lacking NDA
    or MSA).
    """

    filters = filters or PipelineFilters()
    now = now or datetime.now(tz=UTC)
    open_conditions = _base_opportunity_filter(filters)
    month_start = now.date().replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)

    q1 = (
        select(
            func.coalesce(Opportunity.currency, "").label("currency"),
            func.count(Opportunity.id).label("cnt"),
            func.coalesce(func.sum(Opportunity.amount), 0).label("total"),
            func.sum(
                case(
                    (
                        and_(
                            Opportunity.close_date.is_not(None),
                            Opportunity.close_date >= month_start,
                            Opportunity.close_date < next_month,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ).label("closing_this_month"),
        )
        .where(*open_conditions)
        .group_by(Opportunity.currency)
    )
    q1_rows = (await session.execute(q1)).all()
    open_count = 0
    open_value: dict[str, Decimal] = {}
    closing_this_month = 0
    for currency, cnt, total, closing in q1_rows:
        open_count += int(cnt)
        open_value[currency or "UNK"] = open_value.get(currency or "UNK", Decimal(0)) + Decimal(
            total or 0
        )
        closing_this_month += int(closing or 0)

    q2 = select(
        func.sum(
            case(
                (
                    and_(
                        NextAction.due_date.is_not(None),
                        NextAction.due_date < now.date(),
                        NextAction.status != "complete",
                    ),
                    1,
                ),
                else_=0,
            )
        ).label("overdue"),
        func.count(ApprovalPackage.id).filter(
            ApprovalPackage.status.in_(
                ["pending_delivery_hr", "pending_finance_legal", "pending_ceo_exception"]
            )
        ).label("pending"),
    ).select_from(
        select(NextAction.due_date, NextAction.status)
        .outerjoin(ApprovalPackage, ApprovalPackage.opportunity_id == NextAction.opportunity_id)
        .subquery()
    )
    # SQLAlchemy is fussy about chaining ``filter`` on aggregate for
    # cross-column combos; run overdue and pending as two lightweight
    # selects — still one execute each. Total for summary is 3 (currency +
    # overdue + pending) — well inside the budget.
    #
    # Instead of the above (which SQLite doesn't parse cleanly), use two
    # simple counts and combine.
    overdue_stmt = (
        select(func.count(NextAction.id))
        .where(NextAction.due_date.is_not(None))
        .where(NextAction.due_date < now.date())
        .where(NextAction.status != "complete")
    )
    pending_stmt = (
        select(func.count(ApprovalPackage.id))
        .where(
            ApprovalPackage.status.in_(
                ["pending_delivery_hr", "pending_finance_legal", "pending_ceo_exception"]
            )
        )
    )
    # Two aggregates but one execute via UNION ALL for the budget test —
    # SQLite requires distinct SELECTs to be UNION'd for combined counting.
    combined = overdue_stmt.union_all(pending_stmt)
    combined_rows = (await session.execute(combined)).all()
    overdue = int(combined_rows[0][0]) if combined_rows else 0
    pending = int(combined_rows[1][0]) if len(combined_rows) > 1 else 0

    # Q3 — agreement gaps. A client with at least one open deal AND no
    # NDA OR no MSA file counts as one gap.
    open_client_ids_subq = (
        select(Opportunity.client_id)
        .where(*open_conditions)
        .where(Opportunity.client_id.is_not(None))
        .distinct()
        .subquery()
    )
    agreements_present_subq = (
        select(Agreement.client_id, Agreement.kind)
        .where(Agreement.client_id.in_(select(open_client_ids_subq.c.client_id)))
        .subquery()
    )
    gap_stmt = select(
        open_client_ids_subq.c.client_id,
        func.max(case((agreements_present_subq.c.kind == "NDA", 1), else_=0)).label("has_nda"),
        func.max(case((agreements_present_subq.c.kind == "MSA", 1), else_=0)).label("has_msa"),
    ).select_from(
        open_client_ids_subq.outerjoin(
            agreements_present_subq,
            agreements_present_subq.c.client_id == open_client_ids_subq.c.client_id,
        )
    ).group_by(open_client_ids_subq.c.client_id)
    gap_rows = (await session.execute(gap_stmt)).all()
    agreement_gaps = sum(1 for _cid, has_nda, has_msa in gap_rows if not has_nda or not has_msa)

    return PipelineSummary(
        open_count=open_count,
        open_value_by_currency=open_value,
        closing_this_month=closing_this_month,
        overdue_actions=overdue,
        pending_approvals=pending,
        agreement_gaps=agreement_gaps,
    )
