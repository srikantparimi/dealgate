from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest

from app.gm.commercial import (
    PRICING_PROFILES,
    CalendarPricing,
    FeeAllocation,
    FixedFee,
    FxRate,
    HybridPricing,
    Milestone,
    MilestonePricing,
    MSPAdjustment,
    MSPUsage,
    PeriodCost,
    PricingComponent,
    QuantityLine,
    RecurringFee,
    RecurringMSP,
    StaffingRate,
    SharedCostAllocation,
    TimeAndMaterials,
    UnitPricing,
    calculate_component,
)
from app.gm.calendar import CalendarOverride, DayHours, StaffingAssignment, WorkCalendar
from app.gm.commercial_adapter import compute_commercial, to_template_result
from app.gm.engine import DirectCost, SowSpec, compute_gm
from app.gm.types import TemplateResult

D = Decimal
MONTHS = tuple(date(y, m, 1) for y, m in (
    (2026, 11), (2026, 12), (2027, 1), (2027, 2), (2027, 3), (2027, 4),
))


def component(**changes):
    values = dict(
        component_id="build", version="1", source_id="sow-x", source_version="2",
        workstream_id="delivery-x", profile="fixed_assignment", profile_version="1",
        policy_version="gm-1", source_evidence=("sow-x:page-2",),
        service_start=date(2026, 11, 1), service_end=date(2027, 4, 30),
        timezone="America/New_York", currency="USD", billing_cadence="quarterly",
        cost_basis="Approved monthly delivery cost", costs_confirmed=True,
        costs=tuple(PeriodCost(f"team-{i}", month, "India", D("35000"))
                    for i, month in enumerate(MONTHS)),
        pricing=FixedFee(D("420000"), tuple(FeeAllocation(m, "India", D("1"))
                                           for m in MONTHS), "even service months", D("0.01")),
    )
    return PricingComponent(**(values | changes))


def test_registry_has_all_seven_versioned_profile_definitions():
    assert set(PRICING_PROFILES) == {
        "fixed_assignment", "recurring_msp", "calendar_staff_aug", "tm",
        "milestone", "unit", "hybrid",
    }
    assert PRICING_PROFILES["fixed_assignment"].version == "1"
    assert "allocation_basis" in PRICING_PROFILES["fixed_assignment"].required_fields
    with pytest.raises(TypeError):
        PRICING_PROFILES["arbitrary_formula"] = PRICING_PROFILES["fixed_assignment"]


def test_company_x_fixed_total_is_not_repeated_or_driven_by_billing_cadence():
    result = calculate_component(component())
    assert result.complete
    assert [row.revenue for row in result.rows] == [D("70000")] * 6
    assert [row.cost for row in result.rows] == [D("35000")] * 6
    assert result.assess().revenue_total == D("420000")
    assert result.assess().cost_total == D("210000")
    assert result.assess().gm_blended == D("0.5")
    assert calculate_component(component(billing_cadence="monthly")).rows == result.rows
    assert result.component.source_evidence == ("sow-x:page-2",)
    assert result.calculation_version == "commercial-schedule-v1"


def test_fixed_fee_minor_units_are_conserved_with_deterministic_ties():
    terms = FixedFee(D("0.02"), tuple(FeeAllocation(m, "India", D("1"))
                                    for m in MONTHS[:3]), "confirmed equal", D("0.01"))
    result = calculate_component(component(pricing=terms, costs=()))
    assert [row.revenue for row in result.rows] == [D("0.01"), D("0.01"), D("0.00")]
    assert result.assess().revenue_total == D("0.02")
    with localcontext() as ctx:
        ctx.prec = 4
        assert calculate_component(component(pricing=terms, costs=())).rows == result.rows
    reversed_terms = replace(terms, allocations=tuple(reversed(terms.allocations)))
    assert calculate_component(component(pricing=reversed_terms, costs=())).rows == result.rows


def test_mixed_location_component_floor_is_not_hidden_by_blended_margin():
    month = MONTHS[0]
    pricing = FixedFee(D("2000"), (FeeAllocation(month, "US", D("1")),
                                  FeeAllocation(month, "India", D("1"))),
                       "confirmed split", D("0.01"))
    result = calculate_component(component(pricing=pricing, costs=(
        PeriodCost("us-cost", month, "US", D("400")),
        PeriodCost("india-cost", month, "India", D("550")),
    )))
    assert result.assess().gm_blended == D("0.525")
    assert result.assess().passes == {"US": True, "India": False}
    assert result.assess().requires_ceo


