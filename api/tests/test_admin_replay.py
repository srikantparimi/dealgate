"""Admin replay endpoints (S6).

Covers every Given/When/Then in `docs/backlog/s6-admin-replay.md`:

- Non-SystemAdmin -> 403 on every endpoint.
- Failed hubspot writeback listed; replay resets to pending, worker runs,
  audit ``hubspot_write.replayed`` fires and (given a healthy stub) the
  status transitions to ``sent``.
- Failed notification replay resets to pending + audit fires.
- Stuck integration_event listed; replay calls ``handle_event``.
- Successful replay of a job that succeeds -> status transitions correctly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import verify_chain
from app.db import get_session
from app.integrations.hubspot import HubSpotClient, StubHubSpotClient, get_hubspot_client
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.integration import IntegrationEvent
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.user import User

# Scheduler ledger side-import so create_all sees every table when this
# file is run in isolation.
from app.scheduler.ledger import SchedulerFired  # noqa: F401
from app.services.hubspot_writeback import (
    MAX_ATTEMPTS as HUBSPOT_MAX_ATTEMPTS,
)
from app.services.hubspot_writeback import (
    STATUS_FAILED as HUBSPOT_STATUS_FAILED,
)
from app.services.hubspot_writeback import (
    STATUS_PENDING as HUBSPOT_STATUS_PENDING,
)
from app.services.hubspot_writeback import (
    STATUS_SENT as HUBSPOT_STATUS_SENT,
)
from app.services.notifications import (
    MAX_ATTEMPTS as NOTIF_MAX_ATTEMPTS,
)
from app.services.notifications import (
    STATUS_FAILED as NOTIF_STATUS_FAILED,
)
from app.services.notifications import (
    STATUS_PENDING as NOTIF_STATUS_PENDING,
)

DEAL_ID = "7777"
LEADER_EMAIL = "sales-leader@smartek21.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("SALES_LEADER_EMAIL", LEADER_EMAIL)
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _sample_event(event_id: int = 1001, deal_id: str = DEAL_ID) -> dict:
    return {
        "eventId": event_id,
        "subscriptionType": "deal.creation",
        "objectId": int(deal_id),
        "portalId": 12345,
        "occurredAt": 1737000000000,
    }


def _sample_deal(deal_id: str = DEAL_ID, owner_id: str = "42") -> dict:
    return {
        "id": deal_id,
        "properties": {
            "dealname": "Replay Fixture Deal",
            "dealstage": "qualifiedtobuy",
            "pipeline": "default",
            "hubspot_owner_id": owner_id,
            "engagement_type": "TM",
        },
    }


def _sample_owner(owner_id: str = "42") -> dict:
    return {"id": owner_id, "email": "rep@smartek21.com", "firstName": "Rep", "lastName": "One"}


@pytest_asyncio.fixture
async def wired_app(engine):
    """Bind the FastAPI app to a shared in-memory session + stub HubSpot."""

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    stub = StubHubSpotClient(
        deals={DEAL_ID: _sample_deal()},
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


@pytest_asyncio.fixture
async def opportunity(wired_app):
    _, factory, _ = wired_app
    async with factory() as s:
        owner = User(
            id=_uid("owner@smartek21.com"),
            email="owner@smartek21.com",
            name="Owner",
            groups=["Sales"],
        )
        s.add(owner)
        await s.flush()
        opp = Opportunity(
            hubspot_deal_id=DEAL_ID,
            owner_id=owner.id,
            governance_status="Intake",
        )
        s.add(opp)
        await s.commit()
        await s.refresh(opp)
        return opp


# --- permission gates (403 for non-SystemAdmin) -------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/admin/replay/hubspot-writeback"),
        (
            "POST",
            f"/admin/replay/hubspot-writeback/{uuid.uuid4()}",
        ),
        ("GET", "/admin/replay/notifications"),
        (
            "POST",
            f"/admin/replay/notifications/{uuid.uuid4()}",
        ),
        ("GET", "/admin/replay/integration-events"),
        (
            "POST",
            f"/admin/replay/integration-events/{uuid.uuid4()}",
        ),
    ],
)
async def test_non_admin_gets_403(wired_app, monkeypatch, method, path):
    app, _factory, _ = wired_app
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app) as c:
        r = await c.request(
            method, path, headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 403


async def test_requires_auth(wired_app):
    app, _factory, _ = wired_app
    async with _client(app) as c:
        r = await c.get("/admin/replay/hubspot-writeback")
    assert r.status_code == 401


# --- HubSpot writeback listing + replay ---------------------------------


async def _seed_failed_writeback(
    factory: async_sessionmaker[AsyncSession], opportunity: Opportunity
) -> HubspotWritebackJob:
    async with factory() as s:
        job = HubspotWritebackJob(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
            hubspot_deal_id=opportunity.hubspot_deal_id,
            target_state={"governance_status": "Ready to Sign"},
            status=HUBSPOT_STATUS_FAILED,
            attempts=HUBSPOT_MAX_ATTEMPTS,
            last_error="boom",
        )
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def test_failed_writeback_is_listed(wired_app, opportunity, monkeypatch):
    app, factory, _ = wired_app
    job = await _seed_failed_writeback(factory, opportunity)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.get(
            "/admin/replay/hubspot-writeback",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(job.id)
    assert body["items"][0]["status"] == HUBSPOT_STATUS_FAILED
    assert body["items"][0]["last_error"] == "boom"


async def test_replay_writeback_resets_and_reaches_sent(
    wired_app, opportunity, monkeypatch
):
    app, factory, stub = wired_app
    job = await _seed_failed_writeback(factory, opportunity)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.post(
            f"/admin/replay/hubspot-writeback/{job.id}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()

    # The stub HubSpot client accepts the write; the delegated
    # process_pending run must have transitioned the row to `sent`.
    assert body["status"] == HUBSPOT_STATUS_SENT
    assert stub.updates == [
        {
            "deal_id": DEAL_ID,
            "properties": {"dealgate_governance_status": "Ready to Sign"},
        }
    ]

    async with factory() as s:
        fresh = (
            await s.execute(
                select(HubspotWritebackJob).where(HubspotWritebackJob.id == job.id)
            )
        ).scalar_one()
        assert fresh.status == HUBSPOT_STATUS_SENT
        assert fresh.attempts == 1  # reset to 0, then bumped by the send.
        assert fresh.sent_at is not None
        assert fresh.last_error is None

        audits = (
            await s.execute(
                select(AuditEvent)
                .where(AuditEvent.entity == "hubspot_writeback_job")
                .where(AuditEvent.entity_id == str(job.id))
                .order_by(AuditEvent.ts, AuditEvent.id)
            )
        ).scalars().all()
        actions = [a.action for a in audits]
        assert "hubspot_write.replayed" in actions
        # And the worker path's own sent audit lands after the replay row.
        assert actions.index("hubspot_write.replayed") < actions.index(
            "hubspot_write.sent"
        )
        replayed = [a for a in audits if a.action == "hubspot_write.replayed"][0]
        assert replayed.actor_id == _uid("admin@smartek21.com")
        assert replayed.before == {
            "status": HUBSPOT_STATUS_FAILED,
            "attempts": HUBSPOT_MAX_ATTEMPTS,
            "last_error": "boom",
        }
        assert await verify_chain(s) is True


async def test_replay_writeback_that_fails_leaves_row_in_pending(
    wired_app, opportunity, monkeypatch
):
    """Regression: if the stub HubSpot 500s on the replay, the row lands
    back in a mid-lifecycle state (pending with a scheduled retry) and the
    replay audit still fires."""

    app, factory, stub = wired_app
    job = await _seed_failed_writeback(factory, opportunity)

    # Force the delegated process_pending to hit a 500.
    req = httpx.Request("PATCH", "http://stub/crm/v3/objects/deals/" + DEAL_ID)
    stub.update_error = httpx.HTTPStatusError(
        "500", request=req, response=httpx.Response(500, request=req)
    )

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.post(
            f"/admin/replay/hubspot-writeback/{job.id}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    # After the failed dispatch, the row goes back through _mark_retry_or_fail
    # which restores pending (attempts == 1 < MAX_ATTEMPTS).
    async with factory() as s:
        fresh = (
            await s.execute(
                select(HubspotWritebackJob).where(HubspotWritebackJob.id == job.id)
            )
        ).scalar_one()
        assert fresh.status == HUBSPOT_STATUS_PENDING
        assert fresh.attempts == 1
        assert fresh.last_error and "500" in fresh.last_error
        audits = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "hubspot_write.replayed")
            )
        ).scalars().all()
        assert len(audits) == 1


# --- Notifications listing + replay -------------------------------------


async def _seed_user(factory) -> User:
    async with factory() as s:
        u = User(
            id=_uid("recipient@smartek21.com"),
            email="recipient@smartek21.com",
            name="Recipient",
            groups=["Sales"],
        )
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def _seed_failed_notification(factory) -> Notification:
    user = await _seed_user(factory)
    async with factory() as s:
        row = Notification(
            id=uuid.uuid4(),
            user_id=user.id,
            category="task_assigned",
            channel="email",
            subject="Broken thing",
            body_md="body",
            status=NOTIF_STATUS_FAILED,
            attempts=NOTIF_MAX_ATTEMPTS,
            last_error="smtp down",
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def test_failed_notification_is_listed(wired_app, monkeypatch):
    app, factory, _ = wired_app
    row = await _seed_failed_notification(factory)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.get(
            "/admin/replay/notifications",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(row.id)
    assert body["items"][0]["status"] == NOTIF_STATUS_FAILED
    assert body["items"][0]["last_error"] == "smtp down"


async def test_replay_notification_resets_row_and_audits(wired_app, monkeypatch):
    app, factory, _ = wired_app
    row = await _seed_failed_notification(factory)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.post(
            f"/admin/replay/notifications/{row.id}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == NOTIF_STATUS_PENDING

    async with factory() as s:
        fresh = (
            await s.execute(select(Notification).where(Notification.id == row.id))
        ).scalar_one()
        assert fresh.status == NOTIF_STATUS_PENDING
        assert fresh.attempts == 0
        assert fresh.next_attempt_at is not None
        assert fresh.last_error is None

        audits = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.entity == "notification")
                .where(AuditEvent.entity_id == str(row.id))
            )
        ).scalars().all()
        replayed = [a for a in audits if a.action == "notification.replayed"]
        assert len(replayed) == 1
        assert replayed[0].actor_id == _uid("admin@smartek21.com")
        assert replayed[0].before == {
            "status": NOTIF_STATUS_FAILED,
            "attempts": NOTIF_MAX_ATTEMPTS,
            "last_error": "smtp down",
        }
        assert await verify_chain(s) is True


# --- Integration events listing + replay --------------------------------


async def _seed_stuck_event(factory) -> IntegrationEvent:
    async with factory() as s:
        row = IntegrationEvent(
            id=uuid.uuid4(),
            source="hubspot",
            source_event_id="9999",
            payload=_sample_event(event_id=9999),
            received_at=datetime.now(UTC) - timedelta(hours=1),
        )
        s.add(row)
        await s.commit()
        await s.refresh(row)
        return row


async def test_stuck_integration_event_listed_and_young_events_hidden(
    wired_app, monkeypatch
):
    app, factory, _ = wired_app
    stuck = await _seed_stuck_event(factory)

    # A second, brand-new row must NOT surface — only rows > 15m old.
    async with factory() as s:
        fresh = IntegrationEvent(
            id=uuid.uuid4(),
            source="hubspot",
            source_event_id="10000",
            payload=_sample_event(event_id=10000),
        )
        s.add(fresh)
        await s.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.get(
            "/admin/replay/integration-events",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(stuck.id)


async def test_replay_integration_event_runs_handle_event(wired_app, monkeypatch):
    app, factory, _stub = wired_app
    row = await _seed_stuck_event(factory)

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app) as c:
        r = await c.post(
            f"/admin/replay/integration-events/{row.id}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    assert r.json()["status"] == "processed"

    async with factory() as s:
        fresh = (
            await s.execute(
                select(IntegrationEvent).where(IntegrationEvent.id == row.id)
            )
        ).scalar_one()
        assert fresh.processed_at is not None

        opps = (await s.execute(select(Opportunity))).scalars().all()
        assert len(opps) == 1
        assert opps[0].hubspot_deal_id == DEAL_ID

        audits = (await s.execute(select(AuditEvent))).scalars().all()
        actions = [a.action for a in audits]
        assert "integration_event.replayed" in actions
        assert "opportunity.created" in actions
        replayed = [a for a in audits if a.action == "integration_event.replayed"][0]
        assert replayed.actor_id == _uid("admin@smartek21.com")
        assert await verify_chain(s) is True


async def test_replay_missing_ids_return_404(wired_app, monkeypatch):
    app, _factory, _ = wired_app
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    missing = uuid.uuid4()
    async with _client(app) as c:
        r1 = await c.post(
            f"/admin/replay/hubspot-writeback/{missing}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
        r2 = await c.post(
            f"/admin/replay/notifications/{missing}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
        r3 = await c.post(
            f"/admin/replay/integration-events/{missing}",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r1.status_code == 404
    assert r2.status_code == 404
    assert r3.status_code == 404
