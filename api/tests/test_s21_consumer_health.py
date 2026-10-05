"""OP-01 consumer liveness is distinct from business freshness (unit faults)."""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from structlog.testing import capture_logs

from app.integrations.hubspot import StubHubSpotClient
from app.integrations.hubspot_events_queue import StubHubSpotEventsQueue
from app.models.sync_status import SyncStatus
from worker import hubspot_intake as worker


@pytest.mark.asyncio
async def test_quiet_continuous_consumer_stays_alive_without_inventing_processed_watermark(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "session_factory", factory)

    class QuietQueue(StubHubSpotEventsQueue):
        polls = 0
        async def receive(self, **kwargs):
            self.polls += 1
            await asyncio.sleep(0.01)
            return []

    queue = QuietQueue()
    with capture_logs() as logs:
        result = await worker.run_once(queue=queue, client=StubHubSpotClient(), soft_budget_seconds=1, continuous=True)
    assert queue.polls > 2 and result == {"processed": 0, "errors": 0}
    assert any(row["event"] == "hubspot_worker_heartbeat" for row in logs)
    async with factory() as session:
        heartbeat = await session.get(SyncStatus, "hubspot_consumer")
        assert heartbeat and heartbeat.last_success_at
        assert heartbeat.processed_at is None
        assert await session.get(SyncStatus, "hubspot_webhook_processed") is None


@pytest.mark.asyncio
async def test_poison_processing_does_not_emit_healthy_heartbeat(engine, monkeypatch):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "session_factory", factory)
    queue = StubHubSpotEventsQueue()
    queue.inbox = [{"eventId": "unit-poison"}]
    async def failed_handler(*args):
        raise ValueError("Injected handler failure")
    monkeypatch.setattr(worker, "handle_event", failed_handler)
    with capture_logs() as logs:
        result = await worker.run_once(queue=queue, client=StubHubSpotClient(), soft_budget_seconds=1, continuous=False)
    assert result["errors"] == 1 and queue.deleted == []
    assert not any(row["event"] == "hubspot_worker_heartbeat" for row in logs)
    async with factory() as session:
        status = await session.get(SyncStatus, "hubspot_consumer")
        assert status.last_error and status.last_success_at is None


def test_deployed_consumer_cannot_silently_select_stub_queue(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.delenv("HUBSPOT_EVENT_QUEUE_URL", raising=False)
    with pytest.raises(RuntimeError, match="HUBSPOT_EVENT_QUEUE_URL"):
        worker._select_queue()
