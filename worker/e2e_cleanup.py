"""Reviewable trusted-fixture cleanup; dry-run unless explicitly applied."""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import os
import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from app.db import session_factory
from app.services.deletion import delete_client
from app.services.fixture_cleanup import cleanup_manifest

log = logging.getLogger("dealgate.worker.e2e_cleanup")

# Legacy diagnostic compatibility only. Names NEVER select cleanup targets.
_PREFIX_RE = re.compile(
    r"^(?:s1[2-9]-|s17-|S1[2-9] e2e |S14b e2e |S16a e2e |S13a e2e |"
    r"S20 e2e |S21 e2e |"
    r"smoke |Peppermill Casino \(smoke fixture\)|S17 delete-everywhere|"
    r"S17 e2e |Peppermill Casino's, LLC)",
    re.IGNORECASE,
)
def _min_age(*, run_id=None, owner_id=None) -> timedelta:
    raw = os.environ.get("E2E_MIN_AGE_HOURS", "24")
    try:
        hours = Decimal(raw)
        if not hours.is_finite() or hours < 0:
            raise ValueError("Cleanup minimum age must be finite and nonnegative")
        if hours == 0 and not (run_id and owner_id):
            raise ValueError("Zero-age cleanup requires an exact run and owner")
        return timedelta(microseconds=int(hours * 3600000000))
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError("Invalid cleanup minimum age") from exc


async def run_tick(*, apply=False, run_id=None, owner_id=None) -> dict:
    """Produce a manifest, then revalidate each explicit apply target under locks."""
    age = _min_age(run_id=run_id, owner_id=owner_id)
    counts: dict[str, int] = {"clients": 0, "sows": 0, "opportunities": 0, "agreements": 0}
    async with session_factory() as session:
        targets = await cleanup_manifest(session, min_age=age, run_id=run_id, owner_id=owner_id)
        if not apply:
            return {"dry_run": True, "targets": targets, "deleted": counts}
        for target in targets:
            checked = await cleanup_manifest(session, min_age=age, run_id=target["run_id"],
                owner_id=target["owner_id"], lock=True)
            if not any(row["client_id"] == target["client_id"] for row in checked):
                continue
            summary = await delete_client(session, actor_id=uuid.UUID(target["owner_id"]),
                client_id=uuid.UUID(target["client_id"]))
            counts["clients"] += 1
            counts["sows"] += summary.counts.get("sows", 0)
            counts["opportunities"] += summary.counts.get("opportunities", 0)
            counts["agreements"] += summary.counts.get("agreements", 0)
        await session.commit()
    log.info("e2e_cleanup_done", extra=counts)
    return {"dry_run": False, "targets": targets, "deleted": counts}


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--run-id", type=uuid.UUID)
    parser.add_argument("--owner-id", type=uuid.UUID)
    args = parser.parse_args()
    result = asyncio.run(run_tick(apply=args.apply, run_id=args.run_id, owner_id=args.owner_id))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
