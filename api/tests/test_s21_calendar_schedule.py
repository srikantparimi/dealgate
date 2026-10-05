from dataclasses import FrozenInstanceError, replace
from datetime import date
from decimal import Decimal, localcontext

import pytest

from app.gm.calendar import (
    CalendarOverride,
    DayHours,
    StaffingAssignment,
    WorkCalendar,
    monthly_staffing_schedule,
)
from app.gm.engine import SowSpec, compute_gm

D = Decimal
WORK = DayHours(D("8"), D("8"), D("8"))
OFF = DayHours(D("0"), D("0"), D("0"))
PAID_HOLIDAY = DayHours(D("0"), D("0"), D("8"))
HOLIDAYS = (
    "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01",
    "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18", "2027-07-05",
)


def calendar(**changes):
    defaults = dict(
        calendar_id="synthetic-client", version="1", timezone="America/New_York",
        coverage_start=date(2026, 1, 1), coverage_end=date(2027, 12, 31),
        week=(WORK, WORK, WORK, WORK, WORK, OFF, OFF),
        overrides=tuple(
            CalendarOverride(date.fromisoformat(day), PAID_HOLIDAY, "Paid holiday")
            for day in HOLIDAYS
        ),
    )
    return WorkCalendar(**(defaults | changes))


def assignment(**changes):
    defaults = dict(
        assignment_id="staff-1", source_id="sow-1", source_version="3",
        component_id="hourly-1", profile_version="staffing-v1", policy_version="gm-v1",
        role="Engineer", location="US", timezone="America/New_York", currency="USD",
        quantity=10, allocation=D("1"), calendar=calendar(),
        bill_rate=D("100"), cost_rate=D("60"), rate_version="rates-1",
        cost_version="loaded-hourly-1",
    )
    return StaffingAssignment(**(defaults | changes))


def schedule(item=None, start=date(2026, 10, 1), end=date(2027, 7, 31)):
    return monthly_staffing_schedule(item or assignment(), term_start=start, term_end=end)


def test_oracle_b_exact_monthly_quantities_and_economics():
    rows = schedule()
    # Independent directive constants, not produced by the calendar implementation.
    assert [r.billable_hours for r in rows] == list(map(D, (
        "1680", "1520", "1760", "1520", "1520", "1840", "1760", "1600", "1680", "1680",
    )))
    assert [r.paid_hours for r in rows] == list(map(D, (
        "1760", "1680", "1840", "1680", "1600", "1840", "1760", "1680", "1760", "1760",
    )))
    assert [r.revenue for r in rows] == list(map(D, (
        "168000", "152000", "176000", "152000", "152000", "184000", "176000",
        "160000", "168000", "168000",
    )))
    assert [r.cost for r in rows] == list(map(D, (
        "105600", "100800", "110400", "100800", "96000", "110400", "105600",
        "100800", "105600", "105600",
    )))
    assert sum(r.scheduled_hours for r in rows) == D("16560")
    assert sum(r.billable_hours for r in rows) == D("16560")
    assert sum(r.paid_hours for r in rows) == D("17360")
    assert [compute_gm(SowSpec("staff_aug", (r.as_resource_input(),))).gm_blended
            for r in rows] == list(map(D, (
        "0.3714285714285714285714285714", "0.3368421052631578947368421053",
        "0.3727272727272727272727272727", "0.3368421052631578947368421053",
        "0.3684210526315789473684210526", "0.4", "0.4", "0.37",
        "0.3714285714285714285714285714", "0.3714285714285714285714285714",
    )))
    outcome = compute_gm(SowSpec("staff_aug", tuple(r.as_resource_input() for r in rows)))
    assert outcome.revenue_total == D("1656000")
    assert outcome.cost_total == D("1041600")
    assert outcome.gm_blended == D("0.3710144927536231884057971014")
    assert outcome.passes["US"] is True
    assert all(r.complete for r in rows)
    holiday = next(d for d in rows[0].days if d.day == date(2026, 10, 12))
    assert (holiday.scheduled_hours, holiday.billable_hours, holiday.paid_hours) == (
        D("0"), D("0"), D("80"),
    )
    assert holiday.reason == "Paid holiday"


