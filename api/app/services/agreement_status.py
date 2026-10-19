"""S24-AG1 B2 — the ONE place that decides a client's agreement status.

The Agreements page, the Pipeline, the Command Center and the client panel all
call this module; nothing else computes relationship, requirement, document
state or "needs attention". The rules (docs/reference/openapi-agreements.yaml,
components ``Cutover``, ``Relationship``, ``Requirement`` and ``DocState``):

* **Relationship.** Existing when the client has a Closed Won HubSpot deal, or
  an SOW or engagement in DealGate (judged as of the cutover once it is set;
  live and *provisional* before). After the cutover the stored value is used
  and a later win or SOW never turns a net-new client into existing. A
  writer's manual change (basis ``manual``) always wins.
* **Requirement** (net new only). ``required``: an open deal at stage 2 to 6,
  a deal on Hold, a Closed Won deal, or an SOW/engagement created after the
  cutover. ``later``: open deals exist and all are stage 1. ``none``: otherwise.
* **Document state** per kind: ``client`` (own file), ``standard`` (a standard
  copy attached), ``covered`` (marked), else ``existing_none`` for an existing
  client, else ``missing`` / ``due_later`` / ``not_needed`` by requirement.
* **Needs attention** = net new, requirement ``required``, NDA or MSA missing.

Hold: the HubSpot "Hold" stage carries no record of the stage a deal was
paused at, so a deal on Hold counts as open and past stage 1 (the directive's
"open or on-hold deal at stage 2 to 6"); ``furthest_open_stage`` reports stages
1 to 6 only and ``on_hold`` says a Hold deal exists.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Sequence

KINDS: tuple[str, str] = ("NDA", "MSA")
DOC_STATES: tuple[str, ...] = ("client", "standard", "covered", "missing", "due_later", "not_needed", "existing_none")
STATE_LABELS: dict[str, str] = {
    "client": "Client copy",
    "standard": "Standard copy",
    "covered": "Marked covered",
    "missing": "Missing",
    "due_later": "Due at stage 2",
    "not_needed": "Not needed now",
    "existing_none": "Existing, none attached",
}
CARD_KEYS: tuple[str, ...] = ("clients", "existing", "net_new", "needs_attention", "standard_attached", "client_copies")
STAGE_NAMES: dict[int, str] = {
    1: "Prospecting", 2: "Qualification", 3: "Fit gap analysis", 4: "Proposal", 5: "Negotiation", 6: "Contracting",
}
BU_REGIONS: dict[str, str] = {"ST21": "US", "IT Avalon": "US", "Retro Rabbit": "South Africa"}
BU_ORDER: tuple[str, ...] = ("ST21", "IT Avalon", "Retro Rabbit")
PLACEHOLDER_PREFIX = "Unknown company (deal "
RELATIONSHIP_FILTERS = ("all", "existing", "net_new")
STATUS_FILTERS = ("any", "attention", "missing_nda", "missing_msa", "has_standard", "has_client", "marked_covered",
                  "possible_duplicate")
STAGE_FILTERS = ("any", "past_stage_1", "stage_1_only", "no_active_deal")
SORTS = ("attention", "name", "stage")
PAGE_SIZES = (25, 50, 100)

# --- inputs ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DealInput:
    """One live HubSpot deal. ``ordinal`` is the stage position 1-6 (None when unknown or closed)."""

    status: str  # "open" | "hold" | "won" | "lost"
    ordinal: int | None = None
    close_date: date | None = None


@dataclass(frozen=True)
class DocInput:
    """What a client holds for one kind: an agreement row and/or an active mark."""

    source: str | None = None  # "client" | "standard" | None (no agreement row)
    standard_version: int | None = None
    batch_label: str | None = None
    mark_source: str | None = None  # "dealgate" | "hubspot" | None (no active mark)


@dataclass(frozen=True)
class ClientInput:
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None = None
    created_at: datetime | None = None
    stored_relationship: str | None = None
    stored_basis: str | None = None
    deals: tuple[DealInput, ...] = ()
    sow_dates: tuple[date, ...] = ()
    engagement_dates: tuple[date, ...] = ()
    docs: Mapping[str, DocInput] = field(default_factory=dict)
    business_units: tuple[tuple[str, str], ...] = ()  # (business unit, region) pairs
    test_data: bool = False
    hubspot_msa_type: str | None = None


# --- outputs -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class ClientStatus:
    client_id: uuid.UUID
    name: str
    relationship: str
    relationship_basis: str
    provisional: bool
    requirement: str
    nda: str
    msa: str
    nda_label: str | None
    msa_label: str | None
    needs_attention: bool
    furthest_open_stage: int
    on_hold: bool
    open_deals: int
    won_deals: int
    lost_deals: int
    deal_count: int
    business_units: tuple[tuple[str, str], ...]
    flags: tuple[str, ...]
    unknown_stage: bool = False
    hubspot_msa_type: str | None = None

    def state(self, kind: str) -> str:
        return self.nda if kind == "NDA" else self.msa

    @property
    def stage_bucket(self) -> str:
        """past_stage_1 | stage_1_only | no_active_deal."""
        if self.on_hold or self.unknown_stage or self.furthest_open_stage >= 2:
            return "past_stage_1"
        if self.furthest_open_stage == 1:
            return "stage_1_only"
        return "no_active_deal"


# --- pure rules --------------------------------------------------------------------------------

_POSSESSIVE = re.compile(r"[’']s\b", re.IGNORECASE)
_DOTS = re.compile(r"[.’']")
_PUNCT = re.compile(r"[^\w\s]+")
_SUFFIXES = ("llc", "inc", "ltd", "corp", "co", "company")


def normalise_name(name: str) -> str:
    """The duplicate-name key (directive B2): lower case; possessives, then dots and apostrophes removed (so
    "L.L.C." reads "llc"); other punctuation becomes a space; trailing llc/inc/ltd/corp/co/company stripped."""
    text = _POSSESSIVE.sub("", (name or "").lower())
    text = _DOTS.sub("", text)
    tokens = _PUNCT.sub(" ", text).replace("_", " ").split()
    while len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def is_placeholder(name: str, hubspot_company_id: str | None) -> bool:
    return hubspot_company_id is None and (name or "").startswith(PLACEHOLDER_PREFIX)


def live_relationship(client: ClientInput, as_of: date | None) -> tuple[str, str]:
    """The rule: (relationship, basis). ``as_of`` limits the evidence to a date (the cutover); None = all."""
    won = any(d.status == "won" and (as_of is None or d.close_date is None or d.close_date <= as_of)
              for d in client.deals)
    sow = any(as_of is None or d <= as_of for d in (*client.sow_dates, *client.engagement_dates))
    if won and sow:
        return "existing", "closed_won_and_sow"
    if won:
        return "existing", "closed_won"
    if sow:
        return "existing", "sow_engagement"
    return "net_new", "none"


def relationship_of(client: ClientInput, cutover: date | None) -> tuple[str, str, bool]:
    """(relationship, basis, provisional). Before the cutover: live and provisional. After: the stored value."""
    if client.stored_relationship in ("existing", "net_new"):
        return client.stored_relationship, client.stored_basis or "none", cutover is None
    if cutover is None:
        rel, basis = live_relationship(client, None)
        return rel, basis, True
    # Not stamped although the cutover is set (created after it, before the hook or the nightly settle
    # stamped it): judge it as the B8 rule would: net new unless it has a Closed Won deal dated on or before
    # the cutover. A won deal with no close date counts as on or before, as it does at the cutover itself.
    won_before = any(d.status == "won" and (d.close_date is None or d.close_date <= cutover) for d in client.deals)
    return ("existing", "closed_won", False) if won_before else ("net_new", "none", False)


def deal_summary(deals: Iterable[DealInput]) -> tuple[int, bool, int, int, int]:
    """(furthest open stage 1-6 or 0, on hold, open count incl. Hold, won count, lost count)."""
    furthest, hold, open_, won, lost = 0, False, 0, 0, 0
    for d in deals:
        if d.status == "open":
            open_ += 1
            if d.ordinal is not None and 1 <= d.ordinal <= 6:
                furthest = max(furthest, d.ordinal)
        elif d.status == "hold":
            open_ += 1
            hold = True
        elif d.status == "won":
            won += 1
        elif d.status == "lost":
            lost += 1
    return furthest, hold, open_, won, lost


def has_unknown_stage(deals: Iterable[DealInput]) -> bool:
    return any(d.status == "open" and (d.ordinal is None or not 1 <= d.ordinal <= 6) for d in deals)


def requirement_of(client: ClientInput, relationship: str, cutover: date | None) -> str:
    if relationship != "net_new":
        return "none"
    furthest, hold, open_, won, _lost = deal_summary(client.deals)
    later_work = cutover is not None and any(d > cutover for d in (*client.sow_dates, *client.engagement_dates))
    # An open deal whose stage is not in the stage mirror (an archived stage) cannot be placed; warn rather
    # than hide it, so it counts as past stage 1.
    unknown = has_unknown_stage(client.deals)
    if furthest >= 2 or hold or won or later_work or unknown:
        return "required"
    if open_ and furthest == 1:
        return "later"
    return "none"


def doc_state(doc: DocInput | None, relationship: str, requirement: str) -> str:
    if doc is not None and doc.source == "client":
        return "client"
    if doc is not None and doc.source == "standard":
        return "standard"
    if doc is not None and doc.mark_source:
        return "covered"
    if relationship == "existing":
        return "existing_none"
    return {"required": "missing", "later": "due_later"}.get(requirement, "not_needed")


def source_label(doc: DocInput | None, state: str) -> str | None:
    if state == "standard" and doc is not None:
        return f"Standard v{doc.standard_version}" if doc.standard_version else "Standard copy"
    if state == "client":
        return "Client copy"
    if state == "covered" and doc is not None:
        return "Marked by HubSpot" if doc.mark_source == "hubspot" else "Marked covered"
    return None


def classify(client: ClientInput, cutover: date | None, duplicate_keys: frozenset[str] = frozenset()) -> ClientStatus:
    relationship, basis, provisional = relationship_of(client, cutover)
    requirement = requirement_of(client, relationship, cutover)
    furthest, hold, open_, won, lost = deal_summary(client.deals)
    states = {k: doc_state(client.docs.get(k), relationship, requirement) for k in KINDS}
    flags: list[str] = []
    placeholder = is_placeholder(client.name, client.hubspot_company_id)
    if not placeholder and normalise_name(client.name) in duplicate_keys:
        flags.append("possible_duplicate")
    if client.test_data:
        flags.append("test_data")
    if placeholder:
        flags.append("unknown_company")
    elif client.hubspot_company_id is None:
        flags.append("no_hubspot_link")
    seen: dict[str, str] = {}
    for unit, region in client.business_units:
        seen.setdefault(unit, region)
    units = tuple((u, seen[u]) for u in BU_ORDER if u in seen)
    return ClientStatus(
        client_id=client.id, name=client.name, relationship=relationship, relationship_basis=basis,
        provisional=provisional, requirement=requirement, nda=states["NDA"], msa=states["MSA"],
        nda_label=source_label(client.docs.get("NDA"), states["NDA"]),
        msa_label=source_label(client.docs.get("MSA"), states["MSA"]),
        needs_attention=relationship == "net_new" and requirement == "required" and "missing" in states.values(),
        furthest_open_stage=furthest, on_hold=hold, open_deals=open_, won_deals=won, lost_deals=lost,
        deal_count=len(client.deals), business_units=units, flags=tuple(flags),
        hubspot_msa_type=client.hubspot_msa_type, unknown_stage=has_unknown_stage(client.deals),
    )


def duplicate_keys(clients: Iterable[ClientInput]) -> frozenset[str]:
    """Normalised names held by more than one client. "Unknown company (deal …)" placeholders never count."""
    counts: dict[str, int] = defaultdict(int)
    for c in clients:
        if is_placeholder(c.name, c.hubspot_company_id):
            continue
        key = normalise_name(c.name)
        if key:
            counts[key] += 1
    return frozenset(k for k, n in counts.items() if n > 1)


def classify_all(clients: Sequence[ClientInput], cutover: date | None) -> list[ClientStatus]:
    keys = duplicate_keys(clients)
    return [classify(c, cutover, keys) for c in clients]


# --- cards, filters, sort ----------------------------------------------------------------------


def basis_text(status: ClientStatus, *, forecast: bool = False, set_by: str | None = None) -> str:
    """The relationship basis in words, as the page shows it."""
    if status.relationship == "net_new":
        return "Marked net new by " + set_by if status.relationship_basis == "manual" and set_by else (
            "Marked net new" if status.relationship_basis == "manual" else "No earlier work found")
    if status.relationship_basis == "manual":
        return f"Marked existing by {set_by}" if set_by else "Marked existing"
    if status.relationship_basis == "closed_won_and_sow":
        return "Closed Won deal and SOW"
    if status.relationship_basis == "sow_engagement":
        if forecast:
            return "Engagement from the forecast model"
        return "SOW from a test run" if "test_data" in status.flags else "SOW or engagement"
    return "Closed Won deal"


def matches(status: ClientStatus, filters: Mapping[str, Any]) -> bool:
    """THE predicate the workspace rows, the drills and the export use."""
    rel = filters.get("relationship") or "all"
    if rel != "all" and status.relationship != rel:
        return False
    stage = filters.get("stage") or "any"
    if stage != "any" and status.stage_bucket != stage:
        return False
    units = filters.get("bu") or ()
    if units and not set(units) & {name for name, _region in status.business_units}:
        return False
    q = (filters.get("q") or "").strip().casefold()
    if q and q not in status.name.casefold():
        return False
    st = filters.get("status") or "any"
    states = (status.nda, status.msa)
    if st == "attention":
        return status.needs_attention
    if st == "missing_nda":
        return status.nda == "missing"
    if st == "missing_msa":
        return status.msa == "missing"
    if st == "has_standard":
        return "standard" in states
    if st == "has_client":
        return "client" in states
    if st == "marked_covered":
        return "covered" in states
    if st == "possible_duplicate":
        return "possible_duplicate" in status.flags
    return True


def stage_rank(status: ClientStatus) -> float:
    """For sorting: the furthest stage; a deal on Hold (stage unknown) ranks just above stage 1."""
    rank = float(status.furthest_open_stage)
    if (status.on_hold or status.unknown_stage) and rank < 1.5:
        rank = 1.5
    return rank


def sort_rows(rows: list[ClientStatus], sort: str) -> list[ClientStatus]:
    by_name = lambda s: (s.name.casefold(), str(s.client_id))  # noqa: E731
    if sort == "name":
        return sorted(rows, key=by_name)
    if sort == "stage":
        return sorted(rows, key=lambda s: (-stage_rank(s), *by_name(s)))
    return sorted(rows, key=lambda s: (not s.needs_attention, -stage_rank(s), *by_name(s)))


def cards(statuses: Sequence[ClientStatus]) -> list[dict[str, Any]]:
    """The six cards, computed over ALL clients. Each drill applied to the filters returns exactly ``value`` rows."""
    existing = [s for s in statuses if s.relationship == "existing"]
    net_new = [s for s in statuses if s.relationship == "net_new"]
    attention = [s for s in statuses if s.needs_attention]

    def holding(state: str) -> list[ClientStatus]:
        return [s for s in statuses if state in (s.nda, s.msa)]

    def by_kind(state: str, kind: str) -> int:
        return sum(1 for s in statuses if s.state(kind) == state)

    covered = holding("covered")
    closed_won = sum(1 for s in existing if s.relationship_basis in ("closed_won", "closed_won_and_sow"))
    with_sow = sum(1 for s in existing if s.relationship_basis in ("sow_engagement", "closed_won_and_sow"))
    client_note = f"clients · NDA {by_kind('client', 'NDA')} · MSA {by_kind('client', 'MSA')}"
    if covered:
        client_note += f" · {len(covered)} marked covered"
    return [
        {"key": "clients", "label": "Clients", "value": len(statuses),
         "note": f"{len(existing)} existing · {len(net_new)} net new", "drill": {}},
        {"key": "existing", "label": "Existing clients", "value": len(existing),
         "note": f"{closed_won} Closed Won · {with_sow} with an SOW or engagement",
         "drill": {"relationship": "existing"}},
        {"key": "net_new", "label": "Net-new clients", "value": len(net_new),
         "note": "Bring their own copy unless included", "drill": {"relationship": "net_new"}},
        {"key": "needs_attention", "label": "Needs attention", "value": len(attention),
         "note": "Net new, past stage 1, NDA or MSA missing", "drill": {"status": "attention"}},
        {"key": "standard_attached", "label": "Standard copies attached", "value": len(holding("standard")),
         "note": f"clients · NDA {by_kind('standard', 'NDA')} · MSA {by_kind('standard', 'MSA')}",
         "drill": {"status": "has_standard"}},
        {"key": "client_copies", "label": "Client copies on file", "value": len(holding("client")),
         "note": client_note, "drill": {"status": "has_client"}},
    ]


def stage_text(status: ClientStatus, labels: Mapping[int, str] | None = None) -> str:
    """"4 · Proposal", "On hold", "4 · Proposal (and on hold)" or "No active deal". Labels come from the stage
    mirror (pipeline_workspace.Reference) when given, so they match the Pipeline."""
    names = labels or STAGE_NAMES
    if status.furthest_open_stage:
        n = status.furthest_open_stage
        text = f"{n} · {names.get(n, STAGE_NAMES.get(n, ''))}".rstrip(" ·")
        return f"{text} (and on hold)" if status.on_hold else text
    if status.on_hold:
        return "On hold"
    return "Stage not recognised" if status.unknown_stage else "No active deal"


def business_unit_objects(status: ClientStatus) -> list[dict[str, str]]:
    return [{"name": u, "region": r} for u, r in status.business_units]


__all__ = [
    "BU_REGIONS", "CARD_KEYS", "ClientInput", "ClientStatus", "DOC_STATES", "DealInput", "DocInput", "KINDS",
    "PAGE_SIZES", "PLACEHOLDER_PREFIX", "RELATIONSHIP_FILTERS", "SORTS", "STAGE_FILTERS", "STAGE_NAMES",
    "STATE_LABELS", "STATUS_FILTERS", "basis_text", "business_unit_objects", "cards", "classify", "classify_all",
    "deal_summary", "doc_state", "duplicate_keys", "is_placeholder", "live_relationship", "matches",
    "normalise_name", "relationship_of", "requirement_of", "sort_rows", "source_label", "stage_text",
]


# =============================================================================================
# Query layer. Every reader (workspace, export, panel, batch dry run, Pipeline parity, Command
# Center tile) loads the population here. Visibility is the Pipeline's own: real users see every
# non-archived client except server-issued test fixtures; a test identity sees only its fixtures.
#
# Statements for the workspace (budget 8):
#   S1 fixture scope (scope_pipeline_filters)      S2-S3 stage mirror + region map (load_reference)
#   S4 clients with every per-client fact          S5 deals (pipeline_workspace.load_population)
#   S6 who created each client (test-data signal)  S7 header (cutover, latest batch, standards)
#   S8 agreement audit rows (Activity tab count; workspace only)
# =============================================================================================

from sqlalchemy import and_, case, func, literal, select  # noqa: E402
from sqlalchemy.orm import aliased  # noqa: E402

# Run tags, as the leak gate knows them (scripts/check-test-data-clean.sh; test_s24_ag1_run_tags_sync.py keeps the
# two in step): every "S<n>[letter] e2e " and "s1<n>-" tag, "smoke ", and two legacy fixture prefixes.
_RUN_TAG = re.compile(r"^(S\d+[a-z]? e2e |s1\d-|smoke |Peppermill Casino \(smoke fixture\)|S17 delete-everywhere)",
                      re.IGNORECASE)


@dataclass(frozen=True)
class DocDetail:
    """What the client holds for one kind, as stored: the agreement row and/or the active mark."""

    agreement_id: uuid.UUID | None = None
    source: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    version_no: int | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None
    note: str | None = None
    standard_version: int | None = None
    batch_label: str | None = None
    mark_id: uuid.UUID | None = None
    mark_reason: str | None = None
    mark_note: str | None = None
    mark_on: date | None = None
    mark_by: str | None = None
    mark_source: str | None = None
    mark_hubspot_value: str | None = None


@dataclass
class ClientFacts:
    input: ClientInput
    status: ClientStatus
    set_by: str | None
    set_at: datetime | None
    forecast: bool
    docs: dict[str, DocDetail]
    region_note: str | None


@dataclass
class StandardInfo:
    id: uuid.UUID
    kind: str
    version: int
    file_name: str
    file_size: int
    sha256: str
    uploaded_by: str
    uploaded_at: datetime
    file_key: str


@dataclass
class BatchInfo:
    id: uuid.UUID
    label: str
    status: str
    kinds: list[str]
    created_by: str
    created_at: datetime
    target_count: int
    done_count: int
    attached_count: int
    attached_clients: int
    skipped_count: int
    undone_count: int
    error: str | None
    undone_at: datetime | None
    undone_by: str | None
    # Standard attachments of this batch that an undo would remove now (rows still source 'standard'),
    # counted in the database over every client, so the undo dialog's number is the server's.
    undo_would_remove: int | None = None
    # An undo was started (undone_by is set when it starts): a failed batch then failed while undoing.
    undo_started: bool = False


@dataclass
class Population:
    scope: Any
    cutover: date | None
    cutover_set_at: datetime | None
    clients: dict[uuid.UUID, ClientFacts]
    standard: dict[str, StandardInfo | None]
    latest_batch: BatchInfo | None
    stage_labels: dict[int, str]
    # Rows of agreement_audit.feed_count_statement() (action, entity_id, after, before, actor groups) for the
    # Activity tab count; None unless loaded with with_activity=True.
    activity_rows: list[tuple[Any, ...]] | None = None

    @property
    def statuses(self) -> list[ClientStatus]:
        return [f.status for f in self.clients.values()]

    def duplicates_of(self, client_id: uuid.UUID) -> list[str]:
        facts = self.clients.get(client_id)
        if facts is None or "possible_duplicate" not in facts.status.flags:
            return []
        key = normalise_name(facts.input.name)
        return sorted((f.input.name for cid, f in self.clients.items()
                       if cid != client_id and "possible_duplicate" in f.status.flags
                       and normalise_name(f.input.name) == key), key=str.casefold)


def person(name: str | None, email: str | None, fallback: str = "Unknown user") -> str:
    """A display name for a real user; never an id. A name or email that is only a Cognito sub (a uuid, as
    access tokens carry) is skipped, as services.user_identity.display_user_name does."""
    from app.services.user_identity import display_user_name

    return display_user_name(name, email, fallback=fallback)


def iso_z(value: datetime | None) -> str | None:
    """UTC ISO timestamp with 'Z' (SQLite returns naive UTC values)."""
    if value is None:
        return None
    from datetime import UTC

    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def hint_subquery():
    """THE definition of a client's HubSpot msa_type hint: the value on its most recently modified live
    HubSpot deal that has one (row_number works on SQLite and Postgres)."""
    from app.models.opportunity import Opportunity

    ranked = (
        select(
            Opportunity.client_id.label("client_id"),
            Opportunity.hubspot_msa_type.label("value"),
            func.row_number().over(
                partition_by=Opportunity.client_id,
                order_by=(Opportunity.hubspot_last_modified_at.desc().nulls_last(), Opportunity.id.desc()),
            ).label("rn"),
        )
        .where(Opportunity.hubspot_msa_type.is_not(None), Opportunity.archived_at.is_(None),
               Opportunity.source == "hubspot", Opportunity.client_id.is_not(None))
        .subquery("msa_hint_ranked")
    )
    return select(ranked.c.client_id, ranked.c.value).where(ranked.c.rn == 1).subquery("msa_hint")


async def visibility_scope(session, actor):
    """S1: the Pipeline's fixture scope for this caller."""
    from app.services.hubspot_pipeline import PipelineFilters, scope_pipeline_filters

    return await scope_pipeline_filters(session, actor, PipelineFilters(include_closed=True, open_closed="any"))


