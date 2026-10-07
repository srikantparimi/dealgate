"""Finance summary for a commercial GM outcome (S22 click-through fix).

Pure Decimal arithmetic over an assessed ``GmOutcome`` and its source
component: contract revenue, labor vs other delivery cost, gross profit
and the percentage views the Confirm page's GM summary renders. Lives
in ``app.gm`` because it is margin math (CLAUDE.md rule 2). Returns
For an incomplete fixed-fee plan it preserves the confirmed contract
revenue while leaving every cost-derived value unknown. This is not an
estimate: it is the typed fixed-fee term already supplied by the SOW.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.gm.engine import GmOutcome

_ZERO = Decimal("0")
_PCT = Decimal("0.0001")


def _pct(part: Decimal, whole: Decimal) -> str | None:
    if whole == _ZERO:
        return None
    return str((part / whole).quantize(_PCT))


def commercial_finance_summary(outcome: GmOutcome, component: Any) -> dict[str, Any]:
    """Build the FinanceSummary dict the UI renders, preserving known facts."""
    if outcome.status != "ok":
        pricing = getattr(component, "pricing", None)
        revenue = (
            getattr(pricing, "total_fee", None)
            if getattr(component, "profile", None) == "fixed_assignment"
            else None
        )
        if not isinstance(revenue, Decimal) or not revenue.is_finite():
            return {}
        money = Decimal("0.01")
        return {
            "revenue": str(revenue.quantize(money)),
            "labor_cost": None,
            "direct_cost": None,
            "total_delivery_cost": None,
            "gross_profit": None,
            "labor_pct": None,
            "direct_pct": None,
            "total_cost_pct": None,
            "pass_through": "0",
        }
    revenue = sum(outcome.revenue_by_location.values(), _ZERO)
    total_cost = sum(outcome.cost_by_location.values(), _ZERO)
    # "Other delivery expenses" are the component's explicit period
    # costs; everything else in the schedule's cost is the team.
    direct = _ZERO
    for row in getattr(component, "costs", ()) or ():
        amount = getattr(row, "amount", None)
        if amount is not None:
            direct += Decimal(amount)
    if direct > total_cost:
        # A cost line outside the assessed window cannot make labor
        # negative — fall back to the unsplit totals.
        direct = None  # type: ignore[assignment]
    labor = None if direct is None else total_cost - direct
    gross = revenue - total_cost
    money = Decimal("0.01")
    return {
        "revenue": str(revenue.quantize(money)),
        "labor_cost": str(labor.quantize(money)) if labor is not None else None,
        "direct_cost": str((direct if direct is not None else _ZERO).quantize(money)),
        "total_delivery_cost": str(total_cost.quantize(money)),
        "gross_profit": str(gross.quantize(money)),
        "labor_pct": _pct(labor, revenue) if labor is not None else None,
        "direct_pct": _pct(direct, revenue) if direct is not None else None,
        "total_cost_pct": _pct(total_cost, revenue),
        "pass_through": "0",
    }
