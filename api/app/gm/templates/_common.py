"""Shared helpers for template computation.

Not a public API — templates import from here to avoid restating the
component-roll-up in six files.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from app.gm.core import gross_margin
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult

# Locations we know about. Anything else is a caller bug, not a data gap.
_VALID_LOCATIONS = frozenset({"US", "India"})


def _safe_gm(revenue: Money, cost: Money) -> Optional[Decimal]:
    if revenue <= 0:
        return None
    return gross_margin(revenue, cost)


def roll_up(
    resources: Iterable[ResourceLine],
    costs: Iterable[CostLine] = (),
    *,
    field_prefix: str = "resources",
) -> TemplateResult:
    """Aggregate resource lines + non-labor costs into a :class:`TemplateResult`.

    Rules:
      * Unknown ``location`` is a coding error → ``ValueError`` (not a data gap).
      * Missing ``hourly_cost`` on any resource marks the sheet incomplete
        and adds ``"<prefix>[i].hourly_cost"`` to ``missing``.
      * Missing ``amount`` on any :class:`CostLine` does the same, keyed by
        ``"costs[i].amount"``.
      * A negative revenue is invalid data → ``ValueError`` (per §2 rules).
      * When incomplete, computed component costs still reflect *known*
        pieces; the ``complete=False`` flag and ``missing`` list carry the
        warning. This lets the UI show a partial picture without pretending
        gaps are zero.
    """
    revenue_us = Decimal("0")
    revenue_india = Decimal("0")
    cost_us = Decimal("0")
    cost_india = Decimal("0")
    missing: list[str] = []

    for idx, line in enumerate(resources):
        if line.location not in _VALID_LOCATIONS:
            raise ValueError(f"unknown location: {line.location!r}")
        rev = line.revenue()
        if rev < 0:
            raise ValueError("resource revenue must be non-negative")
        if line.location == "US":
            revenue_us += rev
        else:
            revenue_india += rev

        cost = line.cost()
        if cost is None:
            missing.append(f"{field_prefix}[{idx}].hourly_cost")
            continue
        if cost < 0:
            raise ValueError("resource cost must be non-negative")
        if line.location == "US":
            cost_us += cost
        else:
            cost_india += cost

    for idx, cl in enumerate(costs):
        if cl.location not in _VALID_LOCATIONS:
            raise ValueError(f"unknown cost location: {cl.location!r}")
        if cl.amount is None:
            missing.append(f"costs[{idx}].amount")
            continue
        if cl.amount < 0:
            raise ValueError("cost amount must be non-negative")
        if cl.location == "US":
            cost_us += cl.amount
        else:
            cost_india += cl.amount

    return build_result(
        revenue_us=revenue_us,
        cost_us=cost_us,
        revenue_india=revenue_india,
        cost_india=cost_india,
        missing=missing,
    )


def build_result(
    *,
    revenue_us: Money,
    cost_us: Money,
    revenue_india: Money,
    cost_india: Money,
    missing: list[str],
) -> TemplateResult:
    """Compute GMs from already-aggregated components.

    Blended GM is defined over the components that actually have revenue.
    It is informational only — policy checks the components on their own.
    """
    if revenue_us < 0 or revenue_india < 0:
        raise ValueError("revenue must be non-negative")

    gm_us = _safe_gm(revenue_us, cost_us) if revenue_us > 0 else None
    gm_in = _safe_gm(revenue_india, cost_india) if revenue_india > 0 else None

    total_rev = revenue_us + revenue_india
    total_cost = cost_us + cost_india
    gm_blended = _safe_gm(total_rev, total_cost) if total_rev > 0 else None

    return TemplateResult(
        revenue_us=revenue_us,
        cost_us=cost_us,
        revenue_india=revenue_india,
        cost_india=cost_india,
        gm_us=gm_us,
        gm_india=gm_in,
        gm_blended=gm_blended,
        complete=not missing,
        missing=list(missing),
    )
