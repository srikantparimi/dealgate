"""Acceptance tests for S1-E2 HubSpot intake.

Covers every Given/When/Then in docs/backlog/s1-e2-hubspot-webhook-intake.md
plus a permission test on the admin replay endpoint.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.integrations.hubspot import HubSpotClient, StubHubSpotClient, get_hubspot_client
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.integration import IntegrationEvent
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User
from app.services.hubspot_intake import handle_event

HUBSPOT_SECRET = "unit-test-secret"
LEADER_EMAIL = "sales-leader@smartek21.com"
WEBHOOK_URL = "https://dealgate.example.com/integrations/hubspot/webhook"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("HUBSPOT_APP_SECRET", HUBSPOT_SECRET)
    monkeypatch.setenv("HUBSPOT_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("SALES_LEADER_EMAIL", LEADER_EMAIL)
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _sign(body: bytes, timestamp: str) -> str:
    base = f"POST{WEBHOOK_URL}{body.decode('utf-8')}{timestamp}"
    digest = hmac.new(
        HUBSPOT_SECRET.encode("utf-8"), base.encode("utf-8"), hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def _headers(body: bytes, timestamp: str | None = None) -> dict[str, str]:
    ts = timestamp or str(int(time.time() * 1000))
    return {
        "X-HubSpot-Signature-v3": _sign(body, ts),
        "X-HubSpot-Request-Timestamp": ts,
        "Content-Type": "application/json",
    }


def _sample_event(event_id: int = 1001, deal_id: str = "555", owner_id: str = "42") -> dict:
    return {
        "eventId": event_id,
        "subscriptionType": "deal.creation",
        "objectId": int(deal_id),
        "portalId": 12345,
        "occurredAt": 1737000000000,
        "propertyName": None,
        "propertyValue": None,
        "changeSource": "CRM",
        "attemptNumber": 0,
    }


def _sample_deal(deal_id: str = "555", owner_id: str = "42", stage: str = "qualifiedtobuy") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": "Acme Governance Rollout",
            "dealstage": stage,
            "pipeline": "default",
            "hubspot_owner_id": owner_id,
            "engagement_type": "TM",
        },
    }


def _sample_owner(owner_id: str = "42", email: str = "rep@smartek21.com") -> dict:
    return {"id": owner_id, "email": email, "firstName": "Rep", "lastName": "One"}


def _stmt_by_event_id(event_id: str):
    return select(IntegrationEvent).where(IntegrationEvent.source_event_id == event_id)


@pytest_asyncio.fixture
async def wired_app(engine):
    """Bind the FastAPI app to the in-memory session + a stub HubSpot client."""

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    stub = StubHubSpotClient(
        deals={"555": _sample_deal()},
        owners={"42": _sample_owner()},
        companies={},
    )

    def _override_client() -> HubSpotClient:
        return stub

    main_app.dependency_overrides[get_session] = _override_session
    main_app.dependency_overrides[get_hubspot_client] = _override_client
    try:
        yield main_app, factory, stub
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_hubspot_client, None)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_valid_signature_stores_event(wired_app):
    app, factory, _ = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")
    async with _client(app) as c:
        r = await c.post(
            "/integrations/hubspot/webhook",
            content=body,
            headers=_headers(body),
        )
    assert r.status_code == 200
    assert r.json()["stored"] == 1

    async with factory() as s:
        rows = (await s.execute(select(IntegrationEvent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].source_event_id == "1001"
    assert rows[0].processed_at is None  # webhook only enqueues


async def test_invalid_signature_returns_401_and_stores_nothing(wired_app):
    app, factory, _ = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")
    hdrs = _headers(body)
    hdrs["X-HubSpot-Signature-v3"] = "not-a-real-signature"
    async with _client(app) as c:
        r = await c.post("/integrations/hubspot/webhook", content=body, headers=hdrs)
    assert r.status_code == 401

    async with factory() as s:
        rows = (await s.execute(select(IntegrationEvent))).scalars().all()
    assert rows == []


async def test_stale_timestamp_rejected(wired_app):
    app, factory, _ = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")
    # 10 minutes ago — outside the 5-minute skew window.
    stale = str(int((time.time() - 600) * 1000))
    async with _client(app) as c:
        r = await c.post(
            "/integrations/hubspot/webhook",
            content=body,
            headers=_headers(body, timestamp=stale),
        )
    assert r.status_code == 401

    async with factory() as s:
        rows = (await s.execute(select(IntegrationEvent))).scalars().all()
    assert rows == []


async def test_batch_events_all_stored(wired_app):
    app, factory, stub = wired_app
    stub.deals["556"] = _sample_deal(deal_id="556")
    body = json.dumps(
        [_sample_event(event_id=1, deal_id="555"), _sample_event(event_id=2, deal_id="556")]
    ).encode("utf-8")
    async with _client(app) as c:
        r = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
    assert r.status_code == 200
    assert r.json()["stored"] == 2

    async with factory() as s:
        ids = {
            row.source_event_id
            for row in (await s.execute(select(IntegrationEvent))).scalars()
        }
    assert ids == {"1", "2"}


async def test_full_flow_webhook_to_opportunity_task_and_audits(wired_app):
    app, factory, stub = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")

    async with _client(app) as c:
        r = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
    assert r.status_code == 200

    # Simulate the worker draining the queue.
    async with factory() as s:
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
        await handle_event(s, event.payload, stub)

    async with factory() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        tasks = (await s.execute(select(Task))).scalars().all()
        audits = (
            await s.execute(select(AuditEvent).order_by(AuditEvent.ts, AuditEvent.id))
        ).scalars().all()
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()

    assert len(opps) == 1
    assert opps[0].hubspot_deal_id == "555"
    assert opps[0].governance_status == "Intake"
    assert opps[0].sales_stage == "qualifiedtobuy"
    assert opps[0].engagement_type == "TM"

    assert len(tasks) == 1
    assert tasks[0].subject == "Confirm engagement type and next client check-in"
    assert tasks[0].owner_id == opps[0].owner_id
    assert tasks[0].due_date is not None

    actions = [a.action for a in audits]
    assert "opportunity.created" in actions
    assert "task.created" in actions
    # Correlation id ties both audits to the same event.
    corr = {a.correlation_id for a in audits if a.action in {"opportunity.created", "task.created"}}
    assert corr == {"hubspot:1001"}

    assert event.processed_at is not None


async def test_duplicate_event_id_is_idempotent(wired_app):
    """AC #3: same event id twice → one opportunity, one task."""

    app, factory, stub = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")

    async with _client(app) as c:
        r1 = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
        r2 = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
    assert r1.status_code == 200 and r2.status_code == 200
    # Second post is a dedupe hit; nothing new stored.
    assert r2.json()["stored"] == 0
    assert r2.json()["duplicates"] == 1

    async with factory() as s:
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
        await handle_event(s, event.payload, stub)
        # Second processing pass — must be a no-op.
        await handle_event(s, event.payload, stub)

    async with factory() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        tasks = (await s.execute(select(Task))).scalars().all()
    assert len(opps) == 1
    assert len(tasks) == 1


