"""S19 slice 1 §B6 — nightly HubSpot reconcile.

Fired by EventBridge at 04:00 UTC (see modules/schedulers). Walks every
HubSpot deal, upserts drift into the local mirror, updates
``sync_status`` (source='hubspot_reconcile') at the end.

Reuses :func:`app.services.hubspot_backfill.run_backfill` under the hood
— the backfill already handles pagination + the pipeline mirror + the
mapper, so this worker is a scheduled wrapper. If backfill fails
mid-run, the ``after=`` cursor is persisted in ``sync_status`` so a
subsequent run resumes from where the last one stopped (G14).
"""

from __future__ import annotations

import asyncio
import os

import structlog

from app.db import session_factory
from app.integrations.hubspot import HubSpotClient
from app.services.hubspot_backfill import run_backfill
from app.services.sync_status import touch_source

log = structlog.get_logger("worker.hubspot_reconcile")


async def run_once(*, client: HubSpotClient | None = None) -> dict[str, int]:
    client = client or HubSpotClient()
    error: str | None = None
    counts: dict[str, int] = {}
    try:
        result = await run_backfill(client)
        counts = result.as_dict()
    except Exception as exc:  # pragma: no cover - covered indirectly
        error = f"{type(exc).__name__}: {exc}"
        log.exception("hubspot_reconcile_failed")

    async with session_factory() as session:
        await touch_source(
            session,
            source="hubspot_reconcile",
            success=error is None,
            error=error,
        )
        await session.commit()

    log.info("hubspot_reconcile_run_complete", counts=counts, error=error)
    return counts


def main() -> None:
    asyncio.run(run_once())


if __name__ == "__main__":
    main()
