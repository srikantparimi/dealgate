"""One calculation core; a revenue rule and a cost rule per engagement type.

Per the GM-correctness directive. The shape that makes "every SOW we sign"
tractable is not an ``if`` chain per screen — it is a small core that enforces
the universal invariants, plus a pair of rules per type declared as data the
core reads. Adding a new SOW shape means adding a rule pair and its fixtures;
it does not mean touching the core, and it cannot quietly change how any
other type is computed.

The core's contract, which holds for every type:

- ``gross_profit = revenue - cost`` and ``gm = gross_profit / revenue``
  exactly, in Decimal, or the result is ``incomplete`` / ``exception``. Never
  a float, never NaN, never a number presented alongside missing inputs.
- US and India reconcile to the combined figure: revenues sum, costs sum, no
  line counted twice or dropped.
- A missing required input makes the result ``incomplete`` and names the
  field and the line. Supplying it restores the identical number.
- Zero, negative or absent revenue is an ``exception`` state, not a
  percentage. ``0.0%`` reads as a real and very bad margin; "there is nothing
  to divide by" is a different statement and the screen must be able to make
  it.
- The engine never mutates its input and never asks a question. Questions are
  validation reporting an absent field — they come from `missing`, never from
  a rule deciding it would like more information.

Floors are compared unrounded: 35.000% passes, 34.9999% does not. Rounding to
two places before the test would erase exactly the cases that matter.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any, Literal

from app.gm.policy import INDIA_FLOOR, US_FLOOR

__all__ = [
    "ENGINE_RULES",
    "EngagementRule",
    "GmOutcome",
    "Location",
    "MissingInput",
    "ResourceInput",
    "DirectCost",
    "SowSpec",
    "GM_PRECISION",
    "compute_gm",
    "rule_for",
]

Location = Literal["US", "India"]
_LOCATIONS: tuple[Location, ...] = ("US", "India")

ZERO = Decimal("0")

# Decimal division precision, pinned.
#
# Without this the engine's answer depends on whatever the *caller* last set
# `getcontext().prec` to: the same SOW computes 0.3611111111111111111111111111
# at the default 28 and 0.36111111111111111111111111111111111111111111111111
# at 50. Invariant 6 says same inputs, same policy version, same output,
# forever — an ambient global two call frames away is not part of the inputs.
# 28 is Python's default, and the value every stored golden was computed at.
GM_PRECISION = 28


# --- inputs ---------------------------------------------------------------


@dataclass(frozen=True)
class ResourceInput:
    """One person (or one role) on the engagement.

    ``billable_hours`` and ``paid_hours`` are deliberately separate. They are
    equal on most engagements and emphatically not on staff augmentation with
    a leave, bench or replacement clause: the client stops being billed while
    we keep paying. Collapsing them into one number is how a margin quietly
    overstates itself.
    """

    role: str
    seniority: str | None = None
    location: Location | None = None
    billable_hours: Decimal | None = None
    paid_hours: Decimal | None = None
    bill_rate: Decimal | None = None
    cost_rate: Decimal | None = None
    utilization: Decimal = Decimal("1")
    person_name: str | None = None
    is_subcontractor: bool = False

    @property
    def effective_billable(self) -> Decimal | None:
        if self.billable_hours is None:
            return None
        return self.billable_hours * self.utilization

    @property
    def effective_paid(self) -> Decimal | None:
        """Paid hours, defaulting to billable when the SOW does not separate them."""

        hours = self.paid_hours if self.paid_hours is not None else self.billable_hours
        if hours is None:
            return None
        return hours * self.utilization


@dataclass(frozen=True)
class DirectCost:
    """A non-labour cost: travel, tooling, licences, subcontractor invoices."""

    label: str
    amount: Decimal | None
    location: Location | None = None
    pass_through: bool = False


@dataclass(frozen=True)
class SowSpec:
    """Everything the engine needs, in engine-neutral terms."""

    engagement_type: str
    resources: tuple[ResourceInput, ...] = ()
    direct_costs: tuple[DirectCost, ...] = ()

    # Fixed-fee family.
    contract_price: Decimal | None = None
    revenue_allocation: dict[str, Decimal] | None = None
    allocation_basis: str = "cost_weighted"

    # T&M.
    not_to_exceed: Decimal | None = None

    # Managed service.
    term_months: int | None = None
    monthly_fee: dict[str, Decimal] = field(default_factory=dict)
    monthly_team_cost: dict[str, Decimal] = field(default_factory=dict)
    onboarding_fee: Decimal | None = None
    ramp_months: int = 0

    # Permanent placement.
    placement_fee: Decimal | None = None
    recruiting_cost: Decimal | None = None
    refund_reserve_pct: Decimal | None = None
    location: Location | None = None

    # Cross-cutting.
    discounts: tuple[Decimal, ...] = ()
    contingency_pct: Decimal | None = None
    fx_rate: Decimal | None = None
    fx_as_of: str | None = None
    currency: str = "USD"

    # Hybrid.
    components: tuple["SowSpec", ...] = ()


@dataclass(frozen=True)
class MissingInput:
    field: str
    reason: str
    line: int | None = None
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "reason": self.reason,
            "line": self.line,
            "role": self.role,
        }


# --- rule outputs ---------------------------------------------------------


@dataclass(frozen=True)
class RuleOutcome:
    """What a revenue or cost rule returns."""

    by_location: dict[str, Decimal] = field(default_factory=dict)
    missing: tuple[MissingInput, ...] = ()
    notes: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def total(self) -> Decimal:
        return sum(self.by_location.values(), ZERO)


@dataclass(frozen=True)
class GmOutcome:
    status: Literal["ok", "incomplete", "exception"]
    revenue_by_location: dict[str, Decimal] = field(default_factory=dict)
    cost_by_location: dict[str, Decimal] = field(default_factory=dict)
    gm_by_location: dict[str, Decimal | None] = field(default_factory=dict)
    gm_blended: Decimal | None = None
    passes: dict[str, bool | None] = field(default_factory=dict)
    missing: tuple[MissingInput, ...] = ()
    notes: tuple[str, ...] = ()
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    components: tuple["GmOutcome", ...] = ()

    @property
    def revenue_total(self) -> Decimal:
        return sum(self.revenue_by_location.values(), ZERO)

    @property
    def cost_total(self) -> Decimal:
        return sum(self.cost_by_location.values(), ZERO)

    @property
    def requires_ceo(self) -> bool:
        """Any floor that is testable and fails sends this to the CEO.

        An untestable floor (no revenue in that geography) is None, not a
        failure — there is nothing there to fall short.
        """

        return any(v is False for v in self.passes.values())


# --- helpers shared by the rules -----------------------------------------


def _line_cost(line: ResourceInput, index: int) -> tuple[Decimal | None, list[MissingInput]]:
    """Cost of one line, or the reasons it cannot be costed.

    Cost uses PAID hours. Billable hours are what the client is charged for;
    paid hours are what we carry. On a staff-aug line with a leave clause
    they differ, and using billable for both drops the unpaid coverage
    entirely.
    """

    gaps: list[MissingInput] = []
    if line.location not in _LOCATIONS:
        gaps.append(
            MissingInput(
                field="location",
                reason="no location — the line cannot be assigned to a floor",
                line=index,
                role=line.role,
            )
        )
    if line.cost_rate is None:
        gaps.append(
            MissingInput(
                field="cost_rate",
                reason="no cost rate — the line cannot be costed",
                line=index,
                role=line.role,
            )
        )
    hours = line.effective_paid
    if hours is None:
        gaps.append(
            MissingInput(
                field="paid_hours",
                reason="no hours — the line has no effort to cost",
                line=index,
                role=line.role,
            )
        )
    if gaps:
        return None, gaps
    assert line.cost_rate is not None and hours is not None
    return hours * line.cost_rate, []


def _labour_cost(spec: SowSpec) -> RuleOutcome:
    """Σ paid hours × cost rate, split by location."""

    by_loc: dict[str, Decimal] = {}
    missing: list[MissingInput] = []
    for i, line in enumerate(spec.resources):
        amount, gaps = _line_cost(line, i)
        if gaps:
            missing.extend(gaps)
            continue
        assert amount is not None and line.location is not None
        by_loc[line.location] = by_loc.get(line.location, ZERO) + amount
    return RuleOutcome(by_location=by_loc, missing=tuple(missing))


def _direct_costs(spec: SowSpec) -> RuleOutcome:
    """Non-labour cost. Pass-through expenses sit outside GM by Finance policy."""

    by_loc: dict[str, Decimal] = {}
    missing: list[MissingInput] = []
    notes: list[str] = []
    passthrough = ZERO
    for i, cost in enumerate(spec.direct_costs):
        if cost.pass_through:
            if cost.amount is not None:
                passthrough += cost.amount
            continue
        if cost.amount is None:
            missing.append(
                MissingInput(
                    field="amount",
                    reason=f"direct cost {cost.label!r} has no amount",
                    line=i,
                )
            )
            continue
        loc = cost.location if cost.location in _LOCATIONS else "US"
        by_loc[loc] = by_loc.get(loc, ZERO) + cost.amount
    if passthrough:
        notes.append(
            f"{passthrough} of pass-through expense excluded from GM at zero margin"
        )
    return RuleOutcome(
        by_location=by_loc,
        missing=tuple(missing),
        notes=tuple(notes),
        extra={"pass_through_total": passthrough},
    )


def _merge(*outcomes: RuleOutcome) -> RuleOutcome:
    by_loc: dict[str, Decimal] = {}
    missing: list[MissingInput] = []
    notes: list[str] = []
    extra: dict[str, Any] = {}
    for o in outcomes:
        for loc, amount in o.by_location.items():
            by_loc[loc] = by_loc.get(loc, ZERO) + amount
        missing.extend(o.missing)
        notes.extend(o.notes)
        extra.update(o.extra)
    return RuleOutcome(
        by_location=by_loc, missing=tuple(missing), notes=tuple(notes), extra=extra
    )


def _apply_contingency(outcome: RuleOutcome, spec: SowSpec) -> RuleOutcome:
    if not spec.contingency_pct:
        return outcome
    scaled = {
        loc: amount * (Decimal("1") + spec.contingency_pct)
        for loc, amount in outcome.by_location.items()
    }
    return RuleOutcome(
        by_location=scaled,
        missing=outcome.missing,
        notes=outcome.notes + (f"contingency {spec.contingency_pct} applied to cost",),
        extra=outcome.extra,
    )


def _net_of_discounts(price: Decimal, spec: SowSpec) -> tuple[Decimal, list[str]]:
    """Discounts and credits reduce revenue BEFORE any floor test.

    Testing the list price passes the engagement on money we never charged.
    """

    notes: list[str] = []
    net = price
    for d in spec.discounts:
        reduction = price * d if d < 1 else d
        net -= reduction
        notes.append(f"discount {d} reduced revenue by {reduction}")
    return net, notes


def _allocate(total: Decimal, spec: SowSpec, cost: RuleOutcome) -> tuple[dict[str, Decimal], list[str]]:
    """Split one settled price across geographies.

    Recorded allocation wins — Finance may set it with a basis. Otherwise
    cost-weighted effort, which is the documented default. With no cost
    anywhere there is nothing to weight by, so it lands on the single
    location in play, or US.
    """

    notes: list[str] = []
    if spec.revenue_allocation:
        recorded = {
            loc: amount
            for loc, amount in spec.revenue_allocation.items()
            if loc in _LOCATIONS
        }
        if recorded:
            notes.append(f"revenue allocated by recorded basis ({spec.allocation_basis})")
            return recorded, notes

    weights = cost.by_location
    weight_total = sum(weights.values(), ZERO)
    if weight_total <= 0:
        only = [
            line.location
            for line in spec.resources
            if line.location in _LOCATIONS
        ]
        loc = only[0] if only else "US"
        notes.append(f"no cost to weight by — all revenue attributed to {loc}")
        return {loc: total}, notes

    out: dict[str, Decimal] = {}
    running = ZERO
    locs = [loc for loc in _LOCATIONS if loc in weights]
    for loc in locs[:-1]:
        share = (total * weights[loc] / weight_total).quantize(Decimal("0.01"))
        out[loc] = share
        running += share
    # The remainder carries the rounding so the split sums to the price
    # exactly; a lost cent would fail the allocation check downstream.
    out[locs[-1]] = total - running
    notes.append("revenue allocated by cost-weighted effort")
    return out, notes


# --- revenue rules --------------------------------------------------------


def _rev_fixed_price(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    if spec.contract_price is None:
        return RuleOutcome(
            missing=(
                MissingInput(field="contract_price", reason="no contract price"),
            )
        )
    net, notes = _net_of_discounts(spec.contract_price, spec)
    by_loc, alloc_notes = _allocate(net, spec, cost)
    return RuleOutcome(
        by_location=by_loc,
        notes=tuple(notes + alloc_notes),
        extra={"list_price": spec.contract_price, "discount_total": spec.contract_price - net},
    )


def _rev_staff_aug(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    """Σ BILLABLE hours × bill rate. Billable, not paid — the client is not
    charged for leave the contract says they are not charged for."""

    by_loc: dict[str, Decimal] = {}
    missing: list[MissingInput] = []
    for i, line in enumerate(spec.resources):
        if line.bill_rate is None:
            missing.append(
                MissingInput(
                    field="bill_rate", reason="no bill rate", line=i, role=line.role
                )
            )
            continue
        hours = line.effective_billable
        if hours is None:
            missing.append(
                MissingInput(
                    field="billable_hours", reason="no billable hours", line=i,
                    role=line.role,
                )
            )
            continue
        loc = line.location if line.location in _LOCATIONS else "US"
        by_loc[loc] = by_loc.get(loc, ZERO) + hours * line.bill_rate
    net_by_loc = by_loc
    notes: list[str] = []
    if spec.discounts:
        total = sum(by_loc.values(), ZERO)
        net, notes = _net_of_discounts(total, spec)
        if total > 0:
            net_by_loc = {
                loc: (amount * net / total) for loc, amount in by_loc.items()
            }
    return RuleOutcome(
        by_location=net_by_loc, missing=tuple(missing), notes=tuple(notes)
    )


def _rev_tm(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    """Forecast hours × rate, capped at the not-to-exceed if one exists.

    The cap is a ceiling, not a booking. When the forecast is lower, revenue
    is the forecast — booking the cap would overstate every capped T&M deal
    in the portfolio.
    """

    forecast = _rev_staff_aug(
        SowSpec(
            engagement_type="tm",
            resources=spec.resources,
            discounts=spec.discounts,
        ),
        cost,
    )
    if forecast.missing:
        return forecast

    total = forecast.total
    notes = list(forecast.notes)
    extra: dict[str, Any] = {"forecast_revenue": total}
    if spec.not_to_exceed is not None:
        extra["not_to_exceed"] = spec.not_to_exceed
        if total > spec.not_to_exceed and total > 0:
            scale = spec.not_to_exceed / total
            notes.append(
                f"forecast {total} exceeds the not-to-exceed {spec.not_to_exceed}"
                " — revenue booked at the cap"
            )
            return RuleOutcome(
                by_location={
                    loc: amount * scale for loc, amount in forecast.by_location.items()
                },
                notes=tuple(notes),
                extra=extra,
            )
        notes.append(
            f"forecast {total} is within the not-to-exceed {spec.not_to_exceed}"
            " — revenue booked at forecast"
        )
    return RuleOutcome(
        by_location=forecast.by_location, notes=tuple(notes), extra=extra
    )


def _rev_managed_service(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    if spec.term_months is None:
        return RuleOutcome(
            missing=(MissingInput(field="term_months", reason="no contract term"),)
        )
    by_loc: dict[str, Decimal] = {}
    for loc, fee in spec.monthly_fee.items():
        if loc in _LOCATIONS:
            by_loc[loc] = by_loc.get(loc, ZERO) + fee * spec.term_months
    if not by_loc:
        return RuleOutcome(
            missing=(MissingInput(field="monthly_fee", reason="no monthly fee"),)
        )
    notes: list[str] = []
    if spec.onboarding_fee:
        # Onboarding is revenue, not margin. Leaving it out understates the
        # deal; treating the matching cost as margin overstates it.
        first = next(iter(by_loc))
        by_loc[first] += spec.onboarding_fee
        notes.append(f"onboarding fee {spec.onboarding_fee} included in revenue")
    return RuleOutcome(by_location=by_loc, notes=tuple(notes))


def _rev_assessment(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    return _rev_fixed_price(spec, cost)


def _rev_placement(spec: SowSpec, cost: RuleOutcome) -> RuleOutcome:
    if spec.placement_fee is None:
        return RuleOutcome(
            missing=(MissingInput(field="placement_fee", reason="no placement fee"),)
        )
    loc = spec.location if spec.location in _LOCATIONS else "US"
    return RuleOutcome(by_location={loc: spec.placement_fee})


# --- cost rules -----------------------------------------------------------


def _cost_labour_plus_direct(spec: SowSpec) -> RuleOutcome:
    return _apply_contingency(_merge(_labour_cost(spec), _direct_costs(spec)), spec)


def _cost_managed_service(spec: SowSpec) -> RuleOutcome:
    """Monthly team cost × months, plus ramp months at full cost.

    During ramp the team is fully staffed and the fee is not yet fully
    earned. Ignoring it reports a margin the engagement will not see in its
    first quarter.
    """

    if spec.term_months is None:
        return RuleOutcome(
            missing=(MissingInput(field="term_months", reason="no contract term"),)
        )
    by_loc: dict[str, Decimal] = {}
    for loc, monthly in spec.monthly_team_cost.items():
        if loc in _LOCATIONS:
            by_loc[loc] = by_loc.get(loc, ZERO) + monthly * spec.term_months
    if not by_loc:
        return RuleOutcome(
            missing=(
                MissingInput(field="monthly_team_cost", reason="no monthly team cost"),
            )
        )
    notes: list[str] = []
    if spec.ramp_months:
        for loc, monthly in spec.monthly_team_cost.items():
            if loc in _LOCATIONS:
                by_loc[loc] += monthly * spec.ramp_months
        notes.append(
            f"{spec.ramp_months} ramp month(s) costed at full team cost before full fee"
        )
    merged = _merge(
        RuleOutcome(by_location=by_loc, notes=tuple(notes)), _direct_costs(spec)
    )
    return _apply_contingency(merged, spec)


def _cost_placement(spec: SowSpec) -> RuleOutcome:
    """Recruiting effort plus a reserve against the guarantee clause.

    A placement with a 90-day refund is not fully earned on day one. Holding
    nothing back books margin that may have to be given back.
    """

    if spec.recruiting_cost is None:
        return RuleOutcome(
            missing=(
                MissingInput(field="recruiting_cost", reason="no recruiting cost"),
            )
        )
    loc = spec.location if spec.location in _LOCATIONS else "US"
    total = spec.recruiting_cost
    notes: list[str] = []
    if spec.refund_reserve_pct and spec.placement_fee is not None:
        reserve = (spec.placement_fee * spec.refund_reserve_pct).quantize(
            Decimal("0.01")
        )
        total += reserve
        notes.append(f"refund reserve {reserve} held against the guarantee clause")
    merged = _merge(
        RuleOutcome(by_location={loc: total}, notes=tuple(notes)),
        _direct_costs(spec),
    )
    return _apply_contingency(merged, spec)


# --- the rule table -------------------------------------------------------


@dataclass(frozen=True)
class EngagementRule:
    """How one engagement type earns and what it costs.

    `docs/gm-rules.md` is generated from these, so the prose Finance signs off
    on and the code that runs are the same statement. `never_do` is not
    decoration: each one is a mistake that produces a plausible wrong number
    rather than an error, which is the only kind worth writing down.
    """

    engagement_type: str
    label: str
    revenue: Callable[[SowSpec, RuleOutcome], RuleOutcome]
    cost: Callable[[SowSpec], RuleOutcome]
    revenue_rule: str
    cost_rule: str
    never_do: str


ENGINE_RULES: dict[str, EngagementRule] = {
    "fixed_price": EngagementRule(
        engagement_type="fixed_price",
        label="Fixed price",
        revenue=_rev_fixed_price,
        cost=_cost_labour_plus_direct,
        revenue_rule=(
            "The contract price, with discounts and credits deducted first. "
            "Split across geographies by the recorded allocation, or by "
            "cost-weighted effort when none is recorded."
        ),
        cost_rule="Σ paid hours × cost rate, plus direct costs, plus contingency.",
        never_do=(
            "Derive revenue from bill rates, or require a bill rate. On a "
            "fixed fee the revenue is settled and nobody bills by the hour."
        ),
    ),
    "staff_aug": EngagementRule(
        engagement_type="staff_aug",
        label="Staff augmentation",
        revenue=_rev_staff_aug,
        cost=_cost_labour_plus_direct,
        revenue_rule="Σ billable hours × bill rate per line, over the term.",
        cost_rule=(
            "Σ PAID hours × loaded cost rate. Paid is not billable: leave, "
            "bench and replacement obligations are paid and not billed."
        ),
        never_do=(
            "Assume billable equals paid, or drop a person's unpaid coverage "
            "cost. Both overstate the margin."
        ),
    ),
    "single_resource": EngagementRule(
        engagement_type="single_resource",
        label="Single resource",
        revenue=_rev_staff_aug,
        cost=_cost_labour_plus_direct,
        revenue_rule="Staff augmentation with one line.",
        cost_rule="As staff augmentation.",
        never_do="Treat it as a fixed fee because there is only one person.",
    ),
    "tm": EngagementRule(
        engagement_type="tm",
        label="Time and materials",
        revenue=_rev_tm,
        cost=_cost_labour_plus_direct,
        revenue_rule=(
            "Forecast hours × rate card, capped at the not-to-exceed where "
            "one exists. Forecast and cap are reported separately."
        ),
        cost_rule="Forecast hours × cost rate, plus direct costs.",
        never_do=(
            "Book the cap as revenue when the forecast is lower. The cap is a "
            "ceiling, not an amount anyone has agreed to pay."
        ),
    ),
    "managed_service": EngagementRule(
        engagement_type="managed_service",
        label="Managed service",
        revenue=_rev_managed_service,
        cost=_cost_managed_service,
        revenue_rule=(
            "Monthly fee × months, plus onboarding and setup fees, plus "
            "committed volume charges."
        ),
        cost_rule=(
            "Monthly team cost × months, plus tools and licences, plus "
            "on-call, plus ramp months at full cost before the full fee."
        ),
        never_do=(
            "Ignore ramp, or spread onboarding cost as if it were margin."
        ),
    ),
    "assessment": EngagementRule(
        engagement_type="assessment",
        label="Assessment",
        revenue=_rev_assessment,
        cost=_cost_labour_plus_direct,
        revenue_rule="The fixed fee, discounts deducted first.",
        cost_rule=(
            "Working days × day cost per person, plus preparation, reporting "
            "and travel as direct costs."
        ),
        never_do=(
            "Scale cost from the elapsed duration. A four-week assessment is "
            "not four weeks of everybody's time."
        ),
    ),
    "permanent_placement": EngagementRule(
        engagement_type="permanent_placement",
        label="Permanent placement",
        revenue=_rev_placement,
        cost=_cost_placement,
        revenue_rule="The one-time placement fee.",
        cost_rule=(
            "Recruiting effort and sourcing costs, plus a refund reserve set "
            "by the guarantee clause."
        ),
        never_do="Treat it as staff augmentation. There are no billable hours.",
    ),
}

# The classifier's vocabulary is not always the rule table's.
_ALIASES = {
    "time_and_materials": "tm",
    "t&m": "tm",
    "fixed_fee": "fixed_price",
}


def rule_for(engagement_type: str) -> EngagementRule | None:
    key = _ALIASES.get(engagement_type, engagement_type)
    return ENGINE_RULES.get(key)


# --- the core -------------------------------------------------------------


def compute_gm(
    spec: SowSpec,
    *,
    us_floor: Decimal = US_FLOOR,
    india_floor: Decimal = INDIA_FLOOR,
) -> GmOutcome:
    """Compute the gross margin for any engagement the rule table knows.

    The core does the same thing for every type: ask the type's cost rule,
    ask its revenue rule, then apply the invariants. Nothing type-specific
    lives here, which is what stops a new SOW shape changing how an existing
    one is calculated.
    """

    # Every division below happens at a pinned precision, so the result does
    # not move when a caller has widened the context for its own reasons.
    with localcontext() as ctx:
        ctx.prec = GM_PRECISION
        return _compute_gm_inner(spec, us_floor=us_floor, india_floor=india_floor)


def _compute_gm_inner(
    spec: SowSpec, *, us_floor: Decimal, india_floor: Decimal
) -> GmOutcome:
    if spec.engagement_type == "hybrid":
        return _compute_hybrid(spec, us_floor=us_floor, india_floor=india_floor)

    rule = rule_for(spec.engagement_type)
    if rule is None:
        return GmOutcome(
            status="exception",
            reason=(
                f"no rule for engagement type {spec.engagement_type!r} — the "
                "engine will not guess at how an unknown shape earns"
            ),
        )

    # Cost first: the fixed-fee revenue rules allocate by cost weight.
    cost = rule.cost(spec)
    revenue = rule.revenue(spec, cost)

    missing = tuple(revenue.missing) + tuple(cost.missing)
    notes = tuple(revenue.notes) + tuple(cost.notes)
    extra = {**revenue.extra, **cost.extra}

    if missing:
        # Deliberately no numbers presented as final. A margin computed over
        # a line with no cost rate silently treats that person as free.
        return GmOutcome(
            status="incomplete",
            revenue_by_location=dict(revenue.by_location),
            missing=missing,
            notes=notes,
            reason=f"{len(missing)} required input(s) missing",
            extra=extra,
        )

    revenue_total = revenue.total
    if revenue_total <= 0:
        return GmOutcome(
            status="exception",
            revenue_by_location=dict(revenue.by_location),
            cost_by_location=dict(cost.by_location),
            notes=notes,
            reason=(
                "revenue is zero or negative — there is nothing to divide by, "
                "so there is no margin to report"
            ),
            extra=extra,
        )

    fx_notes = list(notes)
    rev_by_loc = dict(revenue.by_location)
    cost_by_loc = dict(cost.by_location)
    if spec.fx_rate is not None and spec.currency != "USD":
        # Converted at the rate Finance published, stored on the version. A
        # live rate at render time makes the same SOW show a different margin
        # tomorrow.
        rev_by_loc = {k: (v * spec.fx_rate).quantize(Decimal("0.01")) for k, v in rev_by_loc.items()}
        cost_by_loc = {k: (v * spec.fx_rate).quantize(Decimal("0.01")) for k, v in cost_by_loc.items()}
        fx_notes.append(
            f"converted from {spec.currency} at {spec.fx_rate} as of {spec.fx_as_of}"
        )

    gm_by_loc: dict[str, Decimal | None] = {}
    passes: dict[str, bool | None] = {}
    floors = {"US": us_floor, "India": india_floor}
    for loc in _LOCATIONS:
        rev = rev_by_loc.get(loc, ZERO)
        cst = cost_by_loc.get(loc, ZERO)
        if rev <= 0:
            # No revenue in this geography is not a failure — there is
            # nothing there to fall short of a floor.
            gm_by_loc[loc] = None
            passes[loc] = None
            continue
        gm = (rev - cst) / rev
        gm_by_loc[loc] = gm
        # Unrounded: 35.000% passes, 34.9999% does not.
        passes[loc] = gm >= floors[loc]

    total_rev = sum(rev_by_loc.values(), ZERO)
    total_cost = sum(cost_by_loc.values(), ZERO)
    blended = (total_rev - total_cost) / total_rev if total_rev > 0 else None

    return GmOutcome(
        status="ok",
        revenue_by_location=rev_by_loc,
        cost_by_location=cost_by_loc,
        gm_by_location=gm_by_loc,
        gm_blended=blended,
        passes=passes,
        notes=tuple(fx_notes),
        extra=extra,
    )


def _compute_hybrid(
    spec: SowSpec, *, us_floor: Decimal, india_floor: Decimal
) -> GmOutcome:
    """Each component under its own rule; combined is informational only.

    Forcing one template over a document that contains a fixed build and a
    monthly service produces a number that describes neither. Worse, a
    healthy build can carry a failing service over the line, and the failing
    half is what gets signed.
    """

    if not spec.components:
        return GmOutcome(
            status="exception",
            reason="a hybrid SOW needs components; none were supplied",
        )

    results = tuple(
        compute_gm(c, us_floor=us_floor, india_floor=india_floor)
        for c in spec.components
    )

    incomplete = [m for r in results for m in r.missing]
    if incomplete:
        return GmOutcome(
            status="incomplete",
            missing=tuple(incomplete),
            components=results,
            reason="one or more components is missing a required input",
        )

    rev_by_loc: dict[str, Decimal] = {}
    cost_by_loc: dict[str, Decimal] = {}
    for r in results:
        for loc, amount in r.revenue_by_location.items():
            rev_by_loc[loc] = rev_by_loc.get(loc, ZERO) + amount
        for loc, amount in r.cost_by_location.items():
            cost_by_loc[loc] = cost_by_loc.get(loc, ZERO) + amount

    gm_by_loc: dict[str, Decimal | None] = {}
    passes: dict[str, bool | None] = {}
    floors = {"US": us_floor, "India": india_floor}
    for loc in _LOCATIONS:
        rev = rev_by_loc.get(loc, ZERO)
        if rev <= 0:
            gm_by_loc[loc] = None
            passes[loc] = None
            continue
        gm = (rev - cost_by_loc.get(loc, ZERO)) / rev
        gm_by_loc[loc] = gm
        passes[loc] = gm >= floors[loc]

    total_rev = sum(rev_by_loc.values(), ZERO)
    total_cost = sum(cost_by_loc.values(), ZERO)

    return GmOutcome(
        status="ok",
        revenue_by_location=rev_by_loc,
        cost_by_location=cost_by_loc,
        gm_by_location=gm_by_loc,
        gm_blended=(total_rev - total_cost) / total_rev if total_rev > 0 else None,
        passes=passes,
        components=results,
        notes=(
            "combined figure is informational — each component is tested "
            "against its own floor",
        ),
    )
