"""FC-01/08: immutable assumption revisions preserve server-owned economics."""

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.forecast import ForecastJob, ForecastPlanVersion
from app.services import forecast_plans as service
from tests.test_s21_forecast_plans import actor, body, scope  # noqa: F401
from tests.test_approval_routing import fixture
from tests.test_approvals import app_with_session  # noqa: F401


def change(version):
    return service.AssumptionsInput(
        expected_version_id=version.id, probability="0.65",
        probability_source="Account owner reviewed", assumptions=["Client dates pending"],
        lifecycle="tentative", change_reason="Updated assessment findings",
    )


async def test_assumption_revision_preserves_economics_and_prior_version(session):
    owner, opp, *_ = await fixture(session)
    request = body(opp.client_id).model_copy(update={
        "opportunity_id": opp.id, "fx_rate": "1.23456789", "fx_version": "fx-proof",
        "fx_date": date(2026, 10, 1),
        "scenario_group": "mutually-exclusive", "selected": False,
    })
    prior = await service.save_plan(session, actor=actor(owner), body=request)
    original = deepcopy(prior.component_inputs)
    revised = await service.revise_assumptions(
        session, actor=actor(owner), plan_id=prior.plan_id, body=change(prior)
    )
    assert revised.version == 2 and revised.id != prior.id
    assert revised.probability == Decimal("0.65")
    assert revised.assumptions == ["Client dates pending"]
    assert revised.lifecycle == "tentative"
    for key in ("scope_id", "policy_snapshot", "fx_rate", "fx_version", "fx_date", "scenario_group", "selected", "title"):
        assert getattr(revised, key) == getattr(prior, key)
    expected = deepcopy(original)
    expected["source_version"] = str(revised.id)
    assert revised.component_inputs == expected
    assert prior.component_inputs == original and prior.probability == Decimal("0.70")
    assert await session.scalar(select(ForecastJob).where(ForecastJob.plan_version_id == revised.id))
    with pytest.raises(HTTPException) as error:
        await service.revise_assumptions(session, actor=actor(owner), plan_id=prior.plan_id, body=change(prior))
    assert error.value.status_code == 409
    assert len((await session.scalars(select(ForecastPlanVersion))).all()) == 2


@pytest.mark.parametrize("role", ["Sales", "HR", "CEO"])
async def test_read_roles_cannot_revise_assumptions(session, role):
    owner, opp, *_ = await fixture(session)
    prior = await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    with pytest.raises(HTTPException) as error:
        await service.revise_assumptions(session, actor=actor(owner, (role,)), plan_id=prior.plan_id, body=change(prior))
    assert error.value.status_code == 403
    assert len((await session.scalars(select(ForecastPlanVersion))).all()) == 1


async def test_cross_tenant_plan_is_unavailable(session, monkeypatch):
    owner, opp, *_ = await fixture(session)
    prior = await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    monkeypatch.setenv("DEALGATE_TENANT_ID", "other-tenant")
    with pytest.raises(HTTPException) as error:
        await service.revise_assumptions(session, actor=actor(owner), plan_id=prior.plan_id, body=change(prior))
    assert error.value.status_code == 404


@pytest.mark.parametrize("update", [{"probability": "1.1"}, {"probability": "NaN"}, {"change_reason": " "}, {"inputs": {}}, {"lifecycle": "signed"}])
async def test_invalid_assumption_update_is_rejected(session, update):
    from pydantic import ValidationError
    owner, opp, *_ = await fixture(session)
    prior = await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    with pytest.raises((ValidationError, HTTPException)):
        payload = service.AssumptionsInput(**(change(prior).model_dump() | update))
        await service.revise_assumptions(session, actor=actor(owner), plan_id=prior.plan_id, body=payload)
    assert len((await session.scalars(select(ForecastPlanVersion))).all()) == 1


async def test_plan_list_exposes_capability_and_safe_evidence(session):
    owner, opp, *_ = await fixture(session)
    await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    writing = (await service.list_plans(session, actor=actor(owner)))[0]
    reading = (await service.list_plans(session, actor=actor(owner, ("Sales",))))[0]
    assert writing["can_edit_assumptions"] is True
    assert reading["can_edit_assumptions"] is False
    assert reading["source_evidence"] == ["sow-x:page-2"]


async def test_assumption_revision_worker_recomputes_literal_expected_revenue(session):
    owner, opp, *_ = await fixture(session)
    prior = await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    revised = await service.revise_assumptions(session, actor=actor(owner), plan_id=prior.plan_id, body=change(prior))
    assert await service.process_plan_jobs(session) == 2
    view = await service.outlook(session, actor=actor(owner), as_of=datetime.fromisoformat("2026-10-01T12:00:00Z"))
    # Independent: $70,000 monthly full value *0.65 *4 future months =182,000.
    assert view["future"]["revenue"] == Decimal("182000")
    assert all(row["source_version"] == str(revised.id) for row in view["rows"])


async def test_assumption_http_route_checks_role_and_persists_version(app_with_session, session, monkeypatch):
    owner, opp, *_ = await fixture(session)
    prior = await service.save_plan(session, actor=actor(owner), body=body(opp.client_id))
    from tests.test_approvals import _client
    path = f"/forecast/plans/{prior.plan_id}/assumptions"
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        denied = await client.post(path, headers={"X-Test-User": owner.email}, json=change(prior).model_dump(mode="json"))
        assert denied.status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        accepted = await client.post(path, headers={"X-Test-User": owner.email}, json=change(prior).model_dump(mode="json"))
        assert accepted.status_code == 201
        assert accepted.json()["version"] == 2
