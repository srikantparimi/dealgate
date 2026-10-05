"""FC-07/T22: immutable source-bound, cost-free publication boundaries."""
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.people_demand import DemandLine, DemandPublicationVersion
from app.services.commercial_models import COMPONENT
from app.services.forecast_plans import save_plan
from app.services.people_demand import PublishDemandInput, publish_plan_demand, demand_sources
from tests.test_approval_routing import fixture
from tests.test_s21_commercial_profiles import component, staffing
from tests.test_s21_forecast_plans import actor, body, scope  # noqa: F401


async def source(session, **assignment_changes):
    owner, opp, _, _, _ = await fixture(session)
    request = body(opp.client_id)
    request.inputs = COMPONENT.dump_python(component(staffing=(staffing(**assignment_changes),)), mode="json")
    version = await save_plan(session, actor=actor(owner), body=request)
    return actor(owner), request, version


def publication(version, **changes):
    return PublishDemandInput(**(dict(plan_id=version.plan_id, expected_source_version_id=version.id,
        expected_publication_version_id=None, request_key=str(uuid.uuid4()),
        reason="Delivery confirms source staffing for HR planning", enrichments={}) | changes))


async def test_publication_is_exact_cost_free_and_idempotent(session):
    user, _, version = await source(session)
    request = publication(version)
    first = await publish_plan_demand(session, actor=user, body=request)
    assert await publish_plan_demand(session, actor=user, body=request) == first
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 1
    row = await session.scalar(select(DemandLine))
    assert row.quantity == 2 and row.allocation == Decimal("0.5")
    assert set(row.missing) == {"skills", "level"}
    stored = await session.get(DemandPublicationVersion, uuid.UUID(first["version_id"]))
    assert stored.source_version == str(version.id)
    assert stored.source_metadata["probability"] == "0.70"
    assert not {"component_inputs", "costs", "pricing", "policy_snapshot"} & stored.source_metadata.keys()
    assert first["missing"] and first["is_reservation"] is False


async def test_missing_location_and_zero_allocation_are_persisted_as_unresolved(session):
    user, _, version = await source(session, location=None, allocation=Decimal("0"))
    await publish_plan_demand(session, actor=user, body=publication(version))
    row = await session.scalar(select(DemandLine))
    assert row.location == "" and row.allocation is None
    assert {"location", "allocation"} <= set(row.missing)


async def test_new_source_and_enrichment_append_without_mutating_old_publication(session):
    from app.gm.demand_source import line_key
    user, request, old = await source(session)
    first = await publish_plan_demand(session, actor=user, body=publication(old))
    new = await save_plan(session, actor=user, plan_id=old.plan_id,
        body=request.model_copy(update={"expected_version_id": old.id, "probability": "0.5"}))
    enriched = {line_key("build", "team-1"): {"skills": ["python"], "level": "Senior",
        "evidence": ["HR capability review"]}}
    second = await publish_plan_demand(session, actor=user, body=publication(new,
        expected_publication_version_id=first["version_id"], enrichments=enriched))
    assert second["revision"] == 2 and second["missing"] == []
    rows = list((await session.scalars(select(DemandLine))).all())
    assert len(rows) == 2 and sorted(len(row.skills) for row in rows) == [0, 1]
    assert (await session.get(DemandPublicationVersion, uuid.UUID(first["version_id"]))).source_version == str(old.id)


@pytest.mark.parametrize("fault", ["source", "publication", "replay"])
async def test_conflicting_write_never_appends(session, fault):
    user, _, version = await source(session)
    request = publication(version)
    first = await publish_plan_demand(session, actor=user, body=request)
    changes = {"reason": "Changed request"} if fault == "replay" else {
        "request_key": str(uuid.uuid4()), "expected_publication_version_id": first["version_id"]}
    if fault == "source": changes["expected_source_version_id"] = uuid.uuid4()
    if fault == "publication": changes["expected_publication_version_id"] = uuid.uuid4()
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=PublishDemandInput(**(request.model_dump() | changes)))
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 1


@pytest.mark.parametrize("role", ["HR", "Sales", "Finance", "CEO", "Legal"])
async def test_publication_requires_delivery_permission(session, role):
    user, _, version = await source(session)
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=replace(user, groups=(role,)), body=publication(version))
    assert error.value.status_code == 403


