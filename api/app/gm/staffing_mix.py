"""Deterministic staffing-mix solver (S22).

Pure Decimal arithmetic, no I/O (CLAUDE.md rule 2: margin math lives in
``api/app/gm``; LLMs never compute a number). Given the engagement's
revenue, duration and a target GM, enumerate onshore/offshore mixes in
half-FTE steps and report:

- the cheapest mix that covers the required FTE at or above target GM;
- the capacity envelope (max FTE affordable at the target);
- an explicit caution when scope needs more people than the fee
  supports — Delivery must see that gap, never have it smoothed over.

Hours follow the manifesto §4 default of 40 billable hours per week
(the same constant ``services.auto_staffing`` uses). The target GM is an
explicit input — policy floors or a contractual margin — because
blended-vs-per-geography advisory feasibility is a policy question the
blueprint does not answer (logged in docs/questions.md); the saved
commercial model still goes through the real engine and real floors.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

HOURS_PER_WEEK = Decimal("40")
_HALF = Decimal("0.5")
_GM_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class MixCandidate:
    onshore: Decimal
    offshore: Decimal
    cost: Decimal
    gm: Decimal

    @property
    def total_fte(self) -> Decimal:
        return self.onshore + self.offshore


@dataclass(frozen=True)
class MixResult:
    feasible: bool
    suggested: MixCandidate | None
    max_fte_at_target: Decimal
    candidates: tuple[MixCandidate, ...]
    caution: str | None
    target_gm: Decimal


def _steps(limit: Decimal) -> list[Decimal]:
    values: list[Decimal] = []
    cursor = Decimal("0")
    while cursor <= limit:
        values.append(cursor)
        cursor += _HALF
    return values


def solve_staffing_mix(
    *,
    revenue: Decimal,
    weeks: Decimal,
    target_gm: Decimal,
    onshore_cost_per_hour: Decimal,
    offshore_cost_per_hour: Decimal,
    required_fte: Decimal | None = None,
    min_onshore_fte: Decimal = Decimal("0"),
    max_fte_per_location: Decimal = Decimal("10"),
) -> MixResult:
    if revenue <= 0 or weeks <= 0:
        raise ValueError("revenue and weeks must be positive")
    if not Decimal("0") <= target_gm < Decimal("1"):
        raise ValueError("target GM must be in [0, 1)")

    hours = HOURS_PER_WEEK * weeks
    candidates: list[MixCandidate] = []
    for onshore in _steps(max_fte_per_location):
        if onshore < min_onshore_fte:
            continue  # delivery-presence constraint is a human input
        for offshore in _steps(max_fte_per_location):
            if onshore + offshore == 0:
                continue
            cost = (
                onshore * onshore_cost_per_hour + offshore * offshore_cost_per_hour
            ) * hours
            gm = ((revenue - cost) / revenue).quantize(
                _GM_QUANTUM, rounding=ROUND_HALF_UP
            )
            candidates.append(MixCandidate(onshore, offshore, cost, gm))

    at_target = [c for c in candidates if c.gm >= target_gm]
    max_fte_at_target = max((c.total_fte for c in at_target), default=Decimal("0"))

    def _preference(c: MixCandidate) -> tuple:
        # Cheapest first, then fewer onshore (cost symmetry tiebreak),
        # then smaller team — deterministic ordering.
        return (c.cost, c.onshore, c.total_fte)

    suggested: MixCandidate | None = None
    feasible = False
    caution: str | None = None

    if required_fte is not None:
        covering = sorted(
            (c for c in at_target if c.total_fte >= required_fte), key=_preference
        )
        if covering:
            suggested, feasible = covering[0], True
        else:
            # Best achievable team at target so Delivery sees the gap.
            best_under = sorted(
                (c for c in at_target if c.total_fte == max_fte_at_target),
                key=_preference,
            )
            suggested = best_under[0] if best_under else None
            caution = (
                f"Scope needs ~{required_fte} FTE but the fee supports at most "
                f"{max_fte_at_target} FTE at the {target_gm:.0%} GM target — "
                "delivery risk: raise the fee, narrow scope, or accept lower "
                "margin with an explicit exception."
            )
    else:
        best_cap = sorted(
            (c for c in at_target if c.total_fte == max_fte_at_target),
            key=_preference,
        )
        suggested = best_cap[0] if best_cap else None
        feasible = suggested is not None

    if required_fte is not None and not feasible and not at_target:
        caution = (
            f"No team of any size reaches the {target_gm:.0%} GM target at "
            "these rates — delivery risk: the engagement is unprofitable as "
            "priced."
        )

    return MixResult(
        feasible=feasible,
        suggested=suggested,
        max_fte_at_target=max_fte_at_target,
        candidates=tuple(candidates),
        caution=caution,
        target_gm=target_gm,
    )
