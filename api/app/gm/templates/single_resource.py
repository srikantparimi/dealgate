"""Single-resource template.

Model: exactly one named resource, hourly. Same math as staff-aug with
one line and no replacement obligation. Kept as a distinct template so
the UI can show the simpler form and Finance can slice by shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.gm.templates._common import roll_up
from app.gm.types import CostLine, ResourceLine, TemplateResult


@dataclass(frozen=True)
class SingleResourceInputs:
    resource: Optional[ResourceLine] = None
    costs: list[CostLine] = field(default_factory=list)


class SingleResourceTemplate:
    key = "single_resource"

    @staticmethod
    def required_inputs() -> list[str]:
        return ["resource", "costs"]

    @staticmethod
    def validate(inputs: SingleResourceInputs) -> list[str]:
        missing: list[str] = []
        if inputs.resource is None:
            missing.append("resource")
            return missing
        if inputs.resource.hourly_cost is None:
            missing.append("resource.hourly_cost")
        for i, c in enumerate(inputs.costs):
            if c.amount is None:
                missing.append(f"costs[{i}].amount")
        return missing

    @staticmethod
    def compute(inputs: SingleResourceInputs) -> TemplateResult:
        if inputs.resource is None:
            return TemplateResult(complete=False, missing=["resource"])
        result = roll_up([inputs.resource], inputs.costs)
        return result
