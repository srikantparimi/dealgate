"""Independent publication persistence faults; not global matching acceptance."""

import uuid
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal as D

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth import AuthUser
from app.db.base import Base
from app.gm.calendar import StaffingAssignment
from app.gm.commercial import PricingComponent
from app.gm.demand_source import line_key
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.people_demand import DemandLine, DemandPublicationVersion
from app.models.people_planning import PeopleSource
from app.models.user import User
from app.services.commercial_models import COMPONENT
from app.services.forecast_plans import PlanInput, save_plan
from app.services.people_demand import PublishDemandInput, demand_sources, publish_plan_demand
from app.services.people_planning import WorkforceImportInput, availability, import_workforce
from tests.test_approvals import app_with_session, _client  # noqa: F401


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "qa-publication-independent")


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def actor(session):
    email = f"{uuid.uuid4()}@example.test"
    identity = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")
    session.add(User(id=identity, email=email, name="Independent publisher", groups=["Delivery"]))
    await session.commit()
    return AuthUser(id=identity, email=email, name="Independent publisher", groups=("Delivery",))


async def plan(session, user, **staffing_changes):
    account = Client(id=uuid.uuid4(), name="Independent demand account")
    session.add(account)
    await session.commit()
    staffing = StaffingAssignment(**(dict(assignment_id="team", source_id="input", source_version="1",
        component_id="delivery", profile_version="1", policy_version="policy", role="Engineer",
        location="US", timezone="America/Los_Angeles", currency="USD", quantity=2, allocation=D("0.5"),
        calendar=None, bill_rate=None, cost_rate=None, rate_version=None, cost_version=None) | staffing_changes))
    component = PricingComponent(component_id="delivery", version="1", source_id="input", source_version="1",
        workstream_id="delivery", profile="fixed_assignment", profile_version="1", policy_version="policy",
        source_evidence=("independent-source:page-1",), service_start=date(2026, 11, 1), service_end=date(2026, 11, 30),
        timezone="America/Los_Angeles", currency="USD", billing_cadence=None, cost_basis=None,
        costs_confirmed=False, costs=(), pricing=None, staffing=(staffing,))
    body = PlanInput(account_id=account.id, title="Independent source", idempotency_key=uuid.uuid4(),
        inputs=COMPONENT.dump_python(component, mode="json"), probability="0.70",
        probability_source="Reviewed assumption", lifecycle="tentative", change_reason="Independent source fixture")
    return body, await save_plan(session, actor=user, body=body)


def request(version, **changes):
    return PublishDemandInput(**(dict(plan_id=version.plan_id, expected_source_version_id=version.id,
        expected_publication_version_id=None, request_key=str(uuid.uuid4()), reason="Confirmed source staffing",
        enrichments={}) | changes))


def enrichment(**changes):
    return {line_key("delivery", "team"): dict(skills=["python"], level="senior",
        evidence=["HR reviewed capability and continuity"]) | changes}


async def roster(session, user, *, previous=None, people=True):
    body = WorkforceImportInput(source_system="independent-roster", request_key=str(uuid.uuid4()),
        expected_previous_batch_id=previous, source_as_of="2026-10-01T00:00:00Z",
        reason="Confirmed workforce snapshot", basis="gross_with_commitments", people=[dict(
            person_key="one", display_name="Synthetic person", role="Engineer", skills=["python"], level="senior",
            location="US", timezone="America/Los_Angeles", evidence=["Roster row 1"], intervals=[dict(
                kind="gross", allocation="1", start_date="2026-11-01", end_date="2026-11-30")])] if people else [])
    hr = replace(user, groups=("HR",))
    batch = await import_workforce(session, actor=hr, body=body)
    view = await availability(session, actor=hr)
    return batch, view["people"][0]["person_id"] if people else None


async def publication_count(session):
    return await session.scalar(select(func.count()).select_from(DemandPublicationVersion))


async def test_uuid_aliases_cannot_claim_two_retained_slots_for_one_workforce_person(session):
    user = await actor(session)
    _, version = await plan(session, user)
    _, person_id = await roster(session, user)
    body = request(version, enrichments=enrichment(retained_person_ids=[person_id, uuid.UUID(person_id).hex]))
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=body)
    assert error.value.status_code == 422
    await session.rollback()
    assert await publication_count(session) == 0


@pytest.mark.parametrize("field", ["level", "role"])
async def test_publication_rejects_text_that_cannot_fit_its_persisted_schema(session, field):
    user = await actor(session)
    _, version = await plan(session, user, **({"role": "x" * 129} if field == "role" else {}))
    body = request(version, enrichments=enrichment(**({"level": "x" * 129} if field == "level" else {})))
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=body)
    assert error.value.status_code == 422
    await session.rollback()
    assert await publication_count(session) == 0


async def test_same_version_source_hash_drift_is_not_reported_as_current_publication(session):
    user = await actor(session)
    _, version = await plan(session, user)
    await publish_plan_demand(session, actor=user, body=request(version))
    changed = deepcopy(version.component_inputs)
    changed["staffing"][0]["quantity"] = 7
    version.component_inputs = changed  # Stored-source corruption, not a supported edit workflow.
    await session.commit()
    item, = (await demand_sources(session, actor=user))["items"]
    assert item["state"] == "stale" and item["lines"] == []