@pytest.mark.parametrize("changes,field", [
    ({"currency": None}, "currency"), ({"service_start": None}, "service_period"),
    ({"costs_confirmed": False}, "costs_confirmed"), ({"cost_basis": None}, "cost_basis"),
    ({"source_evidence": ()}, "source_evidence"),
])
def test_material_unresolved_inputs_never_assess(changes, field):
    draft = component(**changes)
    result = calculate_component(draft)
    assert result.component is draft
    assert not result.complete
    assert field in {m.field for m in result.missing}
    assert result.assess().status == "incomplete"
    assert result.assess().gm_blended is None


def test_missing_cost_is_unknown_and_duplicate_cost_source_is_rejected():
    missing = PeriodCost("cost-1", MONTHS[0], "India", None)
    result = calculate_component(component(costs=(missing,)))
    assert result.rows[0].cost is None
    assert not result.complete
    assert result.assess().passes == {}
    duplicate = calculate_component(component(costs=(missing, missing)))
    assert "costs.source_id" in {m.field for m in duplicate.missing}


@pytest.mark.parametrize("changes", [{"profile": "generated_formula"}, {"profile_version": "999"}])
def test_unsupported_profile_or_version_preserves_draft(changes):
    draft = component(**changes)
    result = calculate_component(draft)
    assert result.status == "unsupported"
    assert result.component is draft
    assert result.rows == ()
    assert result.assess().status == "incomplete"


def test_unconfirmed_allocation_and_outside_service_dates_are_not_guessed():
    terms = component().pricing
    result = calculate_component(component(pricing=replace(terms, allocation_basis=None)))
    assert "allocation_basis" in {m.field for m in result.missing}
    outside = replace(terms, allocations=(FeeAllocation(date(2028, 1, 1), "US", D("1")),))
    assert not calculate_component(component(pricing=outside)).complete


def test_fixed_pricing_requires_decimal_and_confirmed_currency_minor_unit():
    with pytest.raises(ValueError):
        FixedFee(100.0, (), "confirmed", D("0.01"))
    result = calculate_component(component(pricing=replace(component().pricing, total_fee=D("1.005"))))
    assert "total_fee" in {m.field for m in result.missing}


def test_milestones_use_planned_dates_without_treating_invoice_as_recognition():
    terms = MilestonePricing((
        Milestone("design", date(2026, 11, 20), "US", D("12000"), "Design accepted"),
        Milestone("build", date(2027, 2, 10), "US", D("28000"), "Build accepted",
                  approved_invoice_ref="invoice-7"),
    ))
    result = calculate_component(component(profile="milestone", pricing=terms, costs=(
        PeriodCost("delivery", date(2026, 12, 1), "US", D("10000")),
    )))
    assert result.complete
    assert [(r.month, r.revenue, r.cost) for r in result.rows] == [
        (date(2026, 11, 1), D("12000"), D("0")),
        (date(2026, 12, 1), D("0"), D("10000")),
        (date(2027, 2, 1), D("28000"), D("0")),
    ]
    assert result.assess().gm_blended == D("0.75")
    assert result.component.pricing.milestones[1].recognized_revenue_ref is None


def test_milestone_acceptance_and_date_are_required_and_duplicates_do_not_repeat():
    line = Milestone("delivery", None, "US", D("1000"), None)
    result = calculate_component(component(profile="milestone", pricing=MilestonePricing((line, line))))
    assert {"milestones.source_id", "milestones.date", "acceptance_conditions"} <= {
        m.field for m in result.missing
    }
    assert result.assess().status == "incomplete"


def test_billable_story_points_do_not_invent_hours_or_delivery_cost():
    terms = UnitPricing(D("125"), "story_point", (
        QuantityLine("accepted-points", MONTHS[0], "India", D("80")),
    ), "billable_units")
    result = calculate_component(component(profile="unit", pricing=terms, costs=(
        PeriodCost("delivery-plan", MONTHS[0], "India", D("4000")),
    )))
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("10000"), D("4000"))
    assert result.assess().gm_blended == D("0.6")
    ambiguous = calculate_component(component(profile="unit", pricing=replace(
        terms, contractual_basis="delivery_estimate",
    )))
    assert not ambiguous.complete
    assert "contractual_basis" in {m.field for m in ambiguous.missing}


