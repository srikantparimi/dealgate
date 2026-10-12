"""The DealGate cost-margin workbook imports as an engagement — current template and older copies alike —
and the engine reproduces the sheet's own numbers from the imported rows."""
from datetime import date
from decimal import Decimal as D
from pathlib import Path
import pytest
from app.services.forecast import Allocation, Calendar, Engagement, EngagementCost, compute
from app.services.forecast.workbook_import import parse_workbook

REF = Path(__file__).resolve().parents[3] / "docs/reference"
US_HOL = {date(2026,1,1), date(2026,1,19), date(2026,2,16), date(2026,5,25), date(2026,6,19), date(2026,7,3), date(2026,9,7),
          date(2026,10,12), date(2026,11,11), date(2026,11,26), date(2026,12,25), date(2027,1,1), date(2027,1,18), date(2027,2,15),
          date(2027,5,31), date(2027,6,18), date(2027,7,5), date(2027,9,6), date(2027,10,11), date(2027,11,11), date(2027,11,25), date(2027,12,24)}
IN_HOL = {date(2026,1,1), date(2026,1,26), date(2026,8,15), date(2026,10,2), date(2026,12,25), date(2027,1,1), date(2027,1,26), date(2027,8,15), date(2027,10,2), date(2027,12,25)}
CAL = Calendar(D("8"), D("0.35"),
               {("US", "w2_employee"): D("0.36"), ("US", "contractor_1099"): D("0.05"), ("India", "w2_employee"): D("0.08"), ("India", "contractor_1099"): D("0.08")},
               {"US": D("0.35"), "India": D("0.50")}, {"US": US_HOL, "India": IN_HOL})

def to_engine(imp):
    eng = Engagement("imp", imp.type, imp.start, imp.end, imp.total_price, imp.monthly_fee, imp.same_dates_for_all, imp.additional_costs_flag)
    allocs = [Allocation(f"a{i}", a.role, a.location, a.employment_type, a.cost_per_hour or D("0"), a.assignment, a.utilization, a.bill_rate, a.start, a.end, a.hours_override)
              for i, a in enumerate(imp.allocations)]
    costs = [EngagementCost(c.description, c.amount, c.frequency, c.billed_to_client) for c in imp.costs]
    return eng, allocs, costs

def test_sample_staff_aug_workbook_imports_and_matches_the_sheet():
    imp = parse_workbook(REF / "DealGate_Cost_Margin_SAMPLE_StaffAug.xlsx")
    assert not imp.errors, imp.errors
    assert imp.type == "staff_augmentation" and imp.client == "Client A" and imp.additional_costs_flag
    assert len(imp.allocations) == 5 and {a.assignment for a in imp.allocations} == {"Portal rebuild", "Data platform"}
    assert [a.employment_type for a in imp.allocations] == ["w2_employee", "contractor_1099", "contractor_1099", "w2_employee", "w2_employee"]
    assert len(imp.costs) == 2 and sum(c.billed_to_client for c in imp.costs) == 1
    f = compute(*to_engine(imp), CAL)
    assert f.total_revenue == D("339684.00") or abs(f.total_revenue - D("339684")) < D("0.01")
    assert abs(f.total_cost - D("217292.72")) < D("0.01")
    # per-row hours agree with what the sheet showed
    for a, am in zip(imp.allocations, [[x for x in f.allocation_months if x.allocation_id == f"a{i}"] for i in range(5)]):
        assert abs(sum(x.hours for x in am) - a.sheet_hours) < D("0.5"), (a.role, a.sheet_hours, sum(x.hours for x in am))

def test_blank_template_reports_what_is_missing_instead_of_crashing():
    imp = parse_workbook(REF / "DealGate_Cost_Margin_Sheet.xlsx")
    assert imp.errors and any("Engagement type" in e for e in imp.errors) and any("dates" in e for e in imp.errors)

def test_older_copy_without_employment_type_column(tmp_path):
    """Kanna's filled copy (older layout): single Burden % column, no Employment type, holidays not loaded."""
    src = Path(__file__).parent / "fixtures/kanna_peppermill_v2.xlsx"
    if not src.exists():
        pytest.skip("fixture not present")
    imp = parse_workbook(src)
    assert not imp.errors, imp.errors
    assert imp.type == "assessment" and imp.client == "Peppermill" and imp.total_price == D("50000")
    assert imp.start == date(2026, 9, 7) and imp.end == date(2026, 10, 5)
    assert any("Employment type" in w for w in imp.warnings)
    assert [a.role for a in imp.allocations] == ["Vikrin", "srikanth"] and imp.allocations[1].utilization == D("0.24")
    assert len(imp.costs) == 3 and all(not c.billed_to_client for c in imp.costs)
    f = compute(*to_engine(imp), CAL)
    # the sheet showed 168 h for Vikrin because that copy had no holidays; the engine removes Labor Day → 160 h
    vik = sum(x.hours for x in f.allocation_months if x.allocation_id == "a0")
    assert vik == D("160") and imp.allocations[0].sheet_hours == D("168")
    assert f.status in ("PASS", "BELOW FLOOR")

def test_one_time_costs_spread_across_the_term_like_a_fixed_price():
    eng = Engagement("e", "assessment", date(2026, 9, 7), date(2026, 10, 5), D("50000"), None, True, True)
    allocs = [Allocation("a", "SME", "US", "w2_employee", D("120"))]
    f = compute(eng, allocs, [EngagementCost("travel", D("3000"), "one_time", False)], CAL)
    sep, octo = f.months
    assert abs(sep.additional_costs + octo.additional_costs - D("3000")) < D("0.01")
    assert abs(sep.additional_costs / D("3000") - sep.share_of_month / f.duration_months) < D("0.0001")   # same proportion as revenue
