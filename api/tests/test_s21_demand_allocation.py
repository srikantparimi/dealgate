"""Independent recruiting quantities and global dated capacity expectations."""
from datetime import date
from decimal import Decimal as D

import pytest

from app.gm import demand as engine


def need(identity="need-a", **changes):
    values = dict(id=identity, account_id="account-a", role="Engineer", skills=("python",),
        level="senior", location="US", timezone="America/Los_Angeles", quantity=1,
        allocation=D("1"), start=date(2026, 11, 1), end=date(2026, 11, 30),
        probability=D("0.7"), lifecycle="tentative")
    return engine.Demand(**(values | changes))


def person(identity="person-a", **changes):
    values = dict(person_id=identity, role="Engineer", skills=("python",), level="senior",
        location="US", timezone="America/Los_Angeles", allocation=D("1"),
        start=date(2026, 11, 1), end=date(2026, 12, 31))
    return engine.Capacity(**(values | changes))


def project(needs, people=(), commitments=()):
    return engine.allocate_demand(tuple(needs), tuple(people), tuple(commitments),
        policy_version="exact-capability-start-order-proposal-v1")


def test_seven_people_at_seventy_percent_remain_seven_without_supply():
    view = project([need("us", quantity=2), need("india", quantity=5, location="India",
        timezone="Asia/Kolkata")])
    month = view["months"][0]
    assert month["peak_headcount"] == 7
    assert month["peak_fte"] == D("7")
    assert month["gap_fte"] == D("7")
    assert {row["id"]: row["quantity"] for row in view["intervals"][0]["demands"]} == {"us": 2, "india": 5}


def test_overlapping_accounts_allocate_one_person_once_globally():
    view = project([need("a"), need("b", account_id="account-b")], [person()])
    rows = view["intervals"][0]["demands"]
    assert sum(row["matched_fte"] for row in rows) == D("1")
    assert sum(row["gap_fte"] for row in rows) == D("1")
    assert rows[0]["id"] == "a" and rows[0]["matched_fte"] == D("1")
    assert view["is_reservation"] is False


def test_two_half_time_roles_can_share_one_person_without_weighting_quantity():
    view = project([need("a", allocation=D("0.5")), need("b", allocation=D("0.5"))], [person()])
    month = view["months"][0]
    assert month["peak_headcount"] == 2
    assert month["peak_fte"] == D("1") and month["gap_fte"] == D("0")


def test_retained_half_time_commitment_does_not_free_capacity_for_competing_account():
    commitment = engine.Commitment("person-a", "signed", D("0.5"),
        date(2026, 11, 1), date(2026, 11, 30), "committed")
    view = project([need("signed", allocation=D("0.5"), lifecycle="committed",
        retained_person_ids=("person-a",)), need("other", allocation=D("0.5")),
        need("third", allocation=D("0.5"))], [person()], [commitment])
    rows = {row["id"]: row for row in view["intervals"][0]["demands"]}
    assert rows["signed"]["matched_fte"] == D("0.5")
    assert rows["other"]["matched_fte"] == D("0.5")
    assert rows["third"]["matched_fte"] == D("0")


def test_conflicting_authoritative_commitments_do_not_claim_valid_retained_match():
    commitments = [engine.Commitment("person-a", source, D("0.75"),
        date(2026, 11, 1), date(2026, 11, 30), "committed") for source in ("signed", "other")]
    view = project([need("signed", allocation=D("0.75"), lifecycle="committed",
        retained_person_ids=("person-a",))], [person()], commitments)
    assert view["intervals"][0]["overcommitted_person_ids"] == ["person-a"]
    assert view["intervals"][0]["demands"][0]["gap_fte"] == D("0.75")


def test_quantity_two_requires_two_people_even_for_half_time_slots():
    view = project([need(quantity=2, allocation=D("0.5"))], [person()])
    row = view["intervals"][0]["demands"][0]
    assert row["matched_fte"] == D("0.5") and row["gap_fte"] == D("0.5")


def test_committed_rolloff_releases_capacity_next_day_not_start_of_month():
    commitment = engine.Commitment(person_id="person-a", source_id="signed-project",
        start=date(2026, 11, 1), end=date(2026, 11, 15), allocation=D("1"), status="committed")
    view = project([need()], [person()], [commitment])
    first, second = view["intervals"][:2]
    assert first["start"] == date(2026, 11, 1) and first["end_exclusive"] == date(2026, 11, 16)
    assert first["demands"][0]["gap_fte"] == D("1")
    assert second["start"] == date(2026, 11, 16)
    assert second["demands"][0]["gap_fte"] == D("0")


def test_sequential_teams_are_not_summed_as_concurrent_headcount():
    view = project([need("a", quantity=2, end=date(2026, 11, 15)),
        need("b", quantity=3, start=date(2026, 11, 16))])
    assert view["months"][0]["peak_headcount"] == 3
    assert view["months"][0]["peak_fte"] == D("3")


def test_continuing_six_person_team_is_not_six_new_hires():
    identities = tuple(f"person-{index}" for index in range(6))
    view = project([need(quantity=6, retained_person_ids=identities)], [person(identity) for identity in identities])
    row = view["intervals"][0]["demands"][0]
    assert row["retained_quantity"] == 6 and row["incremental_quantity"] == 0
    assert row["gap_fte"] == 0


@pytest.mark.parametrize("changes", [{"skills": ("java",)}, {"level": "junior"},
    {"location": "India"}, {"timezone": "America/New_York"}])
def test_no_invented_skill_level_or_location_equivalence(changes):
    view = project([need()], [person(**changes)])
    assert view["months"][0]["gap_fte"] == D("1")


def test_missing_capability_is_unresolved_not_an_automatic_match():
    view = project([need(skills=())], [person()])
    row = view["intervals"][0]["demands"][0]
    assert "skills" in row["missing"] and row["matched_fte"] == 0


def test_duplicate_capacity_and_commitment_identity_cannot_inflate_or_double_subtract():
    with pytest.raises(ValueError, match="overlap"):
        project([need()], [person(), person()])
    commitment = engine.Commitment(person_id="person-a", source_id="signed-project",
        start=date(2026, 11, 1), end=date(2026, 11, 15), allocation=D("0.5"), status="reserved")
    with pytest.raises(ValueError, match="duplicate"):
        project([need()], [person()], [commitment, commitment])


def test_inactive_alternative_demand_is_not_added_to_recruiting_total():
    view = project([need("a"), need("b", selected=False), need("c", lifecycle="closed_lost")])
    assert view["months"][0]["peak_headcount"] == 1
    assert {row["id"] for row in view["excluded"]} == {"b", "c"}