def test_tm_forecast_uses_estimate_not_approved_usage_and_conserves_cap():
    terms = TimeAndMaterials(D("100"), "hour", (
        QuantityLine("estimate-nov", MONTHS[0], "US", D("100")),
        QuantityLine("estimate-dec", MONTHS[1], "US", D("200")),
    ), approved_usage=(QuantityLine("timesheet-v1", MONTHS[0], "US", D("7")),),
        cap=D("20000"), limit_allocation_basis="proportional_estimate", minor_unit=D("0.01"))
    result = calculate_component(component(profile="tm", pricing=terms, costs=()))
    assert [r.revenue for r in result.rows] == [D("6666.67"), D("13333.33")]
    assert result.assess().revenue_total == D("20000")
    assert result.component.pricing.approved_usage[0].quantity == D("7")
    uncapped = calculate_component(component(profile="tm", pricing=replace(terms, cap=D("50000")), costs=()))
    assert uncapped.assess().revenue_total == D("30000")


def test_tm_minimum_requires_confirmed_allocation_and_never_uses_implicit_flat_split():
    terms = TimeAndMaterials(D("100"), "hour", (
        QuantityLine("estimate", MONTHS[0], "US", D("2")),
    ), minimum=D("500"), limit_allocation_basis="proportional_estimate", minor_unit=D("0.01"))
    assert calculate_component(component(profile="tm", pricing=terms, costs=())).rows[0].revenue == D("500")
    unconfirmed = replace(terms, limit_allocation_basis=None)
    assert not calculate_component(component(profile="tm", pricing=unconfirmed)).complete
    zero = replace(terms, estimates=(replace(terms.estimates[0], quantity=D("0")),))
    assert not calculate_component(component(profile="tm", pricing=zero)).complete
    assert not calculate_component(component(profile="tm", pricing=replace(terms, cap=D("100")))).complete


@pytest.mark.parametrize("quantity", [None, D("1")])
def test_unknown_or_duplicate_quantity_sources_do_not_become_zero_or_repeat(quantity):
    line = QuantityLine("usage", MONTHS[0], "US", quantity)
    terms = UnitPricing(D("100"), "unit", (line,) if quantity is None else (line, line), "billable_units")
    result = calculate_component(component(profile="unit", pricing=terms))
    assert not result.complete
    assert result.rows == ()


def test_extreme_fixed_fee_conserves_cents_but_does_not_exceed_gm_precision_silently():
    fee = D("123456789012345678901234567890.01")
    terms = FixedFee(fee, tuple(FeeAllocation(m, "US", D("1")) for m in MONTHS[:3]),
                     "confirmed thirds", D("0.01"))
    result = calculate_component(component(pricing=terms, costs=()))
    assert [r.revenue for r in result.rows] == [
        D("41152263004115226300411522630.01"),
        D("41152263004115226300411522630.00"),
        D("41152263004115226300411522630.00"),
    ]
    assert result.assess().status == "incomplete"
    assert "precision" in {m.field for m in result.assess().missing}


def test_cost_summation_cannot_discard_small_amounts_at_extreme_magnitude():
    result = calculate_component(component(costs=(
        PeriodCost("large", MONTHS[0], "US", D("1E30")),
        PeriodCost("small", MONTHS[0], "US", D("0.01")),
    )))
    assert not result.complete
    assert "precision" in {m.field for m in result.missing}


def test_quantity_multiplication_cannot_discard_value_at_extreme_magnitude():
    terms = UnitPricing(D("100000000000000000000000000000.01"), "unit", (
        QuantityLine("usage", MONTHS[0], "US", D("1")),
    ), "billable_units")
    result = calculate_component(component(profile="unit", pricing=terms, costs=()))
    assert not result.complete
    assert "precision" in {m.field for m in result.missing}


