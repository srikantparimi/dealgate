"""FC-05/12 persisted plan, worker and authorized outlook boundaries."""

import uuid
from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import TypeAdapter
from sqlalchemy import select

from app.auth import AuthUser
from app.gm.commercial import PricingComponent
from app.models.forecast import ForecastJob, ForecastSchedule
from app.services.forecast_plans import PlanInput, outlook, save_plan, process_plan_jobs
from tests.test_approval_routing import fixture
from tests.test_s21_commercial_profiles import component
from tests.test_approvals import app_with_session, _client  # noqa: F401


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "s21-plan-tests")
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")


def actor(user, groups=("Delivery",)):
    return AuthUser(id=user.id, email=user.email, name=user.name, groups=groups)


def body(account_id):
    return PlanInput(account_id=account_id, title="Company X proposed implementation",
                     idempotency_key=uuid.uuid4(), inputs=TypeAdapter(PricingComponent).dump_python(
                         component(policy_version="blueprint-defaults-v1"), mode="json"),
                     probability="0.70", probability_source="Reviewed sales assumption",
                     assumptions=["Confirmed even six-service-month allocation"],
                     change_reason="Assessment supports proposed implementation")


@pytest.mark.asyncio
async def test_plan_worker_persistence_replay_and_real_totals(session):
    owner, opp, _, _, _ = await fixture(session)
    request = body(opp.client_id)
    version = await save_plan(session, actor=actor(owner), body=request)
    duplicate = await save_plan(session, actor=actor(owner), body=request)
    assert duplicate.id == version.id
    assert len((await session.scalars(select(ForecastJob))).all()) == 1
    before = await outlook(session, actor=actor(owner), as_of=datetime.fromisoformat("2026-10-01T12:00:00Z"))
    assert before["future"]["revenue"] == Decimal("0")
    assert before["pending_sources"] == [str(version.id)]
    assert await process_plan_jobs(session) == 1
    assert await process_plan_jobs(session) == 0
    assert len((await session.scalars(select(ForecastSchedule))).all()) == 1
    after = await outlook(session, actor=actor(owner), as_of=datetime.fromisoformat("2026-10-01T12:00:00Z"))
    assert after["future"]["revenue"] == Decimal("196000")
    assert after["future"]["cost"] == Decimal("98000")
    assert after["future"]["gm"] == Decimal("0.5")
    assert not after["pending_sources"]
    assert after["source_watermark"]
    assert after["source_count"] == 1
    assert after["accounts"][0]["name"]
    assert after["rows"][0]["source_name"] == request.title
    assert after["rows"][0]["source_evidence"] == request.inputs["source_evidence"]
    assert after["rows"][0]["assumptions"] == request.assumptions
    assert after["rows"][0]["calculation_version"]


@pytest.mark.asyncio
async def test_new_version_obsoletes_old_job_and_stale_edit_cannot_overwrite(session):
    from fastapi import HTTPException
    owner, opp, _, _, _ = await fixture(session)
    request = body(opp.client_id)
    old = await save_plan(session, actor=actor(owner), body=request)
    updated = request.model_copy(update={"probability": "0.50", "expected_version_id": old.id})
    new = await save_plan(session, actor=actor(owner), body=updated, plan_id=old.plan_id)
    with pytest.raises(HTTPException) as error:
        await save_plan(session, actor=actor(owner), body=updated, plan_id=old.plan_id)
    assert error.value.status_code == 409
    assert await process_plan_jobs(session) == 2
    jobs = list((await session.scalars(select(ForecastJob))).all())
    assert {row.status for row in jobs} == {"obsolete", "done"}
    assert (await session.scalar(select(ForecastSchedule))).plan_version_id == new.id
    view = await outlook(session, actor=actor(owner), as_of=datetime.fromisoformat("2026-10-01T12:00:00Z"))
    assert view["future"]["revenue"] == Decimal("140000")


