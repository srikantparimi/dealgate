"""Finance-certified service-scope replacement; signed schedules stay immutable."""
from collections import Counter
from datetime import date, datetime
from decimal import Context, Decimal, DecimalException, Inexact, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo

from app.gm.engine import GM_PRECISION


def _number(value):
    if isinstance(value, (float, bool)) or not isinstance(value, (str, Decimal, int)):
        raise ValueError("An exact finite decimal is required")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("An exact finite decimal is required")
    return Fraction(result)


def _money(value):
    with localcontext(Context(prec=GM_PRECISION)) as context:
        context.traps[Inexact] = True
        return Decimal(value.numerator) / Decimal(value.denominator)


def _day(value):
    if not isinstance(value, str):
        raise ValueError("An ISO date is required")
    return date.fromisoformat(value)


def _identity(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError("Explicit source identity is required")
    return value


def _rate(row, currency, cutoff):
    source_currency = _identity(row["currency"])
    if source_currency == currency:
        return Fraction(1)
    rate = _number(row.get("fx_rate"))
    if rate <= 0 or not _identity(row.get("fx_version")) or _day(row.get("fx_date")) > cutoff:
        raise ValueError("Reporting FX rate/version/date is unresolved")
    return rate


def reconcile_actual_coverage(schedules, records, *, as_of, timezone, currency):
    """Inputs are authorized raw signed rows and financial revision dictionaries.

    Fractions are explicitly certified service scope, never elapsed-day weights.
    Revenue and delivery-cost intervals are validated independently. Invalid
    participants stay in exclusions instead of silently affecting the estimate.
    """
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("Reporting cutoff requires a timezone-aware instant")
    cutoff = as_of.astimezone(ZoneInfo(timezone)).date()
    month = cutoff.replace(day=1)
    _identity(currency)
    excluded, valid, candidates = [], {}, {}
    schedules, records = list(schedules), list(records)
    schedule_counts = Counter(row.get("row_id") for row in schedules)
    invalid_schedule = False
    for row in schedules:
        try:
            if _day(row["month"]) != month:
                continue
            identity = _identity(row["row_id"])
            if schedule_counts[identity] != 1:
                raise ValueError("Ambiguous signed schedule row identity")
            for key in ("source_id", "source_version", "account_id"):
                _identity(row[key])
            prefix, index = identity.rsplit(":", 1)
            if prefix != row["source_id"] or not index.isdecimal() or str(int(index)) != index:
                raise ValueError("Schedule identity must bind the exact GM and row")
            rate = _rate(row, currency, cutoff)
            values = {}
            for key in ("revenue", "cost"):
                value = None if row[key] is None else _number(row[key])
                if value is not None and value < 0:
                    raise ValueError("Signed schedule amount cannot be negative")
                values[key] = None if value is None else _money(value * rate)
            valid[identity] = {**{key: row[key] for key in
                ("row_id", "source_id", "source_version", "account_id", "month")}, "scheduled": values}
        except (KeyError, ValueError, TypeError, DecimalException) as error:
            invalid_schedule = True
            excluded.append({"id": row.get("row_id"), "reason": f"Signed schedule unavailable: {error}"})

    record_counts = Counter(row.get("id") for row in records)
    latest = {}
    for row in records:
        revision = row.get("revision")
        if type(revision) is int and revision > 0:
            key = (row.get("source_system"), row.get("source_id"))
            latest[key] = max(latest.get(key, 0), revision)
    revision_counts = Counter((row.get("source_system"), row.get("source_id"), row.get("revision"))
                              for row in records)
    for row in records:
        try:
            identity = _identity(row["id"])
            if record_counts[identity] != 1:
                raise ValueError("Duplicate financial record identity")
            source = (_identity(row["source_system"]), _identity(row["source_id"]))
            revision = row["revision"]
            if type(revision) is not int or revision < 1:
                raise ValueError("Financial revision must be a positive integer")
            if revision != latest[source]:
                raise ValueError("Superseded financial revision remains historical")
            if revision_counts[(*source, revision)] != 1:
                raise ValueError("Ambiguous financial source revision")
            measure = {"recognized_revenue": "revenue", "delivery_cost": "cost"}.get(row["measure"])
            if measure is None:
                raise ValueError("Financial measure remains separate from service estimate")
            coverage = row.get("coverage")
            if not isinstance(coverage, dict):
                raise ValueError("Finance-certified service coverage is unavailable")
            if row.get("source_detached"):
                raise ValueError("Financial source is detached")
            index = coverage["schedule_row"]
            if type(index) is not int or index < 0:
                raise ValueError("Schedule row must be a nonnegative integer")
            target = f"{_identity(row['gm_model_id'])}:{index}"
            schedule = valid.get(target)
            if schedule is None:
                raise ValueError("Matching current signed schedule is unavailable")
            if (row["account_id"], coverage["sow_version_id"], row["period_month"]) != (
                schedule["account_id"], schedule["source_version"], schedule["month"]):
                raise ValueError("Account, SOW version or accounting period does not match")
            through, source_date = _day(coverage["through_date"]), _day(row["source_date"])
            if through.replace(day=1) != month or through > cutoff or source_date > cutoff or source_date < through:
                raise ValueError("Actual source date or coverage cutoff is incompatible")
            _identity(coverage["basis_evidence"])
            left, right = _number(coverage["fraction_start"]), _number(coverage["fraction_end"])
            if not 0 <= left < right <= 1:
                raise ValueError("Certified service fractions must satisfy 0 <= start < end <= 1")
            if schedule["scheduled"][measure] is None:
                raise ValueError("Unknown signed amount cannot establish uncovered forecast")
            amount = _money(_number(row["amount"]) * _rate(row, currency, cutoff))
            candidates.setdefault((target, measure), []).append((identity, left, right, amount))
        except (KeyError, ValueError, TypeError, DecimalException) as error:
            excluded.append({"id": row.get("id"), "reason": str(error)})

    rows = []
    for identity, schedule in valid.items():
        output = {key: value for key, value in schedule.items() if key != "scheduled"}
        for measure in ("revenue", "cost"):
            group = candidates.get((identity, measure), [])
            overlaps = {a[0] for a in group for b in group
                        if a[0] != b[0] and a[1] < b[2] and b[1] < a[2]}
            for key in sorted(overlaps):
                excluded.append({"id": key, "reason": "Overlapping certified coverage for signed row and measure"})
            accepted = sorted((item for item in group if item[0] not in overlaps), key=lambda item: item[0])
            scheduled = schedule["scheduled"][measure]
            try:
                fraction = sum((right - left for _, left, right, _ in accepted), Fraction())
                actual = sum((Fraction(amount) for _, _, _, amount in accepted), Fraction())
                uncovered = None if scheduled is None else Fraction(scheduled) * (1 - fraction)
                result = dict(scheduled=scheduled, actual_to_date=_money(actual),
                    covered_fraction=_money(fraction), uncovered_forecast=None if uncovered is None else _money(uncovered),
                    estimate=None if uncovered is None else _money(actual + uncovered),
                    actual_ids=[item[0] for item in accepted])
            except DecimalException:
                for key, *_ in accepted:
                    excluded.append({"id": key, "reason": "Reconciliation monetary precision requires review"})
                result = dict(scheduled=scheduled, actual_to_date=Decimal(0), covered_fraction=Decimal(0),
                              uncovered_forecast=scheduled, estimate=scheduled, actual_ids=[])
            output[measure] = result
        rows.append(output)
    totals = {}

    def aggregate(value, measure):
        try:
            return _money(value)
        except DecimalException:
            excluded.append({"id": f"totals:{measure}", "reason": "Aggregate monetary precision requires review"})
            return None

    for measure in ("revenue", "cost"):
        values = [row[measure]["estimate"] for row in rows]
        totals[measure] = None if invalid_schedule or not values or None in values else aggregate(
            sum((Fraction(value) for value in values), Fraction()), measure)
    revenue, cost = totals["revenue"], totals["cost"]
    totals["profit"] = None if revenue is None or cost is None else aggregate(
        Fraction(revenue) - Fraction(cost), "profit")
    with localcontext(Context(prec=GM_PRECISION)):
        totals["gm_pct"] = None if revenue is None or totals["profit"] is None or revenue <= 0 else totals["profit"] / revenue
    return dict(rows=rows, excluded=excluded, cutoff=cutoff.isoformat(), currency=currency, totals=totals)
