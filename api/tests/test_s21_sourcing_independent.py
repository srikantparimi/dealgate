"""Independent pure sourcing boundaries, not service or T22/T23 acceptance."""

from copy import deepcopy
from decimal import Decimal, localcontext

import pytest

from app.gm.sourcing import prepare_sourcing


def source(**changes):
    return dict(id="stable-demand", account_id="account-x", plan_id="plan-x",
        title="Reviewed implementation", account_name="Synthetic X", source_url="/forecast",
        role="Engineer", skills=["python"], level="Senior", location="US",
        timezone="America/Los_Angeles", quantity=2, retained_quantity=0, incremental_quantity=2,
        required_fte="2", matched_fte="0", gap_fte="2", matches=[], missing=[]) | changes


def interval(*rows, start="2026-11-01", end="2026-12-01"):
    return {"start": start, "end_exclusive": end, "demands": list(rows)}


def rule(skill="python", location="US", days=45):
    return {"skill": skill, "location": location, "lead_days": days}


def match(person, allocation="1", *, continuity=False):
    return {"person_id": person, "allocation": allocation, "continuity": continuity}


@pytest.mark.parametrize("rules", [
    [rule("*", days=90), rule(days=0)],
    [rule(days=0), rule("*", days=90)],
])
def test_exact_zero_day_override_is_not_replaced_by_wildcard(rules):
    row, = prepare_sourcing([interval(source())], rules)["rows"]
    assert row["sourcing_by"] == "2026-11-01"
    assert row["incremental_gap_quantity"] == 2 and row["missing"] == []


@pytest.mark.parametrize("skills", [["python", "rust"], ["rust", "python"]])
def test_exact_shorter_rule_and_unmatched_skill_wildcard_use_longest_applicable(skills):
    row, = prepare_sourcing([interval(source(skills=skills))],
        [rule("*", days=45), rule(days=10)])["rows"]
    assert row["sourcing_by"] == "2026-09-17"
    assert row["missing"] == []


def test_rules_do_not_infer_case_aliases_or_wildcard_locations():
    row, = prepare_sourcing([interval(source(skills=["Python"]))],
        [rule(), rule("*", location="India"), rule("*", location="*")])["rows"]
    assert row["sourcing_by"] is None and row["missing"] == ["lead_time"]


@pytest.mark.parametrize("timezone", ["America/Los_Angeles", "Asia/Kolkata", "Pacific/Kiritimati"])
def test_calendar_days_keep_local_date_through_dst_and_extreme_offsets(timezone):
    row, = prepare_sourcing([interval(source(timezone=timezone), start="2027-03-15", end="2027-04-01")],
        [rule(days=1)])["rows"]
    assert row["start"] == "2027-03-15" and row["sourcing_by"] == "2027-03-14"
    assert row["timezone"] == timezone


def test_timing_revision_moves_literal_sourcing_dates_without_mutating_old_input():
    original = [interval(source())]
    saved = deepcopy(original)
    first = prepare_sourcing(original, [rule()])
    moved = prepare_sourcing([interval(source(), start="2026-12-01", end="2027-01-01")], [rule()])
    assert first["rows"][0]["sourcing_by"] == "2026-09-17"
    assert moved["rows"][0]["sourcing_by"] == "2026-10-17"
    assert original == saved


@pytest.mark.parametrize("start,end,days,expected", [
    ("0001-01-01", "0001-01-02", 0, "0001-01-01"),
    ("9999-12-30", "9999-12-31", 1, "9999-12-29"),
    ("2028-03-01", "2028-04-01", 60, "2028-01-01"),
])
def test_literal_calendar_bounds_and_leap_year(start, end, days, expected):
    row, = prepare_sourcing([interval(source(), start=start, end=end)], [rule(days=days)])["rows"]
    assert row["sourcing_by"] == expected


@pytest.mark.parametrize("timezone", ["Mars/Olympus", "UTC+05:30"])
def test_nonempty_invalid_timezone_cannot_become_complete_sourcing(timezone):
    with pytest.raises(ValueError):
        prepare_sourcing([interval(source(timezone=timezone))], [rule()])


def test_continuous_monthly_gap_keeps_its_actual_first_gap_deadline():
    rows = prepare_sourcing([
        interval(source()),
        interval(source(), start="2026-12-01", end="2027-01-01"),
        interval(source(), start="2027-01-01", end="2027-02-01"),
    ], [rule()])["rows"]
    assert [row["incremental_gap_quantity"] for row in rows] == [2, 2, 2]
    assert [row["sourcing_by"] for row in rows] == ["2026-09-17", "2026-09-17", "2026-09-17"]


def test_fully_closed_gap_then_reopened_gap_gets_a_new_deadline():
    closed = source(matched_fte="2", gap_fte="0", matches=[match("a"), match("b")])
    rows = prepare_sourcing([
        interval(source(), end="2026-11-15"),
        interval(closed, start="2026-11-15", end="2026-11-20"),
        interval(source(), start="2026-11-20"),
    ], [rule(days=30)])["rows"]
    assert [row["sourcing_by"] for row in rows] == ["2026-10-02", None, "2026-10-21"]
    assert [row["incremental_gap_quantity"] for row in rows] == [2, 0, 2]


def test_no_input_coverage_between_episodes_does_not_invent_continuity():
    rows = prepare_sourcing([
        interval(source(), end="2026-11-10"),
        interval(source(), start="2026-11-20"),
    ], [rule(days=30)])["rows"]
    assert [row["sourcing_by"] for row in rows] == ["2026-10-02", "2026-10-21"]


