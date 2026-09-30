#!/usr/bin/env python3
"""S20 T32 · inject synthetic HubSpot-shape events for freshness testing.

Pushes N events onto the staging queue with the `s20-` marker (so
`worker/e2e_cleanup.py::_PREFIX_RE` can reap them 24 h later per
isolation §7). Each event carries a unique `hubspot_source_event_id`
so W1's dedupe key (D7) can be exercised alongside freshness (T32).

Usage:
    python3 scripts/inject-events.py --n 15
    python3 scripts/inject-events.py --n 1 --after-tick   # injects after
    the scheduled worker window closes (proves L20 fix under D4).

Environment:
    AWS_PROFILE_STAGING (default: lm-arbiter-poc)
    STAGING_QUEUE_URL   (default: read from Terraform outputs)

Isolation:
    Isolation §Resource inventory row 2 confirms this points at the
    `officeapp-dev-hubspot-events` queue. There is no prod-prefixed
    queue on this account, so a misconfigured URL fails visibly rather
    than writing to production.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime

DEFAULT_QUEUE_URL = os.environ.get(
    "STAGING_QUEUE_URL",
    "https://sqs.us-east-2.amazonaws.com/669810405473/officeapp-dev-hubspot-events",
)
PROFILE = os.environ.get("AWS_PROFILE_STAGING", "lm-arbiter-poc")
REGION = os.environ.get("STAGING_E2E_REGION", "us-east-2")

# Fixture marker per isolation §7 — the reaper deletes rows whose name
# matches `_PREFIX_RE`. Every payload uses this marker so a botched run
# does not leak into real dashboards.
S20_MARKER = "s20-injection"


def event_payload(idx: int, batch_id: str) -> dict:
    """Build a HubSpot-webhook-shaped envelope with a stable dedupe key."""
    now = datetime.now(tz=UTC)
    return {
        "eventId": f"{batch_id}-{idx:04d}",
        "subscriptionType": "deal.propertyChange",
        "objectId": 999_000_000 + idx,
        "occurredAt": int(now.timestamp() * 1000),
        "portalId": 12345678,
        "propertyName": "dealname",
        "propertyValue": f"{S20_MARKER} synthetic {batch_id} #{idx}",
        # W1's dedupe key (D7) — the same value under two SQS messages
        # must produce exactly one business effect.
        "hubspot_source_event_id": f"{batch_id}-{idx:04d}",
        "test_marker": S20_MARKER,
    }


def send_event(queue_url: str, payload: dict) -> None:
    subprocess.run(
        [
            "aws",
            "--profile",
            PROFILE,
            "--region",
            REGION,
            "sqs",
            "send-message",
            "--queue-url",
            queue_url,
            "--message-body",
            json.dumps(payload),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=15, help="events to inject (default: 15)")
    parser.add_argument(
        "--after-tick",
        action="store_true",
        help="sleep 60s first, so the burst lands right after a scheduled tick "
        "(demonstrates that scheduled-mode would delay these; continuous mode "
        "picks them up immediately).",
    )
    parser.add_argument(
        "--queue-url",
        default=DEFAULT_QUEUE_URL,
        help=f"SQS queue URL (default: {DEFAULT_QUEUE_URL})",
    )
    args = parser.parse_args()

    if "officeapp-dev" not in args.queue_url:
        print(
            f"REFUSED: queue url does not contain 'officeapp-dev': {args.queue_url}",
            file=sys.stderr,
        )
        return 2

    if args.after_tick:
        print("sleeping 60s to land after scheduled tick window...")
        time.sleep(60)

    batch_id = uuid.uuid4().hex[:8]
    print(f"injecting {args.n} events with batch_id={batch_id} marker='{S20_MARKER}'")
    started = datetime.now(tz=UTC)
    for i in range(args.n):
        send_event(args.queue_url, event_payload(i, batch_id))
    finished = datetime.now(tz=UTC)
    print(
        f"done: {args.n} events sent in {(finished - started).total_seconds():.2f}s "
        f"(batch_id={batch_id})"
    )
    print(
        "next: watch `hubspot_webhook_processed` watermark advance past "
        f"{finished.isoformat()} (T32)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
