"""Independent local commercial checks, not persisted S21F:T13/T15 acceptance."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest

from app.gm.calendar import CalendarOverride, DayHours, StaffingAssignment, WorkCalendar
from app.gm.commercial import (
    CalendarPricing, FeeAllocation, FixedFee, FxRate, HybridPricing, Milestone,
    MilestonePricing, MSPAdjustment, MSPUsage, PeriodCost, PricingComponent,
    QuantityLine, RecurringFee, RecurringMSP, SharedCostAllocation, StaffingRate,
    TimeAndMaterials, UnitPricing, calculate_component,
)

D = Decimal
OCT, NOV = date(2026, 10, 1), date(2026, 11, 1)
PROFILES = ("fixed_assignment", "recurring_msp", "calendar_staff_aug", "tm",
            "milestone", "unit", "hybrid")


def component(**changes):
    values = dict(
        component_id="qa-fee", version="1", source_id="qa-sow", source_version="3",
        workstream_id="qa-work", profile="fixed_assignment", profile_version="1",
        policy_version="qa-policy", source_evidence=("qa-sow:page-4:table-1",),
        service_start=OCT, service_end=date(2026, 10, 31), timezone="UTC",
        currency="USD", billing_cadence="monthly", cost_basis="Confirmed direct cost plan",
        costs_confirmed=True, costs=(PeriodCost("qa-cost", OCT, "US", D("40")),),
        pricing=FixedFee(D("100"), (FeeAllocation(OCT, "US", D("1")),),
                         "confirmed October service", D("0.01")),
    )
    return PricingComponent(**(values | changes))


def staffing(*, start=OCT, end=date(2026, 10, 31), **changes):
    work, off = DayHours(D("8"), D("8"), D("8")), DayHours(D("0"), D("0"), D("0"))
    values = dict(
        assignment_id="qa-person", source_id="qa-sow", source_version="3",
        component_id="qa-fee", profile_version="1", policy_version="qa-policy",
        role="Engineer", location="US", timezone="UTC", currency="USD",
        quantity=1, allocation=D("1"), bill_rate=None, rate_version=None,
        cost_rate=D("5"), cost_version="loaded-cost-1", start=start, end=end,
        calendar=WorkCalendar("qa-calendar", "2", "UTC", OCT, date(2026, 11, 30),
                              (work,) * 5 + (off,) * 2, (
            CalendarOverride(date(2026, 10, 23), DayHours(D("0"), D("0"), D("8")), "Paid holiday"),
        )),
    )
    return StaffingAssignment(**(values | changes))


def profile_case(profile):
    if profile == "fixed_assignment":
        return component(), D("100"), D("40")
    if profile == "recurring_msp":
        terms = RecurringMSP((RecurringFee("US", D("310")),), "calendar_days", "Support", (
            MSPAdjustment("credit", OCT, "US", "credit", D("10")),
        ), (MSPUsage("tickets", OCT, "US", "ticket", D("7"), D("5"), D("12")),))
        return component(profile=profile, service_start=date(2026, 10, 16), pricing=terms), D("174"), D("40")
    if profile == "calendar_staff_aug":
        terms = CalendarPricing((StaffingRate("qa-person", "hourly", D("10"), "rates-1"),))
        return component(profile=profile, pricing=terms, costs=(), staffing=(staffing(),)), D("1680"), D("880")
    if profile == "tm":
        terms = TimeAndMaterials(D("20"), "hour", (QuantityLine("estimate", OCT, "US", D("8")),),
                                 (QuantityLine("actual", OCT, "US", D("999")),), cap=D("150"),
                                 limit_allocation_basis="proportional_estimate", minor_unit=D("0.01"))
        return component(profile=profile, pricing=terms), D("150"), D("40")
    if profile == "milestone":
        terms = MilestonePricing((Milestone("delivery", date(2026, 10, 31), "US", D("120"),
                                            "Written client acceptance", "invoice-a", "actual-a"),))
        return component(profile=profile, pricing=terms), D("120"), D("40")
    if profile == "unit":
        terms = UnitPricing(D("12.5"), "accepted_point", (QuantityLine("points", OCT, "US", D("10")),),
                            "billable_units")
        return component(profile=profile, pricing=terms), D("125"), D("40")
    a = component(component_id="a", costs=(PeriodCost("cost-a", OCT, "US", D("40")),))
    b = component(component_id="b", costs=(PeriodCost("cost-b", OCT, "US", D("40")),))
    terms = HybridPricing((a, b), (SharedCostAllocation("tools", "a", D("1")),
                                  SharedCostAllocation("tools", "b", D("3"))),
                          "confirmed consumption", D("0.01"))
    return component(profile=profile, pricing=terms, costs=(PeriodCost("tools", OCT, "US", D("20")),)), D("200"), D("100")


@pytest.mark.parametrize("profile", PROFILES)
def test_seven_profiles_match_independent_literal_economics(profile):
    spec, expected_revenue, expected_cost = profile_case(profile)
    result = calculate_component(spec)
    assert result.complete
    assert sum(row.revenue for row in result.rows) == expected_revenue
    assert sum(row.cost for row in result.rows) == expected_cost
    outcome = result.assess()
    assert outcome.status == "ok"
    assert (outcome.revenue_total, outcome.cost_total) == (expected_revenue, expected_cost)
    assert outcome.gm_blended == (expected_revenue - expected_cost) / expected_revenue
    assert calculate_component(replace(spec, billing_cadence="quarterly")).rows == result.rows


@pytest.mark.parametrize("profile", PROFILES)
def test_unknown_cost_never_passes_finance_for_any_profile(profile):
    spec, _, _ = profile_case(profile)
    if profile == "calendar_staff_aug":
        spec = replace(spec, staffing=(replace(spec.staffing[0], cost_rate=None),))
    else:
        spec = replace(spec, costs=(replace(spec.costs[0], amount=None),))
    result = calculate_component(spec)
    assert not result.complete
    assert result.missing
    assert result.assess().status == "incomplete"
    assert result.assess().gm_blended is None
    assert result.assess().passes == {}


def test_company_x_fee_cost_and_weighted_quarters_use_independent_expectations():
    months = tuple(date(y, m, 1) for y, m in ((2026, 11), (2026, 12), (2027, 1),
                                           (2027, 2), (2027, 3), (2027, 4)))
    spec = component(service_start=months[0], service_end=date(2027, 4, 30),
        costs=tuple(PeriodCost(str(month), month, "India", D("35000")) for month in months),
        pricing=FixedFee(D("420000"), tuple(FeeAllocation(month, "India", D("1")) for month in months),
                         "confirmed six equal service months", D("0.01")))
    result = calculate_component(spec)
    assert [(row.revenue, row.cost) for row in result.rows] == [(D("70000"), D("35000"))] * 6
    assert result.assess().gm_blended == D("0.5")
    actual_quarters = {(2026, 4): D("24000"), (2027, 1): D("0"), (2027, 2): D("0")}
    for row in result.rows:
        actual_quarters[(row.month.year, (row.month.month - 1) // 3 + 1)] += row.revenue * D("0.7")
    assert actual_quarters == {(2026, 4): D("122000"), (2027, 1): D("147000"), (2027, 2): D("49000")}


def test_fixed_fee_largest_remainders_conserve_confirmed_cents_and_order():
    weights = (FeeAllocation(OCT, "US", D("2")), FeeAllocation(NOV, "India", D("1")))
    spec = component(service_end=date(2026, 11, 30), costs=(),
                     pricing=FixedFee(D("100.01"), weights, "confirmed 2:1 allocation", D("0.01")))
    result = calculate_component(spec)
    assert [row.revenue for row in result.rows] == [D("66.67"), D("33.34")]
    assert calculate_component(replace(spec, pricing=replace(spec.pricing, allocations=weights[::-1]))).rows == result.rows


@pytest.mark.parametrize("basis,rate,expected", [
    ("hourly", "120", "7200"), ("daily", "960", "7200"), ("monthly", "3100", "1200"),
])
def test_partial_calendar_dates_holiday_and_allocation_apply_once(basis, rate, expected):
    start, end = date(2026, 10, 16), date(2026, 10, 31)
    days = [date.fromordinal(n) for n in range(start.toordinal(), end.toordinal() + 1)]
    paid_days = sum(day.weekday() < 5 for day in days)
    assert paid_days == 11
    person = staffing(start=start, end=end, quantity=3, allocation=D("0.25"), cost_rate=D("33"))
    terms = CalendarPricing((StaffingRate("qa-person", basis, D(rate), "1", D("8"), "calendar_days"),))
    result = calculate_component(component(profile="calendar_staff_aug", pricing=terms, staffing=(person,), costs=()))
    assert result.complete
    row = result.rows[0]
    assert (row.billable_hours, row.paid_hours) == (D("60"), D("66"))
    assert (row.revenue, row.cost) == (D(expected), D("2178"))


def test_hybrid_child_floor_cannot_be_hidden_by_aggregate_or_fx():
    a = component(component_id="a", currency="EUR", costs=(PeriodCost("a-cost", OCT, "US", D("80")),))
    b = component(component_id="b", costs=(PeriodCost("b-cost", OCT, "US", D("90")),),
                  pricing=FixedFee(D("900"), (FeeAllocation(OCT, "US", D("1")),), "confirmed", D("0.01")))
    terms = HybridPricing((a, b), fx_rates=(FxRate("EUR", D("1.25"), "fx-1", date(2026, 9, 30)),))
    result = calculate_component(component(profile="hybrid", pricing=terms, costs=()))
    assert result.complete
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("1025"), D("190"))
    outcome = result.assess()
    assert outcome.passes["US"] is True
    assert outcome.components[0].passes["US"] is False
    assert outcome.requires_ceo
    assert outcome.gm_blended == D("835") / D("1025")
    assert result.children[0].rows[0].revenue == D("100")


@pytest.mark.parametrize("fx", [(), (FxRate("EUR", None, "1", OCT),),
                                (FxRate("EUR", D("1.2"), None, OCT),),
                                (FxRate("EUR", D("1.2"), "1", None),)])
def test_hybrid_unknown_fx_never_becomes_parity(fx):
    child = component(component_id="foreign", currency="EUR")
    result = calculate_component(component(profile="hybrid", costs=(), pricing=HybridPricing((child,), fx_rates=fx)))
    assert not result.complete
    assert result.assess().status == "incomplete"
    assert "fx" in {gap.field for gap in result.missing}


def test_hybrid_duplicate_cost_sources_are_rejected():
    a, b = component(component_id="a"), component(component_id="b")
    result = calculate_component(component(profile="hybrid", costs=(), pricing=HybridPricing((a, b))))
    assert not result.complete
    assert "costs.source_id" in {gap.field for gap in result.missing}


@pytest.mark.parametrize("profile", ["unit", "tm", "recurring_msp"])
def test_hybrid_does_not_count_same_identified_revenue_source_twice(profile):
    source = "qa-sow:page-4:table-1:accepted-usage-row-7"
    quantity = QuantityLine(source, OCT, "US", D("10"))
    if profile == "unit":
        pricing = UnitPricing(D("100"), "ticket", (quantity,), "billable_units")
    elif profile == "tm":
        pricing = TimeAndMaterials(D("100"), "hour", (quantity,))
    else:
        pricing = RecurringMSP((RecurringFee("US", D("0")),), "full_month", "Usage only",
                              usage=(MSPUsage(source, OCT, "US", "ticket", D("10"), D("0"), D("100")),))
    a = component(component_id="a", profile=profile, pricing=pricing, costs=())
    b = replace(a, component_id="b")
    result = calculate_component(component(profile="hybrid", costs=(), pricing=HybridPricing((a, b))))
    assert not result.complete, "The same identified 1000 revenue source appears in both children"
    assert result.assess().status == "incomplete"


def test_normal_partial_month_msp_remains_assessable_before_display_rounding():
    terms = RecurringMSP((RecurringFee("US", D("100")),), "calendar_days", "Support")
    result = calculate_component(component(profile="recurring_msp", service_end=date(2026, 11, 1),
                                           pricing=terms, costs=()))
    assert result.complete
    outcome = result.assess()
    assert outcome.status == "ok", "A recurring decimal from 1/30 is not oversized input"
    # No cents policy is invented: this is the existing engine's 28-digit total.
    assert outcome.revenue_total == D("103.3333333333333333333333333")
    assert outcome.gm_blended == D("1")


def test_partial_month_calendar_lines_remain_assessable_when_aggregated():
    people = tuple(staffing(assignment_id=f"person-{i}", start=OCT, end=OCT) for i in range(4))
    terms = CalendarPricing(tuple(StaffingRate(person.assignment_id, "monthly", D("100"), "1",
                                               proration="calendar_days") for person in people))
    result = calculate_component(component(profile="calendar_staff_aug", pricing=terms, costs=(), staffing=people))
    assert result.complete, "Four valid one-day monthly prorations must not trigger precision overflow"
    assert result.rows[0].revenue == D("12.90322580645161290322580645")
    assert result.rows[0].cost == D("160")
    assert result.assess().status == "ok"


def test_calendar_cost_does_not_silently_discard_minor_units_before_commercial_guard():
    rate = D("1000000000000000000000000000000.01")
    person = staffing(start=OCT, end=OCT, cost_rate=rate)
    with localcontext() as context:
        context.prec = 50
        expected_cost = rate * D("8")
    assert expected_cost == D("8000000000000000000000000000000.08")
    spec = component(costs=(), staffing=(person,), pricing=FixedFee(D("1E32"),
                     (FeeAllocation(OCT, "US", D("1")),), "confirmed", D("0.01")))
    result = calculate_component(spec)
    assert not result.complete, "Unsupported precision must remain unresolved, not lose 0.08 of cost"
    assert result.assess().status == "incomplete"


@pytest.mark.parametrize("consumer", ["policy", "builder", "sandbox"])
def test_commercial_consumer_retains_child_floor_authority(consumer):
    from app.gm.commercial_adapter import compute_commercial
    from app.gm.policy import check_floors
    from app.gm.types import EngagementType
    from app.services.delivery_model import build_compute_response
    from app.services.gm_sandbox import ResolvedPolicy, build_response

    a = component(component_id="a", costs=(PeriodCost("a-cost", OCT, "US", D("80")),))
    b = component(component_id="b", costs=(PeriodCost("b-cost", OCT, "US", D("90")),),
                  pricing=FixedFee(D("900"), (FeeAllocation(OCT, "US", D("1")),), "confirmed", D("0.01")))
    result = compute_commercial(component(profile="hybrid", pricing=HybridPricing((a, b)), costs=()),
                                us_floor=D("0.60"))
    assert result.complete
    assert result.gm_us == D("0.83")
    assert result.gm_outcome.components[0].gm_blended == D("0.2")
    assert result.gm_outcome.requires_ceo
    if consumer == "policy":
        policy = check_floors(result, us_floor_value=D("0.60"))
    elif consumer == "builder":
        policy = build_compute_response(result, us_floor=D("0.60"))["policy"]
    else:
        resolved = ResolvedPolicy(D("0.60"), D("0.50"), None, None, "defaults")
        policy = build_response(EngagementType.FIXED_PRICE, result, resolved)["policy"]
    assert policy["requires_ceo"] is True


@pytest.mark.parametrize("case", ["missing_cost", "unsupported", "zero_revenue"])
@pytest.mark.parametrize("consumer", ["builder", "sandbox"])
def test_commercial_unassessed_response_never_serializes_placeholder_zero(case, consumer):
    from app.gm.commercial_adapter import compute_commercial
    from app.gm.types import EngagementType
    from app.services.delivery_model import build_compute_response
    from app.services.gm_sandbox import ResolvedPolicy, build_response

    spec = component()
    if case == "missing_cost":
        spec = replace(spec, costs=(replace(spec.costs[0], amount=None),))
    elif case == "unsupported":
        spec = replace(spec, profile="unapproved_formula")
    else:
        spec = replace(spec, pricing=replace(spec.pricing, total_fee=D("0")))
    result = compute_commercial(spec)
    assert result.complete is False
    assert result.gm_outcome.status == ("exception" if case == "zero_revenue" else "incomplete")
    assert result.gm_us is result.gm_india is result.gm_blended is None
    if consumer == "builder":
        payload = build_compute_response(result)
    else:
        resolved = ResolvedPolicy(D("0.35"), D("0.50"), None, None, "defaults")
        payload = build_response(EngagementType.FIXED_PRICE, result, resolved)
    assert payload["complete"] is False
    assert payload["missing"]
    assert payload["revenue_us"] is payload["cost_us"] is None
    assert payload["revenue_india"] is payload["cost_india"] is None


@pytest.mark.parametrize("case", ["missing_child", "zero_child"])
def test_adapter_preserves_unassessed_child_without_passing_parent(case):
    from app.gm.commercial_adapter import compute_commercial

    a = component(component_id="a", costs=(PeriodCost("a-cost", OCT, "US", D("40")),))
    b = component(component_id="b", costs=(PeriodCost("b-cost", OCT, "US", D("40")),))
    if case == "missing_child":
        a = replace(a, costs=(replace(a.costs[0], amount=None),))
    else:
        a = replace(a, pricing=replace(a.pricing, total_fee=D("0")))
    result = compute_commercial(component(profile="hybrid", costs=(), pricing=HybridPricing((a, b))))
    status = "incomplete" if case == "missing_child" else "exception"
    assert result.complete is False
    assert result.gm_outcome.status == status
    assert result.gm_outcome.components[0].status == status
    assert result.gm_outcome.components[1].status == "ok"
    assert result.gm_us is result.gm_india is result.gm_blended is None


def test_derived_ratio_does_not_allow_losing_entire_currency_units():
    terms = RecurringMSP((RecurringFee("US", D("100")),), "calendar_days", "One day support", (
        MSPAdjustment("large-overage", OCT, "US", "overage", D("1E30")),
    ))
    with localcontext() as context:
        context.prec = 50
        independent_total = D("1E30") + D("100") / D("31")
    assert independent_total > D("1000000000000000000000000000003")
    result = calculate_component(component(profile="recurring_msp", service_end=OCT,
                                           pricing=terms, costs=()))
    assert not result.complete, "Ratio permission must not discard a whole 3.22+ of revenue"
    assert result.assess().status == "incomplete"
