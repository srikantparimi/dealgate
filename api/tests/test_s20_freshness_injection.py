"""T32 · freshness injection (S20 · W5).

Per review + A2:
> Inject more than ten synthetic events and one immediately after a run;
> verify draining, measured freshness, stale banner and DLQ handling.

Per D4: continuous consumer service (`hubspot_intake` ECS long-runner).
Freshness reads source-specific watermarks (received / processed /
last reconcile), NEVER a worker heartbeat. Public target "typically
under 2 minutes", measured.

**Skeleton, xfail until W1's continuous-consumer cutover lands.**

Test cases:
  1. Inject 15 synthetic events; the consumer drains them within 2 min;
     `hubspot_webhook_processed` advances past all 15.
  2. Inject one event immediately after a scheduled tick would have
     ended (was L20 defect: 5-min tick can add 5-min latency).
     The continuous consumer picks it up in ≤ 15s.
  3. When the queue backlog age > 5 min, the SPA renders the Stale
     banner (contract §3 freshness `state == "Stale"`).
  4. A DLQ message > 0 triggers the Failed state; the banner names
     the source.
  5. A worker tick that runs but does no work does NOT advance
     `processed_at` — the freshness stays at the last real event
     watermark (contract §5).
"""

from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="depends on W1 continuous-consumer + watermarks (D4)", strict=False)
@pytest.mark.asyncio
async def test_15_events_drain_within_two_minutes(session):
    """
    Given: 15 synthetic HubSpot events pushed to the staging queue
    with the `s20-` marker (isolation §7).
    When:  the continuous consumer runs.
    Then:  within 120s, `hubspot_webhook_processed` is >= the
           timestamp of the 15th event; the intake table has 15 rows.
    """
    raise AssertionError("skeleton: implement once W1's consumer lands")


@pytest.mark.xfail(reason="depends on W1 continuous consumer (A2)")
@pytest.mark.asyncio
async def test_event_after_tick_boundary_picks_up_within_15_seconds(session):
    """
    Given: an event injected just after a scheduled-worker window
    would have ended (proves scheduled-worker mode wouldn't catch it).
    When:  the continuous consumer runs.
    Then:  the event is processed within 15s. Latency recorded in
           `docs/reports/s20/deploy.md` §consumer cutover.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 stale-state banner via watermark")
@pytest.mark.asyncio
async def test_backlog_over_5_min_flips_freshness_to_stale(session):
    """
    Given: consumer stopped, backlog grows to 6 minutes.
    When:  the pipeline list API is called.
    Then:  meta.freshness.state == "Stale";
           reason includes "backlog_seconds=360".
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 DLQ surface")
@pytest.mark.asyncio
async def test_dlq_message_flips_state_to_failed(session):
    """
    Given: one message sitting in the DLQ.
    Then:  meta.freshness.state == "Failed";
           payload names the queue and the DLQ arn.
           The health page renders Failed with the reason.
    """
    raise AssertionError("skeleton")


@pytest.mark.xfail(reason="depends on W1 watermark discipline (contract §5)")
@pytest.mark.asyncio
async def test_worker_tick_without_events_does_not_advance_processed(session):
    """
    Given: `hubspot_webhook_processed` at T0; the worker runs for 30s
    with zero events on the queue.
    Then:  `hubspot_webhook_processed` is STILL T0 (no heartbeat lie).
           `hubspot_reconcile` may advance if a reconcile ran.
    """
    raise AssertionError("skeleton")