def _client_facts_statement(scope):
    """S4: one row per visible client with every per-client fact (no fan-out: the unique indexes allow at
    most one agreement row and one active mark per client and kind; the work tables are grouped)."""
    from app.models.agreements import AgreementBatch, AgreementMark, StandardAgreement
    from app.models.client import Agreement, Client
    from app.models.engagement import Allocation, Engagement
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow
    from app.models.user import User
    from app.services.hubspot_pipeline import _client_visibility

    sow_opp = aliased(Opportunity, name="sow_opp")
    sow_work = (
        select(sow_opp.client_id.label("client_id"), func.min(Sow.created_at).label("first_at"),
               func.max(Sow.created_at).label("last_at"))
        .select_from(Sow).join(sow_opp, sow_opp.id == Sow.opportunity_id)
        .where(Sow.archived_at.is_(None), sow_opp.client_id.is_not(None))
        .group_by(sow_opp.client_id).subquery("sow_work")
    )
    eng_work = (
        select(Engagement.client_id.label("client_id"), func.min(Engagement.created_at).label("first_at"),
               func.max(Engagement.created_at).label("last_at"),
               *[func.max(case((Engagement.business_unit == unit, 1), else_=0)).label(f"bu_{i}")
                 for i, unit in enumerate(BU_ORDER)],
               func.max(case((Allocation.import_key.is_not(None), 1), else_=0)).label("forecast"))
        .select_from(Engagement).outerjoin(Allocation, Allocation.engagement_id == Engagement.id)
        .group_by(Engagement.client_id).subquery("eng_work")
    )
    hint = hint_subquery()
    set_by = aliased(User, name="set_by")
    cols: list[Any] = [
        Client.id.label("id"), Client.name.label("name"), Client.hubspot_company_id.label("company_id"),
        Client.created_at.label("created_at"), Client.relationship.label("relationship"),
        Client.relationship_basis.label("basis"), Client.relationship_set_at.label("set_at"),
        set_by.name.label("set_by_name"), set_by.email.label("set_by_email"),
        sow_work.c.first_at.label("sow_first"), sow_work.c.last_at.label("sow_last"),
        eng_work.c.first_at.label("eng_first"), eng_work.c.last_at.label("eng_last"),
        *[getattr(eng_work.c, f"bu_{i}").label(f"eng_bu_{i}") for i in range(len(BU_ORDER))],
        eng_work.c.forecast.label("forecast"), hint.c.value.label("msa_hint"),
    ]
    stmt_joins: list[tuple[Any, Any]] = [
        (set_by, set_by.id == Client.relationship_set_by),
        (sow_work, sow_work.c.client_id == Client.id),
        (eng_work, eng_work.c.client_id == Client.id),
        (hint, hint.c.client_id == Client.id),
    ]
    for kind in KINDS:
        k = kind.lower()
        agr = aliased(Agreement, name=f"{k}_agr")
        std = aliased(StandardAgreement, name=f"{k}_std")
        bat = aliased(AgreementBatch, name=f"{k}_batch")
        upl = aliased(User, name=f"{k}_uploader")
        mark = aliased(AgreementMark, name=f"{k}_mark")
        marker = aliased(User, name=f"{k}_marker")
        cols += [
            agr.id.label(f"{k}_id"), agr.source.label(f"{k}_source"), agr.filename.label(f"{k}_file"),
            agr.file_size.label(f"{k}_size"), agr.version_no.label(f"{k}_version"),
            agr.uploaded_at.label(f"{k}_at"), agr.note.label(f"{k}_note"), std.version_no.label(f"{k}_std_version"),
            bat.label.label(f"{k}_batch"), upl.name.label(f"{k}_by_name"), upl.email.label(f"{k}_by_email"),
            mark.id.label(f"{k}_mark_id"), mark.reason.label(f"{k}_mark_reason"), mark.note.label(f"{k}_mark_note"),
            mark.marked_on.label(f"{k}_mark_on"), mark.source.label(f"{k}_mark_source"),
            mark.hubspot_value.label(f"{k}_mark_value"), marker.name.label(f"{k}_marker_name"),
            marker.email.label(f"{k}_marker_email"),
        ]
        stmt_joins += [
            (agr, and_(agr.client_id == Client.id, agr.kind == kind)),
            (std, std.id == agr.standard_agreement_id),
            (bat, bat.id == agr.batch_id),
            (upl, upl.id == agr.uploaded_by),
            (mark, and_(mark.client_id == Client.id, mark.kind == kind, mark.removed_at.is_(None))),
            (marker, marker.id == mark.marked_by),
        ]
    stmt = select(*cols).select_from(Client)
    for target, onclause in stmt_joins:
        stmt = stmt.outerjoin(target, onclause)
    return stmt.where(*_client_visibility(scope)).order_by(Client.name, Client.id)


