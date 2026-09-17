"""Property-based tests for the GM primitives.

We use very small ``max_examples`` because the invariants are algebraic and
Hypothesis finds counterexamples fast — no need to burn CI time.
"""

from decimal import Decimal, getcontext

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.gm import gross_margin, min_price

# Comfortable precision for the intermediate divisions.
getcontext().prec = 50


def _money(min_value: str = "0", max_value: str = "1000000"):
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    )


# A tiny tolerance for the round-trip test — division is exact in Decimal at
# our chosen precision, but the values still need to compare "close enough".
_EPS = Decimal("0.0001")


@given(revenue=_money("0.01"), cost=_money("0"))
@settings(max_examples=200, deadline=None)
def test_min_price_roundtrip(revenue: Decimal, cost: Decimal) -> None:
    assume(cost < revenue)  # otherwise GM <= 0 and floor is degenerate
    gm = gross_margin(revenue, cost)
    assume(0 <= gm < Decimal("0.9999"))  # keep floor strictly < 1
    priced = min_price(cost, gm)
    assert abs(priced - revenue) <= _EPS * max(revenue, Decimal("1"))


@given(revenue=_money("1"), cost_a=_money("0"), delta=_money("0.01"))
@settings(max_examples=200, deadline=None)
def test_gross_margin_monotonic_in_cost(
    revenue: Decimal, cost_a: Decimal, delta: Decimal
) -> None:
    """Holding revenue fixed, increasing cost never increases GM."""
    cost_b = cost_a + delta
    assume(cost_a >= 0 and cost_b >= 0)
    gm_a = gross_margin(revenue, cost_a)
    gm_b = gross_margin(revenue, cost_b)
    assert gm_b <= gm_a


@given(cost_a=_money("0"), delta=_money("0.01"), floor=_money("0", "0.9"))
@settings(max_examples=200, deadline=None)
def test_min_price_monotonic_in_cost(
    cost_a: Decimal, delta: Decimal, floor: Decimal
) -> None:
    """Holding floor fixed, increasing cost never decreases min_price."""
    cost_b = cost_a + delta
    p_a = min_price(cost_a, floor)
    p_b = min_price(cost_b, floor)
    assert p_b >= p_a
