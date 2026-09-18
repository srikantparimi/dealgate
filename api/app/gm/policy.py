"""Margin policy — floors and pass/fail evaluation.

Blueprint §2: US = 35% floor, India = 50% floor, mixed engagements test
each component on its own. A blended number is informational only; a
failing component still routes to the CEO exception queue.

Sprint 2 E4 makes the floors overridable per ``policy_version`` (Finance
publishes new floors from the admin UI). This module stays a pure library
— no DB imports — so the DB read lives in ``app.services.policy`` and
callers pass floors into :func:`check_floors_with` or the ``us_floor`` /
``india_floor`` helpers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from app.gm.core import min_price as _min_price
from app.gm.types import Money, TemplateResult

US_FLOOR: Decimal = Decimal("0.35")
INDIA_FLOOR: Decimal = Decimal("0.50")


class _PolicyLike(Protocol):
    """Duck-typed view of the fields we need from a policy record.

    Kept as a ``Protocol`` on purpose: this module must not import the ORM
    or the service layer (§2 — GM is a pure library). Anything with
    ``us_floor`` and ``india_floor`` Decimals — the ORM row, the sentinel
    from ``app.services.policy``, or a test dataclass — works.
    """

    us_floor: Decimal
    india_floor: Decimal


def us_floor(policy_version: _PolicyLike | None = None) -> Decimal:
    """Return the effective US floor: the version's, else the blueprint default."""

    if policy_version is None:
        return US_FLOOR
    return policy_version.us_floor


def india_floor(policy_version: _PolicyLike | None = None) -> Decimal:
    """Return the effective India floor: the version's, else the default."""

    if policy_version is None:
        return INDIA_FLOOR
    return policy_version.india_floor


def check_floors(
    result: TemplateResult,
    *,
    us_floor_value: Decimal = US_FLOOR,
    india_floor_value: Decimal = INDIA_FLOOR,
) -> dict:
    """Evaluate a computed :class:`TemplateResult` against policy floors.

    Sprint 2 E4: the two ``*_floor_value`` kwargs let callers pass a
    ``policy_version``-derived floor without changing any of Agent B's
    ratified call sites — the defaults preserve the previous behavior byte
    for byte. Use :func:`us_floor` / :func:`india_floor` to derive the
    values from a policy version (or ``None`` for the sentinel).

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
        us_pass = result.gm_us is not None and result.gm_us >= us_floor_value
        if not us_pass:
            failing.append("US")

    india_pass = True
    if india_present:
        india_pass = (
            result.gm_india is not None and result.gm_india >= india_floor_value
        )
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
