"""Permission-neutral monthly planning projections over explicit economic scopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Context, Decimal, Inexact, localcontext
from fractions import Fraction
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.gm.core import gross_margin
from app.gm.engine import GM_PRECISION

ZERO, ONE = Decimal("0"), Decimal("1")
SCHEMA_VERSION = "forecast-outlook-v1"
Scenario = Literal["committed", "expected", "upside"]


@dataclass(frozen=True)
class ForecastLine:
    row_id: str
    account_id: str
    source_id: str
    source_version: str
    scope_id: str
    month: date
    lifecycle: str
    currency: str | None
    revenue: Decimal | None
    cost: Decimal | None
    probability: Decimal | None = None
    probability_source: str | None = None
    assumptions: tuple[str, ...] = ()
    scope_fraction: Decimal = ONE
    unavoidable_cost: Decimal = ZERO  # Included in cost, not an additional charge.
    fx_rate: Decimal | None = None
    fx_version: str | None = None
    fx_date: date | None = None
    scenario_group: str | None = None
    selected: bool = True
    missing: tuple[str, ...] = ()
    revenue_uses_ratio: bool = False


def _money(value: Fraction, *, uses_ratio: bool = False) -> Decimal:
    """Round only proven ratio tails; never silently discard exact monetary digits."""
    with localcontext(Context(prec=GM_PRECISION)) as context:
        context.traps[Inexact] = not uses_ratio
        result = Decimal(value.numerator) / Decimal(value.denominator)
        if uses_ratio and result.adjusted() >= GM_PRECISION - 1:
            raise Inexact("Ratio money exceeds supported fractional precision")
        return result


def _repeating(value: Fraction) -> bool:
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    return denominator != 1


def validate_converted_scope(coverage: tuple[tuple[date, str, Decimal], ...]) -> None:
    """Reject overlapping signed scope before its conversion link can be persisted."""
    totals: dict[tuple[date, str], Fraction] = {}
    for month, location, fraction in coverage:
        if not fraction.is_finite() or not ZERO < fraction <= ONE:
            raise ValueError("Converted scope fraction must be in (0,1]")
        key = (month, location)
        totals[key] = totals.get(key, Fraction()) + Fraction(fraction)
        if totals[key] > 1:
            raise ValueError("Signed conversions exceed the canonical service-month scope")


def _month(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def _index(day: date) -> int:
    return day.year * 12 + day.month - 1


def _validate(line: ForecastLine) -> None:
    if type(line.revenue_uses_ratio) is not bool:
        raise ValueError("Revenue ratio provenance must be a boolean")
    if any(not value.strip() for value in (line.row_id, line.account_id, line.source_id,
                                          line.source_version, line.scope_id)):
        raise ValueError("Forecast identities and economic scope are required")
    if type(line.month) is not date or line.month.day != 1:
        raise ValueError("Forecast month must be the first date of its service month")
    for field in ("revenue", "cost", "probability", "scope_fraction", "unavoidable_cost", "fx_rate"):
        value = getattr(line, field)
        if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < ZERO):
            raise ValueError(f"{field} must be a finite nonnegative Decimal")
    if not ZERO < line.scope_fraction <= ONE:
        raise ValueError("Economic scope fraction must be in (0,1]")
    if line.probability is not None and line.probability > ONE:
        raise ValueError("Probability must be in [0,1]")
    if line.fx_rate is not None and line.fx_rate <= ZERO:
        raise ValueError("FX rate must be positive")
    if line.cost is not None and line.unavoidable_cost > line.cost:
        raise ValueError("Unavoidable cost is a subset of total cost")


def _reasons(line: ForecastLine, reporting_currency: str) -> list[str]:
    reasons = list(line.missing)
    if line.lifecycle not in {"signed", "needs_review", "tentative", "won_unsigned"}:
        reasons.append(f"Lifecycle {line.lifecycle} is excluded")
    if line.scenario_group and not line.selected:
        reasons.append("Alternative option is not selected")
    if line.currency is None or not line.currency.strip():
        reasons.append("Currency is unresolved")
    elif line.currency != reporting_currency and (line.fx_rate is None or not line.fx_version
                                                or not line.fx_version.strip() or not line.fx_date):
        reasons.append("Reporting FX rate/version/date is unresolved")
    if line.revenue is None:
        reasons.append("Revenue is unresolved")
    if line.lifecycle != "signed":
        if line.probability is None or not line.probability_source or not line.probability_source.strip():
            reasons.append("Win probability and its provenance are unresolved")
        if not line.assumptions or any(not assumption.strip() for assumption in line.assumptions):
            reasons.append("Planning assumptions are unresolved")
        if line.cost is None:
            reasons.append("Estimated delivery cost is unresolved")
    return reasons


def _sum_rows(rows: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    included = [row for row in rows if start <= row["month"] < end]

    def total(field: str) -> Decimal:
        values = [row for row in included if row[field] is not None]
        uses_ratio = any(row["cost_uses_ratio" if field in {"cost", "unavoidable_cost"}
                             else "revenue_uses_ratio"] for row in values)
        try:
            return _money(sum((Fraction(row[field]) for row in values), Fraction()), uses_ratio=uses_ratio)
        except Inexact as error:
            raise ValueError("Forecast aggregate monetary precision requires review") from error

    revenue, signed, expected, known_cost = (total(field) for field in ("revenue", "signed", "expected", "cost"))
    complete = all(row["cost"] is not None for row in included)
    cost = known_cost if complete else None
    return {"start": start, "end_exclusive": end, "revenue": revenue, "signed": signed,
            "potential": total("potential"),
            "expected": expected, "cost": cost, "known_cost": known_cost,
            "cost_complete": complete, "gm": gross_margin(revenue, cost) if revenue > ZERO and cost is not None else None,
            "signed_coverage": signed / expected if expected > ZERO else None,
            "provisional": total("provisional"),
            "unavoidable_cost": total("unavoidable_cost")}


def project_outlook(
    lines: tuple[ForecastLine, ...], *, as_of: datetime, timezone: str,
    scenario: Scenario = "expected", future_quarters: int = 2, reporting_currency: str = "USD",
) -> dict[str, Any]:
    if as_of.tzinfo is None:
        raise ValueError("As-of time must be timezone aware")
    if scenario not in {"committed", "expected", "upside"} or future_quarters not in {1, 2, 4}:
        raise ValueError("Unsupported scenario or future-quarter count")
    if not reporting_currency.strip():
        raise ValueError("Reporting currency is required")
    with localcontext(Context(prec=GM_PRECISION)):
        return _project(lines, as_of, timezone, scenario, future_quarters, reporting_currency)


def _project(lines: tuple[ForecastLine, ...], as_of: datetime, timezone: str, scenario: Scenario,
             future_quarters: int, reporting_currency: str) -> dict[str, Any]:
    local = as_of.astimezone(ZoneInfo(timezone)).date()
    current = _index(local) - (local.month - 1) % 3
    start, future_start, end = _month(current), _month(current + 3), _month(current + 3 * (future_quarters + 1))
    identities: set[str] = set()
    economic_identities: set[tuple[str, str, str, date]] = set()
    versions: dict[tuple[str, str], str] = {}
    groups: dict[tuple[str, str], str] = {}
    covered: dict[tuple[str, str, date], Fraction] = {}
    eligible, excluded = [], []
    for line in lines:
        _validate(line)
        if line.row_id in identities:
            raise ValueError("duplicate Forecast row identity")
        identities.add(line.row_id)
        economic_identity = (line.account_id, line.source_id, line.scope_id, line.month)
        if economic_identity in economic_identities:
            raise ValueError("duplicate Forecast economic scope identity")
        economic_identities.add(economic_identity)
        version_key = (line.account_id, line.source_id)
        if version_key in versions and versions[version_key] != line.source_version:
            raise ValueError("Mixed source versions cannot produce one fresh projection")
        versions[version_key] = line.source_version
        reasons = _reasons(line, reporting_currency)
        if reasons:
            excluded.append({"row_id": line.row_id, "source_id": line.source_id,
                             "account_id": line.account_id, "month": line.month, "reasons": reasons})
            continue
        if line.scenario_group and line.selected:
            key = (line.account_id, line.scenario_group)
            if key in groups and groups[key] != line.source_id:
                raise ValueError("Mutually exclusive options have more than one selected source")
            groups[key] = line.source_id
        if line.lifecycle == "signed":
            coverage_key = (line.account_id, line.scope_id, line.month)
            covered[coverage_key] = covered.get(coverage_key, Fraction()) + Fraction(line.scope_fraction)
            if covered[coverage_key] > ONE:
                raise ValueError("Signed economic scope is over-covered")
        eligible.append(line)
    projected = []
    for line in eligible:
        signed = line.lifecycle == "signed"
        coverage = covered.get((line.account_id, line.scope_id, line.month), Fraction())
        remaining = Fraction(1) if signed else max(Fraction(), Fraction(line.scope_fraction) - coverage) / Fraction(line.scope_fraction)
        if remaining == ZERO:
            excluded.append({"row_id": line.row_id, "source_id": line.source_id,
                             "account_id": line.account_id, "month": line.month,
                             "reasons": ["Economic scope converted to signed work"]})
            continue
        assert line.revenue is not None
        assert signed or line.probability is not None
        probability = Fraction(line.probability) if line.probability is not None else Fraction(1)
        weight = Fraction(1) if signed or scenario == "upside" else (probability if scenario == "expected" else Fraction())
        assert line.currency == reporting_currency or line.fx_rate is not None
        fx = Fraction(line.fx_rate) if line.currency != reporting_currency and line.fx_rate is not None else Fraction(1)
        full_value = Fraction(line.revenue) * remaining * fx
        revenue_ratio = line.revenue_uses_ratio or _repeating(full_value)
        unavoidable_value = Fraction(line.unavoidable_cost) * remaining * fx
        cost_value = None if line.cost is None else (
            (Fraction(line.cost) - Fraction(line.unavoidable_cost)) * remaining * fx * weight + unavoidable_value)
        cost_ratio = _repeating(unavoidable_value) or (cost_value is not None and _repeating(cost_value))
        try:
            full = _money(full_value, uses_ratio=revenue_ratio)
            revenue = _money(full_value * weight, uses_ratio=revenue_ratio)
            expected = _money(full_value if signed else full_value * probability, uses_ratio=revenue_ratio)
            unavoidable = _money(unavoidable_value, uses_ratio=cost_ratio)
            cost = None if cost_value is None else _money(cost_value, uses_ratio=cost_ratio)
        except Inexact:
            excluded.append({"row_id": line.row_id, "source_id": line.source_id,
                             "account_id": line.account_id, "month": line.month,
                             "reasons": ["Forecast monetary precision requires review"]})
            continue
        projected.append({"row_id": line.row_id, "account_id": line.account_id,
                          "source_id": line.source_id, "source_version": line.source_version,
                          "scope_id": line.scope_id, "month": line.month, "lifecycle": line.lifecycle,
                          "revenue": revenue, "signed": full if signed else ZERO,
                          "potential": ZERO if signed else revenue, "expected": expected,
                          "cost": cost, "unavoidable_cost": unavoidable,
                          "provisional": revenue if line.lifecycle == "needs_review" else ZERO,
                          "scope_remaining": Decimal(remaining.numerator) / Decimal(remaining.denominator),
                          "revenue_uses_ratio": revenue_ratio, "cost_uses_ratio": cost_ratio,
                          "probability": line.probability,
                          "currency": reporting_currency, "original_currency": line.currency,
                          "fx_version": line.fx_version, "fx_date": line.fx_date})
    def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"current_month": _sum_rows(rows, _month(_index(local)), _month(_index(local) + 1)),
                "current_quarter": _sum_rows(rows, start, future_start),
                "future": _sum_rows(rows, future_start, end),
                "quarters": [_sum_rows(rows, _month(index), _month(index + 3))
                             for index in range(current, _index(end), 3)]}
    accounts = [{"account_id": account, **totals([row for row in projected if row["account_id"] == account])}
                for account in sorted({line.account_id for line in lines})]
    return {"schema_version": SCHEMA_VERSION, "as_of": as_of, "timezone": timezone,
            "currency": reporting_currency, "scenario": scenario, "future_quarters": future_quarters,
            **totals(projected), "accounts": accounts,
            "months": [_sum_rows(projected, _month(index), _month(index + 1)) for index in range(current, _index(end))],
            "rows": projected, "excluded": excluded,
            "actuals_basis": "service_schedule", "actuals_available": False}
