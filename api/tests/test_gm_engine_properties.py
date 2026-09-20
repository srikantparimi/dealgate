"""The universal invariants, asserted against every engagement type.

From the GM-correctness directive. A golden proves one case; a property
proves the shape of every case, including the ones nobody thought to write a
fixture for. These run over generated inputs across all seven types.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.gm.engine import (
    ENGINE_RULES,
    GM_PRECISION,
    ResourceInput,
    SowSpec,
    compute_gm,
)

# Deliberately NOT setting `getcontext().prec` here. The engine pins its own
# precision, and a global set by a test would only prove the tests agree with
# whatever the last file to run happened to want.
ALL_TYPES = sorted(ENGINE_RULES)


def _money(min_value="1", max_value="500000"):
    return st.decimals(
        min_value=Decimal(min_value),
        max_value=Decimal(max_value),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    )


@st.composite
def specs(draw, engagement_type: str | None = None):
    """A spec that the engine will accept, for any type."""

    et = engagement_type or draw(st.sampled_from(ALL_TYPES))
    locations = draw(
        st.lists(st.sampled_from(["US", "India"]), min_size=1, max_size=3)
    )
    resources = tuple(
        ResourceInput(
            role=f"R{i}",
            seniority="Senior",
            location=loc,
            billable_hours=draw(_money("1", "2000")),
            paid_hours=draw(_money("1", "2000")),
            bill_rate=draw(_money("1", "500")),
            cost_rate=draw(_money("1", "400")),
        )
        for i, loc in enumerate(locations)
    )
    base = SowSpec(engagement_type=et, resources=resources)

    if et in ("fixed_price", "assessment"):
        base = replace(base, contract_price=draw(_money("1000", "500000")))
    if et == "managed_service":
        loc = locations[0]
        base = replace(
            base,
            term_months=draw(st.integers(min_value=1, max_value=36)),
            monthly_fee={loc: draw(_money("100", "50000"))},
            monthly_team_cost={loc: draw(_money("50", "40000"))},
            resources=(),
        )
    if et == "permanent_placement":
        base = replace(
            base,
            placement_fee=draw(_money("1000", "100000")),
            recruiting_cost=draw(_money("100", "50000")),
            location=locations[0],
            resources=(),
        )
    return base


# --- invariant 1: the arithmetic is exact, or it is not presented ---------


@settings(max_examples=150, deadline=None)
@given(spec=specs())
def test_profit_and_margin_are_exact_or_absent(spec: SowSpec):
    result = compute_gm(spec)
    assert result.status in ("ok", "incomplete", "exception")

    if result.status != "ok":
        # Never a number alongside missing inputs.
        assert result.gm_blended is None
        return

    revenue = result.revenue_total
    cost = result.cost_total
    assert isinstance(revenue, Decimal) and isinstance(cost, Decimal)
    with localcontext() as ctx:
        ctx.prec = GM_PRECISION
        assert result.gm_blended == (revenue - cost) / revenue
    # Decimal throughout — no float can reach this (CLAUDE.md rule 2).
    assert not isinstance(result.gm_blended, float)


# --- invariant 2: the geographies reconcile ------------------------------


@settings(max_examples=150, deadline=None)
@given(spec=specs())
def test_us_and_india_reconcile_to_combined(spec: SowSpec):
    """No line counted twice, none dropped."""

    result = compute_gm(spec)
    if result.status != "ok":
        return
    assert sum(result.revenue_by_location.values(), Decimal(0)) == result.revenue_total
    assert sum(result.cost_by_location.values(), Decimal(0)) == result.cost_total
    for loc, gm in result.gm_by_location.items():
        rev = result.revenue_by_location.get(loc, Decimal(0))
        if gm is None:
            assert rev <= 0
        else:
            cost = result.cost_by_location.get(loc, Decimal(0))
            # Re-derive at the engine's own precision — comparing against
            # arithmetic done at the ambient precision would test the
            # context, not the engine.
            with localcontext() as ctx:
                ctx.prec = GM_PRECISION
                assert gm == (rev - cost) / rev


# --- invariant 3: removing an input yields incomplete, naming it ---------


@settings(max_examples=100, deadline=None)
@given(spec=specs())
def test_removing_a_cost_rate_flips_to_incomplete_and_names_it(spec: SowSpec):
    assume(spec.resources)
    before = compute_gm(spec)
    assume(before.status == "ok")

    stripped = replace(
        spec,
        resources=(replace(spec.resources[0], cost_rate=None),) + spec.resources[1:],
    )
    after = compute_gm(stripped)

    assert after.status == "incomplete"
    assert any(m.field == "cost_rate" and m.line == 0 for m in after.missing)
    # Missing cost must never be read as zero cost: that inflates the margin
    # and passes a floor the engagement would fail.
    assert after.gm_blended is None

    # Putting it back restores the identical number.
    restored = compute_gm(replace(stripped, resources=spec.resources))
    assert restored.status == "ok"
    assert restored.gm_blended == before.gm_blended


# --- invariant 4: GM% is scale-invariant ---------------------------------


@settings(max_examples=100, deadline=None)
@given(spec=specs(), factor=st.sampled_from([Decimal(2), Decimal(10), Decimal("0.5")]))
def test_scaling_revenue_and_cost_together_leaves_gm_unchanged(
    spec: SowSpec, factor: Decimal
):
    base = compute_gm(spec)
    assume(base.status == "ok")

    def scale(s: SowSpec) -> SowSpec:
        out = replace(
            s,
            resources=tuple(
                replace(
                    r,
                    billable_hours=(r.billable_hours * factor)
                    if r.billable_hours is not None
                    else None,
                    paid_hours=(r.paid_hours * factor)
                    if r.paid_hours is not None
                    else None,
                )
                for r in s.resources
            ),
        )
        if s.contract_price is not None:
            out = replace(out, contract_price=s.contract_price * factor)
        if s.placement_fee is not None:
            out = replace(
                out,
                placement_fee=s.placement_fee * factor,
                recruiting_cost=(s.recruiting_cost or Decimal(0)) * factor,
            )
        if s.monthly_fee:
            out = replace(
                out,
                monthly_fee={k: v * factor for k, v in s.monthly_fee.items()},
                monthly_team_cost={
                    k: v * factor for k, v in s.monthly_team_cost.items()
                },
            )
        return out

    scaled = compute_gm(scale(spec))
    assume(scaled.status == "ok")
    assert scaled.gm_blended == base.gm_blended


# --- invariant 5: the engine does not mutate, and does not ask -----------


@settings(max_examples=100, deadline=None)
@given(spec=specs())
def test_engine_never_mutates_its_input(spec: SowSpec):
    import copy

    before = copy.deepcopy(spec)
    compute_gm(spec)
    assert spec == before


@settings(max_examples=100, deadline=None)
@given(spec=specs())
def test_questions_only_ever_come_from_absent_fields(spec: SowSpec):
    """The engine reports gaps; it never invents a question.

    Every entry in `missing` names a field. None is a prompt, a suggestion or
    a request for a decision — those belong to the screen.
    """

    result = compute_gm(spec)
    for m in result.missing:
        assert m.field and isinstance(m.field, str)
        assert "?" not in m.reason


# --- invariant 6: same inputs, same output, forever ----------------------


@settings(max_examples=100, deadline=None)
@given(spec=specs())
def test_determinism(spec: SowSpec):
    first = compute_gm(spec)
    second = compute_gm(spec)
    assert first.status == second.status
    assert first.gm_blended == second.gm_blended
    assert first.revenue_by_location == second.revenue_by_location
    assert first.cost_by_location == second.cost_by_location


# --- the floor boundary, exactly -----------------------------------------


@pytest.mark.parametrize(
    ("cost", "expected_pass"),
    [
        ("65000", True),    # exactly 0.35
        ("65000.01", False),  # a hair under
        ("64999.99", True),
    ],
)
def test_floor_is_compared_unrounded(cost: str, expected_pass: bool):
    """35.000% passes, 34.9999% fails. Rounding to 2dp would erase this."""

    spec = SowSpec(
        engagement_type="fixed_price",
        contract_price=Decimal("100000"),
        resources=(
            ResourceInput(
                role="Engineer",
                location="US",
                billable_hours=Decimal("1"),
                paid_hours=Decimal("1"),
                cost_rate=Decimal(cost),
            ),
        ),
    )
    assert compute_gm(spec).passes["US"] is expected_pass


@pytest.mark.parametrize("engagement_type", ALL_TYPES)
@settings(max_examples=40, deadline=None)
@given(data=st.data())
def test_every_type_in_the_table_is_exercised(engagement_type: str, data):
    """A rule nobody runs is a rule nobody has checked.

    Parametrised per type and driven by `st.data()` so each rule is exercised
    over generated inputs rather than one sampled example.
    """

    spec = data.draw(specs(engagement_type=engagement_type))
    result = compute_gm(spec)
    assert result.status in ("ok", "incomplete", "exception"), engagement_type
    if result.status == "ok":
        assert result.gm_blended is not None


def test_an_unknown_type_is_refused_rather_than_guessed():
    result = compute_gm(SowSpec(engagement_type="barter_arrangement"))
    assert result.status == "exception"
    assert "will not guess" in (result.reason or "")


def test_result_does_not_depend_on_the_callers_decimal_context():
    """Invariant 6, the way it actually broke.

    The engine originally used whatever `getcontext().prec` the caller had
    last set, so the same SOW computed
    0.3611111111111111111111111111 at the default 28 and
    0.36111111111111111111111111111111111111111111111111 at 50. An ambient
    global two call frames away is not part of the inputs, and "same inputs,
    same output, forever" has to mean forever.

    Found by the property suite raising the precision for its own purposes,
    which is the only reason it showed up at all.
    """

    from decimal import getcontext

    spec = SowSpec(
        engagement_type="fixed_price",
        contract_price=Decimal("200000"),
        discounts=(Decimal("0.10"),),
        resources=(
            ResourceInput(
                role="Engineer",
                location="US",
                billable_hours=Decimal("1000"),
                paid_hours=Decimal("1000"),
                cost_rate=Decimal("115"),
            ),
        ),
    )

    original = getcontext().prec
    try:
        results = []
        for prec in (9, 28, 50, 60):
            getcontext().prec = prec
            results.append(compute_gm(spec).gm_blended)
        assert len(set(results)) == 1, (
            f"the engine returned {len(set(results))} different answers for one "
            f"SOW depending on ambient precision: {results}"
        )
        assert results[0] == Decimal("0.3611111111111111111111111111")
    finally:
        getcontext().prec = original
