"""Literal sourcing dates and headcounts, independent of probability or money."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from app.gm.sourcing import prepare_sourcing, validate_rules


def demand(**changes):
    return dict(id="demand-one", account_id="account-one", plan_id="plan-one",
        title="Company X staffing", account_name="Company X", source_url="/forecast",
        role="Engineer", skills=["python"], level="Senior", location="US",
        timezone="America/New_York", quantity=7, retained_quantity=2, incremental_quantity=5,
        required_fte="3.5", matched_fte="1.5", gap_fte="2.0", lifecycle="tentative",
        probability="0.70", matches=[
            {"person_id": "private-one", "allocation": "0.5", "continuity": True},
            {"person_id": "private-two", "allocation": "0.5", "continuity": False},
            {"person_id": "private-three", "allocation": "0.5", "continuity": False},
        ], missing=["continuity:private-four"]) | changes


def intervals(row=None, start="2026-11-01", end="2026-12-01"):
    return [{"start": start, "end_exclusive": end, "demands": [row or demand()],
        "overcommitted_person_ids": ["private-five"]}]


def rule(skill="python", location="US", days=45):
    return {"skill": skill, "location": location, "lead_days": days}


def test_literal_seven_people_separates_incremental_hiring_and_unmatched_continuity():
    original = intervals()
    before = deepcopy(original)
    result = prepare_sourcing(original, [rule()])
    row, = result["rows"]
    assert row["quantity"] == 7 and row["retained_quantity"] == 2 and row["incremental_quantity"] == 5
    assert row["matched_quantity"] == 3 and row["gap_quantity"] == 4
    assert row["continuity_gap_quantity"] == 1 and row["incremental_gap_quantity"] == 3
    assert row["gap_fte"] == Decimal("2.0")
    assert row["sourcing_by"] == "2026-09-17"
    assert row["start"] == "2026-11-01" and row["end_exclusive"] == "2026-12-01"
    assert row["missing"] == ["continuity_unresolved"]
    assert result["is_reservation"] is False
    assert "private-" not in repr(result) and "probability" not in row and "matches" not in row
    assert original == before


def test_skill_specific_override_and_longest_of_required_skills():
    row = demand(skills=["python", "typescript"])
    result = prepare_sourcing(intervals(row), [rule("*", days=90), rule(days=15), rule("typescript", days=30)])
    assert result["rows"][0]["sourcing_by"] == "2026-10-02"


@pytest.mark.parametrize("skills", [[], ["python", "missing-skill"]])
def test_missing_any_skill_lead_time_never_invents_date(skills):
    result = prepare_sourcing(intervals(demand(skills=skills)), [rule()])
    assert result["rows"][0]["sourcing_by"] is None
    assert result["rows"][0]["missing"]


def test_rules_are_location_specific_with_no_default_values():
    row = demand(location="India")
    assert prepare_sourcing(intervals(row), [rule()])["rows"][0]["sourcing_by"] is None
    assert prepare_sourcing(intervals(row), [rule(location="India", days=30)])["rows"][0]["sourcing_by"] == "2026-10-02"


def test_fully_matched_and_continuity_only_gap_never_propose_incremental_hires():
    matched = demand(quantity=3, retained_quantity=1, incremental_quantity=2, required_fte="1.5", gap_fte="0", missing=[])
    row, = prepare_sourcing(intervals(matched), [])["rows"]
    assert row["gap_quantity"] == 0 and row["sourcing_by"] is None and row["missing"] == []
    continuity = demand(quantity=4, retained_quantity=2, incremental_quantity=2, required_fte="2", gap_fte="0.5")
    row, = prepare_sourcing(intervals(continuity), [])["rows"]
    assert row["incremental_gap_quantity"] == 0 and row["continuity_gap_quantity"] == 1
    assert row["sourcing_by"] is None


def test_each_dated_gap_uses_its_actual_start_with_calendar_leap_boundary():
    row, = prepare_sourcing(intervals(start="2028-03-01", end="2028-04-01"), [rule(days=1)])["rows"]
    assert row["sourcing_by"] == "2028-02-29"


@pytest.mark.parametrize("rules", [[rule(days=-1)], [rule(days=True)], [rule(days=1.5)], [rule(), rule()], [rule() | {"salary": "100"}]])
def test_invalid_or_ambiguous_rules_reject(rules):
    with pytest.raises(ValueError):
        validate_rules(rules)


@pytest.mark.parametrize("field,value", [("gap_fte", "NaN"), ("gap_fte", "Infinity"), ("gap_fte", 2.0),
    ("quantity", True), ("retained_quantity", 8), ("incremental_quantity", 6), ("matched_fte", "1.6"),
    ("gap_fte", "0"), ("matches", None)])
def test_malformed_allocation_cannot_become_zero_or_a_valid_draft(field, value):
    with pytest.raises(ValueError):
        prepare_sourcing(intervals(demand(**{field: value})), [rule()])


def test_high_precision_allocation_checks_do_not_depend_on_ambient_decimal_context():
    allocation = "0.123456789012345678901"
    row = demand(quantity=2, retained_quantity=0, incremental_quantity=2,
        required_fte="0.246913578024691357802", matched_fte=allocation, gap_fte=allocation,
        matches=[{"person_id": "private-one", "allocation": allocation, "continuity": False}], missing=[])
    with localcontext() as context:
        context.prec = 3
        result = prepare_sourcing(intervals(row), [rule()])
    assert result["rows"][0]["gap_fte"] == Decimal(allocation)


def test_unknown_financial_input_fields_are_not_echoed_to_the_cost_free_draft():
    row = demand(salary="90000", cost_rate="150", bill_rate="250", gm="0.40")
    result = prepare_sourcing(intervals(row), [rule()])
    assert not {"salary", "cost_rate", "bill_rate", "gm", "probability", "matches"} & result["rows"][0].keys()
    assert "private-" not in repr(result)


@pytest.mark.parametrize("start,end,days", [("2026-11-01", "2026-11-01", 0),
    ("2026-11-01T00:00:00Z", "2026-12-01", 0), ("0001-01-01", "0001-02-01", 1)])
def test_invalid_or_overflowing_dates_are_explicit_errors(start, end, days):
    with pytest.raises(ValueError):
        prepare_sourcing(intervals(start=start, end=end), [rule(days=days)])


def test_duplicate_named_match_cannot_count_twice():
    row = demand()
    row["matches"][1]["person_id"] = row["matches"][0]["person_id"]
    with pytest.raises(ValueError):
        prepare_sourcing(intervals(row), [rule()])


def test_explicit_zero_day_rule_and_copied_rule_values():
    original = [rule(days=0)]
    validated = validate_rules(original)
    validated[0]["lead_days"] = 90
    assert original == [rule(days=0)]
    assert prepare_sourcing(intervals(), original)["rows"][0]["sourcing_by"] == "2026-11-01"


def test_literal_two_us_five_india_slots_keep_seven_people_at_seventy_percent():
    us = demand(quantity=2, retained_quantity=0, incremental_quantity=2,
        required_fte="2", matched_fte="0", gap_fte="2", matches=[], missing=[])
    india = demand(id="india-demand", location="India", timezone="Asia/Kolkata",
        quantity=5, retained_quantity=0, incremental_quantity=5,
        required_fte="5", matched_fte="0", gap_fte="5", matches=[], missing=[])
    input_intervals = intervals(us)
    input_intervals[0]["demands"].append(india)
    result = prepare_sourcing(input_intervals, [rule(), rule(location="India", days=30)])
    assert [(row["location"], row["quantity"], row["incremental_gap_quantity"], row["sourcing_by"])
        for row in result["rows"]] == [("US", 2, 2, "2026-09-17"), ("India", 5, 5, "2026-10-02")]
    assert result["missing"] == []
