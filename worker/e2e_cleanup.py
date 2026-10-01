"""Nightly e2e/smoke data cleanup for dev + staging.

S17 addendum: e2e and smoke runs must never leave data in Kanna's lists.
Playwright specs and scripts/deploy-smoke.sh delete their own tags in
teardown, but if a run crashes the residue survives. This worker sweeps
any client whose ``legal_name`` matches the run-tag prefix set below AND
is older than 24 hours, and hard-deletes it through
:func:`app.services.deletion.delete_client` so every dependent SOW,
package, task and file goes with it.

Run pattern (mirrors worker/alert_scheduler.py + worker/notification_sender.py):

    python -m worker.e2e_cleanup

Triggered hourly by an EventBridge rule (see
`infra-tf/modules/schedulers/main.tf`). No-op outside dev/staging.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.db import session_factory
from app.models.client import Client
from app.services.deletion import delete_client

log = logging.getLogger("dealgate.worker.e2e_cleanup")

# Names that scream "test data, delete me".
_PREFIX_RE = re.compile(
    r"^(?:s1[2-9]-|s17-|S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |"
    r"S20 e2e |S21 e2e |"
    r"smoke |Peppermill Casino \(smoke fixture\)|S17 delete-everywhere|"
    r"S17 e2e |Peppermill Casino's, LLC)",
    re.IGNORECASE,
)
# Everything created before this cutoff is eligible; hourly ticks keep
# the tail short without racing an in-flight test run.
#
# S21-1d: minimum age is overridable via `E2E_MIN_AGE_HOURS` so a
# one-off run can sweep rows younger than 24h (0 = sweep everything
# that matches the prefix, regardless of age). The default stays at
# 24h for the scheduled nightly tick.
def _min_age() -> timedelta:
    raw = os.environ.get("E2E_MIN_AGE_HOURS")
    if raw is None:
        return timedelta(hours=24)
    try:
        hours = float(raw)
    except ValueError:
        log.warning("e2e_cleanup_invalid_min_age_hours", extra={"value": raw})
        return timedelta(hours=24)
    return timedelta(hours=max(hours, 0))


async def run_tick() -> dict[str, int]:
    """Delete every stale test client. Returns counts by kind."""

    counts: dict[str, int] = {"clients": 0, "sows": 0, "opportunities": 0, "agreements": 0}
    if os.environ.get("DEALGATE_ENV", "local") not in {"dev", "staging"}:
        log.info("e2e_cleanup_skipped_env")
        return counts

    async with session_factory() as session:
        cutoff = datetime.now(UTC) - _min_age()
        candidates = list(
            (
                await session.execute(
                    select(Client).where(
                        or_(
                            Client.created_at < cutoff,
                            Client.created_at.is_(None),
                        )
                    )
                )
            ).scalars()
        )
        for client in candidates:
            if not _PREFIX_RE.match(client.name or ""):
                continue
            log.info(
                "e2e_cleanup_delete",
                extra={"client_id": str(client.id), "client_name": client.name},
            )
            summary = await delete_client(session, actor_id=None, client_id=client.id)
            counts["clients"] += 1
            counts["sows"] += summary.counts.get("sows", 0)
            counts["opportunities"] += summary.counts.get("opportunities", 0)
            counts["agreements"] += summary.counts.get("agreements", 0)
        await session.commit()
    log.info("e2e_cleanup_done", extra=counts)
    return counts


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    counts = asyncio.run(run_tick())
    print(f"e2e_cleanup: {counts}")


if __name__ == "__main__":
    main()