def staffing(**changes):
    work, off = DayHours(D("8"), D("8"), D("8")), DayHours(D("0"), D("0"), D("0"))
    values = dict(
        assignment_id="team-1", source_id="sow-x", source_version="2", component_id="build",
        profile_version="1", policy_version="gm-1", role="Engineer", location="US",
        timezone="America/New_York", currency="USD", quantity=2, allocation=D("0.5"),
        bill_rate=None, rate_version=None, cost_rate=D("60"), cost_version="loaded-1",
        calendar=WorkCalendar("client", "1", "America/New_York", date(2026, 1, 1),
                              date(2027, 12, 31), (work, work, work, work, work, off, off), (
            CalendarOverride(date(2026, 10, 12), DayHours(D("0"), D("0"), D("8")), "Paid holiday"),
        )),
    )
    return StaffingAssignment(**(values | changes))


def test_fixed_fee_calendar_cost_does_not_require_hourly_bill_rate():
    terms = replace(component().pricing, allocations=tuple(FeeAllocation(m, "US", D("1")) for m in MONTHS))
    result = calculate_component(component(pricing=terms, staffing=(staffing(),), costs=()))
    assert result.complete
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("70000"), D("10080"))
    assert result.rows[0].paid_hours == D("168")
    assert result.calendar_rows[0].assignment.bill_rate is None


@pytest.mark.parametrize("basis,rate,expected", [
    ("hourly", "100", "16800"), ("daily", "800", "16800"), ("monthly", "3100", "3100"),
])
def test_calendar_staffing_rates_apply_headcount_allocation_once(basis, rate, expected):
    terms = CalendarPricing((StaffingRate("team-1", basis, D(rate), "rate-2",
                                          hours_per_day=D("8"), proration="calendar_days"),))
    result = calculate_component(component(profile="calendar_staff_aug", pricing=terms,
        service_start=date(2026, 10, 1), service_end=date(2026, 10, 31),
        staffing=(staffing(),), costs=()))
    assert result.complete
    assert (result.rows[0].scheduled_hours, result.rows[0].billable_hours, result.rows[0].paid_hours) == (
        D("168"), D("168"), D("176"),
    )
    assert (result.rows[0].revenue, result.rows[0].cost) == (D(expected), D("10560"))


def test_calendar_monthly_rate_prorates_inclusive_assignment_dates():
    terms = CalendarPricing((StaffingRate("team-1", "monthly", D("3100"), "rate-2",
                                          proration="calendar_days"),))
    result = calculate_component(component(profile="calendar_staff_aug", pricing=terms,
        service_start=date(2026, 10, 1), service_end=date(2026, 10, 31),
        staffing=(staffing(start=date(2026, 10, 16)),), costs=()))
    assert result.rows[0].revenue == D("1600")


def test_msp_proration_credits_and_overage_amounts_are_independent_of_billing():
    terms = RecurringMSP((RecurringFee("US", D("3100")),), "calendar_days", "Weekday support", (
        MSPAdjustment("overage-1", date(2026, 10, 1), "US", "overage", D("200")),
        MSPAdjustment("credit-1", date(2026, 10, 1), "US", "credit", D("50")),
    ))
    spec = component(profile="recurring_msp", pricing=terms, service_start=date(2026, 10, 16),
                     service_end=date(2026, 11, 30), staffing=(staffing(),), costs=())
    result = calculate_component(spec)
    assert result.complete
    assert [r.revenue for r in result.rows] == [D("1750"), D("3100")]
    assert [r.cost for r in result.rows] == [D("5280"), D("10080")]
    assert calculate_component(replace(spec, billing_cadence="annual")).rows == result.rows
    missing_cost = calculate_component(replace(spec, staffing=(staffing(cost_rate=None),)))
    assert not missing_cost.complete
    assert missing_cost.rows[0].cost is None


def test_msp_full_month_requires_explicit_choice_and_rejects_duplicate_adjustments():
    adjustment = MSPAdjustment("credit-1", MONTHS[0], "US", "credit", D("50"))
    terms = RecurringMSP((RecurringFee("US", D("3000")),), None, "Coverage", (adjustment, adjustment))
    result = calculate_component(component(profile="recurring_msp", pricing=terms, costs=()))
    assert not result.complete
    assert {"proration", "adjustments.source_id"} <= {m.field for m in result.missing}


def test_calendar_tm_estimates_use_billable_hours_and_keep_paid_cost_separate():
    terms = TimeAndMaterials(D("100"), "hour", (), calendar_estimates=True)
    result = calculate_component(component(profile="tm", pricing=terms,
        service_start=date(2026, 10, 1), service_end=date(2026, 10, 31),
        staffing=(staffing(),), costs=()))
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("16800"), D("10560"))
    assert result.complete


