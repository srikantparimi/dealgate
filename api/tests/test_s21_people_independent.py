"""Literal recruiting oracles for the pure engine, not People feature acceptance."""

from datetime import date, datetime
from decimal import Decimal as D

import pytest

from app.gm.demand import Capacity, Commitment, Demand, allocate_demand


def demand(identity="demand-a", **changes):
    values = dict(id=identity, account_id="account-a", role="Engineer", skills=("python",),
        level="senior", location="US", timezone="America/Los_Angeles", quantity=1,
        allocation=D("1"), start=date(2026, 11, 1), end=date(2026, 11, 30),
        probability=D("0.70"), lifecycle="tentative")
    return Demand(**(values | changes))


def capacity(identity="person-a", **changes):
    values = dict(person_id=identity, role="Engineer", skills=("python",), level="senior",
        location="US", timezone="America/Los_Angeles", allocation=D("1"),
        start=date(2026, 11, 1), end=date(2026, 11, 30))
    return Capacity(**(values | changes))


def commitment(identity="person-a", source="signed-a", **changes):
    values = dict(person_id=identity, source_id=source, allocation=D("1"),
        start=date(2026, 11, 1), end=date(2026, 11, 30), status="committed")
    return Commitment(**(values | changes))


def allocate(needs, people=(), obligations=()):
    return allocate_demand(tuple(needs), tuple(people), tuple(obligations),
        policy_version="qa-exact-global-proposal-v1")


@pytest.mark.parametrize("probability", [D("0"), D("0.70"), D("1"), None])
def test_company_x_six_month_team_is_seven_people_at_every_probability(probability):
    result = allocate([
        demand("us", quantity=2, end=date(2027, 4, 30), probability=probability),
        demand("india", quantity=5, location="India", timezone="Asia/Kolkata",
            end=date(2027, 4, 30), probability=probability),
    ])
    expected_months = [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1),
        date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
    assert result["months"] == [{"month": month, "peak_headcount": 7,
        "peak_fte": D("7"), "gap_fte": D("7")} for month in expected_months]
    assert result["is_reservation"] is False and result["policy_status"] == "proposal"
    for interval in result["intervals"]:
        rows = {row["id"]: row for row in interval["demands"]}
        assert (rows["us"]["quantity"], rows["india"]["quantity"]) == (2, 5)
        assert (rows["us"]["required_fte"], rows["india"]["required_fte"]) == (D("2"), D("5"))


@pytest.mark.parametrize("reverse", [False, True])
def test_global_priority_and_part_time_budget_are_independent_of_input_order(reverse):
    needs = [demand("a", allocation=D("0.5")),
        demand("b", account_id="account-b", allocation=D("0.5")),
        demand("c", account_id="account-c", allocation=D("0.5"), lifecycle="committed"),
        demand("d", account_id="account-d", allocation=D("0.5"))]
    people = [capacity("person-a"), capacity("person-b", allocation=D("0.5"))]
    if reverse:
        needs.reverse()
        people.reverse()
    result = allocate(needs, people, [commitment("person-b", allocation=D("0.5"))])
    rows = result["intervals"][0]["demands"]
    assert [row["id"] for row in rows] == ["c", "a", "b", "d"]
    assert {row["id"]: row["matched_fte"] for row in rows} == {
        "a": D("0.5"), "b": D("0"), "c": D("0.5"), "d": D("0")}
    assert result["months"] == [{"month": date(2026, 11, 1), "peak_headcount": 4,
        "peak_fte": D("2"), "gap_fte": D("1")}]


def test_already_committed_continuing_team_is_not_subtracted_then_requested_again():
    people = ("one", "two", "three", "four", "five", "six")
    result = allocate([demand("signed-a", quantity=6, lifecycle="committed",
        retained_person_ids=people)], [capacity(key) for key in people],
        [commitment(key, source="signed-a") for key in people])
    row = result["intervals"][0]["demands"][0]
    assert row["retained_quantity"] == 6 and row["incremental_quantity"] == 0
    assert row["required_fte"] == D("6")
    assert row["matched_fte"] == D("6") and row["gap_fte"] == D("0")
    assert {match["person_id"] for match in row["matches"]} == set(people)
    assert all(match["continuity"] for match in row["matches"])


