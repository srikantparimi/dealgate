"""Typed commercial schedules. Service economics are independent of billing cadence."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import date, timedelta
from decimal import Context, Decimal, Inexact, localcontext
from fractions import Fraction
from types import MappingProxyType
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.gm.calendar import MonthlyStaffing, StaffingAssignment, monthly_staffing_schedule
from app.gm.engine import DirectCost, GM_PRECISION, GmOutcome, Location, MissingInput, SowSpec, compute_gm
from app.gm.policy import INDIA_FLOOR, US_FLOOR

ZERO = Decimal("0")
CALCULATION_VERSION = "commercial-schedule-v1"


@dataclass(frozen=True)
class PricingProfile:
    key: str
    version: str
    required_fields: tuple[str, ...]
    calculation_available: bool = False


PRICING_PROFILES = MappingProxyType({p.key: p for p in (
    PricingProfile("fixed_assignment", "1", ("total_fee", "allocations", "allocation_basis"), True),
    PricingProfile("recurring_msp", "1", ("monthly_fee", "proration", "included_scope"), True),
    PricingProfile("calendar_staff_aug", "1", ("assignments", "rate_basis"), True),
    PricingProfile("tm", "1", ("rate", "unit", "estimate", "quantity_basis"), True),
    PricingProfile("milestone", "1", ("milestones", "acceptance_conditions"), True),
    PricingProfile("unit", "1", ("rate", "unit", "quantity", "contractual_basis"), True),
    PricingProfile("hybrid", "1", ("components", "shared_cost_allocations"), True),
)})


def _number(value: Decimal, field: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < ZERO:
        raise ValueError(f"{field} must be a finite nonnegative Decimal")
    if positive and value == ZERO:
        raise ValueError(f"{field} must be positive")


@dataclass(frozen=True)
class FeeAllocation:
    month: date
    location: Location
    weight: Decimal

    def __post_init__(self) -> None:
        _number(self.weight, "weight")


@dataclass(frozen=True)
class FixedFee:
    total_fee: Decimal | None
    allocations: tuple[FeeAllocation, ...]
    allocation_basis: str | None
    minor_unit: Decimal

    def __post_init__(self) -> None:
        if self.total_fee is not None:
            _number(self.total_fee, "total_fee")
        _number(self.minor_unit, "minor_unit", positive=True)
        object.__setattr__(self, "allocations", tuple(self.allocations))


@dataclass(frozen=True)
class PeriodCost:
    source_id: str  # Unique allocated cost line, not a person or a reusable rate ID.
    month: date
    location: Location
    amount: Decimal | None

    def __post_init__(self) -> None:
        if self.amount is not None:
            _number(self.amount, "cost amount")


@dataclass(frozen=True)
class Milestone:
    milestone_id: str
    planned_date: date | None
    location: Location
    amount: Decimal | None
    acceptance_conditions: str | None
    approved_invoice_ref: str | None = None
    recognized_revenue_ref: str | None = None

    def __post_init__(self) -> None:
        if self.amount is not None:
            _number(self.amount, "milestone amount")


@dataclass(frozen=True)
class MilestonePricing:
    milestones: tuple[Milestone, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "milestones", tuple(self.milestones))


@dataclass(frozen=True)
class QuantityLine:
    source_id: str
    month: date
    location: Location
    quantity: Decimal | None

    def __post_init__(self) -> None:
        if self.quantity is not None:
            _number(self.quantity, "quantity")


@dataclass(frozen=True)
class UnitPricing:
    rate: Decimal | None
    unit: str
    quantities: tuple[QuantityLine, ...]
    contractual_basis: str | None

    def __post_init__(self) -> None:
        if self.rate is not None:
            _number(self.rate, "unit rate")
        object.__setattr__(self, "quantities", tuple(self.quantities))


@dataclass(frozen=True)
class TimeAndMaterials:
    rate: Decimal | None
    unit: str
    estimates: tuple[QuantityLine, ...]
    approved_usage: tuple[QuantityLine, ...] = ()
    cap: Decimal | None = None
    minimum: Decimal | None = None
    limit_allocation_basis: str | None = None
    minor_unit: Decimal | None = None
    calendar_estimates: bool = False

    def __post_init__(self) -> None:
        for field in ("rate", "cap", "minimum", "minor_unit"):
            value = getattr(self, field)
            if value is not None:
                _number(value, field, positive=field == "minor_unit")
        object.__setattr__(self, "estimates", tuple(self.estimates))
        object.__setattr__(self, "approved_usage", tuple(self.approved_usage))


@dataclass(frozen=True)
class StaffingRate:
    assignment_id: str
    basis: str
    rate: Decimal | None
    version: str | None
    hours_per_day: Decimal | None = None
    proration: str | None = None

    def __post_init__(self) -> None:
        if self.rate is not None:
            _number(self.rate, "staffing rate")
        if self.hours_per_day is not None:
            _number(self.hours_per_day, "hours_per_day", positive=True)


@dataclass(frozen=True)
class CalendarPricing:
    rates: tuple[StaffingRate, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rates", tuple(self.rates))


@dataclass(frozen=True)
class RecurringFee:
    location: Location
    amount: Decimal | None

    def __post_init__(self) -> None:
        if self.amount is not None:
            _number(self.amount, "monthly fee")


@dataclass(frozen=True)
class MSPAdjustment:
    source_id: str
    month: date
    location: Location
    kind: str  # An explicit contractual overage amount or credit; never a setup fee.
    amount: Decimal | None

    def __post_init__(self) -> None:
        if self.amount is not None:
            _number(self.amount, "adjustment")


@dataclass(frozen=True)
class MSPUsage:
    source_id: str
    month: date
    location: Location
    unit: str
    quantity: Decimal | None
    included_quantity: Decimal | None
    unit_rate: Decimal | None

    def __post_init__(self) -> None:
        for field in ("quantity", "included_quantity", "unit_rate"):
            if getattr(self, field) is not None:
                _number(getattr(self, field), field)


@dataclass(frozen=True)
class RecurringMSP:
    fees: tuple[RecurringFee, ...]
    proration: str | None
    included_scope: str | None
    adjustments: tuple[MSPAdjustment, ...] = ()
    usage: tuple[MSPUsage, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "fees", tuple(self.fees))
        object.__setattr__(self, "adjustments", tuple(self.adjustments))
        object.__setattr__(self, "usage", tuple(self.usage))


@dataclass(frozen=True)
class PricingComponent:
    component_id: str
    version: str
    source_id: str
    source_version: str
    workstream_id: str
    profile: str
    profile_version: str
    policy_version: str
    source_evidence: tuple[str, ...]
    service_start: date | None
    service_end: date | None
    timezone: str | None
    currency: str | None
    billing_cadence: str | None
    cost_basis: str | None
    costs_confirmed: bool
    costs: tuple[PeriodCost, ...]
    pricing: FixedFee | MilestonePricing | UnitPricing | TimeAndMaterials | CalendarPricing | RecurringMSP | HybridPricing | None
    staffing: tuple[StaffingAssignment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_evidence", tuple(self.source_evidence))
        object.__setattr__(self, "costs", tuple(self.costs))
        object.__setattr__(self, "staffing", tuple(self.staffing))


@dataclass(frozen=True)
class SharedCostAllocation:
    source_id: str
    component_id: str
    weight: Decimal

    def __post_init__(self) -> None:
        _number(self.weight, "shared cost weight")


@dataclass(frozen=True)
class FxRate:
    currency: str  # Target currency is the parent component's currency.
    rate: Decimal | None
    version: str | None
    as_of: date | None

    def __post_init__(self) -> None:
        if self.rate is not None:
            _number(self.rate, "FX rate", positive=True)


@dataclass(frozen=True)
class HybridPricing:
    components: tuple[PricingComponent, ...]
    shared_cost_allocations: tuple[SharedCostAllocation, ...] = ()
    allocation_basis: str | None = None
    minor_unit: Decimal | None = None
    fx_rates: tuple[FxRate, ...] = ()

    def __post_init__(self) -> None:
        for field in ("components", "shared_cost_allocations", "fx_rates"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        if self.minor_unit is not None:
            _number(self.minor_unit, "shared cost minor_unit", positive=True)


@dataclass(frozen=True)
class CommercialMonth:
    month: date
    location: Location
    revenue: Decimal
    cost: Decimal | None
    scheduled_hours: Decimal | None = None
    billable_hours: Decimal | None = None
    paid_hours: Decimal | None = None
    revenue_uses_ratio: bool = dataclass_field(default=False, kw_only=True)


@dataclass(frozen=True)
class ComponentSchedule:
    component: PricingComponent
    rows: tuple[CommercialMonth, ...]
    missing: tuple[MissingInput, ...] = ()
    status: Literal["ok", "incomplete", "unsupported"] = "ok"
    calculation_version: str = CALCULATION_VERSION
    calendar_rows: tuple[MonthlyStaffing, ...] = ()
    children: tuple[ComponentSchedule, ...] = ()

    @property
    def complete(self) -> bool:
        return self.status == "ok" and not self.missing

    def assess(
        self, *, us_floor: Decimal = US_FLOOR, india_floor: Decimal = INDIA_FLOOR,
    ) -> GmOutcome:
        children = tuple(child.assess(us_floor=us_floor, india_floor=india_floor) for child in self.children)
        if not self.complete:
            return GmOutcome(status="incomplete", missing=self.missing,
                             components=children,
                             reason="commercial inputs require confirmation")
        if any(child.status != "ok" for child in children):
            return GmOutcome(status="incomplete" if any(c.status == "incomplete" for c in children) else "exception",
                             missing=tuple(m for c in children for m in c.missing), components=children,
                             reason="one or more pricing components cannot be assessed")
        with localcontext(Context(prec=GM_PRECISION)) as ctx:
            revenue: dict[str, Decimal] = {}
            ratio_locations: set[str] = set()
            ctx.traps[Inexact] = True
            try:
                for row in self.rows:
                    if row.revenue_uses_ratio:
                        ratio_locations.add(row.location)
                    revenue[row.location] = _add_revenue(
                        revenue.get(row.location, ZERO), row.revenue, row.location in ratio_locations,
                    )
                sum((row.cost for row in self.rows if row.cost is not None), ZERO)
                total = ZERO
                for value in revenue.values():
                    total = _add_revenue(total, value, bool(ratio_locations))
            except Inexact:
                return GmOutcome(status="incomplete", missing=(
                    _gap("precision", "amounts exceed the GM engine precision"),
                ))
            ctx.traps[Inexact] = False
            outcome = compute_gm(SowSpec(
                "fixed_price", contract_price=total,
                revenue_allocation=revenue, allocation_basis="confirmed component schedule",
                direct_costs=tuple(DirectCost(str(row.month), row.cost, row.location)
                                   for row in self.rows), currency=self.component.currency or "",
            ), us_floor=us_floor, india_floor=india_floor)
            return replace(outcome, components=children)


def _gap(field: str, reason: str) -> MissingInput:
    return MissingInput(field, reason)


def _month_valid(month: date, component: PricingComponent) -> bool:
    start, end = component.service_start, component.service_end
    return (type(month) is date and month.day == 1 and start is not None and end is not None
            and start.replace(day=1) <= month <= end.replace(day=1))


def _validate(component: PricingComponent) -> list[MissingInput]:
    missing = []
    for field in ("component_id", "version", "source_id", "source_version", "workstream_id",
                  "policy_version", "currency", "billing_cadence", "cost_basis"):
        value = getattr(component, field)
        if not isinstance(value, str) or not value.strip():
            missing.append(_gap(field, f"no confirmed {field}"))
    if not component.source_evidence or not all(e.strip() for e in component.source_evidence):
        missing.append(_gap("source_evidence", "source evidence is required"))
    start, end = component.service_start, component.service_end
    if type(start) is not date or type(end) is not date or start > end:
        missing.append(_gap("service_period", "confirmed inclusive service dates are required"))
    try:
        ZoneInfo(component.timezone or "")
    except (ValueError, ZoneInfoNotFoundError):
        missing.append(_gap("timezone", "confirmed IANA timezone is required"))
    if component.costs_confirmed is not True:
        missing.append(_gap("costs_confirmed", "cost plan has not been confirmed"))
    ids: set[str] = set()
    for line in component.costs:
        if not line.source_id.strip() or line.source_id in ids:
            missing.append(_gap("costs.source_id", "cost lines require distinct source IDs"))
        ids.add(line.source_id)
        if line.location not in ("US", "India") or not _month_valid(line.month, component):
            missing.append(_gap("costs.period", "cost location/month is outside confirmed service"))
    for item in component.staffing:
        key = f"calendar:{item.assignment_id}"
        if key in ids:
            missing.append(_gap("costs.source_id", "calendar cost source is duplicated"))
        ids.add(key)
        if any(getattr(item, field) != getattr(component, field) for field in (
            "source_id", "source_version", "component_id", "profile_version", "policy_version",
            "currency", "timezone",
        )):
            missing.append(_gap("staffing.binding", "assignment does not match the component version"))
    return missing


def calculate_component(component: PricingComponent) -> ComponentSchedule:
    """Preserve unsupported/unresolved drafts; only registered typed pricing can calculate."""
    profile = PRICING_PROFILES.get(component.profile)
    if profile is None or profile.version != component.profile_version or not profile.calculation_available:
        return ComponentSchedule(component, (), (_gap("profile", "unsupported profile/version"),),
                                 status="unsupported")
    missing = _validate(component)
    if missing:
        return ComponentSchedule(component, (), tuple(missing), status="incomplete")
    with localcontext(Context(prec=GM_PRECISION)) as ctx:
        ctx.traps[Inexact] = True
        try:
            if component.profile == "fixed_assignment":
                return _fixed_fee(component)
            if component.profile == "milestone":
                return _milestones(component)
            if component.profile == "recurring_msp":
                return _recurring(component)
            if component.profile == "calendar_staff_aug":
                return _calendar_pricing(component)
            if component.profile == "hybrid":
                return _hybrid(component)
            return _quantities(component)
        except Inexact:
            return ComponentSchedule(component, (), (
                _gap("precision", "commercial amounts exceed the engine precision"),
            ), "incomplete")


def _minor_units(amount: Decimal, minor_unit: Decimal) -> int | None:
    units = Fraction(amount) / Fraction(minor_unit)
    return units.numerator if units.denominator == 1 else None


def _apportion(
    amount: Decimal, allocations: list[FeeAllocation], minor_unit: Decimal,
) -> dict[tuple[date, Location], Decimal]:
    keys = [(a.month, a.location) for a in allocations]
    return dict(zip(keys, _unit_shares(amount, [a.weight for a in allocations], minor_unit)))


def _unit_shares(amount: Decimal, weights: list[Decimal], minor_unit: Decimal) -> list[Decimal]:
    # Integer minor-unit counts and exact dimensionless weights avoid context-dependent ties.
    units = _minor_units(amount, minor_unit)
    assert units is not None
    exact_weights = [Fraction(w) for w in weights]
    total_weight = sum(exact_weights, Fraction(0))
    shares = [units * w / total_weight for w in exact_weights]
    whole = [s.numerator // s.denominator for s in shares]
    priority = sorted(range(len(weights)), key=lambda i: (-(shares[i] - whole[i]), i))
    for index in priority[:units - sum(whole)]:
        whole[index] += 1
    with localcontext(Context(prec=max(GM_PRECISION, len(str(units)) + len(minor_unit.as_tuple().digits)))):
        return [Decimal(n) * minor_unit for n in whole]


def _fixed_fee(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    missing = []
    if not isinstance(terms, FixedFee):
        return ComponentSchedule(component, (), (_gap("pricing", "fixed fee terms are required"),),
                                 status="incomplete")
    if not terms.allocation_basis or not terms.allocation_basis.strip():
        missing.append(_gap("allocation_basis", "service allocation basis is unconfirmed"))
    if terms.total_fee is None or _minor_units(terms.total_fee, terms.minor_unit) is None:
        missing.append(_gap("total_fee", "fee must be confirmed in whole currency minor units"))
    allocations = sorted(terms.allocations, key=lambda a: (a.month, a.location))
    keys = [(a.month, a.location) for a in allocations]
    if (not allocations or len(set(keys)) != len(keys)
            or not any(a.weight > ZERO for a in allocations)
            or any(a.location not in ("US", "India") or not _month_valid(a.month, component)
                   for a in allocations)):
        missing.append(_gap("allocations", "distinct service month/location weights are required"))
    if missing:
        return ComponentSchedule(component, (), tuple(missing), status="incomplete")
    assert terms.total_fee is not None
    return _assemble(component, _apportion(terms.total_fee, allocations, terms.minor_unit))


def _assemble(
    component: PricingComponent, revenue: dict[tuple[date, Location], Decimal],
    ratio_keys: set[tuple[date, Location]] | None = None,
) -> ComponentSchedule:
    missing = []
    costs: dict[tuple[date, Location], Decimal | None] = {}
    for line in component.costs:
        key = (line.month, line.location)
        previous = costs.get(key, ZERO)
        costs[key] = None if line.amount is None or previous is None else previous + line.amount
        if line.amount is None:
            missing.append(_gap("costs.amount", f"cost {line.source_id} is unresolved"))
    calendar_rows, calendar_missing = _calendar_rows(component)
    missing.extend(calendar_missing)
    hours: dict[tuple[date, Location], list[Decimal | None]] = {}
    for row in calendar_rows:
        location = row.assignment.location
        if location not in ("US", "India"):
            continue
        key = (row.month, location)
        previous = costs.get(key, ZERO)
        costs[key] = None if previous is None or row.cost is None else previous + row.cost
        values = (row.scheduled_hours, row.billable_hours, row.paid_hours)
        accumulated = hours.setdefault(key, [ZERO, ZERO, ZERO])
        for index, value in enumerate(values):
            prior = accumulated[index]
            accumulated[index] = None if value is None or prior is None else prior + value
    rows = tuple(CommercialMonth(month, location, revenue.get((month, location), ZERO),
                                 costs.get((month, location), ZERO), *hours.get((month, location), (None, None, None)),
                                 revenue_uses_ratio=(month, location) in (ratio_keys or set()))
                 for month, location in sorted(revenue.keys() | costs.keys()))
    return ComponentSchedule(component, rows, tuple(missing), "incomplete" if missing else "ok",
                             calendar_rows=calendar_rows)


def _calendar_rows(component: PricingComponent) -> tuple[tuple[MonthlyStaffing, ...], list[MissingInput]]:
    assert component.service_start is not None and component.service_end is not None
    indexed_rows = tuple(
        (line, row)
        for line, item in enumerate(component.staffing, start=1)
        for row in monthly_staffing_schedule(
            item, term_start=component.service_start, term_end=component.service_end,
        )
    )
    rows = tuple(row for _, row in indexed_rows)
    # Fixed/MSP cost plans have no hourly revenue requirement; all cost/calendar gaps still apply.
    missing = [
        replace(gap, line=line) if gap.line is None else gap
        for line, row in indexed_rows
        for gap in row.missing
        if gap.field not in ("bill_rate", "rate_version")
    ]
    return rows, missing


def _check_ratio_precision(value: Decimal, uses_ratio: bool) -> Decimal:
    # Ratio approximation is supported only while the context retains fractional places.
    # Scaling an already approximated ratio can violate this even without a new Inexact flag.
    if uses_ratio and value.adjusted() >= GM_PRECISION - 1:
        raise Inexact("derived revenue cannot preserve fractional precision")
    return value


def _add_revenue(left: Decimal, right: Decimal, uses_ratio: bool) -> Decimal:
    # Only derived ratio tails use normal calculation precision; inputs remain exact-checked.
    with localcontext(Context(prec=GM_PRECISION)) as ctx:
        ctx.traps[Inexact] = True
        left, right = +left, +right
        ctx.traps[Inexact] = not uses_ratio
        return _check_ratio_precision(left + right, uses_ratio)


def _ratio(numerator: Decimal, denominator: Decimal) -> tuple[Decimal, bool]:
    numerator, denominator = +numerator, +denominator
    with localcontext(Context(prec=GM_PRECISION)) as ctx:
        value = numerator / denominator
        return _check_ratio_precision(value, ctx.flags[Inexact]), ctx.flags[Inexact]


def _prorate(amount: Decimal, start: date, end: date, basis: str) -> tuple[Decimal, bool]:
    if basis == "full_month":
        return +amount, False
    days = (end - start).days + 1
    month_days = monthrange(start.year, start.month)[1]
    if days == month_days:
        return +amount, False
    return _ratio(amount * Decimal(days), Decimal(month_days))


def _calendar_pricing(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    if not isinstance(terms, CalendarPricing) or not component.staffing:
        return ComponentSchedule(component, (), (_gap("pricing", "calendar assignments and rates are required"),), "incomplete")
    missing = []
    rates = {r.assignment_id: r for r in terms.rates}
    if len(rates) != len(terms.rates) or set(rates) != {s.assignment_id for s in component.staffing}:
        missing.append(_gap("rates.assignment_id", "each assignment needs exactly one rate"))
    revenue: dict[tuple[date, Location], Decimal] = {}
    ratio_keys: set[tuple[date, Location]] = set()
    calendar_rows, _ = _calendar_rows(component)
    for row in calendar_rows:
        item = row.assignment
        rate = rates.get(item.assignment_id)
        if (rate is None or rate.rate is None or not rate.version or not rate.version.strip()
                or rate.basis not in ("hourly", "daily", "monthly")
                or item.location not in ("US", "India")):
            missing.append(_gap("rates", "confirmed versioned staffing rates are required"))
            continue
        amount = None
        uses_ratio = False
        if rate.basis == "monthly":
            if rate.proration not in ("calendar_days", "full_month"):
                missing.append(_gap("proration", "monthly rate proration is unconfirmed"))
            else:
                amount, uses_ratio = _prorate(rate.rate * Decimal(item.quantity) * item.allocation,
                                              row.period_start, row.period_end, rate.proration)
        elif row.billable_hours is None:
            missing.append(_gap("calendar.coverage", "billable calendar quantities are unresolved"))
        elif rate.basis == "hourly":
            amount = rate.rate * row.billable_hours
        elif rate.hours_per_day is None:
            missing.append(_gap("hours_per_day", "daily pricing needs confirmed billable hours per day"))
        else:
            base = rate.rate * row.billable_hours
            amount, uses_ratio = _ratio(base, rate.hours_per_day)
        if amount is not None:
            key = (row.month, item.location)
            if uses_ratio:
                ratio_keys.add(key)
            revenue[key] = _add_revenue(revenue.get(key, ZERO), amount, key in ratio_keys)
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete", calendar_rows=calendar_rows)
    return _assemble(component, revenue, ratio_keys)


def _recurring(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    if not isinstance(terms, RecurringMSP):
        return ComponentSchedule(component, (), (_gap("pricing", "typed recurring terms are required"),), "incomplete")
    missing = []
    if terms.proration not in ("calendar_days", "full_month"):
        missing.append(_gap("proration", "recurring fee proration is unconfirmed"))
    if not terms.included_scope or not terms.included_scope.strip():
        missing.append(_gap("included_scope", "included service scope is unconfirmed"))
    fees = {fee.location: fee.amount for fee in terms.fees}
    if (not fees or len(fees) != len(terms.fees)
            or any(loc not in ("US", "India") or value is None for loc, value in fees.items())):
        missing.append(_gap("monthly_fee", "distinct location fees must be confirmed"))
    seen: set[str] = set()
    for item in terms.adjustments:
        if not item.source_id.strip() or item.source_id in seen:
            missing.append(_gap("adjustments.source_id", "adjustments require distinct source IDs"))
        seen.add(item.source_id)
        if (item.location not in fees or not _month_valid(item.month, component)
                or item.kind not in ("overage", "credit") or item.amount is None):
            missing.append(_gap("adjustments", "confirmed in-term overage or credit is required"))
    for usage in terms.usage:
        if not usage.source_id.strip() or usage.source_id in seen:
            missing.append(_gap("usage.source_id", "usage/adjustment sources must be distinct"))
        seen.add(usage.source_id)
        if (usage.location not in fees or not _month_valid(usage.month, component) or not usage.unit.strip()
                or usage.quantity is None or usage.included_quantity is None or usage.unit_rate is None):
            missing.append(_gap("usage", "usage, included units and overage rate must be confirmed"))
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete")
    assert component.service_start is not None and component.service_end is not None
    assert terms.proration is not None
    revenue = {}
    ratio_keys: set[tuple[date, Location]] = set()
    start = component.service_start
    while start <= component.service_end:
        end = min(component.service_end, date(start.year, start.month, monthrange(start.year, start.month)[1]))
        for location, amount in fees.items():
            assert amount is not None
            key = (start.replace(day=1), location)
            revenue[key], uses_ratio = _prorate(amount, start, end, terms.proration)
            if uses_ratio:
                ratio_keys.add(key)
        if end == component.service_end:
            break
        start = end + timedelta(days=1)
    for item in terms.adjustments:
        assert item.amount is not None
        key = (item.month, item.location)
        revenue[key] = _add_revenue(revenue[key], -item.amount if item.kind == "credit" else item.amount,
                                    key in ratio_keys)
    for usage in terms.usage:
        assert usage.quantity is not None and usage.included_quantity is not None and usage.unit_rate is not None
        key = (usage.month, usage.location)
        overage = max(usage.quantity - usage.included_quantity, ZERO) * usage.unit_rate
        revenue[key] = _add_revenue(revenue[key], overage, key in ratio_keys)
    if any(value < ZERO for value in revenue.values()):
        return ComponentSchedule(component, (), (_gap("adjustments", "credits exceed modeled revenue"),), "incomplete")
    return _assemble(component, revenue, ratio_keys)


def _cost_sources(component: PricingComponent) -> set[str]:
    return {line.source_id for line in component.costs} | {f"calendar:{s.assignment_id}" for s in component.staffing}


def _revenue_sources(component: PricingComponent) -> set[str]:
    terms = component.pricing
    if isinstance(terms, UnitPricing):
        return {line.source_id for line in terms.quantities}
    if isinstance(terms, TimeAndMaterials):
        return {line.source_id for line in terms.estimates}
    if isinstance(terms, RecurringMSP):
        return {line.source_id for line in terms.usage} | {line.source_id for line in terms.adjustments}
    return set()


def _hybrid(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    if not isinstance(terms, HybridPricing) or not terms.components:
        return ComponentSchedule(component, (), (_gap("components", "typed hybrid components are required"),), "incomplete")
    missing = []
    children = {c.component_id: c for c in terms.components}
    if len(children) != len(terms.components) or component.component_id in children:
        missing.append(_gap("components.identity", "component IDs must be distinct"))
    shared_calendar, calendar_gaps = _calendar_rows(component)
    missing.extend(calendar_gaps)
    sources = _cost_sources(component)
    seen_sources = set(sources)
    seen_revenue: set[str] = set()
    for child in terms.components:
        if child.profile == "hybrid":
            missing.append(_gap("components.nesting", "nested hybrids require a flattened confirmed component plan"))
        if (any(getattr(child, field) != getattr(component, field) for field in ("source_id", "source_version", "policy_version"))
                or child.service_start is None or child.service_end is None
                or component.service_start is None or component.service_end is None
                or child.service_start < component.service_start or child.service_end > component.service_end):
            missing.append(_gap("components.binding", "child source/policy/term does not match the package"))
        child_sources = _cost_sources(child)
        if seen_sources & child_sources:
            missing.append(_gap("costs.source_id", "a cost source appears in multiple components"))
        seen_sources.update(child_sources)
        child_revenue = _revenue_sources(child)
        if seen_revenue & child_revenue:
            missing.append(_gap("revenue.source_id", "a revenue source appears in multiple components"))
        seen_revenue.update(child_revenue)
    allocations: dict[str, list[SharedCostAllocation]] = {source: [] for source in sources}
    pairs: set[tuple[str, str]] = set()
    for allocation in terms.shared_cost_allocations:
        key = (allocation.source_id, allocation.component_id)
        if key in pairs or allocation.source_id not in sources or allocation.component_id not in children:
            missing.append(_gap("shared_cost_allocations", "allocation must identify a distinct source/child pair"))
        elif allocation.source_id in allocations:
            allocations[allocation.source_id].append(allocation)
        pairs.add(key)
    if sources and (not terms.allocation_basis or not terms.allocation_basis.strip() or terms.minor_unit is None
                    or any(not any(a.weight > ZERO for a in values) for values in allocations.values())):
        missing.append(_gap("shared_cost_allocations", "every shared source needs confirmed positive allocation weights"))
    fx = {rate.currency: rate for rate in terms.fx_rates}
    if len(fx) != len(terms.fx_rates):
        missing.append(_gap("fx", "FX source currencies must be distinct"))
    for child in terms.components:
        if child.currency != component.currency:
            rate = fx.get(child.currency or "")
            if rate is None or rate.rate is None or not rate.version or not rate.version.strip() or type(rate.as_of) is not date:
                missing.append(_gap("fx", "mixed currencies require a versioned dated conversion rate"))
            if sources:
                missing.append(_gap("shared_costs.currency", "cross-currency shared costs require explicit converted allocations"))
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete")
    extra: dict[str, list[PeriodCost]] = {identifier: [] for identifier in children}
    shared_costs = list(component.costs) + [
        PeriodCost(f"calendar:{row.assignment.assignment_id}", row.month, row.assignment.location, row.cost)
        for row in shared_calendar if row.assignment.location in ("US", "India")
    ]
    for cost in shared_costs:
        shares = sorted(allocations[cost.source_id], key=lambda a: a.component_id)
        assert terms.minor_unit is not None
        if cost.amount is not None and _minor_units(cost.amount, terms.minor_unit) is None:
            missing.append(_gap("shared_costs.minor_unit", "shared source is not in confirmed currency minor units"))
            continue
        amounts = ([None] * len(shares) if cost.amount is None else
                   _unit_shares(cost.amount, [s.weight for s in shares], terms.minor_unit))
        for share, amount in zip(shares, amounts):
            extra[share.component_id].append(PeriodCost(
                f"shared:{cost.source_id}:{cost.month}:{share.component_id}", cost.month, cost.location, amount,
            ))
    results = tuple(calculate_component(replace(child, costs=child.costs + tuple(extra[identifier])))
                    for identifier, child in sorted(children.items()))
    for result in results:
        missing.extend(_gap(f"components[{result.component.component_id}].{m.field}", m.reason) for m in result.missing)
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete", children=results)
    totals: dict[tuple[date, Location], list[Decimal]] = {}
    ratio_keys: set[tuple[date, Location]] = set()
    roster = shared_calendar + tuple(row for result in results for row in result.calendar_rows)
    for result in results:
        conversion_rate = Decimal("1") if result.component.currency == component.currency else fx[result.component.currency or ""].rate
        assert conversion_rate is not None
        for row in result.rows:
            assert row.cost is not None
            period_key = (row.month, row.location)
            values = totals.setdefault(period_key, [ZERO, ZERO])
            if row.revenue_uses_ratio:
                ratio_keys.add(period_key)
            native_revenue, conversion_rate = +row.revenue, +conversion_rate
            with localcontext(Context(prec=GM_PRECISION)) as ctx:
                ctx.traps[Inexact] = not row.revenue_uses_ratio
                converted = _check_ratio_precision(native_revenue * conversion_rate, row.revenue_uses_ratio)
            values[0] = _add_revenue(values[0], converted, period_key in ratio_keys)
            values[1] += row.cost * conversion_rate
    hours: dict[tuple[date, Location], list[Decimal]] = {}
    for roster_row in roster:
        if roster_row.assignment.location in ("US", "India"):
            values = hours.setdefault((roster_row.month, roster_row.assignment.location), [ZERO, ZERO, ZERO])
            for index, amount in enumerate((roster_row.scheduled_hours, roster_row.billable_hours, roster_row.paid_hours)):
                assert amount is not None
                values[index] += amount
    rows = tuple(CommercialMonth(month, location, values[0], values[1],
                                 *hours.get((month, location), (None, None, None)),
                                 revenue_uses_ratio=(month, location) in ratio_keys)
                 for (month, location), values in sorted(totals.items()))
    return ComponentSchedule(component, rows, calendar_rows=roster, children=results)


def _milestones(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    if not isinstance(terms, MilestonePricing) or not terms.milestones:
        return ComponentSchedule(component, (), (_gap("pricing", "milestones are required"),), "incomplete")
    missing = []
    revenue: dict[tuple[date, Location], Decimal] = {}
    seen: set[str] = set()
    for item in terms.milestones:
        if not item.milestone_id.strip() or item.milestone_id in seen:
            missing.append(_gap("milestones.source_id", "milestone IDs must be distinct"))
        seen.add(item.milestone_id)
        if not item.acceptance_conditions or not item.acceptance_conditions.strip():
            missing.append(_gap("acceptance_conditions", "milestone acceptance is unconfirmed"))
        if (type(item.planned_date) is not date or component.service_start is None
                or component.service_end is None
                or not component.service_start <= item.planned_date <= component.service_end
                or item.location not in ("US", "India")):
            missing.append(_gap("milestones.date", "milestone date/location is outside service"))
        elif item.amount is not None:
            key = (item.planned_date.replace(day=1), item.location)
            revenue[key] = revenue.get(key, ZERO) + item.amount
        if item.amount is None:
            missing.append(_gap("milestones.amount", "milestone amount is unresolved"))
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete")
    return _assemble(component, revenue)


def _quantity_values(
    component: PricingComponent, lines: tuple[QuantityLine, ...], rate: Decimal,
) -> tuple[dict[tuple[date, Location], Decimal], list[MissingInput]]:
    missing = []
    revenue: dict[tuple[date, Location], Decimal] = {}
    seen: set[str] = set()
    for line in lines:
        if not line.source_id.strip() or line.source_id in seen:
            missing.append(_gap("quantities.source_id", "quantity sources must be distinct"))
        seen.add(line.source_id)
        if line.location not in ("US", "India") or not _month_valid(line.month, component):
            missing.append(_gap("quantities.period", "quantity period/location is outside service"))
        if line.quantity is None:
            missing.append(_gap("quantities.quantity", "quantity is unresolved"))
        else:
            key = (line.month, line.location)
            revenue[key] = revenue.get(key, ZERO) + line.quantity * rate
    return revenue, missing


def _quantities(component: PricingComponent) -> ComponentSchedule:
    terms = component.pricing
    expected = UnitPricing if component.profile == "unit" else TimeAndMaterials
    if not isinstance(terms, expected) or not isinstance(terms, (UnitPricing, TimeAndMaterials)):
        return ComponentSchedule(component, (), (_gap("pricing", "typed quantity terms are required"),), "incomplete")
    missing = []
    lines = terms.quantities if isinstance(terms, UnitPricing) else terms.estimates
    if isinstance(terms, TimeAndMaterials) and terms.calendar_estimates:
        if terms.unit != "hour" or terms.estimates or not component.staffing:
            missing.append(_gap("quantities.basis", "calendar estimates require hourly units and no manual estimates"))
        calendar_rows, _ = _calendar_rows(component)
        lines = tuple(QuantityLine(f"calendar:{row.assignment.assignment_id}:{row.month}", row.month,
                                   row.assignment.location, row.billable_hours)
                      for row in calendar_rows if row.assignment.location in ("US", "India"))
    if not terms.unit.strip() or not lines or terms.rate is None:
        missing.append(_gap("quantities", "confirmed rate, unit and quantities are required"))
    if isinstance(terms, UnitPricing) and terms.contractual_basis not in (
        "billable_units", "sprint_fee", "capacity_fee",
    ):
        missing.append(_gap("contractual_basis", "delivery estimates are not a billing basis"))
    revenue, gaps = _quantity_values(component, lines, terms.rate or ZERO)
    missing.extend(gaps)
    if isinstance(terms, TimeAndMaterials):
        _, usage_gaps = _quantity_values(component, terms.approved_usage, ZERO)
        missing.extend(usage_gaps)
        if terms.cap is not None and terms.minimum is not None and terms.minimum > terms.cap:
            missing.append(_gap("limits", "minimum exceeds the cap"))
        total = sum(revenue.values(), ZERO)
        target = max(total, terms.minimum) if terms.minimum is not None else total
        target = min(target, terms.cap) if terms.cap is not None else target
        if target != total:
            if (terms.limit_allocation_basis != "proportional_estimate" or total <= ZERO
                    or terms.minor_unit is None or _minor_units(target, terms.minor_unit) is None):
                missing.append(_gap("limit_allocation_basis", "changed limits need confirmed allocation and minor units"))
            else:
                revenue = _apportion(target, [FeeAllocation(m, loc, value)
                                              for (m, loc), value in sorted(revenue.items())], terms.minor_unit)
    if missing:
        return ComponentSchedule(component, (), tuple(missing), "incomplete")
    return _assemble(component, revenue)