def test_calendar_assignment_binding_missing_coverage_and_duplicate_costs_block_assessment():
    spec = component(staffing=(staffing(component_id="other-component"),), costs=())
    assert not calculate_component(spec).complete
    unknown = calculate_component(component(staffing=(staffing(calendar=None),), costs=()))
    assert not unknown.complete
    assert unknown.assess().status == "incomplete"
    duplicated = component(staffing=(staffing(), staffing()), costs=())
    assert not calculate_component(duplicated).complete
    manual_duplicate = component(staffing=(staffing(),), costs=(
        PeriodCost("calendar:team-1", MONTHS[0], "US", D("100")),
    ))
    assert not calculate_component(manual_duplicate).complete


def leaf(identifier, fee, cost, **changes):
    return component(component_id=identifier, service_end=date(2026, 11, 30),
                     pricing=FixedFee(D(fee), (FeeAllocation(MONTHS[0], "India", D("1")),),
                                      "confirmed month", D("0.01")),
                     costs=(PeriodCost(f"cost-{identifier}", MONTHS[0], "India", D(cost)),), **changes)


def test_hybrid_allocates_shared_cost_once_and_retains_failing_component_floor():
    terms = HybridPricing((leaf("a", "1000", "900"), leaf("b", "9000", "1000")), (
        SharedCostAllocation("shared-tools", "a", D("1")),
        SharedCostAllocation("shared-tools", "b", D("3")),
    ), "confirmed consumption", D("0.01"))
    result = calculate_component(component(profile="hybrid", pricing=terms, costs=(
        PeriodCost("shared-tools", MONTHS[0], "India", D("100")),
    )))
    assert result.complete
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("10000"), D("2000"))
    assert [child.rows[0].cost for child in result.children] == [D("925"), D("1075")]
    assessment = result.assess()
    assert assessment.gm_blended == D("0.8")
    assert assessment.passes["India"] is True
    assert assessment.components[0].passes["India"] is False
    assert assessment.requires_ceo
    assert terms.components[0].costs[0].amount == D("900")


@pytest.mark.parametrize("case", ["component", "cost", "unallocated", "unknown_child"])
def test_hybrid_duplicate_or_unallocated_sources_remain_unresolved(case):
    a, b = leaf("a", "1000", "100"), leaf("b", "1000", "100")
    shared = ()
    costs = ()
    if case == "component":
        b = a
    elif case == "cost":
        b = replace(b, costs=a.costs)
    elif case == "unallocated":
        costs = (PeriodCost("shared", MONTHS[0], "India", D("100")),)
    else:
        b = replace(b, profile="unknown_formula")
    result = calculate_component(component(profile="hybrid", pricing=HybridPricing((a, b), shared), costs=costs))
    assert not result.complete
    assert result.assess().status == "incomplete"
    assert result.rows == ()


def test_hybrid_fx_is_explicit_versioned_and_child_money_remains_native():
    a, b = leaf("a", "1000", "500"), leaf("b", "1000", "400", currency="EUR")
    terms = HybridPricing((a, b))
    unresolved = calculate_component(component(profile="hybrid", pricing=terms, costs=()))
    assert "fx" in {m.field for m in unresolved.missing}
    terms = replace(terms, fx_rates=(FxRate("EUR", D("2"), "fx-1", date(2026, 10, 31)),))
    result = calculate_component(component(profile="hybrid", pricing=terms, costs=()))
    assert result.complete
    assert (result.rows[0].revenue, result.rows[0].cost) == (D("3000"), D("1300"))
    assert result.children[1].rows[0].revenue == D("1000")
    assert result.component.pricing.fx_rates[0].version == "fx-1"


def test_hybrid_zero_revenue_child_is_not_automatically_assessed():
    terms = HybridPricing((leaf("a", "0", "100"), leaf("b", "1000", "100")))
    result = calculate_component(component(profile="hybrid", pricing=terms, costs=()))
    assert result.complete
    assert result.assess().status == "exception"
    assert result.assess().gm_blended is None


