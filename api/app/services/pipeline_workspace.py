"""S23-PL2 — the Pipeline workspace: one population, one filter function.

``GET /pipeline/workspace`` answers the whole Pipeline page in one request.
The caller's authorized population (every live HubSpot deal they may see, all
statuses) is read once, in one statement, together with everything a row
shows. Every number is then computed in Python by applying ONE predicate,
:func:`matches`, to that population:

- rows, paging and board lanes: the current filters;
- each metric: the current filters with the metric's ``drill`` applied, so the
  number on a card is by construction the length (or USD total) of the list
  the card opens;
- stage counts: the current filters without stage and status;
- focus counts: the default view plus the focus preset;
- the export (``GET /pipeline/export``) and the Command Center's open number
  (:func:`open_totals`) use the same function.

"Open" is :func:`app.services.hubspot_pipeline.is_open` (Hold is open). Dates
are calendar dates in America/Los_Angeles (:mod:`app.services.business_time`).
Money stays ``Decimal``; totals sum USD amounts only (there is no currency
conversion) and are returned as decimal strings.

Statements per workspace call: viewer, fixture scope, sync health, stage
mirror, region map, population, SOW facts, plus visible clients when
``include_unmatched_clients`` is set — at most eight.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import AuthUser
from app.models.approval import ApprovalPackage
from app.models.client import Agreement, Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import BUSINESS_UNITS, HubspotRegionMap
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.user import User
from app.models.watchlist import WatchedItem
from app.services.business_time import business_now, business_today, la_date, preset_range
from app.services.canonical_user import Viewer, resolve_viewer
from app.services.csv_safety import safe_row
from app.services.hubspot_owners import HubspotOwner
from app.services.hubspot_pipeline import (
    UNASSIGNED_OWNER_EMAIL,
    PipelineFilters,
    _base_opportunity_filter,
    _client_visibility,
    _derive_sow_state,
    _effective_bu_column,
    is_open,
    scope_pipeline_filters,
)

log = structlog.get_logger("pipeline_workspace")

TABS = ("deals", "clients")
STATUSES = ("open", "all", "won", "lost", "hold")
ATTENTION = ("overdue", "past_close", "no_owner", "inactive", "pending_approval", "any")
MISSING = ("owner", "close", "activity", "next_action", "nda", "msa", "agreements")
DATE_FIELDS = ("close", "created", "activity")
SORTS = ("value", "close", "activity", "name")
LAYOUTS = ("list", "board")
PAGE_SIZES = (25, 50, 100)
BU_FILTERS = (*BUSINESS_UNITS, "unmapped")
OWNER_NONE = "none"
OWNER_FORMER = "former"
BOARD_LANE_SIZE = 6
INACTIVE_DAYS = 14
UNNAMED_DEAL = "Unnamed deal"
USD = "USD"
CENT = Decimal("0.01")

# The nine states the code derives (``SowApprovalState``), labelled as the page shows them.
SOW_STATE_LABELS: dict[str, str] = {
    "none": "No SOW",
    "draft": "Draft",
    "in_review_delivery_hr": "In review · delivery/hr",
    "in_review_finance_legal": "In review · finance/legal",
    "changes_requested": "Changes requested",
    "ceo_exception": "CEO exception",
    "approved": "Approved",
    "awaiting_signature": "Awaiting signature",
    "signed": "Signed",
}
PENDING_SOW_STATES = frozenset({"in_review_delivery_hr", "in_review_finance_legal", "ceo_exception"})
SOW_FILTERS = (*SOW_STATE_LABELS, "pending")
ATTENTION_FLAGS = ("action_overdue", "close_passed", "no_owner", "inactive_14d")
CLIENT_FLAGS = ("no_owner", "action_overdue", "close_passed")

# Staging's HubSpot label for each stage position → the approved short name.
_SHORT_NAMES: dict[int, tuple[str, str]] = {
    1: ("Initial Contact/Prospecting", "Prospecting"),
    2: ("Qualification", "Qualification"),
    3: ("Requirement/Fit Gap Analysis", "Fit gap analysis"),
    4: ("Proposal", "Proposal"),
    5: ("Negotiation", "Negotiation"),
    6: ("Contracting/Drive Commitment", "Contracting"),
    7: ("Closed Won", "Closed won"),
    8: ("Closed Lost", "Closed lost"),
    9: ("Hold", "On hold"),
}
HOLD_SHORT_LABEL = "On hold"
HOLD_FULL_LABEL = "Hold (open, paused)"
_NUMBER_PREFIX = re.compile(r"^\s*\d+\s*-\s*")
_SLASH = re.compile(r"\s*/\s*")

# Each metric's drill: the query parameters that open the list it counts.
DRILLS: dict[str, dict[str, Any]] = {
    "open_deals": {"tab": "deals", "status": "open"},
    "open_value_usd": {"tab": "deals", "status": "open"},
    "closing_this_month": {"tab": "deals", "status": "open", "date_field": "close", "date_preset": "month"},
    "overdue_next_actions": {"tab": "deals", "attention": "overdue"},
    "pending_approvals": {"tab": "deals", "sow": "pending"},
    "agreement_gap_clients": {"tab": "clients", "missing": "agreements", "include_unmatched_clients": False},
}
# Focus views reset every filter (status back to open), then apply their preset.
FOCUS_PRESETS: dict[str, dict[str, Any]] = {
    "all_open": {},
    "closing_this_month": {"date_field": "close", "date_preset": "month"},
    "mine": {"mine": True},
    "needs_attention": {"attention": "any"},
    "watching": {"watching": True},
}

DEAL_EXPORT_COLUMNS = (
    "Opportunity", "Client", "Deal owner", "Account owner", "Business unit", "HubSpot region", "Sales stage",
    "Amount", "Currency", "Close date", "Created", "Last activity", "SOW state", "NDA on file", "MSA on file",
    "Next action", "Next action due",
)
CLIENT_EXPORT_COLUMNS = (
    "Client", "Account owner", "Matching deals", "Open deals", "Matching value USD", "NDA on file",
    "MSA on file", "Last matching activity",
)


# --- filters -----------------------------------------------------------------


@dataclass(frozen=True)
class WorkspaceFilters:
    """The workspace query parameters (contract ``/api/pipeline/workspace``).

    ``client`` is an additive parameter: one client's deals (client preview).
    """

    tab: str = "deals"
    status: str = "open"
    stage: tuple[int, ...] = ()
    owner: tuple[str, ...] = ()
    account_owner: tuple[str, ...] = ()
    bu: tuple[str, ...] = ()
    q: str | None = None
    sow: str | None = None
    attention: str | None = None
    missing: str | None = None
    group: uuid.UUID | None = None
    watching: bool = False
    mine: bool = False
    date_field: str = "close"
    date_preset: str = "any"
    date_from: date | None = None
    date_to: date | None = None
    include_unmatched_clients: bool = False
    sort: str = "value"
    layout: str = "list"
    page: int = 1
    page_size: int = 25
    client: uuid.UUID | None = None

    def merge(self, drill: Mapping[str, Any]) -> WorkspaceFilters:
        """``current ⊕ drill``: replace only the keys the drill names; back to page 1."""
        return replace(self, **dict(drill), page=1)


DEFAULT_VIEW = WorkspaceFilters()


@dataclass(frozen=True)
class Context:
    """What a filter needs beyond the row: the business day and the viewer."""

    today: date
    mine_owner_id: str | None = None
    group_id: uuid.UUID | None = None  # the group whose membership the population carries


# --- owners (B13) --------------------------------------------------------------


@dataclass(frozen=True)
class Owner:
    """A HubSpot owner as the page shows it: active (named), archived, or none."""

    name: str | None
    state: str  # active | archived | none

    def wire(self) -> dict[str, Any]:
        return {"name": self.name, "state": self.state}

    def export_text(self) -> str:
        if self.state == "none":
            return "Unassigned"
        if self.state == "archived":
            return "Former HubSpot user"
        return self.name or ""


def owner_of(owner_id: str | None, mirror_id: str | None, first: str | None, last: str | None,
             email: str | None, archived: bool | None) -> Owner:
    """No id → none; archived, or missing from the mirror (a former user) → archived."""
    if not (owner_id or "").strip():
        return Owner(None, "none")
    if mirror_id is None or archived:
        return Owner(None, "archived")
    full = f"{(first or '').strip()} {(last or '').strip()}".strip()
    return Owner(full or (email or None), "active")


def owner_matches(owner_id: str | None, owner: Owner, wanted: tuple[str, ...]) -> bool:
    for value in wanted:
        if value == OWNER_NONE:
            if owner.state == "none":
                return True
        elif value == OWNER_FORMER:
            if owner.state == "archived":
                return True
        elif owner_id is not None and owner_id == value:
            return True
    return False


# --- reference data: stage mirror and region map ----------------------------------


@dataclass(frozen=True)
class StageInfo:
    ordinal: int  # 1-based position among the pipeline's live stages
    label: str  # short name
    full_label: str
    is_hold: bool


@dataclass(frozen=True)
class RegionInfo:
    business_unit: str
    region: str
    note: str | None


@dataclass(frozen=True)
class Reference:
    stages: dict[tuple[str, str], StageInfo]  # (pipeline id, HubSpot stage id) → stage
    stage_list: tuple[StageInfo, ...]  # one per ordinal, for the navigator and the board
    regions: dict[str, RegionInfo]  # HubSpot region value → business unit
    business_units: tuple[dict[str, Any], ...]


def _bare_label(label: str | None) -> str:
    return _NUMBER_PREFIX.sub("", label or "").strip()


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


def stage_info(ordinal: int, hubspot_label: str | None, is_closed: bool) -> StageInfo:
    bare = _bare_label(hubspot_label)
    is_hold = _fold(bare) == "hold" and not is_closed
    staging = _SHORT_NAMES.get(ordinal)
    if is_hold:
        short = HOLD_SHORT_LABEL
    elif staging and _fold(staging[0]) == _fold(bare):
        short = staging[1]
    else:
        short = bare
    full = HOLD_FULL_LABEL if is_hold else f"{ordinal} · {_SLASH.sub(' / ', bare)}"
    return StageInfo(ordinal=ordinal, label=short, full_label=full, is_hold=is_hold)


async def load_reference(session: AsyncSession) -> Reference:
    """Stage ordinals and labels, and the region map (two statements)."""
    stage_rows = (await session.execute(
        select(HubspotStage.pipeline_id, HubspotStage.id, HubspotStage.label, HubspotStage.is_closed)
        .join(HubspotPipeline, HubspotPipeline.id == HubspotStage.pipeline_id, isouter=True)
        .where(HubspotStage.archived.is_(False))
        .order_by(HubspotPipeline.display_order, HubspotStage.pipeline_id, HubspotStage.display_order,
                  HubspotStage.id)
    )).all()
    stages: dict[tuple[str, str], StageInfo] = {}
    by_ordinal: dict[int, StageInfo] = {}
    position: Counter[str] = Counter()
    for pipeline_id, stage_id, label, is_closed in stage_rows:
        position[pipeline_id] += 1
        info = stage_info(position[pipeline_id], label, bool(is_closed))
        if info.is_hold and info.ordinal != 9:
            log.warning("pipeline_hold_stage_not_ninth", pipeline_id=pipeline_id, ordinal=info.ordinal)
        stages[(pipeline_id, stage_id)] = info
        by_ordinal.setdefault(info.ordinal, info)  # the first pipeline names the navigator
    region_rows = (await session.execute(
        select(HubspotRegionMap.hubspot_value, HubspotRegionMap.business_unit, HubspotRegionMap.region,
               HubspotRegionMap.note)
    )).all()
    regions = {value: RegionInfo(unit, region, note) for value, unit, region, note in region_rows}
    business_units = tuple(
        {"business_unit": unit,
         "regions": sorted({info.region for info in regions.values() if info.business_unit == unit})}
        for unit in BUSINESS_UNITS
    )
    return Reference(stages=stages, stage_list=tuple(by_ordinal[k] for k in sorted(by_ordinal)),
                     regions=regions, business_units=business_units)


# --- the population -----------------------------------------------------------------


@dataclass(slots=True)
class DealFact:
    """One deal with everything the page shows and filters on."""

    id: uuid.UUID
    title: str
    hubspot_deal_id: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    client_hubspot_company_id: str | None
    deal_owner_id: str | None
    deal_owner: Owner
    account_owner_id: str | None
    account_owner: Owner
    pipeline_label: str | None
    stage: StageInfo | None
    hubspot_stage_label: str | None
    is_closed_won: bool
    is_closed_lost: bool
    amount: Decimal | None
    currency: str | None
    close_date: date | None
    created_date: date | None
    activity_date: date | None
    hubspot_region: str | None
    region: RegionInfo | None
    next_action_id: uuid.UUID | None
    next_action_text: str | None
    next_action_due: date | None
    nda: bool
    msa: bool
    watching: bool
    in_group: bool
    sow_state: str = "none"
    sow_count: int = 0
    flags: tuple[str, ...] = ()
    days_since_activity: int | None = None
    search_fields: tuple[str, ...] = ()

    @property
    def is_hold(self) -> bool:
        return self.stage is not None and self.stage.is_hold

    @property
    def usd_amount(self) -> Decimal | None:
        return self.amount if self.currency == USD else None


@dataclass(frozen=True)
class ClientFact:
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    account_owner_id: str | None
    account_owner: Owner
    nda: bool
    msa: bool


def _owner_columns(alias, prefix: str) -> list:
    return [alias.id.label(f"{prefix}_id"), alias.first_name.label(f"{prefix}_first"),
            alias.last_name.label(f"{prefix}_last"), alias.email.label(f"{prefix}_email"),
            alias.archived.label(f"{prefix}_archived")]


def _ranked_next_actions():
    """Open next actions ranked per deal: earliest due date first, undated last, then newest.

    Position 1 is the action a row shows. One derived table joined once is far
    cheaper on PostgreSQL than three correlated subqueries per deal.
    """
    return (
        select(
            NextAction.opportunity_id.label("opportunity_id"),
            NextAction.id.label("id"),
            func.coalesce(func.nullif(NextAction.title, ""), NextAction.description).label("text"),
            NextAction.due_date.label("due_date"),
            func.row_number().over(
                partition_by=NextAction.opportunity_id,
                order_by=(NextAction.due_date.is_(None), NextAction.due_date, NextAction.created_at.desc(),
                          NextAction.id),
            ).label("position"),
        )
        .where(NextAction.status != "complete")
        .subquery("next_action_ranked")
    )


def _agreement_on_file(kind: str, client_id):
    return select(Agreement.id).where(Agreement.client_id == client_id, Agreement.kind == kind).exists()


def _derive_row_flags(fact: DealFact, today: date) -> None:
    flags: list[str] = []
    if is_open(fact):
        if fact.next_action_due is not None and fact.next_action_due < today:
            flags.append("action_overdue")
        if fact.close_date is not None and fact.close_date < today:
            flags.append("close_passed")
        if fact.deal_owner.state == "none":
            flags.append("no_owner")
        if fact.activity_date is not None and (today - fact.activity_date).days >= INACTIVE_DAYS:
            flags.append("inactive_14d")
    fact.flags = tuple(flags)
    fact.days_since_activity = (today - fact.activity_date).days if fact.activity_date else None


async def load_population(
    session: AsyncSession,
    scope: PipelineFilters,
    *,
    viewer: Viewer,
    reference: Reference,
    today: date,
    group_id: uuid.UUID | None = None,
    with_sow: bool = True,
) -> tuple[list[DealFact], bool]:
    """Every live authorized HubSpot deal, all statuses (one statement), plus SOW facts (one).

    Returns the deals and whether any agreement file exists anywhere.
    """
    deal_owner = aliased(HubspotOwner, name="deal_owner")
    account_owner = aliased(HubspotOwner, name="account_owner")
    next_action = _ranked_next_actions()
    columns = [
        Opportunity.id.label("id"), Opportunity.name.label("title"),
        Opportunity.hubspot_deal_id.label("hubspot_deal_id"), Opportunity.client_id.label("client_id"),
        Opportunity.hubspot_owner_id.label("deal_owner_raw"),
        Opportunity.hubspot_pipeline_id.label("pipeline_id"), Opportunity.hubspot_stage_id.label("stage_id"),
        Opportunity.stage_label.label("stage_label"),
        Opportunity.is_closed_won.label("won"), Opportunity.is_closed_lost.label("lost"),
        Opportunity.amount.label("amount"), Opportunity.currency.label("currency"),
        Opportunity.close_date.label("close_date"),
        Opportunity.hubspot_created_at.label("hubspot_created_at"), Opportunity.created_at.label("created_at"),
        Opportunity.hubspot_last_activity_at.label("activity_at"),
        Client.name.label("client_name"), Client.hubspot_company_id.label("company_id"),
        Client.hubspot_owner_id.label("account_owner_raw"),
        HubspotPipeline.label.label("pipeline_label"),
        *_owner_columns(deal_owner, "deal_owner"), *_owner_columns(account_owner, "account_owner"),
        _effective_bu_column().label("raw_region"),
        next_action.c.id.label("na_id"), next_action.c.text.label("na_text"),
        next_action.c.due_date.label("na_due"),
        _agreement_on_file("NDA", Opportunity.client_id).correlate(Opportunity).label("nda"),
        _agreement_on_file("MSA", Opportunity.client_id).correlate(Opportunity).label("msa"),
        select(Agreement.id).exists().label("any_agreement"),
    ]
    if viewer.user_id is not None:
        columns.append(
            select(WatchedItem.id).where(
                WatchedItem.user_id == viewer.user_id, WatchedItem.kind == "opportunity",
                WatchedItem.item_id == Opportunity.id,
            ).correlate(Opportunity).exists().label("watching"))
        if group_id is not None:
            columns.append(
                select(TrackingGroupMember.member_id)
                .join(TrackingGroup, TrackingGroup.id == TrackingGroupMember.group_id)
                .where(TrackingGroupMember.group_id == group_id, TrackingGroup.owner_id == viewer.user_id,
                       TrackingGroup.archived_at.is_(None), TrackingGroup.member_kind == "opportunity",
                       TrackingGroupMember.member_id == Opportunity.id)
                .correlate(Opportunity).exists().label("in_group"))
    stmt = (
        select(*columns)
        .select_from(Opportunity)
        .outerjoin(Client, Client.id == Opportunity.client_id)
        .outerjoin(HubspotPipeline, HubspotPipeline.id == Opportunity.hubspot_pipeline_id)
        .outerjoin(deal_owner, deal_owner.id == Opportunity.hubspot_owner_id)
        .outerjoin(account_owner, account_owner.id == Client.hubspot_owner_id)
        .outerjoin(next_action, and_(next_action.c.opportunity_id == Opportunity.id, next_action.c.position == 1))
        .where(*_base_opportunity_filter(replace(scope, include_closed=True, open_closed="any")))
    )
    facts: list[DealFact] = []
    any_agreement: bool | None = None
    for row in (await session.execute(stmt)).mappings():
        any_agreement = bool(row["any_agreement"])
        raw_region = row["raw_region"]
        deal_owner_id = (row["deal_owner_raw"] or "").strip() or None
        account_owner_id = (row["account_owner_raw"] or "").strip() or None
        fact = DealFact(
            id=row["id"],
            title=(row["title"] or "").strip() or UNNAMED_DEAL,
            hubspot_deal_id=row["hubspot_deal_id"],
            client_id=row["client_id"],
            client_name=row["client_name"],
            client_hubspot_company_id=row["company_id"],
            deal_owner_id=deal_owner_id,
            deal_owner=owner_of(deal_owner_id, row["deal_owner_id"], row["deal_owner_first"],
                                row["deal_owner_last"], row["deal_owner_email"], row["deal_owner_archived"]),
            account_owner_id=account_owner_id,
            account_owner=owner_of(account_owner_id, row["account_owner_id"], row["account_owner_first"],
                                   row["account_owner_last"], row["account_owner_email"],
                                   row["account_owner_archived"]),
            pipeline_label=row["pipeline_label"],
            stage=reference.stages.get((row["pipeline_id"], row["stage_id"])),
            hubspot_stage_label=_bare_label(row["stage_label"]) or None,
            is_closed_won=bool(row["won"]),
            is_closed_lost=bool(row["lost"]),
            amount=row["amount"],
            currency=row["currency"],
            close_date=row["close_date"],
            created_date=la_date(row["hubspot_created_at"] or row["created_at"]),
            activity_date=la_date(row["activity_at"]),
            hubspot_region=raw_region,
            region=reference.regions.get(raw_region) if raw_region else None,
            next_action_id=row["na_id"],
            next_action_text=row["na_text"] if row["na_id"] is not None else None,
            next_action_due=row["na_due"] if row["na_id"] is not None else None,
            nda=bool(row["nda"]),
            msa=bool(row["msa"]),
            watching=bool(row["watching"]) if "watching" in row else False,
            in_group=bool(row["in_group"]) if "in_group" in row else False,
        )
        _derive_row_flags(fact, today)
        fact.search_fields = tuple(text.casefold() for text in (
            fact.title, fact.client_name, fact.deal_owner.name if fact.deal_owner.state == "active" else None,
            fact.next_action_text) if text)
        facts.append(fact)
    if any_agreement is None:  # no deals: ask once, for the agreement-gap note
        any_agreement = bool(await session.scalar(select(select(Agreement.id).exists())))
    if with_sow and facts:
        sow_facts = await load_sow_facts(session, [fact.id for fact in facts])
        for fact in facts:
            fact.sow_state, fact.sow_count = sow_facts.get(fact.id, ("none", 0))
    return facts, any_agreement


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


@dataclass
class _SowFacts:
    sow_id: uuid.UUID
    created_at: datetime
    stamps: list[datetime] = field(default_factory=list)
    # package id → (status, submitted_at, signed uploads)
    packages: dict[uuid.UUID, tuple[str, datetime, int]] = field(default_factory=dict)


async def load_sow_facts(session: AsyncSession, deal_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, tuple[str, int]]:
    """``{deal id: (sow state, live SOW count)}`` in one statement (B6).

    A deal's state is that of its most recently updated live SOW, where a
    SOW's update time is the latest of its creation, version uploads and
    package submissions, releases and voids. A SOW's state comes from its
    newest non-voided package (``_derive_sow_state``); "awaiting signature"
    needs a signed upload on that package.
    """
    signed = (select(func.count(SignedSowUpload.id))
              .where(SignedSowUpload.package_id == ApprovalPackage.id)
              .correlate(ApprovalPackage).scalar_subquery())
    rows = (await session.execute(
        select(Sow.id, Sow.opportunity_id, Sow.created_at, SowVersion.uploaded_at, ApprovalPackage.id,
               ApprovalPackage.status, ApprovalPackage.submitted_at, ApprovalPackage.released_at,
               ApprovalPackage.voided_at, signed)
        .select_from(Sow)
        .outerjoin(SowVersion, SowVersion.sow_id == Sow.id)
        .outerjoin(ApprovalPackage, ApprovalPackage.sow_version_id == SowVersion.id)
        .where(Sow.archived_at.is_(None), Sow.opportunity_id.in_(list(deal_ids)))
    )).all()
    per_deal: dict[uuid.UUID, dict[uuid.UUID, _SowFacts]] = defaultdict(dict)
    for sow_id, deal_id, created, uploaded, package_id, status, submitted, released, voided, signed_count in rows:
        facts = per_deal[deal_id].setdefault(sow_id, _SowFacts(sow_id, _utc(created)))
        facts.stamps.extend(stamp for stamp in (_utc(created), _utc(uploaded)) if stamp)
        if package_id is not None:
            facts.stamps.extend(stamp for stamp in (_utc(submitted), _utc(released), _utc(voided)) if stamp)
            if status != "voided":
                facts.packages[package_id] = (status, _utc(submitted), int(signed_count or 0))
    out: dict[uuid.UUID, tuple[str, int]] = {}
    for deal_id, sows in per_deal.items():
        latest = max(sows.values(), key=lambda s: (max(s.stamps), s.created_at, s.sow_id))
        current = max(latest.packages.items(), key=lambda item: (item[1][1], item[0]), default=None)
        state = _derive_sow_state(sow_id=latest.sow_id, latest_status=current[1][0] if current else None,
                                  signed_count=current[1][2] if current else 0)
        out[deal_id] = (state.value, len(sows))
    return out


async def load_visible_clients(session: AsyncSession, scope: PipelineFilters) -> list[ClientFact]:
    """Every client the caller may see (for "include clients without matching deals")."""
    account_owner = aliased(HubspotOwner, name="account_owner")
    rows = (await session.execute(
        select(Client.id, Client.name, Client.hubspot_company_id, Client.hubspot_owner_id,
               *_owner_columns(account_owner, "account_owner"),
               _agreement_on_file("NDA", Client.id).correlate(Client).label("nda"),
               _agreement_on_file("MSA", Client.id).correlate(Client).label("msa"))
        .select_from(Client)
        .outerjoin(account_owner, account_owner.id == Client.hubspot_owner_id)
        .where(*_client_visibility(scope))
    )).mappings()
    out = []
    for row in rows:
        owner_id = (row["hubspot_owner_id"] or "").strip() or None
        out.append(ClientFact(
            id=row["id"], name=row["name"], hubspot_company_id=row["hubspot_company_id"],
            account_owner_id=owner_id,
            account_owner=owner_of(owner_id, row["account_owner_id"], row["account_owner_first"],
                                   row["account_owner_last"], row["account_owner_email"],
                                   row["account_owner_archived"]),
            nda=bool(row["nda"]), msa=bool(row["msa"])))
    return out


# --- THE filter function ------------------------------------------------------------


def _status_ok(row: DealFact, status: str) -> bool:
    if status == "open":
        return is_open(row)
    if status == "won":
        return row.is_closed_won
    if status == "lost":
        return row.is_closed_lost
    if status == "hold":
        return row.is_hold
    return True  # all


def _attention_ok(row: DealFact, attention: str) -> bool:
    if attention == "pending_approval":
        return is_open(row) and row.sow_state in PENDING_SOW_STATES
    if attention == "any":
        return bool(row.flags)  # flags exist on open deals only
    return {"overdue": "action_overdue", "past_close": "close_passed", "no_owner": "no_owner",
            "inactive": "inactive_14d"}[attention] in row.flags


def _missing_ok(row: DealFact, missing: str) -> bool:
    if missing == "owner":
        return row.deal_owner.state == "none"
    if missing == "close":
        return row.close_date is None
    if missing == "activity":
        return row.activity_date is None
    if missing == "next_action":
        return is_open(row) and row.next_action_id is None
    if missing == "nda":
        return not row.nda
    if missing == "msa":
        return not row.msa
    return not (row.nda and row.msa)  # agreements: either missing


def _date_value(row: DealFact, date_field: str) -> date | None:
    if date_field == "created":
        return row.created_date
    if date_field == "activity":
        return row.activity_date
    return row.close_date


def matches(row: DealFact, f: WorkspaceFilters, ctx: Context, skip: Iterable[str] = ()) -> bool:
    """THE predicate: does a deal belong to the list these filters describe?

    ``account_owner`` is not a deal filter (it narrows client rows only).
    ``skip`` leaves named filters out (the stage navigator skips stage and status).
    """
    skip = frozenset(skip)
    if f.client is not None and row.client_id != f.client:
        return False
    if "status" not in skip and not _status_ok(row, f.status):
        return False
    if "stage" not in skip and f.stage and (row.stage is None or row.stage.ordinal not in f.stage):
        return False
    if f.owner and not owner_matches(row.deal_owner_id, row.deal_owner, f.owner):
        return False
    if f.bu and not (("unmapped" in f.bu and row.region is None)
                     or (row.region is not None and row.region.business_unit in f.bu)):
        return False
    if f.q:
        needle = f.q.strip().casefold()
        if needle and not any(needle in text for text in row.search_fields):
            return False
    if f.sow and not (row.sow_state in PENDING_SOW_STATES if f.sow == "pending" else row.sow_state == f.sow):
        return False
    if f.attention and not _attention_ok(row, f.attention):
        return False
    if f.missing and not _missing_ok(row, f.missing):
        return False
    if f.group is not None and (f.group != ctx.group_id or not row.in_group):
        return False
    if f.watching and not row.watching:
        return False
    if f.mine and (ctx.mine_owner_id is None or row.deal_owner_id != ctx.mine_owner_id):
        return False
    if f.date_preset != "any":
        value = _date_value(row, f.date_field)
        if value is None:
            return False
        low, high = preset_range(f.date_preset, ctx.today, f.date_from, f.date_to)
        if (low is not None and value < low) or (high is not None and value > high):
            return False
    return True


def apply_filters(rows: Iterable[DealFact], f: WorkspaceFilters, ctx: Context,
                  skip: Iterable[str] = ()) -> list[DealFact]:
    skip = frozenset(skip)
    return [row for row in rows if matches(row, f, ctx, skip)]


# --- client rows ------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientRowData:
    client: ClientFact
    matching_deals: int
    open_deals: int
    matching_value_usd: Decimal | None
    earliest_close_date: date | None
    last_activity_date: date | None
    days_since_activity: int | None
    flags: tuple[str, ...]


def _usd_total(rows: Iterable[DealFact]) -> Decimal:
    return sum((row.usd_amount for row in rows if row.usd_amount is not None), Decimal(0))


def build_client_rows(population: list[DealFact], f: WorkspaceFilters, ctx: Context,
                      visible_clients: Iterable[ClientFact] = ()) -> list[ClientRowData]:
    """Clients with at least one matching deal, then the account-owner filter.

    With ``include_unmatched_clients`` every other visible client is added
    (still filtered by account owner; a search matches the client name only).
    Flags come from the client's matching OPEN deals only.
    """
    open_counts = Counter(row.client_id for row in population if row.client_id is not None and is_open(row))
    matched: dict[uuid.UUID, list[DealFact]] = {}
    for row in apply_filters(population, f, ctx):
        if row.client_id is not None:
            matched.setdefault(row.client_id, []).append(row)
    out: list[ClientRowData] = []
    for client_id, deals in matched.items():
        first = deals[0]
        client = ClientFact(id=client_id, name=first.client_name or "", hubspot_company_id=first.client_hubspot_company_id,
                            account_owner_id=first.account_owner_id, account_owner=first.account_owner,
                            nda=first.nda, msa=first.msa)
        if f.account_owner and not owner_matches(client.account_owner_id, client.account_owner, f.account_owner):
            continue
        usd = [row.usd_amount for row in deals if row.usd_amount is not None]
        closes = [row.close_date for row in deals if row.close_date is not None]
        activity = [row.activity_date for row in deals if row.activity_date is not None]
        last_activity = max(activity) if activity else None
        open_flags = {flag for row in deals if is_open(row) for flag in row.flags}
        out.append(ClientRowData(
            client=client, matching_deals=len(deals), open_deals=open_counts[client_id],
            matching_value_usd=sum(usd, Decimal(0)) if usd else None,
            earliest_close_date=min(closes) if closes else None, last_activity_date=last_activity,
            days_since_activity=(ctx.today - last_activity).days if last_activity else None,
            flags=tuple(flag for flag in CLIENT_FLAGS if flag in open_flags)))
    if f.include_unmatched_clients:
        needle = (f.q or "").strip().casefold()
        for client in visible_clients:
            if client.id in matched or (f.client is not None and client.id != f.client):
                continue
            if f.account_owner and not owner_matches(client.account_owner_id, client.account_owner,
                                                     f.account_owner):
                continue
            if needle and needle not in client.name.casefold():
                continue
            out.append(ClientRowData(client=client, matching_deals=0, open_deals=open_counts[client.id],
                                     matching_value_usd=None, earliest_close_date=None, last_activity_date=None,
                                     days_since_activity=None, flags=()))
    return out


# --- sorting ---------------------------------------------------------------------------------


def sort_deals(rows: list[DealFact], sort: str) -> list[DealFact]:
    """value desc | close asc | activity asc (oldest first) | name; nulls last; then name, id."""
    def name(row: DealFact) -> tuple:
        return (row.title.casefold(), str(row.id))

    if sort == "close":
        return sorted(rows, key=lambda r: (r.close_date is None, r.close_date or date.max, *name(r)))
    if sort == "activity":
        return sorted(rows, key=lambda r: (r.activity_date is None, r.activity_date or date.max, *name(r)))
    if sort == "name":
        return sorted(rows, key=name)
    return sorted(rows, key=lambda r: (r.amount is None, -(r.amount or 0), *name(r)))


def sort_clients(rows: list[ClientRowData], sort: str) -> list[ClientRowData]:
    def name(row: ClientRowData) -> tuple:
        return (row.client.name.casefold(), str(row.client.id))

    if sort == "close":
        return sorted(rows, key=lambda r: (r.earliest_close_date is None, r.earliest_close_date or date.max, *name(r)))
    if sort == "activity":
        return sorted(rows, key=lambda r: (r.last_activity_date is None, r.last_activity_date or date.max, *name(r)))
    if sort == "name":
        return sorted(rows, key=name)
    return sorted(rows, key=lambda r: (r.matching_value_usd is None, -(r.matching_value_usd or 0), *name(r)))


# --- the response ----------------------------------------------------------------------------


def money(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(CENT), "f")


def deal_wire(row: DealFact) -> dict[str, Any]:
    region = row.region
    return {
        "id": row.id,
        "title": row.title,
        "client": {"id": row.client_id, "name": row.client_name},
        "stage_id": row.stage.ordinal if row.stage else None,
        "stage_label": row.stage.label if row.stage else row.hubspot_stage_label,
        # Additive: the status the row is in (open includes Hold, which reads "hold").
        "status": ("won" if row.is_closed_won else "lost" if row.is_closed_lost
                   else "hold" if row.is_hold else "open"),
        "amount": money(row.amount),
        "currency": row.currency,
        "business_unit": region.business_unit if region else None,
        "region": region.region if region else None,
        "region_note": region.note if region else None,
        "hubspot_region": row.hubspot_region,
        "bu_unmapped": region is None,
        "deal_owner": row.deal_owner.wire(),
        "account_owner": row.account_owner.wire(),
        "close_date": row.close_date,
        "created_date": row.created_date,
        "last_activity_date": row.activity_date,
        "days_since_activity": row.days_since_activity,
        "sow_state": row.sow_state,
        "sow_state_label": SOW_STATE_LABELS[row.sow_state],
        "sow_count": row.sow_count,
        "agreements": {"nda_on_file": row.nda, "msa_on_file": row.msa},
        "next_action": ({"id": row.next_action_id, "text": row.next_action_text, "due_on": row.next_action_due}
                        if row.next_action_id is not None else None),
        "flags": list(row.flags),
        "watching": row.watching,
        "hubspot_deal_id": row.hubspot_deal_id,
        "pipeline_label": row.pipeline_label,
    }


def client_wire(row: ClientRowData) -> dict[str, Any]:
    client = row.client
    return {
        "id": client.id,
        "name": client.name,
        "account_owner": client.account_owner.wire(),
        "matching_deals": row.matching_deals,
        "open_deals": row.open_deals,
        "matching_value_usd": money(row.matching_value_usd),
        "earliest_close_date": row.earliest_close_date,
        "last_activity_date": row.last_activity_date,
        "days_since_activity": row.days_since_activity,
        "agreements": {"nda_on_file": client.nda, "msa_on_file": client.msa},
        "flags": list(row.flags),
        "hubspot_company_id": client.hubspot_company_id,
    }


def build_metrics(population: list[DealFact], f: WorkspaceFilters, ctx: Context,
                  any_agreement_files: bool) -> dict[str, Any]:
    """Each value is the list its drill opens, computed by the same filter function."""
    def deals(drill: Mapping[str, Any]) -> list[DealFact]:
        return apply_filters(population, f.merge(drill), ctx)

    open_list = deals(DRILLS["open_deals"])
    closing = deals(DRILLS["closing_this_month"])
    gaps = build_client_rows(population, f.merge(DRILLS["agreement_gap_clients"]), ctx)
    clients_total = build_client_rows(
        population, f.merge({"tab": "clients", "include_unmatched_clients": False, "missing": None}), ctx)
    return {
        "open_deals": {"value": len(open_list),
                       "accounts": len({row.client_id for row in open_list if row.client_id is not None}),
                       "drill": DRILLS["open_deals"]},
        "open_value_usd": {"value": money(_usd_total(open_list)),
                           "includes_on_hold": sum(1 for row in open_list if row.is_hold),
                           "deals": len(open_list), "drill": DRILLS["open_value_usd"]},
        "closing_this_month": {"value": len(closing), "value_usd": money(_usd_total(closing)),
                               "drill": DRILLS["closing_this_month"]},
        "overdue_next_actions": {
            "value": len(deals(DRILLS["overdue_next_actions"])),
            # The denominator is the card's own list without the attention filter the drill
            # replaces, so every overdue deal is one of the deals with a next action.
            "with_next_action": sum(1 for row in deals({"status": "open", "attention": None})
                                    if row.next_action_id is not None),
            "drill": DRILLS["overdue_next_actions"]},
        "pending_approvals": {"value": len(deals(DRILLS["pending_approvals"])),
                              "drill": DRILLS["pending_approvals"]},
        "agreement_gap_clients": {"value": len(gaps), "clients_total": len(clients_total),
                                  "any_agreement_files": any_agreement_files,
                                  "drill": DRILLS["agreement_gap_clients"]},
    }


def build_stage_counts(population: list[DealFact], f: WorkspaceFilters, ctx: Context,
                       reference: Reference) -> list[dict[str, Any]]:
    """Every stage, zero included; counts ignore the stage and status filters."""
    by_ordinal: dict[int, list[DealFact]] = defaultdict(list)
    for row in apply_filters(population, f, ctx, skip=("stage", "status")):
        if row.stage is not None:
            by_ordinal[row.stage.ordinal].append(row)
    return [{"stage_id": stage.ordinal, "label": stage.label, "full_label": stage.full_label,
             "deals": len(by_ordinal[stage.ordinal]),
             "known_value_usd": money(_usd_total(by_ordinal[stage.ordinal])),
             "deals_without_amount": sum(1 for row in by_ordinal[stage.ordinal] if row.amount is None)}
            for stage in reference.stage_list]


def build_focus(population: list[DealFact], ctx: Context) -> dict[str, Any]:
    """Focus counts: the default view (every filter cleared, status open) plus the preset."""
    counts = {key: len(apply_filters(population, DEFAULT_VIEW.merge(preset), ctx))
              for key, preset in FOCUS_PRESETS.items()}
    available = ctx.mine_owner_id is not None
    return {"all_open": counts["all_open"], "closing_this_month": counts["closing_this_month"],
            "mine": counts["mine"] if available else None, "mine_available": available,
            "needs_attention": counts["needs_attention"], "watching": counts["watching"]}


def build_options(population: list[DealFact], reference: Reference) -> dict[str, Any]:
    def active(pairs: Iterable[tuple[str | None, Owner]]) -> list[dict[str, str]]:
        found = {owner_id: owner.name for owner_id, owner in pairs if owner_id and owner.state == "active"}
        return [{"id": owner_id, "name": name or ""}
                for owner_id, name in sorted(found.items(), key=lambda item: ((item[1] or "").casefold(), item[0]))]

    return {
        "deal_owners": active((row.deal_owner_id, row.deal_owner) for row in population),
        "account_owners": active((row.account_owner_id, row.account_owner) for row in population),
        "business_units": list(reference.business_units),
        "sow_states": [{"value": value, "label": label} for value, label in SOW_STATE_LABELS.items()],
    }


@dataclass
class WorkspaceData:
    ctx: Context
    reference: Reference
    population: list[DealFact]
    any_agreement_files: bool
    visible_clients: list[ClientFact]
    freshness: dict[str, Any] | None


async def load_workspace_data(session: AsyncSession, *, actor: AuthUser, filters: WorkspaceFilters,
                              now: datetime | None = None, with_freshness: bool = True) -> WorkspaceData:
    now = business_now(now)
    today = business_today(now)
    viewer = await resolve_viewer(session, actor)
    scope = await scope_pipeline_filters(session, actor, PipelineFilters(include_closed=True, open_closed="any"))
    freshness = None
    if with_freshness:
        from app.services.hubspot_sync_runs import compute_sync_health

        freshness = await compute_sync_health(session, now=now)
    reference = await load_reference(session)
    population, any_agreement = await load_population(
        session, scope, viewer=viewer, reference=reference, today=today, group_id=filters.group)
    visible = await load_visible_clients(session, scope) if filters.include_unmatched_clients else []
    ctx = Context(today=today, mine_owner_id=viewer.hubspot_owner_id, group_id=filters.group)
    return WorkspaceData(ctx, reference, population, any_agreement, visible, freshness)


async def build_workspace(session: AsyncSession, *, actor: AuthUser, filters: WorkspaceFilters,
                          now: datetime | None = None) -> dict[str, Any]:
    """The whole ``GET /pipeline/workspace`` response."""
    data = await load_workspace_data(session, actor=actor, filters=filters, now=now)
    f, ctx, population = filters, data.ctx, data.population
    filtered = apply_filters(population, f, ctx)
    client_rows = build_client_rows(population, f, ctx, data.visible_clients)
    start = (f.page - 1) * f.page_size
    rows_by_stage: dict[str, Any] | None = None
    if f.tab == "clients":
        rows = [client_wire(row) for row in sort_clients(client_rows, f.sort)[start:start + f.page_size]]
        page = {"number": f.page, "size": f.page_size, "total_rows": len(client_rows), "total_value_usd": None}
    else:
        ordered = sort_deals(filtered, f.sort)
        if f.layout == "board":
            rows, rows_by_stage = [], {}
            for stage in data.reference.stage_list:
                lane = [row for row in ordered if row.stage is not None and row.stage.ordinal == stage.ordinal]
                if lane:
                    rows_by_stage[str(stage.ordinal)] = {
                        "total": len(lane), "value_usd": money(_usd_total(lane)),
                        "deals": [deal_wire(row) for row in lane[:BOARD_LANE_SIZE]]}
        else:
            rows = [deal_wire(row) for row in ordered[start:start + f.page_size]]
        page = {"number": f.page, "size": f.page_size, "total_rows": len(filtered),
                "total_value_usd": money(_usd_total(filtered))}
    return {
        "freshness": data.freshness,
        "metrics": build_metrics(population, f, ctx, data.any_agreement_files),
        "stages": build_stage_counts(population, f, ctx, data.reference),
        "focus": build_focus(population, ctx),
        "unmapped_regions": sum(1 for row in filtered if row.region is None),
        "rows": rows,
        "rows_by_stage": rows_by_stage,
        "page": page,
        "tab_counts": {"deals": len(filtered), "clients": len(client_rows)},
        "options": build_options(population, data.reference),
        "today": ctx.today,
    }


# --- export (B10) -------------------------------------------------------------------------------


def _iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def deal_export_cells(row: DealFact) -> list[str]:
    if row.region is not None:
        unit = f"{row.region.business_unit} · {row.region.region}"
    else:
        unit = f"Unmapped · {row.hubspot_region}" if row.hubspot_region else ""
    stage = row.stage.full_label if row.stage else (row.hubspot_stage_label or "")
    return safe_row([
        row.title, row.client_name or "", row.deal_owner.export_text(), row.account_owner.export_text(), unit,
        row.hubspot_region or "", stage, format(row.amount, "f") if row.amount is not None else "",
        row.currency or "", _iso(row.close_date), _iso(row.created_date), _iso(row.activity_date),
        SOW_STATE_LABELS[row.sow_state], _yes_no(row.nda), _yes_no(row.msa), row.next_action_text or "",
        _iso(row.next_action_due),
    ])


def client_export_cells(row: ClientRowData) -> list[str]:
    client = row.client
    return safe_row([
        client.name, client.account_owner.export_text(), row.matching_deals, row.open_deals,
        money(row.matching_value_usd) or "", _yes_no(client.nda), _yes_no(client.msa),
        _iso(row.last_activity_date),
    ])


async def export_workspace(session: AsyncSession, *, actor: AuthUser, filters: WorkspaceFilters,
                           now: datetime | None = None) -> tuple[tuple[str, ...], list[list[str]]]:
    """Header and every filtered row of the active tab, in the current sort, neutralised."""
    data = await load_workspace_data(session, actor=actor, filters=filters, now=now, with_freshness=False)
    if filters.tab == "clients":
        rows = sort_clients(build_client_rows(data.population, filters, data.ctx, data.visible_clients),
                            filters.sort)
        return CLIENT_EXPORT_COLUMNS, [client_export_cells(row) for row in rows]
    rows = sort_deals(apply_filters(data.population, filters, data.ctx), filters.sort)
    return DEAL_EXPORT_COLUMNS, [deal_export_cells(row) for row in rows]


# --- the Command Center's open number (B2) -----------------------------------------------------


@dataclass(frozen=True)
class OpenTotals:
    count: int
    value_usd: Decimal
    # The workspace parameters that open exactly the counted list; None when the
    # Command Center's scope has no Pipeline equivalent (see open_totals).
    pipeline_query: dict[str, list[str]] | None
    business_units: tuple[str, ...] = ()  # the workspace's ``bu`` values the count covers


def _business_unit_filter(reference: Reference, hubspot_value: str) -> str:
    """The workspace's ``bu`` value for a raw HubSpot region: its business unit, else ``unmapped``."""
    mapped = reference.regions.get(hubspot_value)
    return mapped.business_unit if mapped else "unmapped"


