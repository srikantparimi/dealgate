"""Conversion participates in the actual global allocation interval engine."""
from datetime import date
from decimal import Decimal

from app.gm.demand import allocate_demand
from tests.test_s21_demand_coverage import coverage, sources


def test_full_staffing_conversion_allocates_seven_not_fourteen():
    result = allocate_demand(sources(), (), (), policy_version="explicit-slot-v1", coverages=(coverage(),))
    assert result["months"] == [{"month": date(2026, 11, 1), "peak_headcount": 7,
        "peak_fte": Decimal("3.5"), "gap_fte": Decimal("3.5")}]
    assert [row["id"] for row in result["intervals"][0]["demands"]] == ["project"]


def test_partial_dates_create_exact_boundaries_and_restore_original_slots():
    mapping = coverage(plan_slots=(0, 3), project_slots=(0, 3),
        start=date(2026, 11, 10), end=date(2026, 11, 20))
    result = allocate_demand(sources(), (), (), policy_version="explicit-slot-v1", coverages=(mapping,))
    assert [(row["start"], row["end_exclusive"], sum(item["quantity"] for item in row["demands"]))
        for row in result["intervals"]] == [
        (date(2026, 11, 1), date(2026, 11, 10), 14),
        (date(2026, 11, 10), date(2026, 11, 21), 12),
        (date(2026, 11, 21), date(2026, 12, 1), 14)]
    assert result["months"][0]["peak_headcount"] == 14
