"""Independent cost-free source projection boundaries, not publication acceptance."""

import hashlib
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest

from app.gm.calendar import DayHours, StaffingAssignment, WorkCalendar
from app.gm.commercial import FeeAllocation, FixedFee, HybridPricing, PricingComponent, calculate_component
from app.gm.demand_source import line_key, project_staffing


def assignment(component_id="delivery", **changes):
    values = dict(assignment_id="team", source_id="source-one", source_version="source-v1",
        component_id=component_id, profile_version="1", policy_version="policy-v1",
        role="Engineer", location="US", timezone="America/Los_Angeles", currency="USD",
        quantity=2, allocation=D("0.5"), calendar=None, bill_rate=None, cost_rate=None,
        rate_version=None, cost_version=None)
    return StaffingAssignment(**(values | changes))


def source(component_id="delivery", **changes):
    values = dict(component_id=component_id, version="component-v1", source_id="source-one",
        source_version="source-v1", workstream_id="workstream-one", profile="fixed_assignment",
        profile_version="1", policy_version="policy-v1", source_evidence=("source-one:page-7",),
        service_start=date(2026, 11, 1), service_end=date(2026, 11, 30),
        timezone="America/Los_Angeles", currency="USD", billing_cadence="monthly",
        cost_basis="Confirmed staffing inputs", costs_confirmed=True, costs=(),
        pricing=FixedFee(D("100"), (FeeAllocation(date(2026, 11, 1), "US", D("1")),),
            "confirmed month", D("0.01")), staffing=(assignment(component_id),))
    return PricingComponent(**(values | changes))


def hybrid(children, component_id="root", **changes):
    return source(component_id, profile="hybrid", staffing=(), pricing=HybridPricing(tuple(children)), **changes)


def enrichment(component_id="delivery", **changes):
    values = {"skills": ["python"], "level": "senior", "retained_person_ids": [],
        "evidence": ["HR capability confirmation row 2"]}
    return {line_key(component_id, "team"): values | changes}


@pytest.mark.parametrize("field,value", [
    ("source_id", "other-source"), ("source_version", "obsolete-version"),
    ("policy_version", "other-policy"),
])
@pytest.mark.parametrize("nested", [False, True])
def test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context(field, value, nested):
    child = source("child", **{field: value}, staffing=(assignment("child", **{field: value}),))
    parent = hybrid([child])
    if not nested:
        financial = calculate_component(parent)
        assert any(item.field == "components.binding" for item in financial.missing)
    else:
        parent = hybrid([parent], component_id="outer")
    with pytest.raises(ValueError, match="binding"):
        project_staffing(parent, enrichment("child"))


@pytest.mark.parametrize("changes", [
    {"service_start": date(2026, 10, 31)}, {"service_end": date(2026, 12, 1)},
])
def test_child_staffing_outside_confirmed_package_term_is_not_published_as_complete(changes):
    parent = hybrid([source("child", **changes)])
    financial = calculate_component(parent)
    assert any(item.field == "components.binding" for item in financial.missing)
    with pytest.raises(ValueError, match="binding"):
        project_staffing(parent, enrichment("child"))


def test_in_range_child_specific_dates_are_not_forced_to_equal_parent_dates():
    child = source("child", service_start=date(2026, 11, 10), service_end=date(2026, 11, 20))
    result = project_staffing(hybrid([child]), enrichment("child"))
    row, = result["lines"]
    assert (row["start_date"], row["end_date"]) == (date(2026, 11, 10), date(2026, 11, 20))
    assert result["missing"] == []


def test_mixed_currency_and_timezone_do_not_require_financial_fx_to_count_people():
    india = source("india", currency="INR", timezone="Asia/Kolkata", pricing=None,
        staffing=(assignment("india", currency="INR", timezone="Asia/Kolkata", location="India", quantity=5),))
    us = source("us", pricing=None)
    result = project_staffing(hybrid([us, india]), enrichment("us") | enrichment("india"))
    assert result["missing"] == []
    assert [(row["location"], row["timezone"], row["quantity"]) for row in result["lines"]] == [
        ("US", "America/Los_Angeles", 2), ("India", "Asia/Kolkata", 5)]


@pytest.mark.parametrize("evidence", [(), ("   ",)])
def test_manual_capability_evidence_does_not_replace_missing_source_staffing_evidence(evidence):
    result = project_staffing(source(source_evidence=evidence), enrichment())
    assert "component:delivery:source_evidence" in result["missing"]
    assert result["lines"][0]["quantity"] == 2