async def _linked_owner_id(session: AsyncSession, user_id: uuid.UUID) -> str | None:
    """The HubSpot owner a DealGate user is, as the Pipeline's "mine" resolves it.

    The stored link, else the exact-email match (``resolve_viewer``, given the
    row's own email so it never asks Cognito). None for an unknown user, for a
    user with no link, and for the Unassigned placeholder: intake gives it every
    deal whose owner it could not resolve, which no Pipeline owner filter lists.
    """
    email = await session.scalar(select(User.email).where(User.id == user_id))
    if email is None or email == UNASSIGNED_OWNER_EMAIL:
        return None
    viewer = await resolve_viewer(session, AuthUser(user_id, email, "", ()))
    return viewer.hubspot_owner_id


async def open_totals(session: AsyncSession, scope: PipelineFilters, *, now: datetime | None = None) -> OpenTotals:
    """The Pipeline's open count and USD value for a Command Center scope, and the link that lists them.

    ``scope`` is the Command Center's own filter after fixture scoping: raw
    HubSpot region values and DealGate owners. The Pipeline filters by business
    unit and by HubSpot owner, so the count is taken over the list the link
    opens: each region becomes its business unit (or ``unmapped``), each owner
    the HubSpot owner they are linked to, and the workspace's filter function
    keeps the open deals (the default view) — the same function the Pipeline
    runs. An owner the Pipeline cannot filter on (no link, or the Unassigned
    placeholder) leaves no Pipeline equivalent: the count then stays on the
    Command Center's own scope and ``pipeline_query`` is None (no link).
    """
    today = business_today(now)
    reference = await load_reference(session)
    owners = [await _linked_owner_id(session, user_id) for user_id in scope.owner]
    linked = tuple(owner_id for owner_id in owners if owner_id)
    query: dict[str, list[str]] | None = None
    units: tuple[str, ...] = ()
    population_scope, filters = scope, DEFAULT_VIEW
    if len(linked) == len(owners):  # every owner (or none) has a Pipeline equivalent
        units = tuple(dict.fromkeys(_business_unit_filter(reference, value) for value in scope.business_unit))
        population_scope = replace(scope, business_unit=(), owner=())
        filters = replace(DEFAULT_VIEW, bu=units, owner=linked)
        query = {**({"bu": list(units)} if units else {}), **({"owner": list(linked)} if linked else {})}
    population, _ = await load_population(session, population_scope, viewer=Viewer(None, None, None),
                                          reference=reference, today=today, with_sow=False)
    open_rows = apply_filters(population, filters, Context(today=today))
    return OpenTotals(count=len(open_rows), value_usd=_usd_total(open_rows), pipeline_query=query,
                      business_units=units)


__all__ = [
    "ATTENTION", "BU_FILTERS", "CLIENT_EXPORT_COLUMNS", "DATE_FIELDS", "DEAL_EXPORT_COLUMNS", "DRILLS",
    "LAYOUTS", "MISSING", "PAGE_SIZES", "SORTS", "SOW_FILTERS", "SOW_STATE_LABELS", "STATUSES", "TABS",
    "OpenTotals", "WorkspaceFilters", "apply_filters", "build_workspace", "export_workspace", "matches",
    "open_totals",
]
