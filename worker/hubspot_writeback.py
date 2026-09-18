"""HubSpot write-back worker (S4-E2 Wave 3).

Drains the ``hubspot_writeback_job`` outbox produced by
:func:`app.services.hubspot_writeback.queue_writeback`. Every 30 seconds it
opens a session, pulls pending jobs and calls
:func:`app.services.hubspot_writeback.process_pending`.

Production replaces the poll loop with an SQS consumer; the service module
does the real work so the transport is easy to swap.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from app.db import session_factory
from app.integrations.hubspot import HubSpotClient
from app.services.hubspot_writeback import process_pending

log = structlog.get_logger("worker.hubspot_writeback")


POLL_INTERVAL_SECONDS = float(
    os.environ.get("HUBSPOT_WRITEBACK_POLL_INTERVAL", "30")
)


async def _drain_forever(client: HubSpotClient | None = None) -> None:
    hubspot = client or HubSpotClient()
    log.info("hubspot_writeback_started", poll_interval=POLL_INTERVAL_SECONDS)
    while True:
        try:
            async with session_factory() as session:
                count = await process_pending(session, hubspot)
            if count:
                log.info("hubspot_writeback_batch_processed", count=count)
        except Exception:  # pragma: no cover - operational log
            log.exception("hubspot_writeback_batch_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(_drain_forever())
    except KeyboardInterrupt:
        log.info("hubspot_writeback_stopped")


if __name__ == "__main__":
    main()


__all__ = ["POLL_INTERVAL_SECONDS", "main"]