def test_partial_periods_clip_inclusively_and_apply_quantity_allocation_once():
    item = assignment(quantity=3, allocation=D("0.5"), start=date(2026, 10, 29),
                      end=date(2026, 11, 2))
    rows = schedule(item, date(2026, 10, 30), date(2026, 11, 30))
    assert [(r.period_start, r.period_end) for r in rows] == [
        (date(2026, 10, 30), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 2)),
    ]
    assert [(r.billable_hours, r.revenue, r.cost) for r in rows] == [
        (D("12"), D("1200"), D("720")), (D("12"), D("1200"), D("720")),
    ]
    assert rows[0].as_resource_input().utilization == D("1")
    assert schedule(item, date(2027, 1, 1), date(2027, 1, 31)) == ()


def test_mixed_locations_retain_independent_calendars_and_component_floors():
    us = schedule(assignment(quantity=1), date(2026, 10, 12), date(2026, 10, 12))[0]
    india = schedule(assignment(
        assignment_id="staff-2", component_id="hourly-2", location="India", quantity=2,
        allocation=D("0.5"), timezone="Asia/Kolkata", cost_rate=D("55"),
        calendar=calendar(calendar_id="india-client", timezone="Asia/Kolkata", overrides=()),
    ), date(2026, 10, 12), date(2026, 10, 12))[0]
    result = compute_gm(SowSpec("staff_aug", (us.as_resource_input(), india.as_resource_input())))
    assert result.revenue_by_location == {"US": D("0"), "India": D("800")}
    assert result.cost_by_location == {"US": D("480"), "India": D("440")}
    assert result.passes == {"US": None, "India": False}
    assert india.month == date(2026, 10, 1)


def test_msp_arbitrary_week_pattern_and_holiday_coverage():
    shift = DayHours(D("12"), D("10"), D("12"))
    cal = calendar(week=(OFF, OFF, OFF, OFF, OFF, shift, shift), overrides=(
        CalendarOverride(date(2026, 10, 12), WORK, "Contract holiday coverage"),
    ))
    row = schedule(assignment(calendar=cal, quantity=2, allocation=D("0.25")),
                   date(2026, 10, 10), date(2026, 10, 12))[0]
    assert (row.scheduled_hours, row.billable_hours, row.paid_hours) == (D("16"), D("14"), D("16"))
    assert (row.revenue, row.cost) == (D("1400"), D("960"))


@pytest.mark.parametrize("field", [
    "calendar", "cost_rate", "bill_rate", "currency", "location", "rate_version", "cost_version",
])
def test_missing_inputs_are_unresolved_and_cannot_be_adapted_as_complete(field):
    row = schedule(assignment(**{field: None}))[0]
    assert not row.complete
    assert field in {m.field for m in row.missing}
    if field == "calendar":
        assert row.scheduled_hours is row.billable_hours is row.paid_hours is None
        assert row.revenue is row.cost is None
    if field == "cost_rate":
        assert row.revenue == D("168000")
        assert row.cost is None
    with pytest.raises(ValueError, match="incomplete"):
        row.as_resource_input()


def test_coverage_is_explicit_per_affected_month_not_inferred_from_holiday_list():
    cal = calendar(coverage_end=date(2026, 12, 31), overrides=tuple(
        o for o in calendar().overrides if o.day.year == 2026
    ))
    rows = schedule(assignment(calendar=cal), date(2026, 12, 31), date(2027, 1, 1))
    assert rows[0].complete
    assert rows[0].billable_hours == D("80")
    assert rows[1].billable_hours is None
    assert {m.field for m in rows[1].missing} == {"calendar.coverage"}
    partial = schedule(assignment(calendar=replace(cal, coverage_end=date(2026, 12, 30))),
                       date(2026, 12, 29), date(2026, 12, 31))[0]
    assert partial.billable_hours is None


