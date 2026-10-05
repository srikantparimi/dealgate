"""Separate financial measures; these are never added to scheduled forecasts."""

from datetime import date, datetime
from decimal import Context, Decimal, DecimalException, Inexact, localcontext
from fractions import Fraction
from zoneinfo import ZoneInfo

from app.gm.engine import GM_PRECISION

MEASURES = {"recognized_revenue", "billed", "cash_collected", "delivery_cost"}


def summarize_financial_actuals(records, *, as_of: datetime, timezone: str, currency: str):
    if as_of.tzinfo is None:
        raise ValueError("Financial cutoff requires a timezone-aware instant")
    cutoff = as_of.astimezone(ZoneInfo(timezone)).date()
    amounts, excluded, included = {}, [], []
    for row in records:
        try:
            measure = row["measure"]
            if measure not in MEASURES:
                raise ValueError("Unknown financial measure")
            if date.fromisoformat(row["source_date"]) > cutoff:
                raise ValueError("Source date is after reporting cutoff")
            month = date.fromisoformat(row["period_month"])
            if month.day != 1 or month > cutoff:
                raise ValueError("Service period is invalid or after reporting cutoff")
            if isinstance(row["amount"], float):
                raise ValueError("Financial amount must be exact decimal")
            amount = Decimal(row["amount"])
            if not amount.is_finite():
                raise ValueError("Financial amount must be finite")
            value = Fraction(amount)
            if row["currency"] != currency:
                if not all(row.get(key) for key in ("fx_rate", "fx_version", "fx_date")):
                    raise ValueError("Reporting currency conversion is unresolved")
                if isinstance(row["fx_rate"], float):
                    raise ValueError("FX rate must be exact decimal")
                rate = Decimal(row["fx_rate"])
                if not rate.is_finite() or rate <= 0 or date.fromisoformat(row["fx_date"]) > cutoff:
                    raise ValueError("FX rate or reporting cutoff is invalid")
                value *= Fraction(rate)
            key = (month.isoformat(), measure)
            candidate = amounts.get(key, Fraction()) + value
            with localcontext(Context(prec=GM_PRECISION)) as context:
                context.traps[Inexact] = True
                Decimal(candidate.numerator) / Decimal(candidate.denominator)
            amounts[key] = candidate
            included.append(row["id"])
        except (ValueError, KeyError, TypeError, DecimalException) as exc:
            excluded.append({"id": row.get("id"), "reason": str(exc)})
    totals = []
    with localcontext(Context(prec=GM_PRECISION)) as context:
        context.traps[Inexact] = True
        for (month, measure), value in sorted(amounts.items()):
            totals.append({"period_month": month, "measure": measure, "currency": currency,
                           "amount": Decimal(value.numerator) / Decimal(value.denominator)})
    return {"totals": totals, "excluded": excluded, "included_ids": included,
            "cutoff": cutoff.isoformat(), "blended_with_forecast": False}
