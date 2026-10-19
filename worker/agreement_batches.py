"""S24-AG1 B7 — run or resume the agreement batch jobs from a shell (no API needed).

The API runs a batch (and an undo) as a background task and the every-minute deletion-cleanup worker resumes
one whose task died. This command does the same work on demand:

    python -m worker.agreement_batches resume            # every running/undoing batch with a stale heartbeat
    python -m worker.agreement_batches run AG-0001       # continue AG-0001 now (running or undoing)
    python -m worker.agreement_batches status [AG-0001]  # print the batch(es); read-only

Re-running is always safe: each chunk locks the batch row, re-reads its cursor, and skips a client that already
holds the kind, so no row is ever attached twice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def _run(argv: list[str]) -> int:
    from app.db import session_factory
    from app.services import agreement_batches

    parser = argparse.ArgumentParser(prog="python -m worker.agreement_batches")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("resume", help="continue every running or undoing batch whose heartbeat is stale")
    run = sub.add_parser("run", help="continue one running or undoing batch now, whatever its heartbeat")
    run.add_argument("label")
    status = sub.add_parser("status", help="print the batches (read-only)")
    status.add_argument("label", nargs="?")
    args = parser.parse_args(argv)

    if args.command == "status":
        async with session_factory() as session:
            label = args.label.strip().upper() if args.label else None
            items = await agreement_batches.batch_payloads(session, label=label)
        print(json.dumps({"worker": "agreement_batches", "batches": items}, default=str))
        return 0 if items or not args.label else 1
    if args.command == "run":
        results = await agreement_batches.resume_stale(session_factory, label=args.label.strip().upper())
        print(json.dumps({"worker": "agreement_batches", "resumed": results}))
        return 0 if results else 1
    results = await agreement_batches.resume_stale(session_factory)
    print(json.dumps({"worker": "agreement_batches", "resumed": results}))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_run(list(sys.argv[1:] if argv is None else argv)))


if __name__ == "__main__":
    raise SystemExit(main())