def test_hybrid_shared_calendar_cost_is_allocated_once_with_full_roster_preserved():
    terms = HybridPricing((leaf("a", "20000", "0"), leaf("b", "20000", "0")), (
        SharedCostAllocation("calendar:team-1", "a", D("1")),
        SharedCostAllocation("calendar:team-1", "b", D("1")),
    ), "confirmed effort", D("0.01"))
    result = calculate_component(component(profile="hybrid", pricing=terms,
        service_end=date(2026, 11, 30), staffing=(staffing(location="India"),), costs=()))
    assert result.complete
    assert result.rows[0].cost == D("10080")
    assert [child.rows[0].cost for child in result.children] == [D("5040"), D("5040")]
    assert result.rows[0].paid_hours == D("168")
    assert len(result.calendar_rows) == 1


def test_msp_included_units_and_overages_are_calculated_from_explicit_usage():
    terms = RecurringMSP((RecurringFee("US", D("3000")),), "full_month", "100 tickets/month", usage=(
        MSPUsage("usage-nov", MONTHS[0], "US", "ticket", D("125"), D("100"), D("4")),
        MSPUsage("usage-dec", MONTHS[1], "US", "ticket", D("80"), D("100"), D("4")),
    ))
    result = calculate_component(component(profile="recurring_msp", pricing=terms,
                                            service_end=date(2026, 12, 31), costs=()))
    assert [r.revenue for r in result.rows] == [D("3100"), D("3000")]
    unknown = replace(terms, usage=(replace(terms.usage[0], included_quantity=None),))
    assert not calculate_component(component(profile="recurring_msp", pricing=unknown, costs=())).complete
    duplicate = replace(terms, adjustments=(MSPAdjustment("usage-nov", MONTHS[0], "US", "overage", D("100")),))
    assert not calculate_component(component(profile="recurring_msp", pricing=duplicate, costs=())).complete


def test_all_seven_calculators_are_available_only_after_their_implementations():
    assert all(profile.calculation_available for profile in PRICING_PROFILES.values())


@pytest.mark.parametrize("field,value", [
    ("currency", "EUR"), ("source_version", "3"), ("profile_version", "2"),
    ("policy_version", "gm-2"), ("timezone", "Asia/Kolkata"),
])
def test_assignment_currency_timezone_and_versions_cannot_cross_component_snapshot(field, value):
    original = staffing()
    changes = {field: value}
    if field == "timezone":
        changes["calendar"] = replace(original.calendar, timezone=value)
    result = calculate_component(component(staffing=(replace(original, **changes),), costs=()))
    assert not result.complete
    assert "staffing.binding" in {m.field for m in result.missing}


def test_calendar_cost_plan_requires_explicit_confirmation():
    result = calculate_component(component(staffing=(staffing(),), costs=(), costs_confirmed=False))
    assert not result.complete
    assert "costs_confirmed" in {m.field for m in result.missing}


def test_shared_calendar_source_cannot_also_appear_directly_on_a_child():
    child = replace(leaf("a", "20000", "0"), staffing=(staffing(component_id="a"),))
    terms = HybridPricing((child,), (SharedCostAllocation("calendar:team-1", "a", D("1")),),
                          "confirmed effort", D("0.01"))
    result = calculate_component(component(profile="hybrid", pricing=terms,
        service_end=date(2026, 11, 30), staffing=(staffing(),), costs=()))
    assert not result.complete
    assert "costs.source_id" in {m.field for m in result.missing}


def test_shared_cross_currency_cost_allocation_is_unresolved_without_confirmed_conversion_basis():
    terms = HybridPricing((leaf("a", "1000", "100", currency="EUR"),), (
        SharedCostAllocation("shared", "a", D("1")),
    ), "confirmed effort", D("0.01"), (FxRate("EUR", D("2"), "fx-1", date(2026, 10, 31)),))
    result = calculate_component(component(profile="hybrid", pricing=terms, costs=(
        PeriodCost("shared", MONTHS[0], "India", D("100")),
    )))
    assert not result.complete
    assert "shared_costs.currency" in {m.field for m in result.missing}


@pytest.mark.parametrize("invalid_type", ["zero_revenue", "unsupported"])
def test_existing_hybrid_engine_preserves_unassessable_component_status(invalid_type):
    invalid = (SowSpec("unknown_formula") if invalid_type == "unsupported" else
               SowSpec("fixed_price", contract_price=D("0"), direct_costs=(DirectCost("cost", D("100"), "US"),)))
    valid = SowSpec("fixed_price", contract_price=D("1000"), direct_costs=(DirectCost("cost", D("100"), "US"),))
    result = compute_gm(SowSpec("hybrid", components=(invalid, valid)))
    assert result.status == "exception"
    assert result.gm_blended is None
    assert len(result.components) == 2