async def test_missing_owner_falls_back_to_sales_leader(wired_app):
    """AC #5: no owner in HubSpot → intake task goes to the Sales leader."""

    app, factory, stub = wired_app
    stub.deals["555"] = {
        "id": "555",
        "properties": {
            "dealname": "Unowned Deal",
            "dealstage": "appointmentscheduled",
            "pipeline": "default",
            "hubspot_owner_id": None,
            "engagement_type": None,
        },
    }

    body = json.dumps([_sample_event()]).encode("utf-8")
    async with _client(app) as c:
        await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))

    async with factory() as s:
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
        await handle_event(s, event.payload, stub)

    async with factory() as s:
        leader = (
            await s.execute(select(User).where(User.email == LEADER_EMAIL))
        ).scalar_one()
        task = (await s.execute(select(Task))).scalar_one()
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert task.owner_id == leader.id
    assert opp.owner_id == leader.id


async def test_owner_present_in_event_but_deleted_in_hubspot(wired_app):
    """Owner id in webhook but HubSpot API 404s → fall back to Sales leader."""

    app, factory, stub = wired_app
    # Empty `owners` -> get_deal_owner raises KeyError (simulates 404).
    stub.owners.pop("42", None)

    body = json.dumps([_sample_event()]).encode("utf-8")
    async with _client(app) as c:
        await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))

    async with factory() as s:
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
        await handle_event(s, event.payload, stub)

    async with factory() as s:
        leader = (
            await s.execute(select(User).where(User.email == LEADER_EMAIL))
        ).scalar_one()
        task = (await s.execute(select(Task))).scalar_one()
    assert task.owner_id == leader.id


