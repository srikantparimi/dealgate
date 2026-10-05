"""Retained delivery contributes full cost-free staffing, not deleted revenue."""
import uuid
from dataclasses import replace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.people_demand import DemandPublicationVersion
from app.services.people_demand import demand_sources
from app.services.people_allocation import demand_allocation
from tests.test_s21_forecast_plans import actor
from tests.test_s21_project_source_scope import detach, project
from tests.test_s21_project_scope_independent import engine  # noqa: F401


@pytest_asyncio.fixture
async def canonical(session, monkeypatch):
    from app.models.approval import ApprovalPackage
    from app.models.client import Client
    from app.services.commercial_models import save_commercial_model
    from tests.test_approval_routing import fixture
    from tests.test_s21_commercial_persistence import wire
    from tests.test_s21_commercial_profiles import staffing
    monkeypatch.setenv("DEALGATE_TENANT_ID", "source-tenant")
    monkeypatch.setenv("DEALGATE_ENV", "local")
    owner, deal, version, old, _ = await fixture(session)
    deal.hubspot_deal_id = None
    deal.source = "sow_upload"
    (await session.get(Client, deal.client_id)).hubspot_company_id = None
    gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=owner.id,
        sow_version_id=version.id, expected_gm_model_id=old.id,
        inputs=wire(version, staffing=(staffing(source_id=str(version.sow_id), source_version=str(version.id),
            policy_version="blueprint-defaults-v1"),)),
        change_reason="Approved two-person delivery staffing")
    package = ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
        gm_model_id=gm.id, package_hash="a" * 64, status="released", submitted_by=owner.id)
    session.add(package)
    await session.flush()
    return owner, deal, version, gm, package


def request(p, **changes):
    from app.services.people_project_demand import PublishProjectDemandInput
    return PublishProjectDemandInput(**(dict(project_id=p.id,
        expected_source_version_id=p.baseline_snapshot_json["source_scope"]["gm_model_id"],
        expected_publication_version_id=None, request_key=str(uuid.uuid4()),
        reason="Delivery confirms retained staffing", enrichments={}) | changes))


async def test_project_publication_replay_and_cost_free_source(session, canonical):
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    user = actor(canonical[0])
    body = request(p)
    first = await publish_project_demand(session, actor=user, body=body)
    assert await publish_project_demand(session, actor=user, body=body) == first
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == uuid.UUID(first["publication_id"]))) == 1
    result = await demand_sources(session, actor=replace(user, groups=("HR",)))
    row = result["items"][0]
    assert row["source_id"] == str(p.id) and row["source_kind"] == "project"
    assert row["plan_id"] is None and row["project_id"] == str(p.id)
    assert row["lifecycle"] == "committed" and row["probability"] == "1"
    assert row["state"] == "current" and row["lines"][0]["quantity"] == 2
    assert not {"commercial_inputs", "commercial_snapshot", "price", "cost", "baseline"} & row.keys()


async def test_detached_project_keeps_publication_and_stable_demand_identity(session, canonical):
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    user = actor(canonical[0])
    await publish_project_demand(session, actor=user, body=request(p))
    before = (await demand_sources(session, actor=user))["items"][0]
    detach(p)
    await session.commit()
    after = (await demand_sources(session, actor=user))["items"][0]
    assert after["account_id"] == before["account_id"]
    assert after["lines"] == before["lines"] and after["state"] == "current"
    allocated = await demand_allocation(session, actor=user)
    assert allocated["intervals"]
    assert all(row["quantity"] == 2 and row["project_id"] == str(p.id)
        for interval in allocated["intervals"] for row in interval["demands"])


@pytest.mark.parametrize("role", ["HR", "Sales", "Finance", "Legal"])
async def test_project_publication_requires_delivery(session, canonical, role):
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    with pytest.raises(HTTPException) as error:
        await publish_project_demand(session, actor=replace(actor(canonical[0]), groups=(role,)), body=request(p))
    assert error.value.status_code == 403


@pytest.mark.parametrize("fault", ["source", "publication", "replay"])
async def test_project_publication_conflicts_never_append(session, canonical, fault):
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    user = actor(canonical[0])
    body = request(p)
    first = await publish_project_demand(session, actor=user, body=body)
    change = {"reason": "Different meaning"} if fault == "replay" else {
        "request_key": str(uuid.uuid4()), "expected_publication_version_id": uuid.UUID(first["version_id"]),
        "expected_source_version_id": uuid.uuid4()}
    if fault == "publication":
        change.update(expected_source_version_id=body.expected_source_version_id,
            expected_publication_version_id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await publish_project_demand(session, actor=user, body=body.model_copy(update=change))
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == uuid.UUID(first["publication_id"]))) == 1