def test_hybrid_revenue_source_identity_is_shared_across_pricing_profiles():
    line = QuantityLine("source-row-1", MONTHS[0], "India", D("10"))
    a = replace(leaf("a", "1000", "0"), profile="unit",
                pricing=UnitPricing(D("100"), "unit", (line,), "billable_units"))
    b = replace(leaf("b", "1000", "0"), profile="tm",
                pricing=TimeAndMaterials(D("100"), "hour", (line,)))
    result = calculate_component(component(profile="hybrid", costs=(), pricing=HybridPricing((a, b))))
    assert not result.complete
    assert "revenue.source_id" in {gap.field for gap in result.missing}


def test_hybrid_unused_approved_usage_does_not_conflict_with_distinct_forecast_sources():
    usage = QuantityLine("approved-usage", MONTHS[0], "India", D("7"))
    children = tuple(replace(leaf(identifier, "1000", "0"), profile="tm", pricing=TimeAndMaterials(
        D("100"), "hour", (replace(usage, source_id=f"estimate-{identifier}", quantity=D("10")),),
        approved_usage=(usage,),
    )) for identifier in ("a", "b"))
    result = calculate_component(component(profile="hybrid", costs=(), pricing=HybridPricing(children)))
    assert result.complete
    assert result.assess().revenue_total == D("2000")


def test_ratio_proration_with_credits_and_usage_remains_assessable():
    terms = RecurringMSP((RecurringFee("US", D("100")),), "calendar_days", "Support", (
        MSPAdjustment("credit", MONTHS[0], "US", "credit", D("1")),
    ), (MSPUsage("overage", MONTHS[0], "US", "ticket", D("2"), D("1"), D("100")),))
    result = calculate_component(component(profile="recurring_msp", pricing=terms, costs=(),
                                            service_end=date(2026, 11, 1)))
    assert result.complete
    assert result.rows[0].revenue == D("102.3333333333333333333333333")
    assert result.assess().status == "ok"


def test_hybrid_ratio_revenue_and_fx_keep_existing_calculation_precision():
    terms = RecurringMSP((RecurringFee("India", D("100")),), "calendar_days", "Support")
    a = component(component_id="a", profile="recurring_msp", pricing=terms, costs=(),
                  service_end=date(2026, 11, 1), currency="EUR")
    b = replace(a, component_id="b", currency="USD",
                pricing=replace(terms, fees=(RecurringFee("India", D("3000")),)))
    hybrid = HybridPricing((a, b), fx_rates=(FxRate("EUR", D("2"), "fx-1", date(2026, 11, 1)),))
    result = calculate_component(component(profile="hybrid", pricing=hybrid, costs=()))
    assert result.complete
    assert result.rows[0].revenue == D("106.6666666666666666666666667")
    assert result.assess().status == "ok"


def test_ratio_revenue_does_not_relax_cost_precision_guard():
    terms = RecurringMSP((RecurringFee("US", D("100")),), "calendar_days", "Support")
    result = calculate_component(component(profile="recurring_msp", pricing=terms,
        service_end=date(2026, 11, 1), costs=(
            PeriodCost("large", MONTHS[0], "US", D("1E30")),
            PeriodCost("small", MONTHS[0], "US", D("0.01")),
        )))
    assert not result.complete
    assert "precision" in {gap.field for gap in result.missing}


def test_commercial_adapter_keeps_authority_values_and_component_floor_failure():
    spec = component(profile="hybrid", pricing=HybridPricing((
        leaf("a", "1000", "900"), leaf("b", "9000", "1000"),
    )), costs=())
    schedule = calculate_component(spec)
    result = to_template_result(schedule)
    assert isinstance(result, TemplateResult)
    assert result.commercial_schedule is schedule
    assert result.complete
    assert (result.revenue_india, result.cost_india, result.gm_india, result.gm_blended) == (
        D("10000"), D("1900"), D("0.81"), D("0.81"),
    )
    assert result.gm_outcome.status == "ok"
    assert result.gm_outcome.passes["India"] is True
    assert result.gm_outcome.components[0].passes["India"] is False
    assert result.gm_outcome.requires_ceo
    assert result.finance_summary is None


