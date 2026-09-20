"""Fixed-price template.

Model: one price for a scoped deliverable, allocated between US and India
components by an explicit ratio. Delivery cost is a bottom-up plan of
resource lines + non-labor.

Allocation:
  The library takes ``revenue_us`` and ``revenue_india`` as **explicit**
  inputs — allocation basis (work packages, hours, etc.) is a Finance
  decision, not the library's concern (see open question in
  ``docs/questions.md``). We do validate that the two allocations sum to
  the stated total price, so downstream code can't silently drop revenue.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.gm.templates._common import build_result, roll_up
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult


@dataclass(frozen=True)
class FixedPriceInputs:
    total_price: Money
    revenue_us: Money  # explicit allocation
    revenue_india: Money
    resources: list[ResourceLine] = field(default_factory=list)
    costs: list[CostLine] = field(default_factory=list)
    # If some cost is known to exist but not yet quantified, name it here
    # to force ``complete=False`` (e.g. "subcontractor_TBD").
    unallocated_cost_notes: list[str] = field(default_factory=list)


class FixedPriceTemplate:
    key = "fixed_price"

    @staticmethod
    def required_inputs() -> list[str]:
        return [
            "total_price",
            "revenue_us",
            "revenue_india",
            "resources",
            "costs",
            "unallocated_cost_notes",
        ]

    @staticmethod
    def validate(inputs: FixedPriceInputs) -> list[str]:
        missing: list[str] = []
        if inputs.total_price is None:
            missing.append("total_price")
        allocated = inputs.revenue_us + inputs.revenue_india
        if allocated != inputs.total_price:
            missing.append("revenue_allocation")
        if not inputs.resources and not inputs.costs:
            missing.append("delivery_plan")
        for i, r in enumerate(inputs.resources):
            if r.hourly_cost is None:
                missing.append(f"resources[{i}].hourly_cost")
        for i, c in enumerate(inputs.costs):
            if c.amount is None:
                missing.append(f"costs[{i}].amount")
        for note in inputs.unallocated_cost_notes:
            missing.append(f"unallocated:{note}")
        return missing

    @staticmethod
    def compute(inputs: FixedPriceInputs) -> TemplateResult:
        # Aggregate cost from the delivery plan, ignoring resource revenue
        # (fixed-price revenue comes from the explicit allocation, not from
        # hourly bill rates on the plan).
        cost_only = roll_up(inputs.resources, inputs.costs)

        template_missing = FixedPriceTemplate.validate(inputs)
        merged_missing = list(cost_only.missing)
        for m in template_missing:
            if m not in merged_missing:
                merged_missing.append(m)

        result = build_result(
            revenue_us=inputs.revenue_us,
            cost_us=cost_only.cost_us,
            revenue_india=inputs.revenue_india,
            cost_india=cost_only.cost_india,
            missing=merged_missing,
        )
        return result