async def test_foreign_runtime_and_test_identity_cannot_publish(session, monkeypatch):
    user, _, version = await source(session)
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=replace(user, groups=("Delivery", "officeapp-e2e")), body=publication(version))
    assert error.value.status_code == 403
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=publication(version))
    assert error.value.status_code == 404


async def test_unknown_retained_person_is_rejected_before_any_publication(session):
    from app.gm.demand_source import line_key
    user, _, version = await source(session)
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=publication(version,
            enrichments={line_key("build", "team-1"): {"retained_person_ids": [str(uuid.uuid4())],
                "evidence": ["Claimed continuity"]}}))
    assert error.value.status_code == 422
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 0


async def test_current_read_exposes_pending_and_stale_sources_without_old_fresh_lines(session):
    user, request, old = await source(session)
    pending = await demand_sources(session, actor=replace(user, groups=("HR",)))
    assert pending["items"][0]["state"] == "pending"
    assert pending["items"][0]["account_name"]
    assert pending["items"][0]["lines"] == []
    await publish_plan_demand(session, actor=user, body=publication(old))
    current = await demand_sources(session, actor=replace(user, groups=("HR",)))
    assert current["items"][0]["state"] == "current"
    assert current["items"][0]["lines"][0]["quantity"] == 2
    assert current["items"][0]["lines"][0]["allocation"] == "0.5"
    await save_plan(session, actor=user, plan_id=old.plan_id,
        body=request.model_copy(update={"expected_version_id": old.id, "probability": "0.5"}))
    stale = await demand_sources(session, actor=user)
    assert stale["items"][0]["state"] == "stale"
    assert stale["items"][0]["lines"] == []
    assert stale["items"][0]["publication_version_id"]
    own = await demand_sources(session, actor=replace(user, groups=("Sales",)))
    assert own["scope_label"] == "My portfolio" and len(own["items"]) == 1
    other = await demand_sources(session, actor=replace(user, id=uuid.uuid4(), groups=("Sales",)))
    assert other["items"] == []


async def test_republication_preserves_existing_manual_enrichment_unless_explicitly_changed(session):
    from app.gm.demand_source import line_key
    user, _, source_version = await source(session)
    key = line_key("build", "team-1")
    first = await publish_plan_demand(session, actor=user, body=publication(source_version,
        enrichments={key: {"skills": ["python"], "level": "Senior", "evidence": ["Confirmed HR capability"]}}))
    second = await publish_plan_demand(session, actor=user, body=publication(source_version,
        expected_publication_version_id=first["version_id"], enrichments={key: {"level": "Principal",
            "evidence": ["Confirmed revised level"]}}))
    row = await session.scalar(select(DemandLine).where(DemandLine.version_id == uuid.UUID(second["version_id"])))
    assert row.skills == ["python"] and row.level == "Principal"
    assert "Confirmed HR capability" in row.evidence and "Confirmed revised level" in row.evidence


@pytest.mark.parametrize("evidence", [None, [], [{"source": "invalid collection"}], "untyped evidence"])
async def test_changed_enrichment_cannot_reuse_old_justification_or_malformed_evidence(session, evidence):
    from app.gm.demand_source import line_key
    user, _, version = await source(session)
    key = line_key("build", "team-1")
    first = await publish_plan_demand(session, actor=user, body=publication(version,
        enrichments={key: {"skills": ["python"], "level": "Senior", "evidence": ["Original HR review"]}}))
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=publication(version,
            expected_publication_version_id=first["version_id"],
            enrichments={key: {"level": "Principal", "evidence": evidence}}))
    assert error.value.status_code == 422


async def test_demand_api_permission_and_round_trip(app_with_session, session, monkeypatch):
    from tests.test_approvals import _client
    user, _, version = await source(session)
    headers = {"X-Test-User": user.email}
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
        assert (await client.get("/people/demand", headers=headers)).status_code == 403
        request = publication(version).model_dump(mode="json")
        assert (await client.post("/people/demand/publications", json=request, headers=headers)).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
        response = await client.post("/people/demand/publications", json=request, headers=headers)
        assert response.status_code == 201, response.text
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        view = await client.get("/people/demand", headers=headers)
        assert view.status_code == 200
        assert view.json()["items"][0]["lines"][0]["quantity"] == 2
        assert (await client.post("/people/demand/publications", json=request, headers=headers)).status_code == 403


from tests.test_approvals import app_with_session  # noqa: E402,F401
