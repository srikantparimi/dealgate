"""DealGate forecast engine — pure, Decimal, no I/O.

One ledger: every person on every engagement is an Allocation with a start, an end, a bill rate and a cost.
A leaver is an end date; a re-hire is a new row; an extension is a new row from the old end date.

compute(engagement, allocations, costs, calendar) -> Forecast
Every number is Decimal. Matches docs/reference/forecast-goldens.json to the cent.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional
import calendar as _cal

D = Decimal
ZERO = D("0")
HOURLY_TYPES = {"time_and_materials", "staff_augmentation"}
FIXED_TYPES = {"fixed_cost", "assessment"}
TYPES = HOURLY_TYPES | FIXED_TYPES | {"msp"}
EMPLOYMENT_TYPES = {"w2_employee", "contractor_1099"}


# ----------------------------------------------------------------------------- inputs
@dataclass(frozen=True)
class Calendar:
    hours_per_day: Decimal = D("8")
    project_floor_pct: Decimal = D("0.35")
    burden_pct: dict = field(default_factory=dict)          # {(location, employment_type): Decimal}
    resource_floor_pct: dict = field(default_factory=dict)  # {location: Decimal}
    holidays: dict = field(default_factory=dict)            # {location: set[date]}


@dataclass(frozen=True)
class Engagement:
    id: str
    type: str                       # fixed_cost | assessment | msp | time_and_materials | staff_augmentation
    start: date
    end: date
    total_price: Optional[Decimal] = None   # fixed_cost / assessment
    monthly_fee: Optional[Decimal] = None   # msp
    same_dates_for_all: bool = False
    additional_costs_flag: bool = False


@dataclass(frozen=True)
class Allocation:
    id: str
    resource: str
    location: str
    employment_type: str
    cost_per_hour: Decimal
    assignment: Optional[str] = None
    utilization: Decimal = D("1")
    bill_rate: Optional[Decimal] = None
    start: Optional[date] = None            # None -> engagement start
    end: Optional[date] = None              # None -> engagement end
    hours_override: Optional[Decimal] = None


@dataclass(frozen=True)
class EngagementCost:
    description: str
    amount: Decimal
    frequency: str = "one_time"             # one_time | monthly
    billed_to_client: bool = False


# ----------------------------------------------------------------------------- outputs
@dataclass
class AllocationMonth:
    allocation_id: str
    month: str                  # "YYYY-MM"
    assignment: str
    working_days: int
    hours: Decimal
    revenue: Decimal
    labour_cost: Decimal
    burden_cost: Decimal

    @property
    def loaded_cost(self) -> Decimal: return self.labour_cost + self.burden_cost


@dataclass
class MonthLine:
    month: str
    share_of_month: Decimal
    people: int
    hours: Decimal
    revenue: Decimal
    labour_cost: Decimal
    burden_cost: Decimal
    additional_costs: Decimal
    pass_through_revenue: Decimal

    @property
    def total_cost(self) -> Decimal: return self.labour_cost + self.burden_cost + self.additional_costs
    @property
    def total_revenue(self) -> Decimal: return self.revenue + self.pass_through_revenue
    @property
    def gm(self) -> Decimal: return self.total_revenue - self.total_cost
    @property
    def gm_pct(self) -> Optional[Decimal]: return None if self.total_revenue == 0 else self.gm / self.total_revenue


@dataclass
class Forecast:
    engagement_id: str
    duration_months: Decimal
    months: list                      # [MonthLine]
    allocation_months: list           # [AllocationMonth]
    by_assignment: dict               # {assignment: {month: MonthLine-like dict}}
    hours: Decimal
    labour_cost: Decimal
    burden_cost: Decimal
    additional_costs: Decimal
    pass_through_revenue: Decimal
    total_revenue: Decimal
    total_cost: Decimal
    gm_pct: Optional[Decimal]
    status: str                       # PASS | BELOW FLOOR | INCOMPLETE
    location_check: dict              # {location: {"revenue", "loaded_cost", "gm_pct", "floor", "ok"}}
    monthly_required: bool
    missing: list


# ----------------------------------------------------------------------------- calendar maths
def working_days(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    """Mon–Fri between start and end inclusive, minus holidays that fall on weekdays."""
    if end < start:
        return 0
    hol = {h for h in holidays if start <= h <= end and h.weekday() < 5}
    full_weeks, rem = divmod((end - start).days + 1, 7)
    days = full_weeks * 5
    d = start + timedelta(days=full_weeks * 7)
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days - len(hol)


def month_slices(start: date, end: date):
    """Yield (month_key, slice_start, slice_end, share_of_month) for each calendar month the window touches."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        dim = _cal.monthrange(cur.year, cur.month)[1]
        last = date(cur.year, cur.month, dim)
        s, e = max(cur, start), min(last, end)
        share = D((e - s).days + 1) / D(dim)
        yield cur.strftime("%Y-%m"), s, e, share
        cur = last + timedelta(days=1)


def duration_months(start: date, end: date) -> Decimal:
    return sum((share for _, _, _, share in month_slices(start, end)), ZERO)