def test_six_retained_and_two_incremental_half_time_slots_are_not_eight_hires():
    row = source(quantity=8, retained_quantity=6, incremental_quantity=2,
        required_fte="4", matched_fte="3", gap_fte="1",
        matches=[match(f"retained-{index}", "0.5", continuity=True) for index in range(6)])
    output, = prepare_sourcing([interval(row)], [rule()])["rows"]
    assert (output["quantity"], output["retained_quantity"], output["incremental_quantity"]) == (8, 6, 2)
    assert (output["matched_quantity"], output["gap_quantity"]) == (6, 2)
    assert (output["continuity_gap_quantity"], output["incremental_gap_quantity"]) == (0, 2)
    assert output["gap_fte"] == Decimal("1") and output["sourcing_by"] == "2026-09-17"


def test_unmatched_retained_team_is_continuity_risk_not_an_incremental_hiring_date():
    row = source(quantity=6, retained_quantity=6, incremental_quantity=0,
        required_fte="3", matched_fte="0", gap_fte="3")
    output, = prepare_sourcing([interval(row)], [rule()])["rows"]
    assert output["continuity_gap_quantity"] == 6 and output["incremental_gap_quantity"] == 0
    assert output["sourcing_by"] is None and output["missing"] == ["continuity_unresolved"]


def test_forged_display_counters_are_recomputed_from_validated_slots():
    row = source(gap_quantity=999, incremental_gap_quantity=0, matched_quantity=2,
        continuity_gap_quantity=999, sourcing_by="9999-12-31")
    output, = prepare_sourcing([interval(row)], [rule()])["rows"]
    assert output["gap_quantity"] == 2 and output["incremental_gap_quantity"] == 2
    assert output["matched_quantity"] == 0 and output["continuity_gap_quantity"] == 0
    assert output["sourcing_by"] == "2026-09-17"


@pytest.mark.parametrize("changes", [
    {"retained_quantity": True, "incremental_quantity": 1},
    {"required_fte": "2", "matched_fte": "1", "gap_fte": "1", "matches": [match("x", "0.5")]},
    {"required_fte": "3", "matched_fte": "0", "gap_fte": "3"},
    {"retained_quantity": 0, "incremental_quantity": 2, "matched_fte": "1", "gap_fte": "1",
     "matches": [match("x", continuity=True)]},
])
def test_forged_slot_or_continuity_math_is_rejected(changes):
    with pytest.raises(ValueError):
        prepare_sourcing([interval(source(**changes))], [rule()])


def test_one_person_cannot_fill_two_full_time_demands_in_one_interval():
    full = source(quantity=1, incremental_quantity=1, required_fte="1", matched_fte="1",
        gap_fte="0", matches=[match("same-person")])
    with pytest.raises(ValueError):
        prepare_sourcing([interval(full, full | {"id": "other-demand", "plan_id": "other-plan"})], [])


def test_one_person_can_fill_two_half_time_demands_without_new_hiring():
    half = source(quantity=1, incremental_quantity=1, required_fte="0.5", matched_fte="0.5",
        gap_fte="0", matches=[match("same-person", "0.5")])
    result = prepare_sourcing([interval(half, half | {"id": "other-demand", "plan_id": "other-plan"})], [])
    assert len(result["rows"]) == 2
    assert all(row["gap_quantity"] == 0 and row["sourcing_by"] is None for row in result["rows"])
    assert result["missing"] == []


@pytest.mark.parametrize("field,value", [("account_id", "other-account"), ("plan_id", "other-plan")])
def test_stable_demand_identity_cannot_change_owning_source_between_intervals(field, value):
    with pytest.raises(ValueError):
        prepare_sourcing([interval(source()), interval(source(**{field: value}),
            start="2026-12-01", end="2027-01-01")], [rule()])


def test_duplicate_demand_with_different_metadata_is_still_duplicate():
    with pytest.raises(ValueError):
        prepare_sourcing([interval(source(), source(account_id="other-account"))], [rule()])


def test_cost_and_named_private_data_are_not_echoed_at_any_nested_level():
    private = "never-publish-private-identity"
    row = source(quantity=2, retained_quantity=1, incremental_quantity=1,
        matched_fte="1", gap_fte="1", matches=[match(private, continuity=True)],
        retained_person_ids=[private], salary="90000", cost_rate="99", bill_rate="123",
        commercial_snapshot={"private": private}, missing=[f"continuity:{private}"])
    data = [interval(row)]
    data[0]["overcommitted_person_ids"] = [private]
    original = deepcopy(data)
    result = prepare_sourcing(data, [rule()])
    assert private not in repr(result)
    assert not {"salary", "cost_rate", "bill_rate", "commercial_snapshot", "matches",
        "retained_person_ids", "overcommitted_person_ids"} & result["rows"][0].keys()
    assert data == original and result["is_reservation"] is False


def test_fractional_slots_remain_exact_under_tiny_decimal_context():
    row = source(quantity=3, retained_quantity=1, incremental_quantity=2,
        required_fte="0.9999999999999999999999999999",
        matched_fte="0.3333333333333333333333333333",
        gap_fte="0.6666666666666666666666666666",
        matches=[match("retained", "0.3333333333333333333333333333", continuity=True)])
    with localcontext() as context:
        context.prec = 2
        output, = prepare_sourcing([interval(row)], [rule()])["rows"]
    assert output["gap_fte"] == Decimal("0.6666666666666666666666666666")
    assert output["incremental_gap_quantity"] == 2 and output["continuity_gap_quantity"] == 0