@pytest.mark.parametrize("case,expected_status", [
    ("missing_cost", "incomplete"), ("unsupported", "incomplete"),
    ("zero_revenue", "exception"), ("zero_child", "exception"), ("missing_child", "incomplete"),
])
def test_commercial_adapter_retains_unassessed_status_and_reasons(case, expected_status):
    spec = leaf("a", "1000", "100")
    if case == "missing_cost":
        spec = replace(spec, costs=(replace(spec.costs[0], amount=None),))
    elif case == "unsupported":
        spec = replace(spec, profile="unapproved_formula")
    elif case == "zero_revenue":
        spec = replace(spec, pricing=replace(spec.pricing, total_fee=D("0")))
    elif case == "zero_child":
        spec = component(profile="hybrid", pricing=HybridPricing((
            leaf("a", "0", "100"), leaf("b", "1000", "100"),
        )), costs=())
    else:
        spec = component(profile="hybrid", pricing=HybridPricing((
            replace(spec, costs=(replace(spec.costs[0], amount=None),)), leaf("b", "1000", "100"),
        )), costs=())
    result = compute_commercial(spec)
    assert not result.complete
    assert result.gm_outcome.status == expected_status
    assert result.gm_us is result.gm_india is result.gm_blended is None
    assert result.missing
    assert result.commercial_schedule.component is spec
    if case == "zero_child":
        assert result.gm_outcome.components[0].status == "exception"
    if case == "missing_child":
        assert result.gm_outcome.components[0].status == "incomplete"
    if case == "unsupported":
        assert result.commercial_schedule.status == "unsupported"


def test_commercial_adapter_passes_explicit_policy_floors_to_authority():
    result = compute_commercial(leaf("a", "1000", "600"), india_floor=D("0.35"))
    assert result.gm_india == D("0.4")
    assert result.gm_outcome.passes["India"] is True
    assert not result.gm_outcome.requires_ceo


def test_legacy_template_results_do_not_acquire_commercial_authority():
    result = TemplateResult()
    assert result.gm_outcome is None
    assert result.commercial_schedule is None


@pytest.mark.parametrize("fee", ["100", "18001"])
def test_ratio_addition_rejects_total_or_partial_loss_at_whole_unit_precision(fee):
    terms = RecurringMSP((RecurringFee("US", D(fee)),), "calendar_days", "Support", (
        MSPAdjustment("large-overage", MONTHS[0], "US", "overage", D("1E30")),
    ))
    result = calculate_component(component(profile="recurring_msp", pricing=terms, costs=(),
                                            service_end=date(2026, 11, 1)))
    assert not result.complete
    assert "precision" in {gap.field for gap in result.missing}
    assert result.assess().status == "incomplete"


@pytest.mark.parametrize("fx_rate", ["1E30", "1.1E30"])
def test_ratio_fx_conversion_cannot_round_whole_currency_units(fx_rate):
    terms = RecurringMSP((RecurringFee("India", D("100")),), "calendar_days", "Support")
    child = component(component_id="a", profile="recurring_msp", pricing=terms, costs=(),
                      service_end=date(2026, 11, 1), currency="EUR")
    hybrid = HybridPricing((child,), fx_rates=(FxRate("EUR", D(fx_rate), "fx-1", MONTHS[0]),))
    result = calculate_component(component(profile="hybrid", pricing=hybrid, costs=()))
    assert not result.complete
    assert "precision" in {gap.field for gap in result.missing}


def test_ratio_division_cannot_round_whole_currency_units():
    terms = RecurringMSP((RecurringFee("US", D("1E32")),), "calendar_days", "Support")
    result = calculate_component(component(profile="recurring_msp", pricing=terms, costs=(),
                                            service_end=date(2026, 11, 1)))
    assert not result.complete
    assert "precision" in {gap.field for gap in result.missing}


@pytest.mark.parametrize("fee,proration", [("1E30", "full_month"), ("3E31", "calendar_days")])
def test_exact_large_recurring_amount_does_not_require_ratio_rounding(fee, proration):
    terms = RecurringMSP((RecurringFee("US", D(fee)),), proration, "Support")
    result = calculate_component(component(profile="recurring_msp", pricing=terms, costs=(),
                                            service_end=date(2026, 11, 1)))
    assert result.complete
    assert result.assess().status == "ok"
    assert result.assess().revenue_total == D("1E30")
