"""Saved plans retain canonical staffing bindings through immutable revisions."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.gm.commercial import HybridPricing
from app.gm.demand_source import project_staffing
from app.models.forecast import ForecastSchedule
from app.services import forecast_plans as service
from tests.test_approval_routing import fixture
from tests.test_s21_commercial_profiles import component, staffing
from tests.test_s21_forecast_plans import actor, body, scope  # noqa: F401
from tests.test_s21_plan_assumptions import change


def source(hybrid=False):
    leaf = component(costs=(), staffing=(staffing(),))
    if not hybrid:
        return leaf
    leaf = replace(leaf, component_id="leaf", staffing=(staffing(component_id="leaf"),))
    return component(profile="hybrid", costs=(), pricing=HybridPricing((leaf,)))


def assert_binding(spec, version):
    assert spec.source_id == f"forecast:{version.plan_id}"
    assert spec.source_version == str(version.id)
    assert spec.policy_version == version.policy_snapshot["version"]
    for assignment in spec.staffing:
        for field in ("source_id", "source_version", "component_id", "profile_version", "policy_version", "currency", "timezone"):
            assert getattr(assignment, field) == getattr(spec, field)
    if isinstance(spec.pricing, HybridPricing):
        for child in spec.pricing.components:
            assert_binding(child, version)


@pytest.mark.parametrize("hybrid", [False, True])
async def test_save_commercial_revision_and_assumption_revision_bind_real_worker_and_demand(session, hybrid):
    owner, opp, *_ = await fixture(session)
    original = source(hybrid)
    request = body(opp.client_id).model_copy(update={
        "inputs": service.COMPONENT.dump_python(original, mode="json"),
    })
    request_snapshot = deepcopy(request.inputs)
    initial = await service.save_plan(session, actor=actor(owner), body=request)
    initial_inputs = deepcopy(initial.component_inputs)
    assert_binding(service.parse_component(initial.component_inputs), initial)
    assert await service.process_plan_jobs(session) == 1
    schedule = await session.get(ForecastSchedule, initial.id)
    assert schedule.snapshot["schedule"]["status"] == "ok"
    initial_demand = project_staffing(service.parse_component(initial.component_inputs))
    assert len(initial_demand["lines"]) == 1
    revised = await service.save_plan(session, actor=actor(owner), plan_id=initial.plan_id, body=request.model_copy(update={
        "inputs": deepcopy(initial.component_inputs), "expected_version_id": initial.id,
        "change_reason": "Confirmed updated commercial source",
    }))
    assert_binding(service.parse_component(revised.component_inputs), revised)
    assert await service.process_plan_jobs(session) == 1
    assert (await session.get(ForecastSchedule, revised.id)).snapshot["schedule"]["status"] == "ok"
    adjusted = await service.revise_assumptions(session, actor=actor(owner), plan_id=initial.plan_id, body=change(revised))
    assert_binding(service.parse_component(adjusted.component_inputs), adjusted)
    assert await service.process_plan_jobs(session) == 1
    assert (await session.get(ForecastSchedule, adjusted.id)).snapshot["schedule"]["status"] == "ok"
    adjusted_demand = project_staffing(service.parse_component(adjusted.component_inputs))
    assert adjusted_demand == initial_demand
    assert initial.component_inputs == initial_inputs
    assert request.inputs == request_snapshot


@pytest.mark.parametrize("hybrid", [False, True])
@pytest.mark.parametrize("field", ["source_id", "source_version", "component_id", "profile_version", "policy_version", "currency", "timezone"])
async def test_save_rejects_original_foreign_staffing_instead_of_repairing_it(session, hybrid, field):
    owner, opp, *_ = await fixture(session)
    original = source(hybrid)
    leaf = original.pricing.components[0] if hybrid else original
    value = "America/Chicago" if field == "timezone" else "foreign"
    damaged = replace(leaf, staffing=(replace(leaf.staffing[0], calendar=None, **{field: value}),))
    invalid = replace(original, pricing=HybridPricing((damaged,))) if hybrid else damaged
    request = body(opp.client_id).model_copy(update={"inputs": service.COMPONENT.dump_python(invalid, mode="json")})
    with pytest.raises(HTTPException) as error:
        await service.save_plan(session, actor=actor(owner), body=request)
    assert error.value.status_code == 422
    assert "binding" in str(error.value.detail).lower()
