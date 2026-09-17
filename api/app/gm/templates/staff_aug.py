"""Staff augmentation template.

Model: N named resources billed hourly against a client's team for a stated
window. §7 inputs: billable hours, start/end, holidays, paid-but-unbilled
(PBU) time, replacement obligation.

Interpretation note (see ``docs/questions.md``):
  * ``holidays`` and ``pbu_hours`` per resource represent hours the resource
    is *paid for but not billing*. They inflate the cost line only — no
    revenue against them. Modeled by supplying ``hourly_cost`` and
    ``pbu_hours`` per resource; PBU cost = ``pbu_hours * hourly_cost``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from app.gm.templates._common import roll_up
from app.gm.types import CostLine, ResourceLine, TemplateResult


@dataclass(frozen=True)
class StaffAugInputs:
    resources: list[ResourceLine]
    # Hours paid but unbilled per resource (holidays, ramp, PTO absorbed by
    # us). Aligned index-wise with ``resources``.
    pbu_hours: list[Decimal] = field(default_factory=list)
    replacement_obligation: bool = False  # policy flag, no cost impact here
    costs: list[CostLine] = field(default_factory=list)


class StaffAugTemplate:
    key = "staff_aug"

    @staticmethod
    def required_inputs() -> list[str]:
        return [
            "resources",  # list[ResourceLine] with hours_billable, start, end
            "pbu_hours",  # list[Decimal] aligned with resources
            "replacement_obligation",  # bool
            "costs",  # list[CostLine] — travel, tools, etc.
        ]

    @staticmethod
    def validate(inputs: StaffAugInputs) -> list[str]:
        missing: list[str] = []
        if not inputs.resources:
            missing.append("resources")
            return missing
        if len(inputs.pbu_hours) != len(inputs.resources):
            missing.append("pbu_hours")
        for i, r in enumerate(inputs.resources):
            if r.hourly_cost is None:
                missing.append(f"resources[{i}].hourly_cost")
            if r.start is None or r.end is None:
                missing.append(f"resources[{i}].dates")
        for i, c in enumerate(inputs.costs):
            if c.amount is None:
                missing.append(f"costs[{i}].amount")
        return missing

    @staticmethod
    def compute(inputs: StaffAugInputs) -> TemplateResult:
        # Fold PBU hours into cost only. Build synthetic resource lines
        # with zero bill rate and the same hourly_cost to reuse roll_up.
        pbu_lines: list[ResourceLine] = []
        pbu_hours = list(inputs.pbu_hours) + [Decimal("0")] * max(
            0, len(inputs.resources) - len(inputs.pbu_hours)
        )
        for r, hrs in zip(inputs.resources, pbu_hours):
            if hrs <= 0 or r.hourly_cost is None:
                continue
            pbu_lines.append(
                ResourceLine(
                    role=f"{r.role} (PBU)",
                    seniority=r.seniority,
                    location=r.location,
                    allocation_pct=Decimal("1"),
                    start=r.start,
                    end=r.end,
                    hours_billable=hrs,
                    hourly_bill_rate=Decimal("0"),
                    hourly_cost=r.hourly_cost,
                )
            )

        all_resources: Iterable[ResourceLine] = list(inputs.resources) + pbu_lines
        result = roll_up(all_resources, inputs.costs)

        # Propagate template-level missing pieces (e.g. mismatched pbu_hours).
        for m in StaffAugTemplate.validate(inputs):
            if m not in result.missing:
                result.missing.append(m)
        result.complete = not result.missing
        return result