def _header_statement():
    """S7: exactly one row (an anchor row), even with no settings row, no batch and no standard copy."""
    from app.models.agreements import AgreementBatch, AgreementsSettings, StandardAgreement
    from app.models.user import User

    anchor = select(literal(1).label("one")).subquery("anchor")
    latest_id = (
        select(AgreementBatch.id).where(AgreementBatch.status != "undone")
        .order_by(AgreementBatch.created_at.desc(), AgreementBatch.id.desc()).limit(1).scalar_subquery()
    )
    from app.models.client import Agreement

    creator = aliased(User, name="batch_creator")
    undoer = aliased(User, name="batch_undoer")
    removable = aliased(Agreement, name="batch_removable")
    cols: list[Any] = [
        select(AgreementsSettings.cutover_date).where(AgreementsSettings.id == 1).scalar_subquery().label("cutover"),
        select(AgreementsSettings.set_at).where(AgreementsSettings.id == 1).scalar_subquery().label("cutover_set_at"),
        select(func.count()).select_from(removable)
        .where(removable.batch_id == latest_id, removable.source == "standard")
        .scalar_subquery().label("b_removable"),
        AgreementBatch.id.label("b_id"), AgreementBatch.label.label("b_label"), AgreementBatch.status.label("b_status"),
        AgreementBatch.kinds.label("b_kinds"), AgreementBatch.created_at.label("b_created_at"),
        AgreementBatch.target_count.label("b_target"), AgreementBatch.done_count.label("b_done"),
        AgreementBatch.attached_count.label("b_attached"), AgreementBatch.attached_clients.label("b_clients"),
        AgreementBatch.skipped_count.label("b_skipped"), AgreementBatch.undone_count.label("b_undone_count"),
        AgreementBatch.error.label("b_error"), AgreementBatch.undone_at.label("b_undone_at"),
        AgreementBatch.undone_by.label("b_undone_by"),
        creator.name.label("b_by_name"), creator.email.label("b_by_email"),
        undoer.name.label("b_undoer_name"), undoer.email.label("b_undoer_email"),
    ]
    stmt_joins: list[tuple[Any, Any]] = [
        (AgreementBatch, AgreementBatch.id == latest_id),
        (creator, creator.id == AgreementBatch.created_by),
        (undoer, undoer.id == AgreementBatch.undone_by),
    ]
    for kind in KINDS:
        k = kind.lower()
        std = aliased(StandardAgreement, name=f"{k}_current")
        upl = aliased(User, name=f"{k}_std_uploader")
        current = select(func.max(StandardAgreement.version_no)).where(StandardAgreement.kind == kind).scalar_subquery()
        cols += [std.id.label(f"{k}_id"), std.version_no.label(f"{k}_version"), std.filename.label(f"{k}_file"),
                 std.file_size.label(f"{k}_size"), std.sha256.label(f"{k}_sha"), std.uploaded_at.label(f"{k}_at"),
                 std.file_key.label(f"{k}_key"), upl.name.label(f"{k}_by_name"), upl.email.label(f"{k}_by_email")]
        stmt_joins += [(std, and_(std.kind == kind, std.version_no == current)), (upl, upl.id == std.uploaded_by)]
    stmt = select(*cols).select_from(anchor)
    for target, onclause in stmt_joins:
        stmt = stmt.outerjoin(target, onclause)
    return stmt


