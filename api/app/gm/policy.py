"""Margin policy — floors and pass/fail evaluation.

Blueprint §2: US = 35% floor, India = 50% floor, mixed engagements test
each component on its own. A blended number is informational only; a
failing component still routes to the CEO exception queue.
"""

from __future__ import annotations

from decimal import Decimal

from app.gm.core import min_price as _min_price
from app.gm.types import Money, TemplateResult

US_FLOOR: Decimal = Decimal("0.35")
INDIA_FLOOR: Decimal = Decimal("0.50")


def check_floors(result: TemplateResult) -> dict:
    """Evaluate a computed :class:`TemplateResult` against policy floors.

    Returns a dict with:
      - ``us_pass``: bool — US component meets floor (True if no US revenue).
      - ``india_pass``: bool — India component meets floor (True if no India
        revenue).
      - ``requires_ceo``: bool — True iff any *present* component fails, OR
        the sheet is incomplete (missing cost).
      - ``failing``: list[str] — names of failing components, in evaluation
        order. Empty when everything passes.
    """
    failing: list[str] = []

    us_present = result.revenue_us > 0
    india_present = result.revenue_india > 0

    us_pass = True
    if us_present:
        us_pass = result.gm_us is not None and result.gm_us >= US_FLOOR
        if not us_pass:
            failing.append("US")

    india_pass = True
    if india_present:
        india_pass = result.gm_india is not None and result.gm_india >= INDIA_FLOOR
        if not india_pass:
            failing.append("India")

    # Incomplete sheets never auto-pass — someone must approve knowingly.
    requires_ceo = bool(failing) or not result.complete

    return {
        "us_pass": us_pass,
        "india_pass": india_pass,
        "requires_ceo": requires_ceo,
        "failing": failing,
    }


def min_price_for(delivery_cost: Money, floor: Decimal) -> Money:
    """Re-export of :func:`app.gm.core.min_price` for policy call sites."""
    return _min_price(delivery_cost, floor)