async def test_property_change_event_upserts_opportunity(wired_app):
    """`deal.propertyChange` uses the same upsert path."""

    app, factory, stub = wired_app
    change_event = {
        "eventId": 2002,
        "subscriptionType": "deal.propertyChange",
        "objectId": 555,
        "propertyName": "dealstage",
        "propertyValue": "contractsent",
    }
    # First: original creation event to seed the opportunity.
    creation = _sample_event()
    body = json.dumps([creation]).encode("utf-8")
    async with _client(app) as c:
        await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
    async with factory() as s:
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
        await handle_event(s, event.payload, stub)

    # Now the property change with an updated deal stage.
    stub.deals["555"] = _sample_deal(stage="contractsent")
    body2 = json.dumps([change_event]).encode("utf-8")
    async with _client(app) as c:
        await c.post("/integrations/hubspot/webhook", content=body2, headers=_headers(body2))
    async with factory() as s:
        event2 = (
            await s.execute(_stmt_by_event_id("2002"))
        ).scalar_one()
        await handle_event(s, event2.payload, stub)

    async with factory() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        tasks = (await s.execute(select(Task))).scalars().all()
        audits = (await s.execute(select(AuditEvent))).scalars().all()
    assert len(opps) == 1
    assert opps[0].sales_stage == "contractsent"
    # Only one intake task — the update didn't spawn a duplicate.
    assert len(tasks) == 1
    assert any(a.action == "opportunity.updated" for a in audits)


async def test_replay_forbidden_for_non_admin(wired_app, monkeypatch):
    """AC (replay is SystemAdmin only)."""

    app, factory, _ = wired_app
    # Seed an event to replay.
    async with factory() as s:
        s.add(
            IntegrationEvent(
                source="hubspot",
                source_event_id="9999",
                payload=_sample_event(event_id=9999),
            )
        )
        await s.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app) as c:
        r = await c.post(
            "/integrations/hubspot/events/9999/replay",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


async def test_replay_allowed_for_system_admin(wired_app, monkeypatch):
    app, factory, _stub = wired_app
    # Seed an event with `processed_at` already set to prove replay re-runs it.
    async with factory() as s:
        s.add(
            IntegrationEvent(
                source="hubspot",
                source_event_id="7777",
                payload=_sample_event(event_id=7777),
            )
        )
        await s.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.post(
            "/integrations/hubspot/events/7777/replay",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "replayed"

    async with factory() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        audits = (await s.execute(select(AuditEvent))).scalars().all()
    assert len(opps) == 1
    assert any(a.action == "integration_event.replayed" for a in audits)


async def test_missing_signature_headers_return_401(wired_app):
    app, _factory, _ = wired_app
    body = json.dumps([_sample_event()]).encode("utf-8")
    async with _client(app) as c:
        r = await c.post(
            "/integrations/hubspot/webhook",
            content=body,
            headers={"Content-Type": "application/json"},
        )
    assert r.status_code == 401


async def test_worker_process_pending_runs_intake(wired_app):
    """The local worker's poll drains un-processed events."""

    import sys
    from pathlib import Path

    # `worker/` lives one level above `api/` in the repo. Make it importable
    # for this test without touching the top-level conftest.
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from worker import hubspot_intake as worker_mod

    from app.db import session as _db_session_mod

    app, factory, stub = wired_app

    # Rebind the session factory the worker uses to point at the test DB.
    original_factory = _db_session_mod.session_factory
    original_worker_factory = worker_mod.session_factory
    _db_session_mod.session_factory = factory
    worker_mod.session_factory = factory
    try:
        # Seed an event via the webhook path.
        body = json.dumps([_sample_event()]).encode("utf-8")
        async with _client(app) as c:
            await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))

        count = await worker_mod.process_pending(stub)
        assert count == 1
    finally:
        _db_session_mod.session_factory = original_factory
        worker_mod.session_factory = original_worker_factory

    async with factory() as s:
        opps = (await s.execute(select(Opportunity))).scalars().all()
        tasks = (await s.execute(select(Task))).scalars().all()
        event = (
            await s.execute(_stmt_by_event_id("1001"))
        ).scalar_one()
    assert len(opps) == 1
    assert len(tasks) == 1
    assert event.processed_at is not None
