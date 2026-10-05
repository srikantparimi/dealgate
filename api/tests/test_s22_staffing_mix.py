"""S22 · deterministic staffing-mix solver (pure gm math, no I/O).

The owner's scenario, verbatim: "if monthly we are getting 50k and need
4 resources for 1 year, suggest 3 offshore + 1 onshore to meet the
required GM; if the scope needs 6 people but the fee only supports 4 at
the floor, throw a caution so Delivery knows." All Decimal; hours follow
the manifesto §4 default of 40h/week (auto_staffing's constant).
"""

from __future__ import annotations

from decimal import Decimal

from app.gm.staffing_mix import MixCandidate, solve_staffing_mix

D = Decimal

# Caesars-shaped case: $75,400 fixed fee, 7 weeks, stated 35% target.
CAESARS = dict(
    revenue=D("75400"),
    weeks=D("7"),
    target_gm=D("0.35"),
    onshore_cost_per_hour=D("95"),
    offshore_cost_per_hour=D("30"),
)


def test_solver_meets_required_fte_with_cheapest_feasible_mix():
    result = solve_staffing_mix(required_fte=D("2.5"), min_onshore_fte=D("1"), **CAESARS)
    assert result.feasible is True
    best = result.suggested
    assert isinstance(best, MixCandidate)
    assert best.onshore + best.offshore >= D("2.5")
    assert best.gm >= D("0.35")
    # 1 onshore + 1.5 offshore: cost (95+45)*40*7 = 39,200 → GM 48.01%
    assert (best.onshore, best.offshore) == (D("1"), D("1.5"))
    assert best.cost == D("39200")
    assert best.gm == D("0.4801")


def test_owner_scenario_three_offshore_one_onshore():
    # 50k/month for 12 months, 4 FTE needed.
    result = solve_staffing_mix(
        revenue=D("600000"),
        weeks=D("52"),
        target_gm=D("0.35"),
        onshore_cost_per_hour=D("95"),
        offshore_cost_per_hour=D("30"),
        required_fte=D("4"),
        min_onshore_fte=D("1"),
    )
    assert result.feasible is True
    assert (result.suggested.onshore, result.suggested.offshore) == (D("1"), D("3"))
    assert result.suggested.gm >= D("0.35")


def test_caution_when_scope_needs_more_people_than_the_fee_supports():
    result = solve_staffing_mix(required_fte=D("6"), **CAESARS)
    assert result.feasible is False
    assert result.max_fte_at_target < D("6")
    assert result.caution is not None
    assert "6" in result.caution and "delivery" in result.caution.lower()
    # It still proposes the best achievable team so Delivery sees the gap.
    assert result.suggested is not None
    assert result.suggested.onshore + result.suggested.offshore == result.max_fte_at_target


def test_no_required_fte_reports_capacity_envelope():
    result = solve_staffing_mix(required_fte=None, **CAESARS)
    assert result.max_fte_at_target >= D("1")
    assert result.suggested is not None
    assert result.suggested.gm >= D("0.35")
    assert result.caution is None


def test_impossible_target_is_honest():
    result = solve_staffing_mix(
        revenue=D("1000"),
        weeks=D("7"),
        target_gm=D("0.35"),
        onshore_cost_per_hour=D("95"),
        offshore_cost_per_hour=D("30"),
        required_fte=D("1"),
    )
    assert result.feasible is False
    assert result.max_fte_at_target == D("0")
    assert result.caution is not None


def test_without_onshore_minimum_pure_offshore_wins_on_economics():
    result = solve_staffing_mix(required_fte=D("2.5"), **CAESARS)
    assert result.suggested.onshore == D("0")
    assert result.suggested.offshore == D("2.5")


def test_half_fte_steps_are_supported():
    # 2 full-time + 1 half-time — the Caesars team shape.
    result = solve_staffing_mix(required_fte=D("2.5"), **CAESARS)
    half_steps = {c for c in result.candidates if c.offshore == D("0.5") or c.onshore == D("0.5")}
    assert half_steps, "solver must consider half-FTE assignments"


def test_every_candidate_number_is_exact_decimal():
    result = solve_staffing_mix(required_fte=D("2"), **CAESARS)
    for candidate in result.candidates:
        assert isinstance(candidate.cost, Decimal)
        assert isinstance(candidate.gm, Decimal)
        assert candidate.gm == candidate.gm.quantize(D("0.0001"))