def standards_from_header(header: Mapping[str, Any]) -> dict[str, StandardInfo | None]:
    """The current standard copy of each kind from an S7 header row (None for a kind never uploaded)."""
    standard: dict[str, StandardInfo | None] = {}
    for kind in KINDS:
        k = kind.lower()
        if header[f"{k}_id"] is None:
            standard[kind] = None
            continue
        standard[kind] = StandardInfo(
            id=header[f"{k}_id"], kind=kind, version=header[f"{k}_version"], file_name=header[f"{k}_file"],
            file_size=header[f"{k}_size"], sha256=header[f"{k}_sha"],
            uploaded_by=person(header[f"{k}_by_name"], header[f"{k}_by_email"]), uploaded_at=header[f"{k}_at"],
            file_key=header[f"{k}_key"])
    return standard


async def load_standards(session) -> dict[str, StandardInfo | None]:
    """The current standard NDA and MSA (one statement: the S7 header)."""
    header = (await session.execute(_header_statement())).mappings().one()
    return standards_from_header(header)


def _deal_inputs(deal_facts) -> dict[uuid.UUID, list[tuple[DealInput, Any]]]:
    out: dict[uuid.UUID, list[tuple[DealInput, Any]]] = defaultdict(list)
    for fact in deal_facts:
        if fact.client_id is None:
            continue
        if fact.is_closed_won:
            status = "won"
        elif fact.is_closed_lost:
            status = "lost"
        elif fact.is_hold:
            status = "hold"
        else:
            status = "open"
        ordinal = fact.stage.ordinal if fact.stage is not None and not fact.stage.is_hold else None
        out[fact.client_id].append((DealInput(status=status, ordinal=ordinal, close_date=fact.close_date), fact))
    return out


