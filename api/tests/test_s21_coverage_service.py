"""Explicit staffing conversion must survive real publication and allocation paths."""
import uuid
from dataclasses import replace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select

from app.gm.demand_source import line_key
from app.models.people_coverage import DemandCoverageVersion
from app.services.forecast_plans import save_plan
from app.services.people_allocation import demand_allocation
from app.services.people_demand import publish_plan_demand
from app.services.people_project_demand import publish_project_demand
from tests.test_s21_demand_publication import publication
from tests.test_s21_forecast_plans import actor, body
from tests.test_s21_project_demand import canonical, request  # noqa: F401
from tests.test_s21_project_scope_independent import engine  # noqa: F401
from tests.test_s21_project_source_scope import project


@pytest_asyncio.fixture
async def pair(session, canonical):
    p = await project(session, canonical)
    user = actor(canonical[0])
    plan = body(canonical[1].client_id)
    plan.inputs = p.baseline_snapshot_json["commercial_inputs"]
    version = await save_plan(session, actor=user, body=plan)
    enrichment = {line_key("build", "team-1"): {
        "skills": ["python"], "level": "senior", "evidence": ["Delivery capability review"]}}
    a = await publish_plan_demand(session, actor=user, body=publication(version, enrichments=enrichment))
    b = await publish_project_demand(session, actor=user, body=request(p, enrichments=enrichment))
    return user, a, b, version, enrichment


def coverage(pair, **changes):
    from app.services.people_coverage import CoverageInput
    _, a, b, _, _ = pair
    return CoverageInput(**(dict(plan_publication_id=a["publication_id"], project_publication_id=b["publication_id"],
        expected_plan_version_id=a["version_id"], expected_project_version_id=b["version_id"],
        expected_mapping_version_id=None, request_key=str(uuid.uuid4()), reason="Delivery confirms replacement staffing",
        mappings=[dict(plan_line_key=line_key("build", "team-1"), project_line_key=line_key("build", "team-1"),
            plan_slots=[0, 1], project_slots=[0, 1], start_date="2026-11-01", end_date="2027-04-30")]) | changes))


async def test_coverage_reduces_real_global_demand_and_clear_appends(session, pair):
    from app.services.people_coverage import list_coverage, save_coverage
    user, a, _, _, _ = pair
    before = await demand_allocation(session, actor=user)
    assert max(sum(d["quantity"] for d in i["demands"]) for i in before["intervals"]) == 4
    request_body = coverage(pair)
    first = await save_coverage(session, actor=user, body=request_body)
    assert await save_coverage(session, actor=user, body=request_body) == first
    after = await demand_allocation(session, actor=user)
    assert max(sum(d["quantity"] for d in i["demands"]) for i in after["intervals"]) == 2
    assert before["source_watermark"] != after["source_watermark"]
    assert first["state"] == "current" and first["is_reservation"] is False
    second = await save_coverage(session, actor=user, body=coverage(pair,
        expected_mapping_version_id=first["version_id"], mappings=[], reason="Remove mistaken mapping"))
    history = await list_coverage(session, actor=user, plan_publication_id=uuid.UUID(a["publication_id"]),
        root_id=uuid.UUID(first["id"]))
    assert [row["revision"] for row in history["items"]] == [2, 1]
    assert history["current_version_id"] == second["version_id"]
    assert history["items"][1]["mappings"] == first["mappings"]
    restored = await demand_allocation(session, actor=user)
    assert max(sum(d["quantity"] for d in i["demands"]) for i in restored["intervals"]) == 4


@pytest.mark.parametrize("fault", ["cas", "source", "replay", "overlap"])
async def test_coverage_rejects_conflicts_without_appending(session, pair, fault):
    from app.services.people_coverage import save_coverage
    user = pair[0]
    original = coverage(pair)
    first = await save_coverage(session, actor=user, body=original)
    change = dict(expected_mapping_version_id=first["version_id"])
    if fault == "cas": change["expected_mapping_version_id"] = uuid.uuid4()
    if fault == "source": change["expected_plan_version_id"] = uuid.uuid4()
    if fault == "replay": change.update(request_key=original.request_key, reason="Changed reason")
    if fault == "overlap": change["mappings"] = original.model_dump(mode="json")["mappings"] * 2
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=user, body=coverage(pair, **change))
    assert error.value.status_code in ({422} if fault == "overlap" else {409})
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandCoverageVersion)) == 1