# ----------------------------------------------------------------------------- engine
def compute(eng: Engagement, allocations: list, costs: list, cal: Calendar) -> Forecast:
    missing = _validate(eng, allocations, costs)
    dur = duration_months(eng.start, eng.end)
    slices = list(month_slices(eng.start, eng.end))

    alloc_months: list[AllocationMonth] = []
    for a in allocations:
        a_start = eng.start if (eng.same_dates_for_all or a.start is None) else a.start
        a_end = eng.end if (eng.same_dates_for_all or a.end is None) else a.end
        hol = cal.holidays.get(a.location, set())
        total_wd = working_days(a_start, a_end, hol)
        burden = cal.burden_pct.get((a.location, a.employment_type), ZERO)
        for key, ms, me, _ in slices:
            s, e = max(a_start, ms), min(a_end, me)
            wd = working_days(s, e, hol) if e >= s else 0
            if wd == 0:
                continue
            if a.hours_override is not None:
                hours = a.hours_override * D(wd) / D(total_wd)
            else:
                hours = D(wd) * cal.hours_per_day * a.utilization
            revenue = hours * a.bill_rate if (eng.type in HOURLY_TYPES and a.bill_rate is not None) else ZERO
            labour = hours * a.cost_per_hour
            alloc_months.append(AllocationMonth(a.id, key, a.assignment or "(unassigned)", wd, hours, revenue, labour, labour * burden))

    monthly_costs = sum((c.amount for c in costs if c.frequency == "monthly"), ZERO) if eng.additional_costs_flag else ZERO
    onetime_costs = sum((c.amount for c in costs if c.frequency != "monthly"), ZERO) if eng.additional_costs_flag else ZERO
    monthly_pass = sum((c.amount for c in costs if c.frequency == "monthly" and c.billed_to_client), ZERO) if eng.additional_costs_flag else ZERO
    onetime_pass = sum((c.amount for c in costs if c.frequency != "monthly" and c.billed_to_client), ZERO) if eng.additional_costs_flag else ZERO

    months: list[MonthLine] = []
    for i, (key, ms, me, share) in enumerate(slices):
        rows = [am for am in alloc_months if am.month == key]
        hours = sum((r.hours for r in rows), ZERO)
        labour = sum((r.labour_cost for r in rows), ZERO)
        burden = sum((r.burden_cost for r in rows), ZERO)
        if eng.type == "msp":
            revenue = (eng.monthly_fee or ZERO) * share
        elif eng.type in HOURLY_TYPES:
            revenue = sum((r.revenue for r in rows), ZERO)
        else:
            revenue = (eng.total_price or ZERO) * share / dur if dur else ZERO
        addl = monthly_costs * share + (onetime_costs if i == 0 else ZERO)
        pt = monthly_pass * share + (onetime_pass if i == 0 else ZERO)
        months.append(MonthLine(key, share, sum(1 for r in rows if r.hours > 0), hours, revenue, labour, burden, addl, pt))

    by_asg: dict = {}
    for am in alloc_months:
        line = by_asg.setdefault(am.assignment, {}).setdefault(am.month, dict(people=0, hours=ZERO, revenue=ZERO, loaded_cost=ZERO))
        line["people"] += 1 if am.hours > 0 else 0
        line["hours"] += am.hours; line["revenue"] += am.revenue; line["loaded_cost"] += am.loaded_cost

    tot_rev = sum((m.total_revenue for m in months), ZERO)
    tot_cost = sum((m.total_cost for m in months), ZERO)
    gm_pct = None if tot_rev == 0 else (tot_rev - tot_cost) / tot_rev

    loc_check = {}
    if eng.type in HOURLY_TYPES:
        for loc in sorted({a.location for a in allocations}):
            rows = [am for am in alloc_months if _loc_of(am, allocations) == loc]
            rev = sum((r.revenue for r in rows), ZERO); lc = sum((r.loaded_cost for r in rows), ZERO)
            floor = cal.resource_floor_pct.get(loc, cal.project_floor_pct)
            pct = None if rev == 0 else (rev - lc) / rev
            loc_check[loc] = dict(revenue=rev, loaded_cost=lc, gm_pct=pct, floor=floor, ok=(pct is not None and pct >= floor))

    if missing:
        status = "INCOMPLETE"
    elif gm_pct is None:
        status = "INCOMPLETE"
    else:
        status = "PASS" if gm_pct >= cal.project_floor_pct else "BELOW FLOOR"

    return Forecast(eng.id, dur, months, alloc_months, by_asg,
                    hours=sum((m.hours for m in months), ZERO), labour_cost=sum((m.labour_cost for m in months), ZERO),
                    burden_cost=sum((m.burden_cost for m in months), ZERO), additional_costs=sum((m.additional_costs for m in months), ZERO),
                    pass_through_revenue=sum((m.pass_through_revenue for m in months), ZERO), total_revenue=tot_rev, total_cost=tot_cost,
                    gm_pct=gm_pct, status=status, location_check=loc_check, monthly_required=dur > 2, missing=missing)


def _loc_of(am: AllocationMonth, allocations: list) -> str:
    return next(a.location for a in allocations if a.id == am.allocation_id)


def _validate(eng: Engagement, allocations: list, costs: list) -> list:
    m = []
    if eng.type not in TYPES: m.append(f"unknown engagement type {eng.type!r}")
    if eng.end < eng.start: m.append("engagement end is before start")
    if eng.type in FIXED_TYPES and eng.total_price is None: m.append("total_price required for fixed cost / assessment")
    if eng.type == "msp" and eng.monthly_fee is None: m.append("monthly_fee required for MSP")
    for a in allocations:
        if a.employment_type not in EMPLOYMENT_TYPES: m.append(f"{a.resource}: unknown employment type")
        if not (ZERO <= a.utilization <= D("1")): m.append(f"{a.resource}: utilization must be 0–1")
        if a.start and a.end and a.end < a.start: m.append(f"{a.resource}: end before start")
        if eng.type in HOURLY_TYPES and a.bill_rate is None: m.append(f"{a.resource}: bill rate required for hourly engagement types")
    if eng.additional_costs_flag:
        for c in costs:
            if c.frequency not in ("one_time", "monthly"): m.append(f"{c.description}: frequency must be one_time or monthly")
    return m


def money(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)
