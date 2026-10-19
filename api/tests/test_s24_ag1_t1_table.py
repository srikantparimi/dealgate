"""S24-AG1 T1 (lane T-C) — table-driven completeness: relationship x requirement x NDA/MSA state.

ONE parametrised table, ``TABLE``, names every row (its pytest id). It holds:

* the grid: every reachable (relationship, requirement, NDA state, MSA state) cell, once judged live before
  the cutover and once from a stored relationship after it (2 x 64 rows);
* the directive's cases, each named: a net-new client's first Closed Won deal after the cutover stays net
  new and stays flagged; a client created after the cutover whose company has an earlier win starts
  existing; Hold counts as open and past stage 1; stage 1 only; an unknown stage; a manual override (beats
  every rule, before and after the cutover); test data; possible_duplicate normalisation (llc, inc, ltd,
  corp, co, company; dots and apostrophes; placeholders excluded); undated wins count as on or before the
  cutover.

The expectations come from the directive and the contract (components Cutover, Relationship, Requirement,
DocState) and the decided deviations in docs/bugs/s24-ag1.md (#2 Hold, #3 unknown stage, #4 duplicate
names, #5 undated wins), never from the implementation. Completeness is checked three ways: the table
covers every reachable cell; an exhaustive sweep of 23,520 inputs never leaves the reachable cells and
agrees with an oracle written from the contract text; every directive case is a named row. The cutover
stamp rule (what the first real batch stores) has its own named table.

Pure: app.services.agreement_status is called directly; the loader that builds ClientInput from the
database is tested in test_s24_ag1_loader.py.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

import pytest

from app.services.agreement_status import (
    ClientInput,
    DealInput,
    DocInput,
    cards,
    classify,
    duplicate_keys,
    live_relationship,
    matches,
    stage_text,
)

CUTOVER = date(2026, 10, 1)
BEFORE = CUTOVER - timedelta(days=45)
AFTER = CUTOVER + timedelta(days=12)
DAY_AFTER = CUTOVER + timedelta(days=1)

# --- the contract's cells (written from DocState and Requirement, not from the code) -----------------

HELD = ("client", "standard", "covered")
# What a client holding nothing shows, by (relationship, requirement). Existing clients have requirement none.
NOTHING_HELD: dict[tuple[str, str], str] = {
    ("existing", "none"): "existing_none",
    ("net_new", "required"): "missing",
    ("net_new", "later"): "due_later",
    ("net_new", "none"): "not_needed",
}
REACHABLE: frozenset[tuple[str, str, str, str]] = frozenset(
    (rel, req, nda, msa)
    for (rel, req), empty in NOTHING_HELD.items()
    for nda in (*HELD, empty)
    for msa in (*HELD, empty)
)

# --- inputs ------------------------------------------------------------------------------------------------


def won(close: date | None = BEFORE) -> DealInput:
    return DealInput("won", close_date=close)


def at(stage: int) -> DealInput:
    return DealInput("open", stage)


HOLD = DealInput("hold")
LOST = DealInput("lost", close_date=BEFORE)
UNKNOWN = DealInput("open", None)  # an open deal in a stage the mirror no longer has (#3)
OWN = DocInput(source="client")
STD = DocInput(source="standard", standard_version=1, batch_label="AG-0001")
STD_V2 = DocInput(source="standard", standard_version=2, batch_label="AG-0002")
MARK = DocInput(mark_source="dealgate")
HS_MARK = DocInput(mark_source="hubspot")


def client(name: str = "Arvella Foods", *, company: str | None = "co-1", stored: str | None = None,
           basis: str | None = None, deals=(), sows=(), engagements=(), docs=None,
           test_data: bool = False) -> ClientInput:
    return ClientInput(
        id=uuid.uuid4(), name=name, hubspot_company_id=company, stored_relationship=stored,
        stored_basis=basis, deals=tuple(deals), sow_dates=tuple(sows), engagement_dates=tuple(engagements),
        docs=dict(docs or {}), test_data=test_data)


@dataclass(frozen=True)
class Expect:
    relationship: str
    basis: str
    requirement: str
    nda: str
    msa: str
    attention: bool
    # Optional columns: None means the row does not assert it (the spec is silent for that row).
    provisional: bool | None = None
    bucket: str | None = None  # the stage filter's bucket: past_stage_1 | stage_1_only | no_active_deal
    furthest: int | None = None
    open: int | None = None  # open deals, Hold included
    on_hold: bool | None = None
    stage: str | None = None  # stage_text
    flags: tuple[str, ...] | None = None
    labels: tuple[str | None, str | None] | None = None  # (NDA, MSA) source labels


@dataclass(frozen=True)
class Row:
    id: str
    item: ClientInput
    cutover: date | None
    expect: Expect
    others: tuple[ClientInput, ...] = field(default=())  # the rest of the population (duplicate names)

    @property
    def cell(self) -> tuple[str, str, str, str]:
        e = self.expect
        return e.relationship, e.requirement, e.nda, e.msa


def needs(rel: str, req: str, nda: str, msa: str) -> bool:
    """Needs attention = net new, requirement required, and either kind missing (the directive)."""
    return rel == "net_new" and req == "required" and "missing" in (nda, msa)


# --- the grid: every reachable cell, before (live) and after (stored) the cutover --------------------------

# (relationship, requirement) -> inputs that produce it, per phase.
_GRID_BASE: dict[tuple[str, str], dict[str, dict]] = {
    ("existing", "none"): {
        "before": {"deals": (won(),)},
        "after": {"stored": "existing", "basis": "closed_won", "deals": (won(),)},
    },
    ("net_new", "required"): {
        "before": {"deals": (at(3),)},
        "after": {"stored": "net_new", "basis": "none", "deals": (at(4),)},
    },
    ("net_new", "later"): {
        "before": {"deals": (at(1),)},
        "after": {"stored": "net_new", "basis": "none", "deals": (at(1),)},
    },
    ("net_new", "none"): {
        "before": {"deals": (LOST,)},
        "after": {"stored": "net_new", "basis": "none"},
    },
}
# What the client holds per kind for each target state (a DealGate mark on the NDA, a HubSpot mark on the MSA).
_HOLDINGS = {"NDA": {"client": OWN, "standard": STD, "covered": MARK},
             "MSA": {"client": OWN, "standard": STD_V2, "covered": HS_MARK}}
_LABELS = {"NDA": {"client": "Client copy", "standard": "Standard v1", "covered": "Marked covered"},
           "MSA": {"client": "Client copy", "standard": "Standard v2", "covered": "Marked by HubSpot"}}


def _grid() -> list[Row]:
    rows: list[Row] = []
    for phase in ("before", "after"):
        for (rel, req), empty in NOTHING_HELD.items():
            for nda in (*HELD, empty):
                for msa in (*HELD, empty):
                    docs = {kind: _HOLDINGS[kind][state] for kind, state in (("NDA", nda), ("MSA", msa))
                            if state in HELD}
                    item = client(f"Grid {phase} {rel} {req} {nda} {msa}", docs=docs, **_GRID_BASE[(rel, req)][phase])
                    rows.append(Row(
                        id=f"grid {phase}: {rel}/{req}, NDA={nda}, MSA={msa}",
                        item=item, cutover=None if phase == "before" else CUTOVER,
                        expect=Expect(
                            rel, "closed_won" if rel == "existing" else "none", req, nda, msa,
                            needs(rel, req, nda, msa), provisional=phase == "before",
                            labels=(_LABELS["NDA"].get(nda), _LABELS["MSA"].get(msa)))))
    return rows


# --- the directive's cases, each named ------------------------------------------------------------------

E_NONE = ("existing_none", "existing_none")
MISSING = ("missing", "missing")


def _cases() -> list[Row]:
    r: list[Row] = []

    def add(row_id: str, item: ClientInput, cutover: date | None, expect: Expect, others=()) -> None:
        r.append(Row(row_id, item, cutover, expect, tuple(others)))

    net_new = {"stored": "net_new", "basis": "none"}

    # A net-new client's first Closed Won deal after the cutover stays net new and stays flagged (Cutover).
    add("cutover: before it is set, a Closed Won deal makes a client existing (live, provisional)",
        client(deals=(won(AFTER),)), None,
        Expect("existing", "closed_won", "none", *E_NONE, False, provisional=True))
    add("cutover: a net-new client's first Closed Won deal after the cutover stays net new and stays flagged",
        client(deals=(won(AFTER),), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, provisional=False))
    add("cutover: first win after the cutover after an earlier lost deal stays net new and flagged",
        client(deals=(LOST, won(AFTER)), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, provisional=False))
    add("cutover: first win after the cutover keeps its warning while only the NDA client copy is attached",
        client(deals=(won(AFTER),), docs={"NDA": OWN}, **net_new), CUTOVER,
        Expect("net_new", "none", "required", "client", "missing", True, labels=("Client copy", None)))
    add("cutover: first win after the cutover, both client copies attached, clears the warning",
        client(deals=(won(AFTER),), docs={"NDA": OWN, "MSA": OWN}, **net_new), CUTOVER,
        Expect("net_new", "none", "required", "client", "client", False))
    add("cutover: first win after the cutover, both marked covered, clears the warning",
        client(deals=(won(AFTER),), docs={"NDA": MARK, "MSA": MARK}, **net_new), CUTOVER,
        Expect("net_new", "none", "required", "covered", "covered", False))
    add("cutover: a net-new pipeline client given the standard copies stays net new, not flagged",
        client(deals=(at(3),), docs={"NDA": STD, "MSA": STD}, **net_new), CUTOVER,
        Expect("net_new", "none", "required", "standard", "standard", False, labels=("Standard v1", "Standard v1")))
    add("cutover: an unstamped client whose only win is after the cutover starts net new and flagged",
        client(deals=(won(AFTER),)), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, provisional=False))
    add("cutover: an unstamped client whose company won the day after the cutover starts net new",
        client(deals=(won(DAY_AFTER),)), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, provisional=False))
    # A client created after the cutover whose company has an earlier win starts existing (B8, Cutover).
    add("cutover: a client created after the cutover whose company has an earlier win starts existing",
        client(deals=(won(BEFORE),)), CUTOVER,
        Expect("existing", "closed_won", "none", *E_NONE, False, provisional=False))
    add("cutover: a client created after the cutover whose company won on the cutover day starts existing",
        client(deals=(won(CUTOVER),)), CUTOVER,
        Expect("existing", "closed_won", "none", *E_NONE, False, provisional=False))
    add("cutover: created after the cutover with an earlier win and an open stage 4 deal is never flagged",
        client(deals=(won(BEFORE), at(4)), docs={"MSA": OWN}), CUTOVER,
        Expect("existing", "closed_won", "none", "existing_none", "client", False))
    add("cutover: a client created after the cutover by SOW studio is net new and its SOW makes it required",
        client(company=None, sows=(AFTER,), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, flags=("no_hubspot_link",)))
    add("cutover: an engagement created after the cutover makes a net-new client required",
        client(engagements=(AFTER,), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True))
    add("cutover: an engagement created on the cutover day is not after it",
        client(engagements=(CUTOVER,), **net_new), CUTOVER,
        Expect("net_new", "none", "none", "not_needed", "not_needed", False))
    add("cutover: a stamped existing client with no evidence left stays existing",
        client(stored="existing", basis="sow_engagement"), CUTOVER,
        Expect("existing", "sow_engagement", "none", *E_NONE, False, provisional=False))
    add("cutover: a stamped existing client with an open stage 3 deal is never flagged",
        client(stored="existing", basis="closed_won", deals=(at(3),)), CUTOVER,
        Expect("existing", "closed_won", "none", *E_NONE, False))

    # Hold counts as open and past stage 1 (#2): furthest_open_stage reports 1-6 only, on_hold says it.
    add("hold: a deal on Hold counts as open and past stage 1",
        client(deals=(HOLD,)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", furthest=0, open=1, on_hold=True,
               stage="On hold"))
    add("hold: Hold plus a stage 1 deal is past stage 1",
        client(deals=(at(1), HOLD)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", furthest=1, open=2, on_hold=True,
               stage="1 · Prospecting (and on hold)"))
    add("hold: Hold plus a stage 4 deal keeps the furthest stage and says on hold",
        client(deals=(at(4), HOLD)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", furthest=4, on_hold=True,
               stage="4 · Proposal (and on hold)"))
    add("hold: Hold with a lost deal is still required",
        client(deals=(HOLD, LOST)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", open=1))
    add("hold: after the cutover a stamped net-new client on Hold is required and flagged",
        client(deals=(HOLD,), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", on_hold=True))
    add("hold: a client on Hold holding both standard copies is not flagged",
        client(deals=(HOLD,), docs={"NDA": STD, "MSA": STD}, **net_new), CUTOVER,
        Expect("net_new", "none", "required", "standard", "standard", False, bucket="past_stage_1"))
    add("hold: an existing client on Hold needs nothing",
        client(deals=(won(), HOLD)), None,
        Expect("existing", "closed_won", "none", *E_NONE, False, bucket="past_stage_1"))

    # Stage 1 only: requirement later, state due_later, never flagged.
    add("stage 1 only: due at stage 2, never flagged",
        client(deals=(at(1),)), None,
        Expect("net_new", "none", "later", "due_later", "due_later", False, bucket="stage_1_only", furthest=1,
               on_hold=False, stage="1 · Prospecting"))
    add("stage 1 only: two stage 1 deals",
        client(deals=(at(1), at(1))), None,
        Expect("net_new", "none", "later", "due_later", "due_later", False, bucket="stage_1_only", open=2))
    add("stage 1 only: with a lost deal",
        client(deals=(at(1), LOST)), None,
        Expect("net_new", "none", "later", "due_later", "due_later", False, bucket="stage_1_only"))
    add("stage 1 only: after the cutover on a stamped net-new client",
        client(deals=(at(1),), **net_new), CUTOVER,
        Expect("net_new", "none", "later", "due_later", "due_later", False, bucket="stage_1_only"))
    add("stage 1 only: a Closed Won deal after the cutover makes it required",
        client(deals=(at(1), won(AFTER)), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, bucket="stage_1_only", furthest=1))
    add("stage 1 only: a client copy shows client, not due later",
        client(deals=(at(1),), docs={"NDA": OWN}), None,
        Expect("net_new", "none", "later", "client", "due_later", False, bucket="stage_1_only"))
    add("no active deal: lost deals only need nothing",
        client(deals=(LOST, LOST)), None,
        Expect("net_new", "none", "none", "not_needed", "not_needed", False, bucket="no_active_deal", furthest=0,
               open=0, on_hold=False, stage="No active deal"))

    # An unknown stage cannot be placed: it counts as past stage 1 and warns (#3).
    add("unknown stage: an open deal whose stage is not in the mirror counts as past stage 1",
        client(deals=(UNKNOWN,)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", furthest=0, on_hold=False,
               stage="Stage not recognised"))
    add("unknown stage: plus a stage 1 deal is past stage 1",
        client(deals=(at(1), UNKNOWN)), None,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1", furthest=1))
    add("unknown stage: after the cutover on a stamped net-new client",
        client(deals=(UNKNOWN,), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, bucket="past_stage_1"))
    add("unknown stage: an existing client is not affected",
        client(deals=(won(), UNKNOWN)), None,
        Expect("existing", "closed_won", "none", *E_NONE, False))

    # A manual override beats every rule, before and after the cutover.
    add("manual: existing set by hand before the cutover beats an open stage 4 deal",
        client(stored="existing", basis="manual", deals=(at(4),)), None,
        Expect("existing", "manual", "none", *E_NONE, False))
    add("manual: net new set by hand before the cutover beats a Closed Won deal and an SOW",
        client(stored="net_new", basis="manual", deals=(won(),), sows=(BEFORE,)), None,
        Expect("net_new", "manual", "required", *MISSING, True))
    add("manual: existing set by hand after the cutover beats a first win and an open deal",
        client(stored="existing", basis="manual", deals=(won(AFTER), at(3))), CUTOVER,
        Expect("existing", "manual", "none", *E_NONE, False, provisional=False))
    add("manual: net new set by hand after the cutover beats an earlier win and an earlier SOW",
        client(stored="net_new", basis="manual", deals=(won(BEFORE),), sows=(BEFORE,)), CUTOVER,
        Expect("net_new", "manual", "required", *MISSING, True, provisional=False))
    add("manual: net new set by hand with only a stage 1 deal is due later",
        client(stored="net_new", basis="manual", deals=(at(1),)), CUTOVER,
        Expect("net_new", "manual", "later", "due_later", "due_later", False))
    add("manual: net new set by hand with an earlier SOW only needs nothing",
        client(stored="net_new", basis="manual", sows=(BEFORE,)), CUTOVER,
        Expect("net_new", "manual", "none", "not_needed", "not_needed", False))
    add("manual: existing set by hand holding the standard copies",
        client(stored="existing", basis="manual", docs={"NDA": STD, "MSA": STD}), CUTOVER,
        Expect("existing", "manual", "none", "standard", "standard", False))

    # Test data is a flag only (B12): it changes no relationship, requirement, state or warning.
    add("test data: a run-tagged net-new client past stage 1 is flagged and still needs attention",
        client("S24 e2e 4f1c fixture", deals=(at(3),), test_data=True), None,
        Expect("net_new", "none", "required", *MISSING, True, flags=("test_data",)))
    add("test data: an existing test client keeps its relationship and gains the flag",
        client("S24 e2e 4f1c won", deals=(won(),), test_data=True), None,
        Expect("existing", "closed_won", "none", *E_NONE, False, flags=("test_data",)))
    add("test data: created by a test identity through SOW studio (no company) has both flags",
        client("Embertine Labs", company=None, sows=(BEFORE,), test_data=True), None,
        Expect("existing", "sow_engagement", "none", *E_NONE, False, flags=("test_data", "no_hubspot_link")))
    add("test data: after the cutover a stamped net-new test client is flagged like any other",
        client("smoke 2026-10-15 run", deals=(HOLD,), test_data=True, **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, flags=("test_data",)))

    # possible_duplicate: lower case; possessives, dots and apostrophes dropped; other punctuation a space;
    # trailing llc/inc/ltd/corp/co/company stripped (#4); placeholders never count.
    plain = Expect("net_new", "none", "none", "not_needed", "not_needed", False)

    def dup(row_id: str, name: str, *others: str, is_dup: bool, company: str | None = "co-a") -> None:
        mates = [client(o, company=None if o.startswith("Unknown company (deal ") else f"co-{i}")
                 for i, o in enumerate(others)]
        expect = replace(plain, flags=("possible_duplicate",) if is_dup else ())
        add(row_id, client(name, company=company), None, expect, mates)

    dup("duplicate: llc is stripped", "Arvella Foods LLC", "Arvella Foods", is_dup=True)
    dup("duplicate: inc is stripped (with its dot and comma)", "Brintmoor, Inc.", "BRINTMOOR", is_dup=True)
    dup("duplicate: ltd is stripped", "Cassowin Ltd", "Cassowin", is_dup=True)
    dup("duplicate: corp is stripped", "Dellford Corp.", "Dellford", is_dup=True)
    dup("duplicate: co is stripped", "Embertine Co", "Embertine", is_dup=True)
    dup("duplicate: company is stripped", "Fenwick Orchard Company", "Fenwick Orchard", is_dup=True)
    dup("duplicate: stacked suffixes are stripped", "Glimmerbay Holdings Co., LLC", "Glimmerbay Holdings",
        is_dup=True)
    dup("duplicate: dots are dropped so L.L.C. strips", "Hollowmere L.L.C.", "Hollowmere", is_dup=True)
    dup("duplicate: dotted initials match their plain form", "J.R.V. Retail", "JRV Retail", is_dup=True)
    dup("duplicate: a possessive is dropped", "Kestrine's", "Kestrine", is_dup=True)
    dup("duplicate: a curly possessive is dropped", "Lunavale’s Studio, Inc.", "Lunavale Studio", is_dup=True)
    dup("duplicate: an apostrophe inside a word is dropped", "O'Marra Partners", "OMarra Partners", is_dup=True)
    dup("duplicate: other punctuation separates words", "Istvale-Analytics", "Istvale Analytics", is_dup=True)
    dup("duplicate: case and spacing do not matter", "  istvale   ANALYTICS ", "Istvale Analytics", is_dup=True)
    dup("duplicate: three spellings of one name", "Arvella Foods, Inc.", "Arvella Foods LLC", "Arvella Foods",
        is_dup=True)
    dup("not duplicate: limited is not one of the suffixes", "Jorvane Limited", "Jorvane", is_dup=False)
    dup("not duplicate: corporation is not one of the suffixes", "Jorvane Corporation", "Jorvane", is_dup=False)
    dup("not duplicate: incorporated is not one of the suffixes", "Jorvane Incorporated", "Jorvane", is_dup=False)
    dup("not duplicate: a suffix word that leads the name stays", "Co Arvella", "Arvella", is_dup=False)
    dup("not duplicate: a name is never stripped to nothing", "Company", "Co", is_dup=False)
    dup("not duplicate: different names", "Arvella Foods", "Arvella Farms", is_dup=False)
    placeholder = replace(plain, flags=("unknown_company",))
    add("duplicate: two identical Unknown company placeholders never count",
        client("Unknown company (deal 7001)", company=None), None, placeholder,
        [client("Unknown company (deal 7001)", company=None)])
    add("duplicate: a placeholder never counts against a real client of the same text",
        client("Unknown company (deal 7002)", company="co-real"), None,
        replace(plain, flags=()), [client("Unknown company (deal 7002)", company=None)])

    # Undated wins count as on or before the cutover (#5).
    add("undated win: before the cutover it makes the client existing",
        client(deals=(won(None),)), None,
        Expect("existing", "closed_won", "none", *E_NONE, False, provisional=True))
    add("undated win: a client judged after the cutover with an undated win starts existing",
        client(deals=(won(None),)), CUTOVER,
        Expect("existing", "closed_won", "none", *E_NONE, False, provisional=False))
    add("undated win: a stamped net-new client with an undated win stays net new and required",
        client(deals=(won(None),), **net_new), CUTOVER,
        Expect("net_new", "none", "required", *MISSING, True, provisional=False))
    return r


TABLE: list[Row] = [*_grid(), *_cases()]


@pytest.mark.parametrize("row", TABLE, ids=[row.id for row in TABLE])
def test_t1_table(row: Row):
    population = [row.item, *row.others]
    status = classify(row.item, row.cutover, duplicate_keys(population))
    e = row.expect
    assert (status.relationship, status.relationship_basis, status.requirement, status.nda, status.msa,
            status.needs_attention) == (e.relationship, e.basis, e.requirement, e.nda, e.msa, e.attention)
    # The row's own expectation must obey the directive's definition of needs attention.
    assert e.attention == needs(*row.cell)
    if e.provisional is not None:
        assert status.provisional is e.provisional
    if e.bucket is not None:
        assert status.stage_bucket == e.bucket
    if e.furthest is not None:
        assert status.furthest_open_stage == e.furthest
    if e.open is not None:
        assert status.open_deals == e.open
    if e.on_hold is not None:
        assert status.on_hold is e.on_hold
    if e.stage is not None:
        assert stage_text(status) == e.stage
    if e.flags is not None:  # an array with no order in the contract
        assert sorted(status.flags) == sorted(e.flags)
    if e.labels is not None:
        assert (status.nda_label, status.msa_label) == e.labels


# --- the cutover stamp: what the first real batch stores for every client (live rule as of the cutover) ---

STAMP = [
    ("stamp: a win dated before the cutover is existing", client(deals=(won(BEFORE),)), ("existing", "closed_won")),
    ("stamp: a win dated on the cutover day is existing", client(deals=(won(CUTOVER),)), ("existing", "closed_won")),
    ("stamp: a win dated after the cutover is net new", client(deals=(won(AFTER),)), ("net_new", "none")),
    ("stamp: an undated win counts as on or before the cutover", client(deals=(won(None),)),
     ("existing", "closed_won")),
    ("stamp: an SOW created before the cutover is existing", client(sows=(BEFORE,)), ("existing", "sow_engagement")),
    ("stamp: an SOW created on the cutover day is existing", client(sows=(CUTOVER,)), ("existing", "sow_engagement")),
    ("stamp: an SOW created after the cutover is net new", client(sows=(AFTER,)), ("net_new", "none")),
    ("stamp: an engagement created on the cutover day is existing", client(engagements=(CUTOVER,)),
     ("existing", "sow_engagement")),
    ("stamp: a forecast-model engagement with no HubSpot link is existing",
     client(company=None, engagements=(BEFORE,)), ("existing", "sow_engagement")),
    ("stamp: an earlier win and an earlier engagement", client(deals=(won(),), engagements=(BEFORE,)),
     ("existing", "closed_won_and_sow")),
    ("stamp: an earlier win and a later SOW is closed won only", client(deals=(won(),), sows=(AFTER,)),
     ("existing", "closed_won")),
    ("stamp: a later win and an earlier SOW is sow only", client(deals=(won(AFTER),), sows=(BEFORE,)),
     ("existing", "sow_engagement")),
    ("stamp: open, Hold, unknown and lost deals are net new", client(deals=(at(3), HOLD, UNKNOWN, LOST)),
     ("net_new", "none")),
    ("stamp: nothing at all is net new", client(), ("net_new", "none")),
]


@pytest.mark.parametrize(("case", "item", "expected"), STAMP, ids=[c[0] for c in STAMP])
def test_the_cutover_stamp_rule(case, item, expected):
    assert live_relationship(item, CUTOVER) == expected, case


# --- completeness --------------------------------------------------------------------------------------


def test_the_table_names_every_reachable_cell_before_and_after_the_cutover():
    for phase, cutover in (("before", None), ("after", CUTOVER)):
        cells = {row.cell for row in TABLE if row.cutover == cutover}
        assert cells == REACHABLE, (phase, sorted(REACHABLE - cells), sorted(cells - REACHABLE))
    assert len(REACHABLE) == 64
    ids = [row.id for row in TABLE]
    assert len(ids) == len(set(ids)), "every row has its own name"


DIRECTIVE_CASES = (
    "cutover: a net-new client's first Closed Won deal after the cutover stays net new and stays flagged",
    "cutover: a client created after the cutover whose company has an earlier win starts existing",
    "hold: a deal on Hold counts as open and past stage 1",
    "stage 1 only: due at stage 2, never flagged",
    "unknown stage: an open deal whose stage is not in the mirror counts as past stage 1",
    "manual: existing set by hand before the cutover beats an open stage 4 deal",
    "manual: net new set by hand after the cutover beats an earlier win and an earlier SOW",
    "test data: a run-tagged net-new client past stage 1 is flagged and still needs attention",
    "duplicate: llc is stripped", "duplicate: inc is stripped (with its dot and comma)", "duplicate: ltd is stripped",
    "duplicate: corp is stripped", "duplicate: co is stripped", "duplicate: company is stripped",
    "duplicate: dots are dropped so L.L.C. strips", "duplicate: a possessive is dropped",
    "duplicate: two identical Unknown company placeholders never count",
    "undated win: a client judged after the cutover with an undated win starts existing",
)


def test_every_directive_case_is_a_named_row():
    ids = {row.id for row in TABLE}
    assert [case for case in DIRECTIVE_CASES if case not in ids] == []


# The oracle: the contract's words, written independently of agreement_status.


def _oracle_requirement(item: ClientInput, cutover: date | None) -> str:
    """Requirement (net new only): required for an open deal at stage 2-6, a deal on Hold (#2), an open deal
    whose stage cannot be placed (#3), a Closed Won deal, or an SOW/engagement created after the cutover;
    later when open deals exist and all are stage 1; none otherwise."""
    opened = [d for d in item.deals if d.status == "open"]
    if (any(d.ordinal is None or 2 <= d.ordinal <= 6 for d in opened)
            or any(d.status in ("hold", "won") for d in item.deals)
            or (cutover is not None and any(w > cutover for w in (*item.sow_dates, *item.engagement_dates)))):
        return "required"
    return "later" if opened else "none"


def _oracle_relationship(item: ClientInput, cutover: date | None) -> tuple[str, str]:
    if item.stored_relationship is not None and (cutover is not None or item.stored_basis == "manual"):
        return item.stored_relationship, item.stored_basis or "none"  # stored after the cutover; manual always
    wins = [d for d in item.deals if d.status == "won"]
    if cutover is None:  # live
        won_any, work_any = bool(wins), bool(item.sow_dates or item.engagement_dates)
        if won_any and work_any:
            return "existing", "closed_won_and_sow"
        if won_any:
            return "existing", "closed_won"
        return ("existing", "sow_engagement") if work_any else ("net_new", "none")
    # Created after the cutover (B8): existing only for a Closed Won deal dated on or before it (#5: undated counts).
    if any(d.close_date is None or d.close_date <= cutover for d in wins):
        return "existing", "closed_won"
    return "net_new", "none"


def _oracle_state(doc: DocInput | None, rel: str, req: str) -> str:
    if doc is not None and doc.source in ("client", "standard"):
        return doc.source  # a file wins over a mark
    if doc is not None and doc.mark_source is not None:
        return "covered"
    return NOTHING_HELD[(rel, "none" if rel == "existing" else req)]


def test_the_rules_never_leave_the_reachable_cells_and_agree_with_the_contract():
    deal_sets = [(), (at(1),), (at(3),), (HOLD,), (UNKNOWN,), (LOST,), (won(BEFORE),), (won(AFTER),),
                 (won(None),), (at(1), won(AFTER)), (at(1), HOLD), (at(6), LOST)]
    work = [((), ()), ((BEFORE,), ()), ((), (AFTER,)), ((CUTOVER,), ()), ((AFTER,), (BEFORE,))]
    stored = [(None, None), ("existing", "closed_won"), ("net_new", "none"), ("existing", "manual"),
              ("net_new", "manual")]
    docs = [None, OWN, STD, MARK, HS_MARK, DocInput(source="client", mark_source="dealgate"),
            DocInput(source="standard", standard_version=1, mark_source="hubspot")]
    seen: set[tuple[str, str, str, str]] = set()
    checked = 0
    for deals, (sows, engagements), (rel_stored, basis_stored), nda_doc, msa_doc, cutover in itertools.product(
            deal_sets, work, stored, docs, docs, (None, CUTOVER)):
        if cutover is None and rel_stored is not None and basis_stored != "manual":
            continue  # before the cutover nothing is stamped (B8); only a writer's manual value is stored
        held = {k: d for k, d in (("NDA", nda_doc), ("MSA", msa_doc)) if d is not None}
        item = client(stored=rel_stored, basis=basis_stored, deals=deals, sows=sows, engagements=engagements,
                      docs=held)
        s = classify(item, cutover)
        cell = (s.relationship, s.requirement, s.nda, s.msa)
        assert cell in REACHABLE, (item, cutover, cell)
        rel, basis = _oracle_relationship(item, cutover)
        req = _oracle_requirement(item, cutover) if rel == "net_new" else "none"
        expected = (rel, basis, req, _oracle_state(nda_doc, rel, req), _oracle_state(msa_doc, rel, req))
        assert (s.relationship, s.relationship_basis, s.requirement, s.nda, s.msa) == expected, (item, cutover)
        assert s.needs_attention == needs(*cell)
        if cutover is not None:
            assert s.provisional is False  # after the cutover nothing is provisional
        elif rel_stored is None:
            assert s.provisional is True  # judged live before the cutover
        seen.add(cell)
        checked += 1
    assert seen == REACHABLE  # the sweep reaches every cell the contract allows, and nothing else
    assert checked > 20_000


def test_every_card_drill_returns_its_value_over_the_whole_table():
    for cutover in (None, CUTOVER):
        rows = [row for row in TABLE if row.cutover == cutover]
        keys = duplicate_keys([row.item for row in rows])
        statuses = [classify(row.item, row.cutover, keys) for row in rows]
        for card in cards(statuses):
            assert sum(1 for s in statuses if matches(s, card["drill"])) == card["value"], (cutover, card["key"])
        values = {c["key"]: c["value"] for c in cards(statuses)}
        assert values["clients"] == values["existing"] + values["net_new"] == len(rows)
        assert values["needs_attention"] == sum(1 for row in rows if row.expect.attention)
