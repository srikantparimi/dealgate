"""Assessment / discovery template.

Model: short fixed-scope, fixed-price engagement (usually 2-6 weeks) run
by a small team to produce a report. Same math shape as fixed-price with
a mandatory ``deliverable`` field and a shorter duration guard-rail
handled downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.gm.templates._common import build_result, roll_up
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult


@dataclass(frozen=True)
class AssessmentInputs:
    deliverable: str
    total_price: Money
    revenue_us: Money
    revenue_india: Money
    resources: list[ResourceLine] = field(default_factory=list)
    costs: list[CostLine] = field(default_factory=list)


class AssessmentTemplate:
    key = "assessment"

    @staticmethod
    def required_inputs() -> list[str]:
        return [
            "deliverable",
            "total_price",
            "revenue_us",
            "revenue_india",
            "resources",
            "costs",
        ]

    @staticmethod
    def validate(inputs: AssessmentInputs) -> list[str]:
        missing: list[str] = []
        if not inputs.deliverable:
            missing.append("deliverable")
        if inputs.total_price is None:
            missing.append("total_price")
        if inputs.revenue_us + inputs.revenue_india != inputs.total_price:
            missing.append("revenue_allocation")
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
    def compute(inputs: AssessmentInputs) -> TemplateResult:
        cost_only = roll_up(inputs.resources, inputs.costs)
        merged_missing = list(cost_only.missing)
        for m in AssessmentTemplate.validate(inputs):
            if m not in merged_missing:
                merged_missing.append(m)
        return build_result(
            revenue_us=inputs.revenue_us,
            cost_us=cost_only.cost_us,
            revenue_india=inputs.revenue_india,
            cost_india=cost_only.cost_india,
            missing=merged_missing,
        )
