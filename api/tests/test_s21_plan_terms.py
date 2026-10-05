"""T19 commercial edits preserve noncommercial planning authority."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
import uuid

import pytest
from sqlalchemy import select

from app.models.forecast import ForecastPlanVersion
from app.services.forecast_plans import save_plan
from tests.test_s21_forecast_plans import actor, body, scope
from tests.test_approval_routing import fixture
from tests.test_approvals import app_with_session, _client
from app.auth import current_user
from app.models.user import User


@pytest.mark.asyncio
async def test_terms_endpoint_preserves_metadata_immutable_prior_and_rejects_stale(app_with_session, session, monkeypatch):
    owner, opp, _, _, _ = await fixture(session)
    initial = body(opp.client_id).model_copy(update={
        "opportunity_id": opp.id, "scenario_group": "exclusive-route", "selected": False,
        "fx_rate": "1.25", "fx_version": "finance-confirmed", "fx_date": date(2026, 10, 1),
    })
    prior = await save_plan(session, actor=actor(owner), body=initial)
    original = deepcopy(prior.component_inputs)
    inputs = deepcopy(original)
    inputs["pricing"]["total_fee"] = "480000"
    request = dict(expected_version_id=str(prior.id), inputs=inputs, change_reason="Revised customer estimate")
    headers = {"X-Test-User": owner.email}
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
        assert (await client.post(f"/forecast/plans/{prior.plan_id}/commercial", json=request, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
        response = await client.post(f"/forecast/plans/{prior.plan_id}/commercial", json=request, headers=headers)
        assert response.status_code == 201, response.text
        current = await session.get(ForecastPlanVersion, uuid.UUID(response.json()["version_id"]))
        assert current.id != prior.id
        assert current.component_inputs["pricing"]["total_fee"] == "480000"
        for field in ("title", "scope_id", "lifecycle", "probability", "probability_source", "assumptions", "scenario_group", "selected", "fx_rate", "fx_version", "fx_date"):
            assert getattr(current, field) == getattr(prior, field), field
        await session.refresh(prior)
        assert prior.component_inputs == original
        stale = await client.post(f"/forecast/plans/{prior.plan_id}/commercial", json=request, headers=headers)
        assert stale.status_code == 409
        assert len((await session.scalars(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == prior.plan_id))).all()) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("invited", [False, True])
async def test_first_finance_editor_is_canonicalized_before_revision(app_with_session, session, invited, monkeypatch):
    owner, opp, _, _, _ = await fixture(session)
    prior = await save_plan(session, actor=actor(owner), body=body(opp.client_id))
    principal = replace(actor(owner, ("Finance",)), id=uuid.uuid4(), email="new-finance@example.test", name="New Finance")
    identity = uuid.uuid4() if invited else principal.id
    if invited:
        session.add(User(id=identity, email=principal.email, name=principal.name, groups=["Finance"]))
        await session.commit()
    monkeypatch.setitem(app_with_session.dependency_overrides, current_user, lambda: principal)
    async with _client(app_with_session) as client:
        response = await client.post(f"/forecast/plans/{prior.plan_id}/commercial", json={
            "expected_version_id": str(prior.id), "inputs": prior.component_inputs, "change_reason": "First authorized finance review",
        })
        assert response.status_code == 201, response.text
        revision = await session.get(ForecastPlanVersion, uuid.UUID(response.json()["version_id"]))
        assert revision.created_by == identity
        assert (await session.get(User, identity)).email == principal.email