def test_continuity_cannot_consume_capacity_committed_to_a_different_source():
    result = allocate([demand("extension", retained_person_ids=("person-a",))],
        [capacity()], [commitment(source="different-project")])
    row = result["intervals"][0]["demands"][0]
    assert row["matched_fte"] == D("0") and row["gap_fte"] == D("1")
    assert row["missing"] == ["continuity:person-a"]


def test_missing_retained_identity_is_not_replaced_with_unlinked_free_person():
    result = allocate([demand(retained_person_ids=("retained-missing",))], [capacity()])
    row = result["intervals"][0]["demands"][0]
    assert row["matches"] == [] and row["gap_fte"] == D("1")
    assert row["missing"] == ["continuity:retained-missing"]


def test_overlapping_segments_of_one_commitment_are_rejected_not_double_subtracted():
    obligations = [commitment(allocation=D("0.5"), end=date(2026, 11, 20)),
        commitment(allocation=D("0.5"), start=date(2026, 11, 10))]
    with pytest.raises(ValueError):
        allocate([demand(allocation=D("0.5"))], [capacity()], obligations)


def test_adjacent_segments_of_one_commitment_are_allowed_without_double_subtraction():
    obligations = [commitment(allocation=D("0.5"), end=date(2026, 11, 15)),
        commitment(allocation=D("0.5"), start=date(2026, 11, 16))]
    result = allocate([demand(allocation=D("0.5"))], [capacity()], obligations)
    assert [(item["start"], item["end_exclusive"]) for item in result["intervals"]] == [
        (date(2026, 11, 1), date(2026, 11, 16)), (date(2026, 11, 16), date(2026, 12, 1))]
    assert all(item["demands"][0]["gap_fte"] == D("0") for item in result["intervals"])


@pytest.mark.parametrize("selected", [None, "false", 0, 1])
def test_scenario_selection_requires_an_explicit_boolean(selected):
    with pytest.raises(ValueError):
        allocate([demand(selected=selected)])


@pytest.mark.parametrize("field", ["role", "level", "location"])
def test_blank_capability_cannot_be_matched_as_confirmed_information(field):
    result = allocate([demand(**{field: "   "})], [capacity(**{field: "   "})])
    row = result["intervals"][0]["demands"][0]
    assert row["matched_fte"] == D("0") and row["gap_fte"] == D("1")
    assert field in row["missing"]


@pytest.mark.parametrize("identity", [True, 42, "   "])
def test_person_identity_must_be_a_nonblank_stable_text_key(identity):
    with pytest.raises(ValueError):
        capacity(identity)


def test_leap_day_rolloff_and_month_end_use_inclusive_local_dates():
    start, end = date(2028, 2, 28), date(2028, 3, 1)
    result = allocate([demand(start=start, end=end)], [capacity(start=start, end=end)],
        [commitment(start=start, end=date(2028, 2, 29))])
    intervals = result["intervals"]
    assert [(item["start"], item["end_exclusive"]) for item in intervals] == [
        (date(2028, 2, 28), date(2028, 3, 1)), (date(2028, 3, 1), date(2028, 3, 2))]
    assert [item["demands"][0]["gap_fte"] for item in intervals] == [D("1"), D("0")]
    assert result["months"] == [
        {"month": date(2028, 2, 1), "peak_headcount": 1, "peak_fte": D("1"), "gap_fte": D("1")},
        {"month": date(2028, 3, 1), "peak_headcount": 1, "peak_fte": D("1"), "gap_fte": D("0")}]


def test_accepted_final_year_interval_does_not_require_an_unrepresentable_next_month():
    result = allocate([demand(start=date(9999, 12, 29), end=date(9999, 12, 30))])
    assert result["months"] == [{"month": date(9999, 12, 1), "peak_headcount": 1,
        "peak_fte": D("1"), "gap_fte": D("1")}]
    assert result["intervals"][0]["end_exclusive"] == date(9999, 12, 31)


@pytest.mark.parametrize("allocation", [D("0"), D("1.01"), D("NaN"), 0.5])
def test_invalid_allocations_fail_before_any_candidate_is_proposed(allocation):
    with pytest.raises(ValueError):
        demand(allocation=allocation)


@pytest.mark.parametrize("changes", [
    {"start": date(2026, 12, 1)}, {"start": datetime(2026, 11, 1)}, {"end": date.max},
])
def test_invalid_local_intervals_are_rejected(changes):
    with pytest.raises(ValueError):
        demand(**changes)
