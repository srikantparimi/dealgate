"""S24-AG1 T1 — table-driven classification: relationship × requirement × state, with the cutover cases.

Pure: calls app.services.agreement_status directly (no database). The rules are the contract's
components Cutover, Relationship, Requirement and DocState plus the decisions logged in docs/bugs/s24-ag1.md
(#2 Hold, #3 unknown stage, #4 duplicate names, #5 undated wins).
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.services.agreement_status import (
    ClientInput,
    DealInput,
    DocInput,
    cards,
    classify,
    classify_all,
    duplicate_keys,
    matches,
    normalise_name,
    stage_text,
)

CUTOVER = date(2026, 10, 20)
BEFORE, AFTER = date(2026, 9, 30), date(2026, 11, 2)


def client(name: str = "Client", **kw) -> ClientInput:
    return ClientInput(id=uuid.uuid4(), name=name, hubspot_company_id=kw.pop("company", "c-1"), **kw)


def won(when=BEFORE):
    return DealInput("won", close_date=when)


def stage(n):
    return DealInput("open", n)


HOLD = DealInput("hold")
LOST = DealInput("lost")
STD = DocInput(source="standard", standard_version=1, batch_label="AG-0001")
OWN = DocInput(source="client")
MARK = DocInput(mark_source="dealgate")
HS_MARK = DocInput(mark_source="hubspot")

# (case, ClientInput, cutover) -> (relationship, basis, provisional, requirement, nda, msa, needs_attention)
CASES = [
    # --- before the cutover: live and provisional -------------------------------------------------
    ("won is existing", client(deals=(won(),)), None,
     ("existing", "closed_won", True, "none", "existing_none", "existing_none", False)),
    ("sow is existing", client(sow_dates=(BEFORE,)), None,
     ("existing", "sow_engagement", True, "none", "existing_none", "existing_none", False)),
    ("engagement, no company", client(company=None, engagement_dates=(BEFORE,)), None,
     ("existing", "sow_engagement", True, "none", "existing_none", "existing_none", False)),
    ("won and engagement", client(deals=(won(),), engagement_dates=(BEFORE,)), None,
     ("existing", "closed_won_and_sow", True, "none", "existing_none", "existing_none", False)),
    ("open stage 3 is required", client(deals=(stage(3),)), None,
     ("net_new", "none", True, "required", "missing", "missing", True)),
    ("Hold counts as open past stage 1", client(deals=(HOLD,)), None,
     ("net_new", "none", True, "required", "missing", "missing", True)),
    ("stage 1 only is due later", client(deals=(stage(1),)), None,
     ("net_new", "none", True, "later", "due_later", "due_later", False)),
    ("stage 1 plus lost is still later", client(deals=(stage(1), LOST)), None,
     ("net_new", "none", True, "later", "due_later", "due_later", False)),
    ("lost only is not needed", client(deals=(LOST,)), None,
     ("net_new", "none", True, "none", "not_needed", "not_needed", False)),
    ("no deals is not needed", client(), None,
     ("net_new", "none", True, "none", "not_needed", "not_needed", False)),
    ("open stage unknown counts as past stage 1", client(deals=(DealInput("open", None),)), None,
     ("net_new", "none", True, "required", "missing", "missing", True)),
    ("standard NDA, MSA missing: still attention", client(deals=(stage(4),), docs={"NDA": STD}), None,
     ("net_new", "none", True, "required", "standard", "missing", True)),
    ("client NDA + HubSpot MSA mark: covered", client(deals=(stage(4),), docs={"NDA": OWN, "MSA": HS_MARK}), None,
     ("net_new", "none", True, "required", "client", "covered", False)),
    ("existing with standard copies", client(deals=(won(),), docs={"NDA": STD, "MSA": STD}), None,
     ("existing", "closed_won", True, "none", "standard", "standard", False)),
    ("a file wins over a mark", client(deals=(stage(2),), docs={"NDA": DocInput(source="client", mark_source="dealgate")}),
     None, ("net_new", "none", True, "required", "client", "missing", True)),
    ("marked covered clears the warning", client(deals=(stage(5),), docs={"NDA": MARK, "MSA": MARK}), None,
     ("net_new", "none", True, "required", "covered", "covered", False)),
    # --- after the cutover: the stored relationship is used, never moved by the rule ------------------
    ("stored net new + first win after the cutover stays net new and flagged",
     client(stored_relationship="net_new", stored_basis="none", deals=(won(AFTER),)), CUTOVER,
     ("net_new", "none", False, "required", "missing", "missing", True)),
    ("stored net new + SOW after the cutover is required",
     client(stored_relationship="net_new", stored_basis="none", sow_dates=(AFTER,)), CUTOVER,
     ("net_new", "none", False, "required", "missing", "missing", True)),
    ("stored net new + SOW on the cutover day is not 'after'",
     client(stored_relationship="net_new", stored_basis="none", sow_dates=(CUTOVER,)), CUTOVER,
     ("net_new", "none", False, "none", "not_needed", "not_needed", False)),
    ("created after the cutover; company has an earlier win: existing",
     client(deals=(won(BEFORE),)), CUTOVER,
     ("existing", "closed_won", False, "none", "existing_none", "existing_none", False)),
    ("created after the cutover; only a later win: net new and required",
     client(deals=(won(AFTER),)), CUTOVER,
     ("net_new", "none", False, "required", "missing", "missing", True)),
    ("undated win counts as on or before the cutover",
     client(deals=(DealInput("won", close_date=None),)), CUTOVER,
     ("existing", "closed_won", False, "none", "existing_none", "existing_none", False)),
    ("manual existing beats the rule",
     client(stored_relationship="existing", stored_basis="manual", deals=(stage(4),)), CUTOVER,
     ("existing", "manual", False, "none", "existing_none", "existing_none", False)),
    ("manual net new with an old win is required",
     client(stored_relationship="net_new", stored_basis="manual", deals=(won(BEFORE),)), CUTOVER,
     ("net_new", "manual", False, "required", "missing", "missing", True)),
    ("stored existing stays existing before any cutover (manual change pre-cutover is provisional)",
     client(stored_relationship="existing", stored_basis="manual"), None,
     ("existing", "manual", True, "none", "existing_none", "existing_none", False)),
]


@pytest.mark.parametrize("case,item,cutover,expected", CASES, ids=[c[0] for c in CASES])
def test_classification_table(case, item, cutover, expected):
    s = classify(item, cutover)
    got = (s.relationship, s.relationship_basis, s.provisional, s.requirement, s.nda, s.msa, s.needs_attention)
    assert got == expected, case


def test_flags_test_data_placeholder_and_no_link():
    placeholder = client("Unknown company (deal 4417)", company=None, deals=(stage(2),))
    forecast = client("Northgate Dental", company=None, engagement_dates=(BEFORE,))
    tester = client("S21 e2e 1234 label", company=None, sow_dates=(BEFORE,), test_data=True)
    s_ph, s_fc, s_t = classify_all([placeholder, forecast, tester], None)
    assert s_ph.flags == ("unknown_company",) and s_ph.relationship == "net_new" and s_ph.needs_attention
    assert s_fc.flags == ("no_hubspot_link",)
    assert "test_data" in s_t.flags and "no_hubspot_link" in s_t.flags


@pytest.mark.parametrize("a,b,dup", [
    ("Peppermill Casino", "Peppermill Casino's, LLC", True),
    ("Delta", "Delta, L.L.C.", True),
    ("Acme Co.", "ACME", True),
    ("Smith & Co", "Smith", True),
    ("Acme Limited", "Acme", False),  # the directive's rule strips llc/inc/ltd/corp/co/company only (bugs #4)
    ("Unknown company (deal 1)", "Unknown company (deal 1)", False),  # placeholders never count
])
def test_possible_duplicate_rule(a, b, dup):
    company_a = None if a.startswith("Unknown company") else "c-a"
    company_b = None if b.startswith("Unknown company") else "c-b"
    pair = [client(a, company=company_a), client(b, company=company_b)]
    keys = duplicate_keys(pair)
    statuses = [classify(c, None, keys) for c in pair]
    assert all(("possible_duplicate" in s.flags) == dup for s in statuses), (a, b, keys)


def test_normalise_name_examples():
    assert normalise_name("Peppermill Casino's, LLC") == "peppermill casino"
    assert normalise_name("Co") == "co"  # never strips the last token


def test_stage_text_and_buckets():
    hold_only = classify(client(deals=(HOLD,)), None)
    both = classify(client(deals=(stage(4), HOLD)), None)
    s1 = classify(client(deals=(stage(1),)), None)
    none = classify(client(deals=(LOST,)), None)
    assert (hold_only.stage_bucket, stage_text(hold_only)) == ("past_stage_1", "On hold")
    assert stage_text(both) == "4 · Proposal (and on hold)"
    assert (s1.stage_bucket, none.stage_bucket) == ("stage_1_only", "no_active_deal")


def test_every_card_equals_the_list_its_drill_opens():
    population = [
        client("A", deals=(won(),), docs={"NDA": STD, "MSA": STD}),
        client("B", deals=(stage(3),)),
        client("C", deals=(stage(1),)),
        client("D", deals=(HOLD,), docs={"NDA": OWN}),
        client("E", sow_dates=(BEFORE,), docs={"MSA": MARK}),
        client("F"),
    ]
    statuses = classify_all(population, None)
    for card in cards(statuses):
        assert sum(1 for s in statuses if matches(s, card["drill"])) == card["value"], card["key"]
    by_key = {c["key"]: c["value"] for c in cards(statuses)}
    assert by_key == {"clients": 6, "existing": 2, "net_new": 4, "needs_attention": 2, "standard_attached": 1,
                      "client_copies": 1}
