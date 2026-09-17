"""Local HubSpot intake worker.

Production replaces this with an SQS consumer. Locally we poll the
`integration_event` table for un-processed rows and hand them to
`services.hubspot_intake.handle_event`.

Run: `python -m worker.hubspot_intake` from the `api/` directory (so the
`app.*` imports resolve).
"""

from __future__ import annotations

import asyncio
import os

import structlog
from sqlalchemy import select

from app.db import session_factory
from app.integrations.hubspot import HubSpotClient
from app.models.integration import IntegrationEvent
from app.services.hubspot_intake import handle_event

log = structlog.get_logger("worker.hubspot_intake")


POLL_INTERVAL_SECONDS = float(os.environ.get("HUBSPOT_WORKER_POLL_INTERVAL", "5"))


async def process_pending(client: HubSpotClient) -> int:
    """Process every un-processed `integration_event` row once. Returns count."""

    processed = 0
    async with session_factory() as session:
        result = await session.execute(
            select(IntegrationEvent)
            .where(IntegrationEvent.processed_at.is_(None))
            .where(IntegrationEvent.source == "hubspot")
            .order_by(IntegrationEvent.received_at)
        )
        rows = list(result.scalars())

    # Handle each event in its own session so a poison message doesn't
    # rollback siblings.
    for row in rows:
        try:
            async with session_factory() as session:
                await handle_event(session, row.payload, client)
            processed += 1
        except Exception:
            log.exception("hubspot_event_failed", event_id=row.source_event_id)
    return processed


async def run_forever(client: HubSpotClient | None = None) -> None:
    client = client or HubSpotClient()
    log.info("worker_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        count = await process_pending(client)
        if count:
            log.info("worker_batch_processed", count=count)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        log.info("worker_stopped")


if __name__ == "__main__":
    main()
