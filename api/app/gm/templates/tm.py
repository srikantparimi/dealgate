"""Time and materials template.

Model: hourly rates with a cap. Revenue is the smaller of billed hours *
bill rate and the cap. Cost is billed hours * hourly cost. For SOW
approval we score at the *forecast* hours (not the cap), since we need
to know the expected GM, not the worst case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.gm.templates._common import roll_up
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult


@dataclass(frozen=True)
class TMInputs:
    resources: list[ResourceLine]  # hours_billable = **forecast** hours
    revenue_cap: Optional[Money] = None  # None = uncapped
    costs: list[CostLine] = field(default_factory=list)


class TMTemplate:
    key = "tm"

    @staticmethod
    def required_inputs() -> list[str]:
        return ["resources", "revenue_cap", "costs"]

    @staticmethod
    def validate(inputs: TMInputs) -> list[str]:
        missing: list[str] = []
        if not inputs.resources:
            missing.append("resources")
        for i, r in enumerate(inputs.resources):
            if r.hourly_cost is None:
                missing.append(f"resources[{i}].hourly_cost")
        for i, c in enumerate(inputs.costs):
            if c.amount is None:
                missing.append(f"costs[{i}].amount")
        return missing

    @staticmethod
    def compute(inputs: TMInputs) -> TemplateResult:
        result = roll_up(inputs.resources, inputs.costs)

        # Apply the cap by scaling each component proportionally to its
        # share of pre-cap revenue. Cost stays as forecast (we still incur
        # it even if we can't bill above the cap).
        if inputs.revenue_cap is not None:
            forecast_total = result.revenue_us + result.revenue_india
            if forecast_total > inputs.revenue_cap and forecast_total > 0:
                scale_us = result.revenue_us / forecast_total
                scale_in = result.revenue_india / forecast_total
                capped = inputs.revenue_cap
                result.revenue_us = capped * scale_us
                result.revenue_india = capped * scale_in
                # Re-derive GMs against the same cost.
                from app.gm.templates._common import build_result

                result = build_result(
                    revenue_us=result.revenue_us,
                    cost_us=result.cost_us,
                    revenue_india=result.revenue_india,
                    cost_india=result.cost_india,
                    missing=result.missing,
                )

        for m in TMTemplate.validate(inputs):
            if m not in result.missing:
                result.missing.append(m)
        result.complete = not result.missing
        return result
