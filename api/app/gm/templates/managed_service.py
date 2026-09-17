"""Managed service template.

Model: recurring monthly fee for a defined outcome, over N months. Cost
is a staffed pod (resource lines with allocation %) plus tools and
other run costs. GM is measured on the term as a whole — a month-by-month
view is left to the reporting layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.gm.templates._common import build_result, roll_up
from app.gm.types import CostLine, Money, ResourceLine, TemplateResult


@dataclass(frozen=True)
class ManagedServiceInputs:
    monthly_fee_us: Money
    monthly_fee_india: Money
    term_months: Decimal
    resources: list[ResourceLine] = field(default_factory=list)  # cost side
    costs: list[CostLine] = field(default_factory=list)


class ManagedServiceTemplate:
    key = "managed_service"

    @staticmethod
    def required_inputs() -> list[str]:
        return [
            "monthly_fee_us",
            "monthly_fee_india",
            "term_months",
            "resources",
            "costs",
        ]

    @staticmethod
    def validate(inputs: ManagedServiceInputs) -> list[str]:
        missing: list[str] = []
        if inputs.term_months is None or inputs.term_months <= 0:
            missing.append("term_months")
        if not inputs.resources and not inputs.costs:
            missing.append("delivery_plan")
        for i, r in enumerate(inputs.resources):
            if r.hourly_cost is None:
                missing.append(f"resources[{i}].hourly_cost")
        for i, c in enumerate(inputs.costs):
            if c.amount is None:
                missing.append(f"costs[{i}].amount")
        return missing

    @staticmethod
    def compute(inputs: ManagedServiceInputs) -> TemplateResult:
        cost_only = roll_up(inputs.resources, inputs.costs)

        term = inputs.term_months or Decimal("0")
        revenue_us = inputs.monthly_fee_us * term
        revenue_india = inputs.monthly_fee_india * term

        merged_missing = list(cost_only.missing)
        for m in ManagedServiceTemplate.validate(inputs):
            if m not in merged_missing:
                merged_missing.append(m)

        return build_result(
            revenue_us=revenue_us,
            cost_us=cost_only.cost_us,
            revenue_india=revenue_india,
            cost_india=cost_only.cost_india,
            missing=merged_missing,
        )