def _engagement_units(reference) -> dict[str, str]:
    """The region each business unit maps to (from the region map), falling back to the BU's home region."""
    out = dict(BU_REGIONS)
    for entry in getattr(reference, "business_units", ()) or ():
        regions = list(entry.get("regions") or [])
        if len(regions) == 1:
            out[entry["business_unit"]] = regions[0]
    return out


async def load_agreement_population(
    session, actor, *, now: datetime | None = None, with_activity: bool = False, scope=None,
) -> Population:
    """Load and classify every client the caller may see. 7 statements (8 with the activity count)."""
    from app.models.audit import AuditEvent
    from app.models.user import User
    from app.services.business_time import business_today, la_date
    from app.services.canonical_user import Viewer
    from app.services.pipeline_workspace import load_population, load_reference
    from app.services.test_fixtures import E2E_USER_GROUP

    if scope is None:
        scope = await visibility_scope(session, actor)  # S1
    reference = await load_reference(session)  # S2-S3
    header = (await session.execute(_header_statement())).mappings().one()  # S7 (needed before classifying)
    cutover: date | None = header["cutover"]
    rows = (await session.execute(_client_facts_statement(scope))).mappings().all()  # S4
    deal_facts, _ = await load_population(  # S5
        session, scope, viewer=Viewer(None, None, None), reference=reference, today=business_today(now),
        with_sow=False)
    created = (await session.execute(  # S6
        select(AuditEvent.entity_id, User.groups).join(User, User.id == AuditEvent.actor_id)
        .where(AuditEvent.entity == "client", AuditEvent.action == "client.created")
    )).all()
    test_created: set[uuid.UUID] = set()
    for entity_id, groups in created:
        if E2E_USER_GROUP in (groups or []):
            try:
                test_created.add(uuid.UUID(str(entity_id)))
            except ValueError:
                continue
    authorized = set(getattr(scope, "authorized_client_ids", None) or ())
    deals_by_client = _deal_inputs(deal_facts)
    eng_regions = _engagement_units(reference)

    inputs: list[ClientInput] = []
    extra: dict[uuid.UUID, tuple[str | None, datetime | None, bool, dict[str, DocDetail], str | None]] = {}
    for row in rows:
        cid = row["id"]
        pairs: list[tuple[str, str]] = []
        unmapped: set[str] = set()
        client_deals = deals_by_client.get(cid, [])
        for _deal, fact in client_deals:
            if fact.region is not None:
                pairs.append((fact.region.business_unit, fact.region.region))
            elif fact.hubspot_region:
                unmapped.add(fact.hubspot_region)
        for i, unit in enumerate(BU_ORDER):
            if row[f"eng_bu_{i}"]:
                pairs.append((unit, eng_regions.get(unit, BU_REGIONS[unit])))
        docs_in: dict[str, DocInput] = {}
        details: dict[str, DocDetail] = {}
        for kind in KINDS:
            k = kind.lower()
            has_row = row[f"{k}_id"] is not None
            has_mark = row[f"{k}_mark_id"] is not None
            if has_row or has_mark:
                docs_in[kind] = DocInput(
                    source=row[f"{k}_source"] if has_row else None,
                    standard_version=row[f"{k}_std_version"], batch_label=row[f"{k}_batch"],
                    mark_source=row[f"{k}_mark_source"] if has_mark else None)
            details[kind] = DocDetail(
                agreement_id=row[f"{k}_id"], source=row[f"{k}_source"], file_name=row[f"{k}_file"],
                file_size=row[f"{k}_size"], version_no=row[f"{k}_version"],
                uploaded_by=person(row[f"{k}_by_name"], row[f"{k}_by_email"]) if has_row else None,
                uploaded_at=row[f"{k}_at"], note=row[f"{k}_note"], standard_version=row[f"{k}_std_version"],
                batch_label=row[f"{k}_batch"], mark_id=row[f"{k}_mark_id"], mark_reason=row[f"{k}_mark_reason"],
                mark_note=row[f"{k}_mark_note"], mark_on=row[f"{k}_mark_on"],
                mark_by=person(row[f"{k}_marker_name"], row[f"{k}_marker_email"]) if has_mark else None,
                mark_source=row[f"{k}_mark_source"], mark_hubspot_value=row[f"{k}_mark_value"])
        sow_dates = tuple(d for d in (la_date(row["sow_first"]), la_date(row["sow_last"])) if d is not None)
        eng_dates = tuple(d for d in (la_date(row["eng_first"]), la_date(row["eng_last"])) if d is not None)
        test_data = cid in authorized or cid in test_created or bool(_RUN_TAG.match(row["name"] or ""))
        inputs.append(ClientInput(
            id=cid, name=row["name"] or "", hubspot_company_id=row["company_id"], created_at=row["created_at"],
            stored_relationship=row["relationship"], stored_basis=row["basis"],
            deals=tuple(d for d, _ in client_deals), sow_dates=sow_dates, engagement_dates=eng_dates,
            docs=docs_in, business_units=tuple(pairs), test_data=test_data, hubspot_msa_type=row["msa_hint"]))
        region_note = None
        if not pairs and unmapped:
            region_note = "Region not mapped to a business unit: " + ", ".join(sorted(unmapped))
        extra[cid] = (
            person(row["set_by_name"], row["set_by_email"]) if row["set_by_name"] or row["set_by_email"] else None,
            row["set_at"], bool(row["forecast"]), details, region_note)

    keys = duplicate_keys(inputs)
    clients: dict[uuid.UUID, ClientFacts] = {}
    for item in inputs:
        set_by, set_at, forecast, details, region_note = extra[item.id]
        clients[item.id] = ClientFacts(input=item, status=classify(item, cutover, keys), set_by=set_by,
                                       set_at=set_at, forecast=forecast, docs=details, region_note=region_note)

    standard = standards_from_header(header)
    latest = None
    if header["b_id"] is not None:
        latest = BatchInfo(
            id=header["b_id"], label=header["b_label"], status=header["b_status"], kinds=list(header["b_kinds"] or []),
            created_by=person(header["b_by_name"], header["b_by_email"]), created_at=header["b_created_at"],
            target_count=header["b_target"], done_count=header["b_done"], attached_count=header["b_attached"],
            attached_clients=header["b_clients"], skipped_count=header["b_skipped"],
            undone_count=header["b_undone_count"], error=header["b_error"], undone_at=header["b_undone_at"],
            undone_by=person(header["b_undoer_name"], header["b_undoer_email"]) if header["b_undone_at"] else None,
            undo_would_remove=int(header["b_removable"] or 0), undo_started=header["b_undone_by"] is not None)
    labels = {info.ordinal: info.label for info in reference.stage_list if not info.is_hold}
    pop = Population(scope=scope, cutover=cutover, cutover_set_at=header["cutover_set_at"], clients=clients,
                     standard=standard, latest_batch=latest, stage_labels=labels)
    if with_activity:
        from app.services import agreement_audit

        pop.activity_rows = [tuple(row) for row in (  # S8
            await session.execute(agreement_audit.feed_count_statement())).all()]
    return pop