async def test_replay_after_source_revision_returns_history_without_restoring_freshness(session):
    user = await actor(session)
    edit, old = await plan(session, user)
    body = request(old)
    first = await publish_plan_demand(session, actor=user, body=body)
    new = await save_plan(session, actor=user, plan_id=old.plan_id,
        body=edit.model_copy(update={"expected_version_id": old.id, "probability": "0.20"}))
    assert await publish_plan_demand(session, actor=user, body=body) == first
    item, = (await demand_sources(session, actor=user))["items"]
    assert item["state"] == "stale" and item["source_version_id"] == str(new.id) and item["lines"] == []
    assert await publication_count(session) == 1
    audits = (await session.scalars(select(AuditEvent).where(AuditEvent.action == "people.demand_published"))).all()
    assert len(audits) == 1


async def test_same_source_enrichment_revision_preserves_old_lines_and_current_exactness(session):
    user = await actor(session)
    _, version = await plan(session, user, allocation=D("0.123456789012345678901"))
    first = await publish_plan_demand(session, actor=user, body=request(version))
    second = await publish_plan_demand(session, actor=user, body=request(version,
        expected_publication_version_id=first["version_id"], enrichments=enrichment()))
    rows = list((await session.scalars(select(DemandLine))).all())
    assert sorted(len(row.skills) for row in rows) == [0, 1]
    item, = (await demand_sources(session, actor=user))["items"]
    assert item["publication_version_id"] == second["version_id"]
    assert item["lines"][0]["allocation"] == "0.123456789012345678901"
    assert item["lines"][0]["quantity"] == 2 and item["missing"] == []


async def test_replay_key_cannot_be_reused_by_another_authorized_publisher(session):
    user, other = await actor(session), await actor(session)
    _, version = await plan(session, user)
    body = request(version)
    await publish_plan_demand(session, actor=user, body=body)
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=other, body=body)
    assert error.value.status_code == 409 and await publication_count(session) == 1


@pytest.mark.parametrize("field", ["expected_source_version_id", "expected_publication_version_id"])
async def test_stale_compare_and_swap_does_not_append_lines_or_audit(session, field):
    user = await actor(session)
    _, version = await plan(session, user)
    first = await publish_plan_demand(session, actor=user, body=request(version))
    values = dict(expected_publication_version_id=first["version_id"])
    values[field] = uuid.uuid4()
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=request(version, **values))
    assert error.value.status_code == 409
    await session.rollback()
    assert await publication_count(session) == 1
    assert await session.scalar(select(func.count()).select_from(DemandLine)) == 1


@pytest.mark.parametrize("fault", ["removed", "foreign_tenant", "test_roster"])
async def test_continuity_requires_current_matching_scope_not_any_historical_identity(session, fault):
    user = await actor(session)
    _, version = await plan(session, user)
    batch, person_id = await roster(session, user)
    if fault == "removed":
        await roster(session, user, previous=batch["id"], people=False)
    else:
        source = await session.scalar(select(PeopleSource))
        if fault == "foreign_tenant":
            source.tenant_id = "foreign"
        else:
            source.test_fixture = True
        await session.commit()
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user,
            body=request(version, enrichments=enrichment(retained_person_ids=[person_id])))
    assert error.value.status_code == 422 and await publication_count(session) == 0


@pytest.mark.parametrize("key,value", [("DEALGATE_TENANT_ID", "foreign"), ("DEALGATE_ENV", "staging")])
async def test_foreign_runtime_cannot_read_or_publish_a_known_plan(session, monkeypatch, key, value):
    user = await actor(session)
    _, version = await plan(session, user)
    monkeypatch.setenv(key, value)
    assert (await demand_sources(session, actor=user))["items"] == []
    with pytest.raises(HTTPException) as error:
        await publish_plan_demand(session, actor=user, body=request(version))
    assert error.value.status_code == 404 and await publication_count(session) == 0


async def test_incomplete_publication_is_current_but_does_not_fabricate_zero_or_capability(session):
    user = await actor(session)
    _, version = await plan(session, user, location=None, allocation=D("0"))
    await publish_plan_demand(session, actor=user, body=request(version))
    item, = (await demand_sources(session, actor=user))["items"]
    row, = item["lines"]
    assert item["state"] == "current" and item["missing"]
    assert row["allocation"] is None and row["quantity"] == 2
    assert set(row["missing"]) == {"allocation", "location", "skills", "level"}


@pytest.mark.parametrize("role,allowed", [("HR", True), ("SystemAdmin", True),
    ("Sales", False), ("Delivery", False), ("Finance", False), ("CEO", False)])
async def test_named_continuity_is_only_exposed_to_hr_or_admin(session, role, allowed):
    user = await actor(session)
    _, version = await plan(session, user)
    _, person_id = await roster(session, user)
    await publish_plan_demand(session, actor=user,
        body=request(version, enrichments=enrichment(retained_person_ids=[person_id])))
    item, = (await demand_sources(session, actor=replace(user, groups=(role,))))["items"]
    row, = item["lines"]
    assert ("retained_person_ids" in row) is allowed
    if allowed:
        assert row["retained_person_ids"] == [person_id]
    assert not {"cost_rate", "bill_rate", "costs", "pricing", "salary"} & row.keys()


async def test_actual_http_rejects_financial_enrichment_without_publishing(app_with_session, session, monkeypatch):  # noqa: F811
    user = await actor(session)
    _, version = await plan(session, user)
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
    body = request(version, enrichments=enrichment(cost_rate="100")).model_dump(mode="json")
    async with _client(app_with_session) as client:
        response = await client.post("/people/demand/publications", json=body, headers={"X-Test-User": user.email})
    assert response.status_code == 422, response.text
    assert await publication_count(session) == 0
