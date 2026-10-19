"""Drain tenant-scoped persisted SOW object cleanup jobs.

S24-AG1 B7: after the cleanup, resume any agreement batch (attach or undo) whose job died with the API task
(heartbeat older than about two minutes). That step is isolated: it never changes the cleanup's outcome and
never fails this run.
"""

import asyncio
import json

from app.db import session_factory
from app.services.deletion_cleanup import process_deletion_jobs


async def resume_agreement_batches(factory=None) -> None:
    """Never raises: a batch problem is recorded on the batch, and anything else is printed and skipped."""
    try:
        from app.services.agreement_batches import resume_stale

        resumed = await resume_stale(factory or session_factory)
        print(json.dumps({"worker": "agreement_batches", "resumed": resumed}))
    except Exception as exc:  # noqa: BLE001 — must never fail the deletion run
        print(json.dumps({"worker": "agreement_batches", "error": type(exc).__name__}))


async def main():
    try:
        async with session_factory() as session:
            handled = await process_deletion_jobs(session)
        print(json.dumps({"worker": "deletion_cleanup", "handled": handled}))
    finally:
        await resume_agreement_batches()


if __name__ == "__main__":
    asyncio.run(main())