def visible_activity_count(pop: Population) -> int:
    """The Activity tab count: exactly the events GET /agreements/activity lists for this caller (the same
    visibility and the same folding, agreement_audit.visible_events)."""
    from app.services import agreement_audit

    return agreement_audit.count_visible(pop.activity_rows or [], scope=pop.scope)


# --- wire shapes -----------------------------------------------------------------------------


def client_row(pop: Population, facts: ClientFacts) -> dict[str, Any]:
    s = facts.status
    return {
        "client_id": str(s.client_id), "name": s.name, "relationship": s.relationship,
        "relationship_basis": s.relationship_basis, "requirement": s.requirement,
        "nda": {"state": s.nda, "source_label": s.nda_label}, "msa": {"state": s.msa, "source_label": s.msa_label},
        "needs_attention": s.needs_attention, "furthest_open_stage": s.furthest_open_stage,
        "business_units": business_unit_objects(s), "deal_count": s.deal_count, "flags": list(s.flags),
        # additive
        "provisional": s.provisional, "on_hold": s.on_hold,
        "stage_text": stage_text(s, pop.stage_labels),
        "basis_text": basis_text(s, forecast=facts.forecast, set_by=facts.set_by),
        # Why business_units is empty (never an invented unit); null whenever a unit is known.
        "business_unit_note": business_unit_reason(facts),
    }


