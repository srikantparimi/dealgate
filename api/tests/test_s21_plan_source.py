"""FC-08 plan provenance is authoritative identity, not mere local linkage."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.models.client import Client
from app.models.forecast import ForecastPlan
from app.models.opportunity import Opportunity
from app.services.forecast_plans import list_plans, save_plan
from tests.test_s21_forecast_plans import actor, body, scope  # noqa: F401
from tests.test_approval_routing import fixture


@pytest.mark.parametrize(("source", "external_id", "expected"), [
    ("sow_upload", None, "Linked local deal"),
    ("manual", None, "Linked local deal"),
    ("bulk_import", None, "Linked local deal"),
    ("hubspot", "123456", "Linked HubSpot deal"),
    ("sow_upload", "123456", "Linked HubSpot deal"),
    ("hubspot", None, "Linked deal; CRM identity unavailable"),
    ("hubspot", " ", "Linked deal; CRM identity unavailable"),
])
async def test_linked_plan_reports_actual_external_identity(session, source, external_id, expected):
    owner, deal, *_ = await fixture(session)
    deal.source, deal.hubspot_deal_id = source, external_id
    await session.commit()
    request = body(deal.client_id).model_copy(update={"opportunity_id": deal.id})
    await save_plan(session, actor=actor(owner), body=request)
    row, = await list_plans(session, actor=actor(owner))
    assert row["source_status"] == expected
    assert row["opportunity_id"] == str(deal.id)
    assert row["source_evidence"] == ["sow-x:page-2"]
    await session.refresh(deal)
    assert deal.source == source and deal.hubspot_deal_id == external_id


async def test_unlinked_plan_remains_explicitly_local(session):
    owner, deal, *_ = await fixture(session)
    await save_plan(session, actor=actor(owner), body=body(deal.client_id))
    row, = await list_plans(session, actor=actor(owner))
    assert row["source_status"] == "Local forecast only"
    assert row["opportunity_id"] is None


@pytest.mark.parametrize("state", ["missing", "archived", "foreign_account"])
async def test_unavailable_deal_does_not_expose_a_live_link_or_foreign_metadata(session, state):
    owner, deal, *_ = await fixture(session)
    version = await save_plan(session, actor=actor(owner), body=body(deal.client_id))
    plan = await session.get(ForecastPlan, version.plan_id)
    if state == "missing":
        plan.opportunity_id = uuid.uuid4()  # Simulate legacy dangling source data.
    elif state == "archived":
        deal.archived_at = datetime.now(UTC)
        plan.opportunity_id = deal.id
    else:
        other = Client(id=uuid.uuid4(), name="Hidden account")
        session.add(other)
        await session.flush()
        hidden = Opportunity(id=uuid.uuid4(), client_id=other.id, source="hubspot", hubspot_deal_id="PRIVATE-CRM-ID", name="Hidden deal")
        session.add(hidden)
        await session.flush()
        plan.opportunity_id = hidden.id
    await session.commit()
    row, = await list_plans(session, actor=actor(owner))
    assert row["source_status"] == "Linked deal unavailable"
    assert row["opportunity_id"] is None
    assert "PRIVATE-CRM-ID" not in str(row) and "Hidden deal" not in str(row)


async def test_hidden_owner_and_tenant_cannot_learn_plan_sources(session, monkeypatch):
    owner, deal, *_ = await fixture(session)
    await save_plan(session, actor=actor(owner), body=body(deal.client_id).model_copy(update={"opportunity_id": deal.id}))
    outsider = replace(actor(owner, ("Sales",)), id=uuid.uuid4())
    assert await list_plans(session, actor=outsider) == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "different-tenant")
    assert await list_plans(session, actor=actor(owner)) == []


async def test_server_issued_fixture_remains_local_and_hidden_from_business_users(session, monkeypatch):
    from app.services.test_fixtures import create_fixture
    owner, _, *_ = await fixture(session)
    owner.groups = ["SystemAdmin", "officeapp-e2e"]
    await session.commit()
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    issued = await create_fixture(session, actor_id=owner.id, label="Plan source proof", reviewer_ids=[])
    await session.commit()
    test_actor = actor(owner, ("SystemAdmin", "officeapp-e2e"))
    await save_plan(session, actor=test_actor, body=body(issued["client_id"]).model_copy(update={"opportunity_id": issued["opportunity_id"]}))
    row, = await list_plans(session, actor=test_actor)
    assert row["source_status"] == "Linked local deal"
    assert await list_plans(session, actor=actor(owner, ("SystemAdmin",))) == []
    # A fixture grant names one deal, not arbitrary siblings in the same account.
    ungranted = Opportunity(id=uuid.uuid4(), client_id=issued["client_id"], source="manual")
    session.add(ungranted)
    await session.flush()
    plan = await session.get(ForecastPlan, uuid.UUID(row["id"]))
    plan.opportunity_id = ungranted.id
    await session.commit()
    unavailable, = await list_plans(session, actor=test_actor)
    assert unavailable["source_status"] == "Linked deal unavailable"
    assert unavailable["opportunity_id"] is None


@pytest.mark.parametrize("state", ["missing", "archived", "foreign_account"])
async def test_calculated_outlook_removes_unavailable_deal_destinations(session, state):
    from app.routers.forecast import _planning_response
    from app.services.forecast_plans import outlook, process_plan_jobs

    owner, deal, *_ = await fixture(session)
    version = await save_plan(session, actor=actor(owner), body=body(deal.client_id))
    assert await process_plan_jobs(session) == 1
    plan = await session.get(ForecastPlan, version.plan_id)
    if state == "missing":
        plan.opportunity_id = uuid.uuid4()
    elif state == "archived":
        deal.archived_at = datetime.now(UTC)
        plan.opportunity_id = deal.id
    else:
        hidden_account = Client(id=uuid.uuid4(), name="Hidden source account")
        session.add(hidden_account)
        await session.flush()
        hidden = Opportunity(id=uuid.uuid4(), client_id=hidden_account.id, source="hubspot", hubspot_deal_id="PRIVATE-SOURCE", name="Hidden source deal")
        session.add(hidden)
        await session.flush()
        plan.opportunity_id = hidden.id
    await session.commit()
    reader = actor(owner, ("Sales",))
    view = _planning_response(await outlook(
        session, actor=reader, as_of=datetime(2026, 10, 1, 12, tzinfo=UTC)
    ), reader)
    assert view["rows"]
    for row in view["rows"]:
        assert row["source_url"] is None
        assert row["opportunity_id"] is None
        assert row["source_status"] == "Linked deal unavailable"
        assert row["source_evidence"] == ["sow-x:page-2"]
        assert "cost" not in row
    assert "PRIVATE-SOURCE" not in str(view) and "Hidden source deal" not in str(view)
