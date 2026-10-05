"""Plan rebinding cannot launder a foreign child into an authorized source."""
from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.gm.commercial import HybridPricing
from app.models.forecast import ForecastPlanVersion
from app.services.commercial_models import COMPONENT
from app.services.forecast_plans import save_plan
from tests.test_approval_routing import fixture
from tests.test_s21_commercial_profiles import component, staffing
from tests.test_s21_forecast_plans import actor, body, scope  # noqa: F401


@pytest.mark.parametrize("field", ["source_id", "source_version", "policy_version"])
async def test_foreign_hybrid_child_is_rejected_before_rebinding(session, field):
    owner, opportunity, _, _, _ = await fixture(session)
    child = component(component_id="child", staffing=(staffing(component_id="child"),))
    child = replace(child, **{field: "foreign"}, staffing=(replace(child.staffing[0], **{field: "foreign"}),))
    root = component(profile="hybrid", pricing=HybridPricing((child,)), staffing=())
    request = body(opportunity.client_id).model_copy(update={"inputs": COMPONENT.dump_python(root, mode="json")})
    with pytest.raises(HTTPException) as error:
        await save_plan(session, actor=actor(owner), body=request)
    assert error.value.status_code == 422
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(ForecastPlanVersion)) == 0