def test_duplicate_manual_skill_keys_are_rejected_as_noncanonical_enrichment():
    with pytest.raises(ValueError, match="skills"):
        project_staffing(source(), enrichment(skills=["python", "python"]))


@pytest.mark.parametrize("changes", [{"skills": ["python"]}, {"level": "senior"},
    {"retained_person_ids": ["retained-one"]}])
def test_each_manual_capability_or_continuity_change_requires_its_own_evidence(changes):
    manual = {line_key("delivery", "team"): changes}
    with pytest.raises(ValueError, match="evidence"):
        project_staffing(source(), manual)


def test_zero_allocation_and_unknown_location_remain_distinct_from_missing_assignment():
    result = project_staffing(source(staffing=(assignment(allocation=D("0"), location=None),)), enrichment())
    row, = result["lines"]
    assert row["quantity"] == 2 and row["allocation"] == D("0") and row["location"] is None
    assert set(row["missing"]) == {"allocation", "location"}
    absent = project_staffing(source(staffing=()))
    assert absent == {"lines": [], "missing": ["component:delivery:staffing"]}


def test_calendar_coverage_is_not_invented_as_an_unknown_service_term():
    hours = DayHours(D("8"), D("8"), D("8"))
    calendar = WorkCalendar("explicit-calendar", "v1", "America/Los_Angeles",
        date(2028, 2, 1), date(2028, 3, 31), (hours,) * 7)
    original = source(service_start=None, service_end=None,
        staffing=(assignment(calendar=calendar),))
    row, = project_staffing(original, enrichment())["lines"]
    assert row["start_date"] is None and row["end_date"] is None
    assert set(row["missing"]) == {"start_date", "end_date"}


def test_leap_day_and_partial_assignment_bound_preserve_inclusive_source_dates():
    original = source(service_start=date(2028, 2, 28), service_end=date(2028, 3, 1),
        staffing=(assignment(start=date(2028, 2, 29)),))
    row, = project_staffing(original, enrichment())["lines"]
    assert (row["start_date"], row["end_date"]) == (date(2028, 2, 29), date(2028, 3, 1))
    assert row["quantity"] == 2 and row["allocation"] == D("0.5")


def test_output_and_enrichment_lists_do_not_mutate_immutable_staffing_or_each_other():
    original = source(staffing=(assignment(allocation=D("0.123456789012345678901")),))
    manual = enrichment(retained_person_ids=["retained-one"])
    before_source, before_manual = deepcopy(original), deepcopy(manual)
    result = project_staffing(original, manual)
    row = result["lines"][0]
    assert row["allocation"] == D("0.123456789012345678901")
    row["skills"].append("new-output-only")
    row["retained_person_ids"].clear()
    row["evidence"].append("output evidence")
    assert original == before_source and manual == before_manual
    assert project_staffing(original, manual)["lines"][0]["skills"] == ["python"]


def test_stable_structured_identity_does_not_include_mutable_versions():
    expected = hashlib.sha256(b'["delivery","team"]').hexdigest()
    original = source()
    newer = replace(original, version="component-v2", source_version="source-v2",
        staffing=(replace(original.staffing[0], source_version="source-v2"),))
    assert project_staffing(original)["lines"][0]["line_key"] == expected
    assert project_staffing(newer)["lines"][0]["line_key"] == expected
    assert line_key("delivery:team", "one") != line_key("delivery", "team:one")


@pytest.mark.parametrize("profile", ["unsupported", "", "calendar_staffing"])
def test_unsupported_profile_is_not_relabelled_as_a_supported_delivery_model(profile):
    with pytest.raises(ValueError, match="unsupported"):
        project_staffing(source(profile=profile))


def test_projection_has_no_financial_fields_even_when_authoritative_rates_are_present():
    result = project_staffing(source(staffing=(assignment(bill_rate=D("200"), cost_rate=D("90"),
        rate_version="approved-rate", cost_version="approved-cost"),)), enrichment())
    assert set(result["lines"][0]) == {"line_key", "component_id", "assignment_id", "role",
        "skills", "level", "location", "timezone", "quantity", "allocation", "start_date", "end_date",
        "delivery_model", "retained_person_ids", "evidence", "missing"}
