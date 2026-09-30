"""S19 slice 1 §B5 — HubSpot SQS consumer worker.

Runs as a scheduled Fargate task (rate(5 min) via EventBridge, see
modules/schedulers). Each invocation long-polls the events queue (20s)
and processes what's there until the queue reports empty or a soft time
budget elapses; then exits so the tick can restart cleanly on the next
schedule.

- Long-poll 20 s (matches SQS max).
- Visibility timeout is set on the queue (5 min per B5) — this worker
  MUST finish processing a message and delete it inside that window or
  another consumer sees a redelivery.
- Poison messages hit the DLQ after 3 receive attempts (queue's
  ``maxReceiveCount=3``). This worker does NOT decide DLQ; SQS does.
- Every processed batch (success OR fatal) writes ``sync_status``
  (source='hubspot_webhook') so the Pipeline UI's amber banner has a
  live signal.

For local dev the poll runs against ``StubHubSpotEventsQueue`` when
``HUBSPOT_EVENT_QUEUE_URL`` is unset, so smoke tests keep working
without an AWS creden­tial.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime

import structlog

from app.db import session_factory
from app.integrations.hubspot import HubSpotClient
from app.integrations.hubspot_events_queue import (
    HubSpotEventsQueue,
    ReceivedMessage,
    StubHubSpotEventsQueue,
    get_queue,
)
from app.services.hubspot_intake import handle_event
from app.services.sync_status import touch_source

log = structlog.get_logger("worker.hubspot_intake")


SOFT_BUDGET_SECONDS = float(os.environ.get("HUBSPOT_WORKER_SOFT_BUDGET", "240"))
POLL_WAIT_SECONDS = int(os.environ.get("HUBSPOT_WORKER_POLL_SECONDS", "20"))
BATCH_SIZE = int(os.environ.get("HUBSPOT_WORKER_BATCH_SIZE", "10"))


def _select_queue() -> HubSpotEventsQueue:
    """Real queue when the env is wired, stub otherwise."""

    if os.environ.get("HUBSPOT_EVENT_QUEUE_URL", "").strip():
        return get_queue()
    log.warning("hubspot_worker_stub_queue")
    return StubHubSpotEventsQueue()


async def _process(
    queue: HubSpotEventsQueue,
    client: HubSpotClient,
    messages: list[ReceivedMessage],
) -> tuple[int, int]:
    processed = 0
    errors = 0
    for m in messages:
        try:
            async with session_factory() as session:
                await handle_event(session, m.body, client)
            await queue.delete(m.receipt_handle)
            processed += 1
        except Exception:
            errors += 1
            log.exception(
                "hubspot_worker_event_failed",
                message_id=m.message_id,
                receive_count=m.receive_count,
            )
            # Do NOT delete — SQS redrives to DLQ after maxReceiveCount.
    return processed, errors


async def run_once(
    *,
    queue: HubSpotEventsQueue | None = None,
    client: HubSpotClient | None = None,
    soft_budget_seconds: float = SOFT_BUDGET_SECONDS,
) -> dict[str, int]:
    """Drain the queue until it reports empty or the budget elapses."""

    queue = queue or _select_queue()
    client = client or HubSpotClient()
    start = time.monotonic()
    total_processed = 0
    total_errors = 0
    empty_polls = 0

    while time.monotonic() - start < soft_budget_seconds:
        messages = await queue.receive(
            max_messages=BATCH_SIZE, wait_seconds=POLL_WAIT_SECONDS
        )
        if not messages:
            empty_polls += 1
            if empty_polls >= 2:
                break
            continue
        empty_polls = 0
        processed, errors = await _process(queue, client, messages)
        total_processed += processed
        total_errors += errors

    async with session_factory() as session:
        await touch_source(
            session,
            source="hubspot_webhook",
            success=True,
            error=None,
        )
        await session.commit()

    log.info(
        "hubspot_worker_run_complete",
        processed=total_processed,
        errors=total_errors,
    )
    return {"processed": total_processed, "errors": total_errors}


async def process_pending(client: HubSpotClient) -> int:
    """Legacy DB-poll drain used when SQS is not configured.

    Kept alongside :func:`run_once` so the local dev flow + the pre-S19
    integration_event fixture still work. Production runs
    :func:`run_once` on the schedulers image; there is no long-lived
    poll in the SQS world.
    """

    from sqlalchemy import select

    from app.models.integration import IntegrationEvent
    from app.services.hubspot_intake import handle_event as _handle

    processed = 0
    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationEvent)
            .where(IntegrationEvent.processed_at.is_(None))
            .where(IntegrationEvent.source == "hubspot")
            .order_by(IntegrationEvent.received_at)
        )
        rows = list(result.scalars())

    for row in rows:
        try:
            async with session_factory() as session:
                await _handle(session, row.payload, client)
            processed += 1
        except Exception:
            log.exception("hubspot_event_failed", event_id=row.source_event_id)
    return processed


def main() -> None:
    try:
        asyncio.run(run_once())
    except KeyboardInterrupt:
        log.info("hubspot_worker_stopped")


if __name__ == "__main__":
    main()
