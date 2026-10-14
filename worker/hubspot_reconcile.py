"""S19 slice 1 §B6 — nightly HubSpot reconcile.

Fired by EventBridge at 04:00 UTC (see modules/schedulers). Walks every
HubSpot deal and upserts drift into the local mirror through
:func:`app.services.hubspot_backfill.run_backfill`, which resumes from the
persisted page cursor if an earlier run stopped part-way (G14).

S23-PL1 — the run fails loudly (item 3):

- every run writes one ``hubspot_sync_run`` row (ok / partial / failed) via
  :func:`app.services.hubspot_sync_runs.run_deal_sync`;
- a failed run exits non-zero, so the ECS task shows failed; a partial run
  (deals written, some records refused) exits 0 and logs at error level with
  the HubSpot ids it could not write;
- nothing logs or records success unless the run succeeded.

``--test-failure`` starts a **test** run (kind ``test``) whose HubSpot client
fails on the first call: it reads nothing, writes no deal, records a failed run
and exits 1. It exists to prove the failure path on a deployed environment
without touching production data.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.integrations.hubspot import HubSpotClient
from app.services.hubspot_sync_runs import SyncRunOutcome, run_deal_sync

log = structlog.get_logger("worker.hubspot_reconcile")


class InjectedSyncFailure(RuntimeError):
    """Raised by the test-run client on its first HubSpot call."""


class _InjectedFailureClient(HubSpotClient):
    """A client that never reaches HubSpot and never reads a credential."""

    def __init__(self) -> None:  # deliberately skips HubSpotClient.__init__
        self._token = ""
        self._base_url = "http://injected-failure.invalid"

    def scan_scope(self) -> dict[str, str]:
        raise InjectedSyncFailure("test run")

    async def _get(self, path, params=None):
        raise InjectedSyncFailure("test run")

    async def list_pipelines(self):
        raise InjectedSyncFailure("test run")

    async def list_deals_page(self, *, after=None, limit=100, additional_properties=()):
        raise InjectedSyncFailure("test run")


async def run_once(*, client: HubSpotClient | None = None,
                   test_failure: bool = False) -> SyncRunOutcome:
    if test_failure:
        return await run_deal_sync("test", _InjectedFailureClient())
    return await run_deal_sync("nightly", client)


def exit_code(outcome: SyncRunOutcome) -> int:
    return 1 if outcome.status == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worker.hubspot_reconcile")
    parser.add_argument("--test-failure", action="store_true",
        help="record a failed TEST run without contacting HubSpot (exits 1)")
    args = parser.parse_args(argv)
    outcome = asyncio.run(run_once(test_failure=args.test_failure))
    return exit_code(outcome)


if __name__ == "__main__":
    sys.exit(main())