@pytest.mark.parametrize("role", ["HR", "Sales", "Finance", "CEO", "Legal"])
async def test_coverage_write_role_boundary(session, pair, role):
    from app.services.people_coverage import save_coverage
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=replace(pair[0], groups=(role,)), body=coverage(pair))
    assert error.value.status_code == 403


async def test_republication_stales_mapping_and_never_silently_rebinds(session, pair):
    from app.services.people_coverage import list_coverage, save_coverage
    user, a, _, version, enrichment = pair
    await save_coverage(session, actor=user, body=coverage(pair))
    await publish_plan_demand(session, actor=user, body=publication(version,
        expected_publication_version_id=a["version_id"], enrichments=enrichment))
    history = await list_coverage(session, actor=user, plan_publication_id=uuid.UUID(a["publication_id"]))
    assert history["items"][0]["state"] == "stale"
    allocated = await demand_allocation(session, actor=user)
    assert "staffing_coverage_stale" in allocated["missing"]
    assert allocated["complete"] is False


@pytest.mark.parametrize("fault", ["tenant", "environment", "classification"])
async def test_coverage_cross_runtime_and_fixture_access_is_denied(session, pair, monkeypatch, fault):
    from app.services.people_coverage import save_coverage
    user = pair[0]
    if fault == "tenant": monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    if fault == "environment": monkeypatch.setenv("DEALGATE_ENV", "foreign")
    if fault == "classification": user = replace(user, groups=("Delivery", "officeapp-e2e"))
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=user, body=coverage(pair))
    assert error.value.status_code == 404


async def test_project_slots_cannot_cover_two_distinct_plans(session, pair, canonical):
    from app.services.people_coverage import save_coverage
    from app.models.forecast import ForecastPlanVersion
    user, _, _, version, enrichment = pair
    await save_coverage(session, actor=user, body=coverage(pair))
    inputs = (await session.get(ForecastPlanVersion, version.id)).component_inputs
    new = body(canonical[1].client_id)
    new.inputs = inputs
    other = await save_plan(session, actor=user, body=new)
    published = await publish_plan_demand(session, actor=user, body=publication(other, enrichments=enrichment))
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=user, body=coverage(pair,
            plan_publication_id=published["publication_id"], expected_plan_version_id=published["version_id"]))
    assert error.value.status_code == 422 and "overlap" in error.value.detail


async def test_coverage_http_role_history_and_slot_validation(app_with_session, session, pair, monkeypatch):
    from tests.test_approvals import _client
    payload = coverage(pair).model_dump(mode="json")
    headers = {"X-Test-User": pair[0].email}
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        assert (await client.post("/people/demand/coverage", json=payload, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        created = await client.post("/people/demand/coverage", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        history = await client.get("/people/demand/coverage", params={"plan_publication_id": payload["plan_publication_id"]}, headers=headers)
        assert history.status_code == 200 and history.json()["items"][0] == created.json()
        assert "retained_person_ids" not in history.text
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
        assert (await client.get("/people/demand/coverage", params={"plan_publication_id": payload["plan_publication_id"]}, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        payload["mappings"][0]["plan_slots"] = [True]
        assert (await client.post("/people/demand/coverage", json=payload, headers=headers)).status_code == 422


async def test_sow_deletion_retains_mapping_but_plan_deletion_cascades(session, pair, canonical):
    from sqlalchemy import delete
    from app.models.forecast import ForecastPlan
    from app.models.people_coverage import DemandCoverageRoot
    from app.services.deletion import request_sow_deletion
    from app.services.people_coverage import list_coverage, save_coverage
    user, a, _, version, _ = pair
    saved = await save_coverage(session, actor=user, body=coverage(pair))
    await request_sow_deletion(session, actor_id=user.id, sow_id=canonical[2].sow_id)
    await session.commit()
    history = await list_coverage(session, actor=user, plan_publication_id=uuid.UUID(a["publication_id"]))
    assert history["items"][0] == saved
    allocated = await demand_allocation(session, actor=user)
    assert max(sum(d["quantity"] for d in i["demands"]) for i in allocated["intervals"]) == 2
    await session.execute(delete(ForecastPlan).where(ForecastPlan.id == version.plan_id))
    await session.commit()
    assert await session.get(DemandCoverageRoot, uuid.UUID(saved["id"]), populate_existing=True) is None
    assert await session.get(DemandCoverageVersion, uuid.UUID(saved["version_id"]), populate_existing=True) is None


from tests.test_approvals import app_with_session  # noqa: E402,F401
