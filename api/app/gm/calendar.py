"""Versioned local-date staffing quantities; margin remains in ``compute_gm``.

Hours are explicit per local service date, including for overnight coverage.
There is no assumed workweek, holiday source, monthly hours or FX conversion.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Context, Decimal, Inexact, ROUND_DOWN, localcontext
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.gm.engine import GM_PRECISION, Location, MissingInput, ResourceInput

ZERO = Decimal("0")
ONE = Decimal("1")
CALCULATION_VERSION = "calendar-hours-v1"


def _decimal(value: Decimal, name: str, maximum: Decimal | None = None) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{name} must be a finite nonnegative Decimal")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")


def _period(start: date, end: date) -> None:
    if type(start) is not date or type(end) is not date or start > end:
        raise ValueError("period requires ordered local dates")


def _timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise ValueError("timezone must be a valid IANA name") from exc


@dataclass(frozen=True)
class DayHours:
    """Per-person hours before quantity/allocation; a paid holiday can be 0/0/8."""

    scheduled: Decimal
    billable: Decimal
    paid: Decimal

    def __post_init__(self) -> None:
        for field in ("scheduled", "billable", "paid"):
            _decimal(getattr(self, field), field, Decimal("24"))


@dataclass(frozen=True)
class CalendarOverride:
    day: date
    hours: DayHours
    reason: str

    def __post_init__(self) -> None:
        _period(self.day, self.day)
        if not isinstance(self.hours, DayHours) or not self.reason.strip():
            raise ValueError("calendar override requires hours and a reason")


@dataclass(frozen=True)
class WorkCalendar:
    calendar_id: str
    version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    week: tuple[DayHours, ...]  # Monday first; all seven days must be explicit.
    overrides: tuple[CalendarOverride, ...] = ()

    def __post_init__(self) -> None:
        _period(self.coverage_start, self.coverage_end)
        if not all((self.calendar_id.strip(), self.version.strip(), self.timezone.strip())):
            raise ValueError("calendar identity, version and timezone are required")
        _timezone(self.timezone)
        object.__setattr__(self, "week", tuple(self.week))
        object.__setattr__(self, "overrides", tuple(self.overrides))
        if len(self.week) != 7 or not all(isinstance(h, DayHours) for h in self.week):
            raise ValueError("week must contain seven DayHours entries, Monday first")
        seen: set[date] = set()
        for override in self.overrides:
            if override.day in seen:
                raise ValueError("duplicate calendar override date")
            if not self.coverage_start <= override.day <= self.coverage_end:
                raise ValueError("calendar override falls outside declared coverage")
            seen.add(override.day)


@dataclass(frozen=True)
class StaffingAssignment:
    assignment_id: str
    source_id: str
    source_version: str
    component_id: str
    profile_version: str
    policy_version: str
    role: str
    location: Location | None
    timezone: str
    currency: str | None
    quantity: int
    allocation: Decimal
    calendar: WorkCalendar | None
    bill_rate: Decimal | None  # Per billable hour in currency.
    cost_rate: Decimal | None  # Confirmed per-person cost at 100% allocation in currency.
    rate_version: str | None
    cost_version: str | None
    start: date | None = None
    end: date | None = None
    cost_rate_basis: str | None = "hourly"  # Missing legacy JSON fields remain hourly.
    cost_proration: str | None = None
    seniority: str | None = None
    # Simple staffing plans state the total per-person hours directly. The
    # monthly schedule is derived server-side; users do not maintain a second
    # weekday/holiday calendar merely to calculate GM.
    hours_billable: Decimal | None = None

    def __post_init__(self) -> None:
        for field in ("assignment_id", "source_id", "source_version", "component_id",
                      "profile_version", "policy_version", "role", "timezone"):
            if not getattr(self, field).strip():
                raise ValueError(f"{field} is required")
        _timezone(self.timezone)
        if type(self.quantity) is not int or self.quantity < 1:
            raise ValueError("quantity must be a positive integer headcount")
        _decimal(self.allocation, "allocation", ONE)
        if self.cost_rate_basis not in (None, "hourly", "monthly"):
            raise ValueError("cost_rate_basis must be hourly, monthly or unresolved")
        if self.cost_proration not in (None, "full_month"):
            raise ValueError("cost_proration must be full_month or unresolved")
        for field in ("bill_rate", "cost_rate"):
            if getattr(self, field) is not None:
                _decimal(getattr(self, field), field)
        if self.hours_billable is not None:
            _decimal(self.hours_billable, "hours_billable")
        for bound in (self.start, self.end):
            if bound is not None:
                _period(bound, bound)
        if self.start is not None and self.end is not None:
            _period(self.start, self.end)
        if self.location not in (None, "US", "India"):
            raise ValueError("location must be US, India or unresolved")
        if self.calendar is not None and self.calendar.timezone != self.timezone:
            raise ValueError("assignment and calendar timezone must match")


@dataclass(frozen=True)
class DailyStaffing:
    day: date
    scheduled_hours: Decimal
    billable_hours: Decimal
    paid_hours: Decimal
    reason: str | None = None


@dataclass(frozen=True)
class MonthlyStaffing:
    assignment: StaffingAssignment  # Immutable source, calendar, rate and policy assumptions.
    term_start: date
    term_end: date
    month: date
    period_start: date
    period_end: date
    scheduled_hours: Decimal | None
    billable_hours: Decimal | None
    paid_hours: Decimal | None
    revenue: Decimal | None
    cost: Decimal | None
    days: tuple[DailyStaffing, ...]
    missing: tuple[MissingInput, ...]
    calculation_version: str = CALCULATION_VERSION

    @property
    def complete(self) -> bool:
        return not self.missing

    def as_resource_input(self) -> ResourceInput:
        """Adapt an hourly component after weighting once; never assess an incomplete row."""
        if not self.complete:
            raise ValueError("incomplete schedule cannot be used as a complete GM input")
        if self.assignment.cost_rate_basis != "hourly":
            raise ValueError("monthly cost cannot be converted to an hourly GM input")
        return ResourceInput(
            role=self.assignment.role, location=self.assignment.location,
            billable_hours=self.billable_hours, paid_hours=self.paid_hours,
            bill_rate=self.assignment.bill_rate, cost_rate=self.assignment.cost_rate,
            utilization=ONE,
        )


def monthly_staffing_schedule(
    assignment: StaffingAssignment, *, term_start: date, term_end: date,
) -> tuple[MonthlyStaffing, ...]:
    """Inclusive intersection of assignment/term, one row per affected local month.

    An uncovered day leaves that month's quantities unknown, never a partial total
    presented as complete. Monthly/fixed pricing callers use the cost and quantities;
    hourly revenue here is only applicable to an hourly pricing component.
    """
    _period(term_start, term_end)
    start = max(term_start, assignment.start or term_start)
    end = min(term_end, assignment.end or term_end)
    if start > end:
        return ()
    if assignment.calendar is None and assignment.hours_billable is not None:
        return _explicit_hours_schedule(assignment, term_start, term_end, start, end)
    rows: list[MonthlyStaffing] = []
    with localcontext(Context(prec=GM_PRECISION)) as ctx:
        ctx.traps[Inexact] = True
        while start <= end:
            month_end = date(start.year, start.month, monthrange(start.year, start.month)[1])
            period_end = min(end, month_end)
            try:
                row = _month(assignment, term_start, term_end, start, period_end)
            except Inexact:
                row = MonthlyStaffing(
                    assignment=assignment, term_start=term_start, term_end=term_end,
                    month=start.replace(day=1), period_start=start, period_end=period_end,
                    scheduled_hours=None, billable_hours=None, paid_hours=None,
                    revenue=None, cost=None, days=(), missing=(MissingInput(
                        "precision", "calendar quantities exceed the engine precision", role=assignment.role,
                    ),),
                )
            rows.append(row)
            if period_end == end:
                break
            start = period_end + timedelta(days=1)
    return tuple(rows)


def _explicit_hours_schedule(
    item: StaffingAssignment,
    term_start: date,
    term_end: date,
    start: date,
    end: date,
) -> tuple[MonthlyStaffing, ...]:
    """Allocate an entered total across service months without a calendar UI.

    The total is preserved exactly at the precision the user entered. Month
    shares use inclusive calendar days; the final month receives the remainder.
    Quantity and allocation are applied once, after the per-person split.
    """

    periods: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        period_end = min(
            end, date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        )
        periods.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)

    decimal_places = max(0, -item.hours_billable.as_tuple().exponent)
    quantum = Decimal(1).scaleb(-decimal_places)
    total_units = int(item.hours_billable / quantum)
    weights = [(period_end - period_start).days + 1 for period_start, period_end in periods]
    total_weight = sum(weights)
    units: list[int] = []
    assigned = 0
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            share = total_units - assigned
        else:
            # The monthly split is a presentation/forecast allocation. It may
            # repeat (for example, 31/62), so round down in the input's own
            # precision and put the exact remainder in the final month. The
            # outer GM context deliberately traps inexact money arithmetic.
            with localcontext(Context(prec=GM_PRECISION)) as split_context:
                split_context.traps[Inexact] = False
                share = int(
                    (
                        Decimal(total_units)
                        * Decimal(weight)
                        / Decimal(total_weight)
                    ).to_integral_value(rounding=ROUND_DOWN)
                )
            assigned += share
        units.append(share)

    rows: list[MonthlyStaffing] = []
    multiplier = Decimal(item.quantity) * item.allocation
    for (period_start, period_end), unit_share in zip(periods, units):
        per_person = Decimal(unit_share) * quantum
        hours = per_person * multiplier
        missing: list[MissingInput] = []
        for field in ("location", "currency", "cost_rate", "cost_version", "cost_rate_basis"):
            value = getattr(item, field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.append(MissingInput(field, f"no confirmed {field}", role=item.role))
        revenue = hours * item.bill_rate if item.bill_rate is not None else None
        cost = hours * item.cost_rate if item.cost_rate is not None else None
        rows.append(
            MonthlyStaffing(
                assignment=item,
                term_start=term_start,
                term_end=term_end,
                month=period_start.replace(day=1),
                period_start=period_start,
                period_end=period_end,
                scheduled_hours=hours,
                billable_hours=hours,
                paid_hours=hours,
                revenue=revenue,
                cost=cost,
                days=(),
                missing=tuple(missing),
            )
        )
    return tuple(rows)


def _month(
    item: StaffingAssignment, term_start: date, term_end: date, start: date, end: date,
) -> MonthlyStaffing:
    missing: list[MissingInput] = []
    for field in ("location", "currency", "bill_rate", "cost_rate", "rate_version", "cost_version", "cost_rate_basis"):
        value = getattr(item, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(MissingInput(field, f"no confirmed {field}", role=item.role))
    cal = item.calendar
    days: list[DailyStaffing] = []
    scheduled = billable = paid = None
    if cal is None:
        missing.append(MissingInput("calendar", "no confirmed calendar", role=item.role))
    elif start < cal.coverage_start or end > cal.coverage_end:
        missing.append(MissingInput(
            "calendar.coverage", f"calendar does not cover {start} through {end}", role=item.role,
        ))
    else:
        overrides = {o.day: o for o in cal.overrides}
        multiplier = Decimal(item.quantity) * item.allocation
        day = start
        while True:
            override = overrides.get(day)
            hours = override.hours if override else cal.week[day.weekday()]
            days.append(DailyStaffing(
                day, hours.scheduled * multiplier, hours.billable * multiplier,
                hours.paid * multiplier, override.reason if override else None,
            ))
            if day == end:
                break
            day += timedelta(days=1)
        scheduled = sum((d.scheduled_hours for d in days), ZERO)
        billable = sum((d.billable_hours for d in days), ZERO)
        paid = sum((d.paid_hours for d in days), ZERO)
    full_month = start.day == 1 and end.day == monthrange(end.year, end.month)[1]
    monthly_cost_confirmed = full_month or item.cost_proration == "full_month"
    if item.cost_rate_basis == "monthly" and not monthly_cost_confirmed:
        missing.append(MissingInput("cost_proration", "no confirmed partial-month cost policy", role=item.role))
    revenue = cost = None
    if item.currency and item.currency.strip():
        if billable is not None and item.bill_rate is not None:
            try:
                revenue = billable * item.bill_rate
            except Inexact:
                missing.append(MissingInput("precision", "hourly revenue exceeds the engine precision", role=item.role))
        if paid is not None and item.cost_rate is not None:
            try:
                if item.cost_rate_basis == "hourly":
                    cost = paid * item.cost_rate
                elif item.cost_rate_basis == "monthly" and monthly_cost_confirmed:
                    cost = item.cost_rate * Decimal(item.quantity) * item.allocation
            except Inexact:
                missing.append(MissingInput("precision", "loaded cost exceeds the engine precision", role=item.role))
    return MonthlyStaffing(
        assignment=item, term_start=term_start, term_end=term_end,
        month=date(start.year, start.month, 1), period_start=start, period_end=end,
        scheduled_hours=scheduled, billable_hours=billable, paid_hours=paid,
        revenue=revenue, cost=cost, days=tuple(days), missing=tuple(missing),
    )
