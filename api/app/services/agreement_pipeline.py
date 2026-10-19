"""S24-AG1 B10 — the Pipeline and the Command Center on the shared agreement status service.

The Pipeline shows each client's NDA and MSA *state* (``client``, ``standard``,
``covered``, ``missing``, ``due_later``, ``not_needed``, ``existing_none``) and
counts the clients that need attention, exactly as the Agreements page does. It
must not add a statement to the PL2 workspace (test_s23_pl2_cost.py pins
7 / 7 / 7 / 8), so the per-client facts the rules need are ONE derived table,
:func:`facts_subquery`, LEFT JOINed once into the statements the workspace
already runs (the deal population and the visible clients), with the cutover as
a scalar column. Classification then goes through
:func:`app.services.agreement_status.classify` — the one place that decides
relationship, requirement, state and "needs attention" — fed with the same deal
set the Agreements page uses (the Pipeline's own population, all statuses).

The facts match the Agreements page's loader (``agreement_status``, S4):
stored relationship and basis; the first and last live SOW (not archived, on
any deal of the client) and engagement creation dates as America/Los_Angeles
calendar dates; and per kind the agreement row's source and standard version
and the active mark's source. ``tests/test_s24_ag1_bec_pipeline.py`` holds the
two in step: the Pipeline's gap card equals the Agreements page's
Needs-attention card on the same database, and every row's state equals the
Agreements page's state for that client.

The Command Center tile counts every client the caller may see
(:func:`attention_clients`): the Agreements page has no owner filter and its
business units come from deals and engagements, so the Command Center's own
business-unit and owner filters do not apply to it.
"""

from __future__ import annotations

import functools
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from app.models.agreements import AgreementMark, AgreementsSettings, StandardAgreement
from app.models.client import Agreement, Client
from app.models.engagement import Engagement
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.services import agreement_status
from app.services.agreement_status import KINDS, ClientInput, ClientStatus, DocInput
from app.services.business_time import la_date
from app.services.hubspot_pipeline import PipelineFilters

# A file is on file when the client holds its own copy or a standard copy (a mark holds no file).
ON_FILE_STATES: frozenset[str] = frozenset({"client", "standard"})
# The workspace's ``missing`` values that are agreement states (the others are deal fields).
AGREEMENT_MISSING: frozenset[str] = frozenset({"nda", "msa", "agreements"})
# Facts columns are labelled with this prefix in the statements they are folded into.
PREFIX = "ag_"
_FACT_KEYS: tuple[str, ...] = (
    "client_id", "relationship", "basis", "sow_first", "sow_last", "eng_first", "eng_last",
    *(f"{kind.lower()}_{part}" for kind in KINDS for part in ("source", "std_version", "mark_source")),
)


@dataclass(frozen=True)
class ClientAgreementFacts:
    """What the rules need about one client besides its deals (read from one joined row)."""

    relationship: str | None
    basis: str | None
    sow_dates: tuple[date, ...]
    engagement_dates: tuple[date, ...]
    docs: Mapping[str, DocInput] = field(default_factory=dict)
    cutover: date | None = None


@functools.lru_cache(maxsize=1)
def facts_subquery():
    """One row per client: everything :func:`agreement_status.classify` needs except the deals.

    No fan-out: ``ux_agreement_client_kind`` and ``ux_agreement_mark_active`` allow at most one
    agreement row and one active mark per client and kind, and the SOW and engagement dates are
    grouped by client. Aliased throughout so nothing correlates with the statement it is joined into.
    It takes no parameters, so it is built once per process (building the aliases costs about as much
    as the whole workspace query); SQL elements are immutable, so every statement can embed it, and
    the compiled statement is cached.
    """
    client = aliased(Client, name="ag_client")
    sow_opp = aliased(Opportunity, name="ag_sow_opp")
    sow_work = (
        select(sow_opp.client_id.label("client_id"), func.min(Sow.created_at).label("first_at"),
               func.max(Sow.created_at).label("last_at"))
        .select_from(Sow).join(sow_opp, sow_opp.id == Sow.opportunity_id)
        .where(Sow.archived_at.is_(None), sow_opp.client_id.is_not(None))
        .group_by(sow_opp.client_id).subquery("ag_sow_work")
    )
    eng_work = (
        select(Engagement.client_id.label("client_id"), func.min(Engagement.created_at).label("first_at"),
               func.max(Engagement.created_at).label("last_at"))
        .group_by(Engagement.client_id).subquery("ag_eng_work")
    )
    columns: list[Any] = [
        client.id.label("client_id"), client.relationship.label("relationship"),
        client.relationship_basis.label("basis"),
        sow_work.c.first_at.label("sow_first"), sow_work.c.last_at.label("sow_last"),
        eng_work.c.first_at.label("eng_first"), eng_work.c.last_at.label("eng_last"),
    ]
    joins: list[tuple[Any, Any]] = [
        (sow_work, sow_work.c.client_id == client.id),
        (eng_work, eng_work.c.client_id == client.id),
    ]
    for kind in KINDS:
        k = kind.lower()
        agreement = aliased(Agreement, name=f"ag_{k}_agreement")
        standard = aliased(StandardAgreement, name=f"ag_{k}_standard")
        mark = aliased(AgreementMark, name=f"ag_{k}_mark")
        columns += [agreement.source.label(f"{k}_source"), standard.version_no.label(f"{k}_std_version"),
                    mark.source.label(f"{k}_mark_source")]
        joins += [
            (agreement, and_(agreement.client_id == client.id, agreement.kind == kind)),
            (standard, standard.id == agreement.standard_agreement_id),
            (mark, and_(mark.client_id == client.id, mark.kind == kind, mark.removed_at.is_(None))),
        ]
    stmt = select(*columns).select_from(client)
    for target, onclause in joins:
        stmt = stmt.outerjoin(target, onclause)
    return stmt.subquery("agreement_facts")


