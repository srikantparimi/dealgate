"""S19 slice 1 §B4 + §B5: SQS webhook + consumer round-trip.

The webhook path enqueues to SQS when HUBSPOT_EVENT_QUEUE_URL is set,
falls back to the legacy DB store otherwise. The consumer worker
drains queued events, hands each to the same handle_event as the
legacy path, and deletes from the queue on success.

Uses the StubHubSpotEventsQueue so nothing touches AWS.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from app.integrations.hubspot import StubHubSpotClient
from app.integrations.hubspot_events_queue import (
    StubHubSpotEventsQueue,
    get_queue,
)
from app.main import app
from app.services.sync_status import touch_source


SECRET = "unit-test-secret"


def _sign(method: str, uri: str, body: bytes, timestamp: str, secret: str = SECRET) -> str:
    base = f"{method}{uri}{body.decode('utf-8')}{timestamp}"
    digest = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


@pytest_asyncio.fixture
async def http(engine, monkeypatch):
    monkeypatch.setenv("HUBSPOT_APP_SECRET", SECRET)
    monkeypatch.setenv("HUBSPOT_EVENT_QUEUE_URL", "https://sqs.us-east-2.amazonaws.com/x/y")

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    from app.db import get_session

    async def _session():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _session

    stub = StubHubSpotEventsQueue()
    app.dependency_overrides[get_queue] = lambda: stub

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        client.app_stub = stub  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_enqueues_when_queue_url_set(http):
    body = b'[{"eventId": 42, "subscriptionType": "deal.creation", "objectId": "1"}]'
    ts = "1737000000000"
    uri = "http://testserver/integrations/hubspot/webhook"
    sig = _sign("POST", uri, body, ts)

    # Freeze the replay-defense clock so a stale-looking timestamp still passes.
    import time as _time

    orig = _time.time
    _time.time = lambda: 1737000000.0
    try:
        r = await http.post(
            "/integrations/hubspot/webhook",
            content=body,
            headers={
                "X-HubSpot-Signature-v3": sig,
                "X-HubSpot-Request-Timestamp": ts,
                "Content-Type": "application/json",
            },
        )
    finally:
        _time.time = orig

    assert r.status_code == 200, r.text
    result = r.json()
    assert result["received"] == 1
    assert result["queued"] == 1
    assert http.app_stub.sent == [
        {"eventId": 42, "subscriptionType": "deal.creation", "objectId": "1"}
    ]


@pytest.mark.asyncio
async def test_consumer_drains_stub_queue_and_writes_sync_status(engine, monkeypatch):
    from worker.hubspot_intake import run_once

    monkeypatch.setenv("HUBSPOT_EVENT_QUEUE_URL", "https://sqs.local/x/y")

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Redirect session_factory used by the worker to point at the test DB.
    import app.db as _db

    monkeypatch.setattr(_db, "session_factory", factory)
    import worker.hubspot_intake as intake

    monkeypatch.setattr(intake, "session_factory", factory)

    stub = StubHubSpotEventsQueue()
    # Empty inbox — the worker should still complete cleanly and write
    # a healthy sync_status row after two empty polls.
    client = StubHubSpotClient()

    result = await run_once(queue=stub, client=client, soft_budget_seconds=1.0)
    assert result["errors"] == 0
    assert result["processed"] == 0
    # sync_status row landed for hubspot_webhook.
    from app.models.sync_status import SyncStatus

    async with factory() as session:
        row = await session.get(SyncStatus, "hubspot_webhook")
        assert row is not None
        assert row.last_success_at is not None
        assert row.last_error is None
        assert row.lag_seconds == 0


@pytest.mark.asyncio
async def test_touch_source_records_error_without_clobbering_success(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        row = await touch_source(session, source="probe", success=True, error=None)
        assert row.last_success_at is not None
        assert row.last_error is None
        first_success = row.last_success_at
        await session.commit()

    async with factory() as session:
        row = await touch_source(
            session, source="probe", success=False, error="boom"
        )
        assert row.last_error == "boom"
        # SQLite drops tz info on the DateTime round-trip; compare after
        # normalising to naive.
        assert row.last_success_at.replace(tzinfo=None) == first_success.replace(tzinfo=None)
        assert row.lag_seconds is not None and row.lag_seconds >= 0
        await session.commit()