async def test_project_authorization_precedes_portfolio_and_archive_projection(session, canonical, monkeypatch):
    from datetime import UTC, datetime
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    user = actor(canonical[0])
    assert (await demand_sources(session, actor=user))["items"][0]["state"] == "pending"
    outsider = replace(user, id=uuid.uuid4(), groups=("Sales",))
    assert (await demand_sources(session, actor=outsider))["items"] == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert (await demand_sources(session, actor=user))["items"] == []
    with pytest.raises(HTTPException) as error:
        await publish_project_demand(session, actor=user, body=request(p))
    assert error.value.status_code == 404
    monkeypatch.setenv("DEALGATE_TENANT_ID", "source-tenant")
    p.archived_at = datetime.now(UTC)
    assert (await demand_sources(session, actor=user))["items"] == []


async def test_legacy_project_scope_never_adopted_as_current_demand(session, canonical):
    from app.services.people_project_demand import publish_project_demand
    p = await project(session, canonical)
    body = request(p)
    p.baseline_snapshot_json = {**p.baseline_snapshot_json, "source_scope": None}
    assert (await demand_sources(session, actor=actor(canonical[0])))["items"] == []
    with pytest.raises(HTTPException) as error:
        await publish_project_demand(session, actor=actor(canonical[0]), body=body)
    assert error.value.status_code == 404


async def test_actual_sow_and_client_deletion_preserves_project_sourcing_history(session, canonical):
    from app.gm.demand_source import line_key
    from app.services.deletion import request_sow_deletion
    from app.services.parent_deletion import request_client_deletion
    from app.services.people_project_demand import publish_project_demand
    from app.services.people_sourcing import DraftInput, RulesInput, list_drafts, prepare_draft, save_rules
    p = await project(session, canonical)
    user = actor(canonical[0])
    client_id, sow_id = p.client_id, canonical[2].sow_id
    published = await publish_project_demand(session, actor=user, body=request(p, enrichments={
        line_key("build", "team-1"): {"skills": ["python"], "level": "senior", "evidence": ["HR confirms staffing"]}}))
    hr = replace(user, groups=("HR",))
    rules = await save_rules(session, actor=hr, body=RulesInput(expected_version_id=None,
        request_key="retained-rules", reason="Regional hiring review",
        rules=[{"skill": "python", "location": "US", "lead_days": 45}]))
    body = DraftInput(publication_id=published["publication_id"], expected_demand_version_id=published["version_id"],
        expected_rule_version_id=rules["id"], expected_draft_version_id=None,
        request_key="retained-draft", reason="Prepare delivery sourcing")
    original = await prepare_draft(session, actor=hr, body=body)
    await request_sow_deletion(session, actor_id=user.id, sow_id=sow_id)
    await session.commit()
    await request_client_deletion(session, actor_id=user.id, client_id=client_id)
    await session.commit()
    await session.refresh(p)
    assert p.client_id is p.gm_model_id is p.opportunity_id is None
    sources = (await demand_sources(session, actor=hr))["items"]
    assert len(sources) == 1 and sources[0]["account_id"] == str(client_id)
    history = await list_drafts(session, actor=hr, publication_id=body.publication_id)
    assert history["items"][0] == original
    refreshed = await prepare_draft(session, actor=hr, body=body.model_copy(update={
        "request_key": "retained-refresh", "expected_draft_version_id": uuid.UUID(original["id"])}))
    assert refreshed["revision"] == 2 and refreshed["snapshot"]["lifecycle"] == "committed"
    assert all(row["project_id"] == str(p.id) and row["plan_id"] is None and row["quantity"] == 2
        and row["sourcing_by"] == "2026-09-17" for row in refreshed["snapshot"]["rows"])
    assert refreshed["snapshot"]["rows"]


async def test_project_publication_http_enforces_role_and_returns_real_persisted_source(app_with_session, session, canonical, monkeypatch):
    from tests.test_approvals import _client
    p = await project(session, canonical)
    body = request(p).model_dump(mode="json")
    headers = {"X-Test-User": canonical[0].email}
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        assert (await client.post("/people/demand/project-publications", json=body, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        response = await client.post("/people/demand/project-publications", json=body, headers=headers)
        assert response.status_code == 201, response.text
        view = await client.get("/people/demand", headers=headers)
        assert view.status_code == 200 and view.json()["items"][0]["project_id"] == str(p.id)


from tests.test_approvals import app_with_session  # noqa: E402,F401
