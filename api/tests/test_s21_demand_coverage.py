"""Explicit staffing slot coverage, independent of financial conversion fractions."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.gm.demand import Demand
from app.gm.demand_coverage import DemandCoverage, apply_coverage, validate_coverage


START, END = date(2026, 11, 1), date(2026, 11, 30)


def demand(identity="plan", **changes):
    return Demand(**(dict(id=identity, account_id="account", role="Engineer", skills=("python", "sql"),
        level="Senior", location="US", timezone="America/New_York", quantity=7, allocation=Decimal("0.5"),
        start=START, end=END, probability=Decimal("0.70"), lifecycle="tentative") | changes))


def coverage(**changes):
    return DemandCoverage(**(dict(plan_id="plan", project_id="project", plan_slots=tuple(range(7)),
        project_slots=tuple(range(7)), start=START, end=END) | changes))


def sources():
    return (demand(), demand("project", lifecycle="committed", probability=Decimal("1")))


def test_full_conversion_is_seven_people_not_fourteen_at_seventy_percent():
    original = sources()
    residual = apply_coverage(original, (coverage(),), START, END)
    assert residual == (original[1],)
    assert sum(row.quantity for row in residual) == 7
    assert original[0].quantity == 7
    assert residual[0] is original[1]


def test_partial_slots_and_dates_reduce_only_explicit_covered_interval():
    original = sources()
    mapping = coverage(plan_slots=(1, 4), project_slots=(3, 6), start=date(2026, 11, 10), end=date(2026, 11, 20))
    before = apply_coverage(original, (mapping,), START, date(2026, 11, 9))
    during = apply_coverage(original, (mapping,), date(2026, 11, 10), date(2026, 11, 20))
    after = apply_coverage(original, (mapping,), date(2026, 11, 21), END)
    assert before == original and after == original
    assert [(row.id, row.quantity) for row in during] == [("plan", 5), ("project", 7)]
    assert during[0].allocation == Decimal("0.5") and during[0].probability == Decimal("0.70")


def test_named_continuity_preserves_unremoved_slots_and_stable_demand_identity():
    original = (demand(retained_person_ids=("person-a", "person-b", "person-c")),
        demand("project", lifecycle="committed", retained_person_ids=("person-b",)))
    mapping = coverage(plan_slots=(1, 5), project_slots=(0, 4))
    result = apply_coverage(original, (mapping,), START, END)
    assert result[0].id == "plan" and result[0].quantity == 5
    assert result[0].retained_person_ids == ("person-a", "person-c")
    assert result[1] is original[1]


@pytest.mark.parametrize("project_people", [(), ("someone-else",)])
def test_retained_plan_slot_cannot_disappear_into_unknown_or_different_identity(project_people):
    original = (demand(retained_person_ids=("person-a",)),
        demand("project", lifecycle="committed", retained_person_ids=project_people))
    with pytest.raises(ValueError, match="continuity"):
        validate_coverage(original, (coverage(plan_slots=(0,), project_slots=(0,)),))


def test_unnamed_plan_slot_may_be_filled_by_named_project_hire():
    original = (demand(), demand("project", lifecycle="committed", retained_person_ids=("hired-person",)))
    result = apply_coverage(original, (coverage(plan_slots=(0,), project_slots=(0,)),), START, END)
    assert result[0].quantity == 6 and result[1].retained_person_ids == ("hired-person",)


@pytest.mark.parametrize("updates", [{"plan_slots": (True,)}, {"plan_slots": ("0",)}, {"plan_slots": (0.5,)},
    {"plan_slots": (-1,)}, {"plan_slots": (7,)}, {"project_slots": (7,)},
    {"plan_slots": (0, 0)}, {"plan_slots": ()}, {"plan_slots": (0, 1)}])
def test_invalid_slot_mapping_rejects(updates):
    with pytest.raises(ValueError):
        validate_coverage(sources(), (coverage(**(dict(plan_slots=(0,), project_slots=(0,)) | updates)),))


@pytest.mark.parametrize("field,value", [("account_id", "other"), ("role", "Analyst"), ("skills", ("java",)),
    ("level", "Junior"), ("location", "India"), ("timezone", "Asia/Kolkata"), ("allocation", Decimal("0.6")),
    ("lifecycle", "tentative"), ("selected", False), ("skills", ()), ("level", "")])
def test_mismatched_or_incomplete_replacement_rejects(field, value):
    original = sources()
    with pytest.raises(ValueError):
        validate_coverage((original[0], replace(original[1], **{field: value})), (coverage(),))


@pytest.mark.parametrize("changes", [{"lifecycle": "committed"}, {"lifecycle": "closed_lost"}, {"selected": False}])
def test_inactive_or_committed_plan_cannot_be_covered(changes):
    original = sources()
    with pytest.raises(ValueError):
        validate_coverage((replace(original[0], **changes), original[1]), (coverage(),))


@pytest.mark.parametrize("updates", [{"plan_id": "unknown"}, {"project_id": "unknown"}, {"project_id": "plan"},
    {"start": date(2026, 10, 31)}, {"end": date(2026, 12, 1)}])
def test_unknown_same_or_out_of_bounds_sources_reject(updates):
    with pytest.raises(ValueError):
        validate_coverage(sources(), (coverage(**updates),))


@pytest.mark.parametrize("reuse", ["plan", "project"])
def test_simultaneous_endpoint_slot_reuse_rejects_even_between_different_mappings(reuse):
    first = coverage(plan_slots=(0,), project_slots=(0,), end=date(2026, 11, 15))
    second = coverage(plan_slots=(0 if reuse == "plan" else 1,), project_slots=(0 if reuse == "project" else 1,), start=date(2026, 11, 15))
    with pytest.raises(ValueError, match="overlap"):
        validate_coverage(sources(), (first, second))


def test_adjacent_nonoverlapping_slot_reuse_and_unordered_skills_are_valid():
    first = coverage(end=date(2026, 11, 15))
    second = coverage(start=date(2026, 11, 16))
    original = (demand(skills=("sql", "python")), sources()[1])
    assert apply_coverage(original, (first, second), START, date(2026, 11, 15)) == (original[1],)


def test_application_must_not_cross_coverage_boundary_and_source_ids_must_be_unique():
    with pytest.raises(ValueError, match="interval"):
        apply_coverage(sources(), (coverage(start=date(2026, 11, 15)),), START, END)
    with pytest.raises(ValueError, match="identity"):
        validate_coverage((*sources(), demand()), ())


def test_disjoint_simultaneous_mappings_use_original_slot_indices_before_removal():
    original = (demand(retained_person_ids=("a", "b", "c")),
        demand("project", lifecycle="committed", retained_person_ids=("a", "c")))
    mappings = (coverage(plan_slots=(0,), project_slots=(0,)), coverage(plan_slots=(2,), project_slots=(1,)))
    residual = apply_coverage(original, mappings, START, END)
    assert residual[0].quantity == 5 and residual[0].retained_person_ids == ("b",)
    assert residual[1] is original[1]


def test_full_coverage_is_restored_after_its_inclusive_end_and_input_lists_are_copied():
    slots = list(range(7))
    mapping = coverage(plan_slots=slots, project_slots=slots, end=date(2026, 11, 15))
    slots.clear()
    assert mapping.plan_slots == tuple(range(7))
    assert apply_coverage(sources(), (mapping,), START, date(2026, 11, 15)) == (sources()[1],)
    assert apply_coverage(sources(), (mapping,), date(2026, 11, 16), END) == sources()


@pytest.mark.parametrize("start,end", [(END, START), ("2026-11-01", END), (START, None)])
def test_malformed_inclusive_bounds_reject(start, end):
    with pytest.raises(ValueError):
        coverage(start=start, end=end)


@pytest.mark.parametrize("quantity", [True, 1.5, "7"])
def test_noninteger_source_quantities_reject_before_slot_arithmetic(quantity):
    original = sources()
    object.__setattr__(original[0], "quantity", quantity)
    with pytest.raises(ValueError):
        apply_coverage(original, (coverage(),), START, END)