def cutover_column():
    """The cutover date as a scalar column (NULL before the first real batch, or with no settings row)."""
    return select(AgreementsSettings.cutover_date).where(AgreementsSettings.id == 1).scalar_subquery()


@functools.lru_cache(maxsize=2)
def _fact_columns(facts) -> tuple[Any, ...]:
    return (*(facts.c[key].label(PREFIX + key) for key in _FACT_KEYS), cutover_column().label(PREFIX + "cutover"))


def fact_columns(facts) -> list[Any]:
    """The facts and the cutover, labelled ``ag_*``, for the statement ``facts`` is joined into."""
    return list(_fact_columns(facts))


def _dates(*values: datetime | None) -> tuple[date, ...]:
    return tuple(d for d in (la_date(value) for value in values) if d is not None)


def facts_from_row(row: Mapping[str, Any]) -> ClientAgreementFacts | None:
    """The client's facts from a row carrying :func:`fact_columns`; None for a deal with no client."""
    if row[PREFIX + "client_id"] is None:
        return None
    docs: dict[str, DocInput] = {}
    for kind in KINDS:
        k = kind.lower()
        source, mark = row[f"{PREFIX}{k}_source"], row[f"{PREFIX}{k}_mark_source"]
        if source is not None or mark is not None:
            docs[kind] = DocInput(source=source, standard_version=row[f"{PREFIX}{k}_std_version"],
                                  mark_source=mark)
    return ClientAgreementFacts(
        relationship=row[PREFIX + "relationship"], basis=row[PREFIX + "basis"],
        sow_dates=_dates(row[PREFIX + "sow_first"], row[PREFIX + "sow_last"]),
        engagement_dates=_dates(row[PREFIX + "eng_first"], row[PREFIX + "eng_last"]),
        docs=docs, cutover=row[PREFIX + "cutover"],
    )


def classify_clients(deals: Iterable[Any], clients: Iterable[Any] = ()) -> dict[uuid.UUID, ClientStatus]:
    """``{client id: status}`` for every client in the population (and every extra client given).

    ``deals`` are Pipeline deal facts carrying ``agreement_facts``; ``clients`` are client facts
    (clients without matching deals) carrying the same. Each client is classified once, with ALL of
    its deals in the population, by the shared service.
    """
    deals = list(deals)
    by_client = agreement_status._deal_inputs(deals)  # the Agreements page's own deal mapping
    inputs: dict[uuid.UUID, tuple[ClientInput, date | None]] = {}

    def add(client_id, name, company_id, facts: ClientAgreementFacts | None) -> None:
        if client_id is None or facts is None or client_id in inputs:
            return
        inputs[client_id] = (ClientInput(
            id=client_id, name=name or "", hubspot_company_id=company_id,
            stored_relationship=facts.relationship, stored_basis=facts.basis,
            deals=tuple(deal for deal, _fact in by_client.get(client_id, ())),
            sow_dates=facts.sow_dates, engagement_dates=facts.engagement_dates, docs=facts.docs,
        ), facts.cutover)

    for deal in deals:
        add(deal.client_id, deal.client_name, deal.client_hubspot_company_id, deal.agreement_facts)
    for client in clients:
        add(client.id, client.name, client.hubspot_company_id, client.agreement_facts)
    return {client_id: agreement_status.classify(item, cutover) for client_id, (item, cutover) in inputs.items()}


def agreement_missing(nda_state: str | None, msa_state: str | None, attention: bool, missing: str) -> bool:
    """The workspace's ``missing`` filter on agreement states: nda / msa = that kind's state is
    ``missing``; agreements = the client needs attention (net new, past stage 1, either missing).
    A deal with no client has no state and never matches."""
    if missing == "nda":
        return nda_state == "missing"
    if missing == "msa":
        return msa_state == "missing"
    return attention


def agreement_scope(scope: PipelineFilters) -> PipelineFilters:
    """The caller's client and deal visibility only (fixture scoping), every other filter dropped:
    the scope the Agreements page itself uses (``agreement_status.visibility_scope``)."""
    return PipelineFilters(
        include_closed=True, open_closed="any",
        authorized_client_ids=scope.authorized_client_ids, hidden_client_ids=scope.hidden_client_ids,
        authorized_opportunity_ids=scope.authorized_opportunity_ids,
        authorized_fixture_opportunity_ids=scope.authorized_fixture_opportunity_ids,
    )


def needs_attention_href() -> str:
    """The Agreements page filtered to Needs attention: that card's own drill."""
    drill = next(card["drill"] for card in agreement_status.cards([]) if card["key"] == "needs_attention")
    return "/agreements?" + urlencode(drill, doseq=True)


async def attention_clients(session, scope: PipelineFilters, *, now: datetime | None = None) -> int:
    """Net-new clients past stage 1 without an NDA or MSA, over every client the caller may see
    (the Agreements page's Needs-attention card, same service, same scope)."""
    return await agreement_status.needs_attention_count(session, None, scope=agreement_scope(scope), now=now)


__all__ = [
    "AGREEMENT_MISSING", "ON_FILE_STATES", "PREFIX", "ClientAgreementFacts", "agreement_missing",
    "agreement_scope", "attention_clients", "classify_clients", "cutover_column", "fact_columns",
    "facts_from_row", "facts_subquery", "needs_attention_href",
]
