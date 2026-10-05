"""Independent cost-free recruiting projection expectations, FC-07/T22."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.gm.commercial import HybridPricing
from app.gm.demand_source import line_key, project_staffing
from tests.test_s21_commercial_profiles import component, staffing


def confirmed_enrichment(key):
    return {key: {"skills": ["python"], "level": "Senior", "retained_person_ids": [], "evidence": ["HR reviewed skill profile"]}}


def test_literal_company_x_seven_people_are_not_probability_weighted():
    source = component(staffing=(
        staffing(assignment_id="us-two", quantity=2, allocation=Decimal("1")),
        staffing(assignment_id="india-five", location="India", quantity=5, allocation=Decimal("1")),
    ))
    enriched = confirmed_enrichment(line_key("build", "us-two")) | confirmed_enrichment(line_key("build", "india-five"))
    result = project_staffing(source, enriched)
    assert result["missing"] == []
    assert [(line["location"], line["quantity"]) for line in result["lines"]] == [("US", 2), ("India", 5)]
    assert sum(line["quantity"] for line in result["lines"]) == 7
    assert all(line["allocation"] == Decimal("1") for line in result["lines"])
    assert all(line["start_date"] == date(2026, 11, 1) and line["end_date"] == date(2027, 4, 30) for line in result["lines"])
    assert "cost_rate" not in str(result) and "bill_rate" not in str(result)


@pytest.mark.parametrize("profile", ["fixed_assignment", "recurring_msp", "calendar_staff_aug", "tm", "milestone", "unit"])
def test_projection_does_not_require_financial_completeness_for_any_staffed_profile(profile):
    source = component(profile=profile, pricing=None, costs=(), costs_confirmed=False, staffing=(staffing(),))
    row, = project_staffing(source)["lines"]
    assert row["delivery_model"] == profile
    assert row["quantity"] == 2 and row["allocation"] == Decimal("0.5")
    assert row["skills"] == [] and row["level"] == ""
    assert {"skills", "level"} <= set(row["missing"])


def test_hybrid_projects_each_component_once_and_rejects_duplicate_components():
    child = component(component_id="child", staffing=(staffing(component_id="child"),))
    parent = component(profile="hybrid", staffing=(), pricing=HybridPricing((child,)))
    result = project_staffing(parent)
    assert len(result["lines"]) == 1
    assert result["lines"][0]["component_id"] == "child"
    with pytest.raises(ValueError, match="component"):
        project_staffing(replace(parent, pricing=HybridPricing((child, child))))


@pytest.mark.parametrize("field", ["source_id", "source_version", "component_id", "profile_version", "policy_version", "currency", "timezone"])
def test_foreign_assignment_binding_is_rejected(field):
    value = "America/Chicago" if field == "timezone" else "foreign"
    row = staffing(calendar=None, **{field: value})
    with pytest.raises(ValueError, match="binding"):
        project_staffing(component(staffing=(row,)))


def test_duplicate_assignment_is_rejected():
    row = staffing()
    with pytest.raises(ValueError, match="assignment"):
        project_staffing(component(staffing=(row, row)))


def test_keys_are_collision_safe_and_stable_across_versions():
    assert line_key("a:b", "c") != line_key("a", "b:c")
    old = component(staffing=(staffing(),))
    new = replace(old, version="3", source_version="source-v3", staffing=(replace(old.staffing[0], source_version="source-v3"),))
    assert project_staffing(old)["lines"][0]["line_key"] == project_staffing(new)["lines"][0]["line_key"]


def test_unknown_dates_and_absent_staffing_are_not_zero_demand():
    result = project_staffing(component(staffing=()))
    assert result["lines"] == [] and result["missing"]
    line, = project_staffing(component(service_start=None, service_end=None, staffing=(staffing(),)))["lines"]
    assert line["start_date"] is None and line["end_date"] is None
    assert {"start_date", "end_date"} <= set(line["missing"])


def test_assignment_dates_and_explicit_continuity_are_retained_without_source_mutation():
    original = component(staffing=(staffing(start=date(2026, 12, 1), end=date(2027, 1, 15)),))
    enrichment = confirmed_enrichment(line_key("build", "team-1"))
    enrichment[line_key("build", "team-1")]["retained_person_ids"] = ["person-a"]
    row, = project_staffing(original, enrichment)["lines"]
    assert row["start_date"] == date(2026, 12, 1) and row["end_date"] == date(2027, 1, 15)
    assert row["retained_person_ids"] == ["person-a"]
    assert row["evidence"] == ["sow-x:page-2", "HR reviewed skill profile"]
    assert original.source_evidence == ("sow-x:page-2",)


@pytest.mark.parametrize("key", ["quantity", "allocation", "role", "probability", "cost_rate", "salary", "bill_rate", "delivery_model", "start_date"])
def test_enrichment_cannot_override_source_or_inject_financial_fields(key):
    with pytest.raises(ValueError, match="enrichment"):
        project_staffing(component(staffing=(staffing(),)), {line_key("build", "team-1"): {key: "0.7"}})


def test_unknown_enrichment_and_invalid_continuity_fail_explicitly():
    source = component(staffing=(staffing(),))
    with pytest.raises(ValueError, match="enrichment"):
        project_staffing(source, {"unknown": {"skills": ["python"]}})
    for people in (["p", "p"], ["p1", "p2", "p3"], [""]):
        with pytest.raises(ValueError, match="retained"):
            project_staffing(source, {line_key("build", "team-1"): {"retained_person_ids": people}})


def test_assignment_period_uses_same_inclusive_service_intersection_as_calendar():
    source = component(staffing=(staffing(start=date(2026, 10, 1), end=date(2027, 5, 1)),))
    row, = project_staffing(source)["lines"]
    assert (row["start_date"], row["end_date"]) == (date(2026, 11, 1), date(2027, 4, 30))
    outside = replace(source, staffing=(staffing(start=date(2027, 5, 1), end=date(2027, 6, 1)),))
    row, = project_staffing(outside)["lines"]
    assert row["start_date"] is None and row["end_date"] is None
    assert "service_period" in row["missing"]


def test_enrichment_requires_evidence_for_manual_capabilities():
    with pytest.raises(ValueError, match="evidence"):
        project_staffing(component(staffing=(staffing(),)), {
            line_key("build", "team-1"): {"skills": ["python"], "level": "Senior"},
        })


@pytest.mark.parametrize("value", [None, "python", [""], ["python", 4]])
def test_invalid_skill_collections_are_rejected(value):
    with pytest.raises(ValueError, match="skills"):
        project_staffing(component(staffing=(staffing(),)), {
            line_key("build", "team-1"): {"skills": value, "evidence": ["HR source"]},
        })


def test_same_assignment_name_in_distinct_components_remains_unambiguous():
    left = component(component_id="left", staffing=(staffing(component_id="left"),))
    right = component(component_id="right", staffing=(staffing(component_id="right"),))
    source = component(profile="hybrid", staffing=(), pricing=HybridPricing((left, right)))
    result = project_staffing(source)
    assert len(result["lines"]) == 2
    assert len({row["line_key"] for row in result["lines"]}) == 2
    assert [row["assignment_id"] for row in result["lines"]] == ["team-1", "team-1"]


def test_unresolved_location_and_zero_allocation_stay_explicitly_incomplete():
    source = component(staffing=(staffing(location=None, allocation=Decimal("0")),))
    row, = project_staffing(source)["lines"]
    assert row["location"] is None and row["allocation"] == Decimal("0")
    assert {"location", "allocation"} <= set(row["missing"])
    assert row["quantity"] == 2


def test_unstaffed_hybrid_child_remains_visible_as_missing_source():
    staffed = component(component_id="staffed", staffing=(staffing(component_id="staffed"),))
    absent = component(component_id="unstaffed", staffing=())
    source = component(profile="hybrid", staffing=(), pricing=HybridPricing((staffed, absent)))
    result = project_staffing(source)
    assert len(result["lines"]) == 1
    assert "component:unstaffed:staffing" in result["missing"]
