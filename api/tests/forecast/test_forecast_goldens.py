"""Golden tests: forecast.compute() must reproduce docs/reference/forecast-goldens.json to the cent."""
import json, pytest
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from app.services.forecast import Calendar, Engagement, Allocation, EngagementCost, compute, working_days, duration_months

G = json.load(open(Path(__file__).resolve().parents[3] / "docs/reference/forecast-goldens.json"))
TYPE = {"Fixed cost": "fixed_cost", "Assessment": "assessment", "MSP": "msp", "Time & materials": "time_and_materials", "Staff augmentation": "staff_augmentation"}
EMP = {"W-2 / Employee": "w2_employee", "1099 / Contractor": "contractor_1099"}
d = date.fromisoformat
CAL = Calendar(
    hours_per_day=D(str(G["hours_per_day"])), project_floor_pct=D(str(G["project_floor"])),
    burden_pct={(k.split("|")[0], EMP[k.split("|")[1]]): D(str(v)) for k, v in G["burden"].items()},
    resource_floor_pct={k: D(str(v)) for k, v in G["resource_floor"].items()},
    holidays={k: {d(x) for x in v} for k, v in G["holidays"].items()})

def close(a, b, tol="0.01"):
    return abs(D(str(a)) - D(str(b))) <= D(tol)

@pytest.mark.parametrize("sc", G["scenarios"], ids=[s["name"] for s in G["scenarios"]])
def test_scenario(sc):
    eng = Engagement("e", TYPE[sc["engagement_type"]], d(sc["start"]), d(sc["end"]),
                     None if sc["total_price"] is None else D(str(sc["total_price"])),
                     None if sc["monthly_fee"] is None else D(str(sc["monthly_fee"])),
                     same_dates_for_all=sc["same_dates_for_all"], additional_costs_flag=sc["additional_costs_flag"] == "Y")
    allocs = [Allocation(f"a{i}", r["role"], r["location"], EMP[r["employment_type"]], D(str(r["cost_per_hour"])), r["assignment"],
                         D(str(r["utilization"])), None if r["bill_rate"] is None else D(str(r["bill_rate"])), d(r["start"]), d(r["end"]),
                         None if r["hours_override"] is None else D(str(r["hours_override"])))
              for i, r in enumerate(sc["allocations"])]
    costs = [EngagementCost(f"c{i}", D(str(c["amount"])), "monthly" if c["frequency"] == "Monthly" else "one_time", c["billed_to_client"] == "Y")
             for i, c in enumerate(sc["additional_costs"])]
    f = compute(eng, allocs, costs, CAL)
    e = sc["expected"]
    assert close(f.duration_months, e["duration_months"], "0.000001")
    assert close(f.hours, e["hours"], "0.001")
    assert close(f.labour_cost, e["labour_cost"]); assert close(f.burden_cost, e["burden_cost"])
    assert close(f.additional_costs, e["additional_costs"]); assert close(f.pass_through_revenue, e["pass_through_revenue"])
    assert close(f.total_revenue, e["total_revenue"]); assert close(f.total_cost, e["total_cost"])
    assert close(f.gm_pct, e["gm_pct"], "0.000001")
    assert f.status == e["status"]; assert f.monthly_required == e["monthly_required"]
    # per-allocation expectations
    for a, r in zip(allocs, sc["allocations"]):
        rows = [am for am in f.allocation_months if am.allocation_id == a.id]
        assert sum(am.working_days for am in rows) == r["expected"]["working_days"]
        assert close(sum(am.hours for am in rows), r["expected"]["hours"], "0.001")
        assert close(sum(am.labour_cost for am in rows), r["expected"]["labour_cost"])
        assert close(sum(am.burden_cost for am in rows), r["expected"]["burden_cost"])
        assert close(sum(am.revenue for am in rows), r["expected"]["revenue"])
    # month × assignment expectations (hourly types)
    for row in sc["expected_monthly_by_assignment"]:
        got = f.by_assignment[row["assignment"]][row["month"]]
        assert got["people"] == row["people"], (row, got)
        assert close(got["hours"], row["hours"], "0.001"); assert close(got["revenue"], row["revenue"]); assert close(got["loaded_cost"], row["loaded_cost"])
    # the monthly lines reconcile to the totals
    assert close(sum(m.total_revenue for m in f.months), f.total_revenue, "0.000001")
    assert close(sum(m.total_cost for m in f.months), f.total_cost, "0.000001")

def test_working_days_known_values():
    us = CAL.holidays["US"]
    assert working_days(d("2026-09-07"), d("2026-10-05"), us) == 20      # Labor Day removed
    assert working_days(d("2026-10-12"), d("2026-10-23"), us) == 9       # Columbus Day removed
    assert working_days(d("2026-11-02"), d("2027-04-30"), us) == 124
    assert working_days(d("2026-11-02"), d("2027-04-30"), CAL.holidays["India"]) == 127
    assert working_days(d("2026-10-05"), d("2026-10-04")) == 0

def test_duration_is_exact_not_calendar_months():
    assert close(duration_months(d("2026-09-07"), d("2026-10-05")), "0.961290", "0.000001")
    assert duration_months(d("2026-11-01"), d("2027-04-30")) == D("6")

def test_validation_reports_missing_inputs():
    eng = Engagement("e", "msp", d("2026-11-01"), d("2026-10-01"))
    f = compute(eng, [Allocation("a", "x", "US", "w2_employee", D("50"), utilization=D("1.5"))], [], CAL)
    assert f.status == "INCOMPLETE"
    assert any("before start" in m for m in f.missing) and any("monthly_fee" in m for m in f.missing) and any("0–1" in m for m in f.missing)

def test_leaver_gap_rehire_month_by_month():
    eng = Engagement("e", "staff_augmentation", d("2026-11-02"), d("2027-06-30"))
    allocs = [Allocation("a", "Dev A", "US", "w2_employee", D("68"), "Team X", bill_rate=D("130"), end=d("2026-12-31")),
              Allocation("b", "Dev A2", "US", "contractor_1099", D("72"), "Team X", bill_rate=D("130"), start=d("2027-02-01"))]
    f = compute(eng, allocs, [], CAL)
    x = f.by_assignment["Team X"]
    assert x["2026-12"]["people"] == 1 and "2027-01" not in x and x["2027-02"]["people"] == 1   # January: nobody billing
    assert f.location_check["US"]["floor"] == D("0.35")