def business_unit_reason(facts: ClientFacts) -> str | None:
    """The reason a client shows no business unit, or None when it has one. A missing value shows its reason."""
    if facts.status.business_units:
        return None
    if facts.region_note:
        return facts.region_note
    if facts.status.deal_count or facts.input.engagement_dates or facts.input.sow_dates:
        return "No business unit on its deals or engagements"
    return "No deals or engagements yet"


def business_unit_text(facts: ClientFacts) -> str:
    """Business units with their regions, as the export writes them: "ST21 · US; IT Avalon · US"."""
    units = facts.status.business_units
    if units:
        return "; ".join(f"{unit} · {region}" for unit, region in units)
    return business_unit_reason(facts) or ""


def standard_version_payload(info: StandardInfo, attached_clients: int) -> dict[str, Any]:
    """The contract's StandardVersion."""
    return {"kind": info.kind, "version": info.version, "file_name": info.file_name, "file_size": info.file_size,
            "sha256": info.sha256, "uploaded_by": info.uploaded_by, "uploaded_at": iso_z(info.uploaded_at),
            "attached_clients": attached_clients}


def standard_payload(pop: Population) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in KINDS:
        info = pop.standard.get(kind)
        if info is None:
            out[kind] = None
            continue
        attached = sum(1 for f in pop.clients.values()
                       if f.docs[kind].source == "standard" and f.docs[kind].standard_version == info.version)
        out[kind] = standard_version_payload(info, attached)
    return out


def batch_payload(info: BatchInfo | None) -> dict[str, Any] | None:
    if info is None:
        return None
    return {"id": info.label, "status": info.status, "kinds": info.kinds, "created_by": info.created_by,
            "created_at": iso_z(info.created_at), "target_count": info.target_count, "done_count": info.done_count,
            "attached_count": info.attached_count, "skipped_count": info.skipped_count, "error": info.error,
            "undone_at": iso_z(info.undone_at), "undone_by": info.undone_by,
            # additive
            "attached_clients": info.attached_clients, "undone_count": info.undone_count,
            "undo_would_remove": info.undo_would_remove,
            # Which job stopped, for a failed batch: the attach run or its undo (None otherwise).
            "failed_phase": ("undo" if info.undo_started else "run") if info.status == "failed" else None}