@pytest.mark.asyncio
async def test_tenant_and_owner_scope_applied_before_aggregation(session, monkeypatch):
    owner, opp, _, _, _ = await fixture(session)
    await save_plan(session, actor=actor(owner), body=body(opp.client_id))
    await process_plan_jobs(session)
    now = datetime.fromisoformat("2026-10-01T12:00:00Z")
    sales = actor(owner, ("Sales",))
    own = await outlook(session, actor=sales, as_of=now)
    assert own["scope_label"] == "My portfolio"
    assert own["future"]["revenue"] == Decimal("196000")
    outsider = replace(sales, id=uuid.uuid4())
    hidden = await outlook(session, actor=outsider, as_of=now)
    assert hidden["future"]["revenue"] == Decimal("0")
    assert hidden["accounts"] == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "different-tenant")
    foreign = await outlook(session, actor=actor(owner), as_of=now)
    assert foreign["future"]["revenue"] == Decimal("0")
    assert foreign["source_watermark"] != own["source_watermark"]


@pytest.mark.asyncio
async def test_planning_endpoint_roles_and_cost_redaction(app_with_session, session, monkeypatch):  # noqa: F811
    owner, opp, _, _, _ = await fixture(session)
    request = body(opp.client_id).model_dump(mode="json")
    headers = {"X-Test-User": owner.email}
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
        for path in ("/forecast/plans", "/forecast/outlook"):
            assert (await client.get(path, headers=headers)).status_code == 403
        assert (await client.post("/forecast/plans", json=request, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        created = await client.post("/forecast/plans", json=request, headers=headers)
        assert created.status_code == 201, created.text
        identity = created.json()
        assert await process_plan_jobs(session) == 1
        params = {"as_of": "2026-10-01T12:00:00Z"}
        finance = await client.get("/forecast/outlook", params=params, headers=headers)
        assert finance.status_code == 200, finance.text
        assert Decimal(finance.json()["future"]["revenue"]) == Decimal("196000")
        assert isinstance(finance.json()["future"]["cost"], str)
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
        own = await client.get("/forecast/outlook", params=params, headers=headers)
        assert own.status_code == 200
        assert "cost" not in own.json()["future"] and "gm" not in own.json()["future"]
        listed = await client.get("/forecast/plans", headers=headers)
        assert listed.json()["total"] == 1
        assert "commercial_inputs" not in listed.json()["items"][0]
        request["expected_version_id"] = identity["version_id"]
        assert (await client.post(f"/forecast/plans/{identity['id']}/versions", json=request, headers=headers)).status_code == 403
        conversion = {"gm_model_id": str(uuid.uuid4()), "expected_version_id": identity["version_id"],
                      "scope_fraction": "1", "reason": "Confirmed signed scope"}
        assert (await client.post(f"/forecast/plans/{identity['id']}/conversions", json=conversion, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_worker_failure_is_durable_backed_off_and_repair_uses_new_version(session):
    from datetime import UTC, timedelta
    owner, opp, _, _, _ = await fixture(session)
    request = body(opp.client_id)
    failed_version = await save_plan(session, actor=actor(owner), body=request)
    # Inject stored-data corruption at the worker boundary, not a mocked calculator.
    failed_version.component_inputs = {**failed_version.component_inputs, "costs": [{"amount": "not-money"}]}
    await session.commit()
    assert await process_plan_jobs(session) == 1
    job = await session.scalar(select(ForecastJob))
    assert job.status == "failed" and job.attempts == 1 and job.last_error
    assert await session.get(ForecastSchedule, failed_version.id) is None
    assert await process_plan_jobs(session) == 0
    for attempt in range(2, 6):
        job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
        assert await process_plan_jobs(session) == 1
        assert job.attempts == attempt
    assert job.status == "dead"
    assert await process_plan_jobs(session) == 0
    repaired = body(opp.client_id).model_copy(update={"expected_version_id": failed_version.id})
    new = await save_plan(session, actor=actor(owner), body=repaired, plan_id=failed_version.plan_id)
    assert await process_plan_jobs(session) == 1
    assert await session.get(ForecastSchedule, new.id) is not None
    assert job.status == "dead"


@pytest.mark.asyncio
async def test_fixture_endpoint_provisions_authenticated_test_admin(session, monkeypatch):
    from app.routers.dev_seed import FixtureCreate, create_test_fixture
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    user = AuthUser(id=uuid.uuid4(), email="new-plan-principal@example.test", name="Test admin",
                    groups=("SystemAdmin", "officeapp-e2e"))
    result = await create_test_fixture(FixtureCreate(label="New test principal", reviewer_ids=[]), user, session)
    assert result["client_id"] and result["opportunity_id"]
