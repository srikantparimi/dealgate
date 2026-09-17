"""Pure GM calculation library. No I/O. All money is Decimal.

The math for every SOW lives here and nowhere else. LLMs never compute or alter
a number. See docs/build-guide.md §7 for the six engagement templates.
"""

from typing import Any

from app.gm.core import gross_margin, min_price
from app.gm.types import (
    CostLine,
    EngagementType,
    Geography,
    Location,
    Money,
    ResourceLine,
    TemplateResult,
    quantize_money,
)

__all__ = [
    "CostLine",
    "EngagementType",
    "Geography",
    "Location",
    "Money",
    "ResourceLine",
    "TemplateResult",
    "compute",
    "gross_margin",
    "min_price",
    "quantize_money",
    "template_for",
]


def template_for(engagement_type: EngagementType | str):
    """Return the template class for an engagement type."""
    from app.gm.templates import (
        AssessmentTemplate,
        FixedPriceTemplate,
        ManagedServiceTemplate,
        SingleResourceTemplate,
        StaffAugTemplate,
        TMTemplate,
    )

    key = (
        engagement_type.value
        if isinstance(engagement_type, EngagementType)
        else str(engagement_type)
    )
    dispatch = {
        EngagementType.STAFF_AUG.value: StaffAugTemplate,
        EngagementType.SINGLE_RESOURCE.value: SingleResourceTemplate,
        EngagementType.FIXED_PRICE.value: FixedPriceTemplate,
        EngagementType.ASSESSMENT.value: AssessmentTemplate,
        EngagementType.TM.value: TMTemplate,
        EngagementType.MANAGED_SERVICE.value: ManagedServiceTemplate,
    }
    if key not in dispatch:
        raise ValueError(f"no template for engagement type {key!r}")
    return dispatch[key]


def compute(engagement_type: EngagementType | str, inputs: Any) -> TemplateResult:
    """Dispatch to the correct template's ``compute``."""
    return template_for(engagement_type).compute(inputs)