def filtered(pop: Population, filters: Mapping[str, Any]) -> list[ClientStatus]:
    return sort_rows([s for s in pop.statuses if matches(s, filters)], filters.get("sort") or "attention")


def document_count(pop: Population) -> int:
    return sum(1 for f in pop.clients.values() for k in KINDS if f.docs[k].source in ("client", "standard"))


def workspace_payload(pop: Population, filters: Mapping[str, Any], *, page: int, page_size: int,
                      can_write: bool, is_admin: bool) -> dict[str, Any]:
    rows = filtered(pop, filters)
    start = (page - 1) * page_size
    return {
        "cutover": {"set": pop.cutover is not None, "date": pop.cutover.isoformat() if pop.cutover else None,
                    "latest_batch": batch_payload(pop.latest_batch)},
        "cards": cards(pop.statuses),
        "standard": standard_payload(pop),
        "total": len(rows),
        "items": [client_row(pop, pop.clients[s.client_id]) for s in rows[start:start + page_size]],
        # additive
        "can_write": can_write, "is_admin": is_admin,
        "document_count": document_count(pop),
        "activity_count": visible_activity_count(pop) if pop.activity_rows is not None else None,
    }


async def needs_attention_count(session, actor, *, scope=None, now: datetime | None = None) -> int:
    """For the Command Center tile and the Pipeline parity check."""
    pop = await load_agreement_population(session, actor, now=now, scope=scope)
    return sum(1 for s in pop.statuses if s.needs_attention)


# --- export, documents (S24-AG1 B3) ----------------------------------------------------------------

EXPORT_HEADER: tuple[str, ...] = (
    "Client", "Business unit", "Relationship", "Relationship basis", "Furthest open stage", "NDA", "MSA",
    "Needs attention", "Possible duplicate",
)
EXPORT_FILE_NAME = "DealGate_Agreements.csv"


def export_rows(pop: Population, filters: Mapping[str, Any]) -> list[list[str]]:
    """Every row of the filtered client view (no paging), in the workspace's order, in the contract's column
    order, every cell neutralised against spreadsheet formulas (csv_safety)."""
    from app.services.csv_safety import safe_row

    out: list[list[str]] = []
    for status in filtered(pop, filters):
        facts = pop.clients[status.client_id]
        out.append(safe_row([
            status.name,
            business_unit_text(facts),
            "Existing" if status.relationship == "existing" else "Net new",
            basis_text(status, forecast=facts.forecast, set_by=facts.set_by),
            stage_text(status, pop.stage_labels),
            STATE_LABELS[status.nda],
            STATE_LABELS[status.msa],
            "Yes" if status.needs_attention else "No",
            "Yes" if "possible_duplicate" in status.flags else "No",
        ]))
    return out


async def visible_client_ids(session, scope) -> set[uuid.UUID]:
    """Clients the caller can open (non-archived, the Pipeline's fixture visibility). One statement."""
    from app.models.client import Client
    from app.services.hubspot_pipeline import _client_visibility

    return set((await session.scalars(select(Client.id).where(*_client_visibility(scope)))).all())


async def load_documents(session, actor, *, scope=None) -> list[dict[str, Any]]:
    """The Documents tab: one row per stored document (an agreement row of source client or standard) on a
    client the caller can see, ordered by client name then kind as the prototype lists them. Two statements
    (the fixture scope, then the rows); the total equals the workspace's ``document_count``."""
    from app.models.agreements import AgreementBatch, StandardAgreement
    from app.models.client import Agreement, Client
    from app.models.user import User
    from app.services.hubspot_pipeline import _client_visibility

    if scope is None:
        scope = await visibility_scope(session, actor)
    std = aliased(StandardAgreement, name="doc_standard")
    bat = aliased(AgreementBatch, name="doc_batch")
    upl = aliased(User, name="doc_uploader")
    stmt = (
        select(Agreement.id.label("id"), Agreement.client_id.label("client_id"), Client.name.label("client_name"),
               Agreement.kind.label("kind"), Agreement.filename.label("file_name"),
               Agreement.file_size.label("file_size"), Agreement.source.label("source"),
               Agreement.version_no.label("version_no"), Agreement.note.label("note"),
               Agreement.uploaded_at.label("uploaded_at"), std.version_no.label("standard_version"),
               bat.label.label("batch_label"), upl.name.label("by_name"), upl.email.label("by_email"))
        .select_from(Agreement)
        .join(Client, Client.id == Agreement.client_id)
        .outerjoin(std, std.id == Agreement.standard_agreement_id)
        .outerjoin(bat, bat.id == Agreement.batch_id)
        .outerjoin(upl, upl.id == Agreement.uploaded_by)
        .where(Agreement.source.in_(("client", "standard")), *_client_visibility(scope))
    )
    docs = [{
        "client_id": str(row["client_id"]), "client_name": row["client_name"] or "", "kind": row["kind"],
        "file_name": row["file_name"], "source": row["source"],
        "standard_version": row["standard_version"] if row["source"] == "standard" else None,
        "batch_id": row["batch_label"] if row["source"] == "standard" else None,
        "uploaded_by": person(row["by_name"], row["by_email"]), "uploaded_at": iso_z(row["uploaded_at"]),
        # additive: the row for history and replace, and the version's size and note
        "agreement_id": str(row["id"]), "version_no": row["version_no"], "file_size": row["file_size"],
        "note": row["note"] if row["source"] == "client" else None,
    } for row in (await session.execute(stmt)).mappings().all()]
    docs.sort(key=lambda d: (d["client_name"].casefold(), d["kind"], d["client_id"]))
    return docs


def documents_page(rows: Sequence[Mapping[str, Any]], *, q: str | None = None, kind: str | None = None,
                   source: str | None = None, page: int = 1, page_size: int = 25) -> tuple[int, list[Any]]:
    """Filter and page the Documents tab. Search covers client name, kind, file name and uploader."""
    needle = (q or "").strip().casefold()
    matching = [
        d for d in rows
        if (kind is None or d["kind"] == kind) and (source is None or d["source"] == source)
        and (not needle or any(needle in str(d[field] or "").casefold()
                               for field in ("client_name", "kind", "file_name", "uploaded_by")))
    ]
    start = (page - 1) * page_size
    return len(matching), list(matching[start:start + page_size])
