"""Bridge typed commercial schedules to existing consumers without new margin math."""

from decimal import Decimal

from app.gm.commercial import ComponentSchedule, PricingComponent, calculate_component
from app.gm.policy import INDIA_FLOOR, US_FLOOR
from app.gm.engine import GmOutcome
from app.gm.types import TemplateResult

ZERO = Decimal("0")


def to_template_result(
    schedule: ComponentSchedule, *, us_floor: Decimal = US_FLOOR, india_floor: Decimal = INDIA_FLOOR,
    frozen_outcome: GmOutcome | None = None,
) -> TemplateResult:
    """Retain the authority and its child tree; legacy numeric slots are not a snapshot.

    For unassessed results the legacy zero defaults are compatibility placeholders.
    Consumers must use ``gm_outcome.status`` and expose unknown amounts as null,
    never interpret those defaults as assessed economics or recompute child floors.
    """
    outcome = frozen_outcome if frozen_outcome is not None else schedule.assess(us_floor=us_floor, india_floor=india_floor)
    missing = list(dict.fromkeys(gap.field for gap in outcome.missing))
    if outcome.status != "ok" and outcome.reason:
        missing.append(outcome.reason)
    result = TemplateResult(
        complete=outcome.status == "ok", missing=missing,
        gm_outcome=outcome, commercial_schedule=schedule, policy_frozen=frozen_outcome is not None,
    )
    if outcome.status == "ok":
        result.revenue_us = outcome.revenue_by_location.get("US", ZERO)
        result.revenue_india = outcome.revenue_by_location.get("India", ZERO)
        result.cost_us = outcome.cost_by_location.get("US", ZERO)
        result.cost_india = outcome.cost_by_location.get("India", ZERO)
        result.gm_us = outcome.gm_by_location.get("US")
        result.gm_india = outcome.gm_by_location.get("India")
        result.gm_blended = outcome.gm_blended
    return result


def compute_commercial(
    component: PricingComponent, *, us_floor: Decimal = US_FLOOR, india_floor: Decimal = INDIA_FLOOR,
) -> TemplateResult:
    """Calculate confirmed typed inputs and adapt the existing GM authority's outcome."""
    return to_template_result(calculate_component(component), us_floor=us_floor, india_floor=india_floor)