def test_leap_year_and_local_date_boundaries_without_timezone_conversion():
    row = schedule(assignment(quantity=1, calendar=calendar(
        coverage_start=date(2028, 1, 1), coverage_end=date(2028, 12, 31), overrides=(),
    )), date(2028, 2, 28), date(2028, 2, 29))[0]
    assert row.billable_hours == D("16")
    assert [d.day for d in row.days] == [date(2028, 2, 28), date(2028, 2, 29)]


def test_snapshots_are_frozen_and_caller_decimal_precision_does_not_change_results():
    normal = schedule()
    with localcontext() as ctx:
        ctx.prec = 4
        assert schedule() == normal
    assert normal[0].assignment.source_version == "3"
    assert normal[0].assignment.calendar.version == "1"
    assert normal[0].calculation_version == "calendar-hours-v1"
    with pytest.raises(FrozenInstanceError):
        normal[0].assignment.quantity = 20


@pytest.mark.parametrize("changes", [
    {"quantity": 0}, {"allocation": D("1.1")}, {"allocation": 0.5},
    {"cost_rate": D("NaN")}, {"bill_rate": D("-1")},
    {"start": date(2027, 1, 2), "end": date(2027, 1, 1)},
    {"timezone": "Asia/Kolkata"},
])
def test_invalid_assignment_inputs_are_rejected(changes):
    with pytest.raises(ValueError):
        schedule(assignment(**changes))


def test_ambiguous_calendar_overrides_and_inverted_term_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        calendar(overrides=(calendar().overrides[0], calendar().overrides[0]))
    with pytest.raises(ValueError):
        calendar(week=(WORK,))
    with pytest.raises(ValueError):
        schedule(start=date(2026, 10, 2), end=date(2026, 10, 1))


@pytest.mark.parametrize("field", ["currency", "rate_version", "cost_version"])
def test_blank_financial_metadata_remains_unresolved(field):
    row = schedule(assignment(**{field: " "}))[0]
    assert not row.complete
    assert field in {m.field for m in row.missing}
    if field == "currency":
        assert row.revenue is row.cost is None


def test_invalid_timezone_is_rejected_even_when_calendar_and_assignment_match():
    with pytest.raises(ValueError, match="timezone"):
        schedule(assignment(timezone="Unknown/Zone", calendar=calendar(timezone="Unknown/Zone")))


def test_zero_revenue_is_not_assessed_and_dated_quantity_changes_do_not_repeat():
    weekend = schedule(assignment(quantity=1), date(2026, 10, 3), date(2026, 10, 4))[0]
    result = compute_gm(SowSpec("staff_aug", (weekend.as_resource_input(),)))
    assert result.status == "exception"
    assert result.gm_blended is None
    assert result.passes == {}
    first = schedule(assignment(quantity=1, start=date(2026, 10, 1), end=date(2026, 10, 15)))[0]
    second = schedule(assignment(quantity=2, allocation=D("0.5"), start=date(2026, 10, 16),
                                 end=date(2026, 10, 31)))[0]
    assert (first.billable_hours, second.billable_hours) == (D("80"), D("88"))


@pytest.mark.parametrize("value", [D("Infinity"), D("-1"), D("25"), 8.0])
def test_invalid_daily_hours_are_rejected(value):
    with pytest.raises(ValueError):
        DayHours(value, D("8"), D("8"))


@pytest.mark.parametrize("field", ["cost_rate", "bill_rate"])
@pytest.mark.parametrize("rate", [
    D("1000000000000000000000000000000.01"), D("99999999999999999999999999.99"),
])
def test_calendar_rejects_money_truncation_before_exposing_complete_quantities(field, rate):
    row = schedule(assignment(quantity=1, **{field: rate}), date(2026, 10, 1), date(2026, 10, 1))[0]
    assert (row.scheduled_hours, row.billable_hours, row.paid_hours) == (D("8"), D("8"), D("8"))
    assert not row.complete
    assert "precision" in {gap.field for gap in row.missing}
    assert (row.cost if field == "cost_rate" else row.revenue) is None
    with pytest.raises(ValueError, match="incomplete"):
        row.as_resource_input()
