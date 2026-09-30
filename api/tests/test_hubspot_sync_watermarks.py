"""S20 W1 D4 · watermarks + freshness envelope acceptance.

Covers:
- ``touch_source`` advances only the typed clocks the caller asks for.
- ``get_watermarks`` returns every key from contracts §5 (missing rows
  come back with null timestamps rather than being dropped).
- ``get_hubspot_freshness`` maps received/processed gap → verified /
  Stale / Failed / Unknown per contracts §3.
- ``claim_scan_generation`` monotonically increments and clears
  ``scan_completed_at`` so the archive gate is closed mid-scan.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.sync_status import SyncStatus
from app.services.hubspot_sync import (
    STALE_AFTER_SECONDS,
    get_hubspot_freshness,
    get_watermarks,
)
from app.services.sync_status import (
    WATERMARK_KEYS,
    claim_scan_generation,
    mark_scan_completed,
    touch_source,
)


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def test_touch_source_marks_only_requested_clocks(factory):
    async with factory() as s:
        await touch_source(
            s,
            source="hubspot_webhook_received",
            success=True,
            error=None,
            mark_received=True,
        )
        await s.commit()
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_webhook_received")
    assert row is not None
    assert row.received_at is not None
    assert row.processed_at is None
    assert row.reconciled_at is None


async def test_get_watermarks_returns_every_contract_key(factory):
    async with factory() as s:
        marks = await get_watermarks(s)
    keys = {m.source for m in marks}
    for expected in WATERMARK_KEYS:
        assert expected in keys, f"contract watermark missing: {expected}"


async def test_freshness_verified_when_processed_close_to_received(factory):
    now = datetime.now(UTC)
    async with factory() as s:
        # Simulate a webhook received 30 s ago + processed 20 s ago.
        row_r = SyncStatus(source="hubspot_webhook_received", received_at=now - timedelta(seconds=30))
        row_p = SyncStatus(source="hubspot_webhook_processed", processed_at=now - timedelta(seconds=20))
        s.add(row_r)
        s.add(row_p)
        await s.commit()
    async with factory() as s:
        env = await get_hubspot_freshness(s, now=now)
    assert env.state == "verified working"
    assert env.reason is None


async def test_freshness_stale_when_gap_exceeds_threshold(factory):
    now = datetime.now(UTC)
    async with factory() as s:
        row_r = SyncStatus(source="hubspot_webhook_received", received_at=now)
        # Processed lagging by threshold + 1s.
        row_p = SyncStatus(
            source="hubspot_webhook_processed",
            processed_at=now - timedelta(seconds=STALE_AFTER_SECONDS + 1),
        )
        s.add(row_r)
        s.add(row_p)
        await s.commit()
    async with factory() as s:
        env = await get_hubspot_freshness(s, now=now)
    assert env.state == "Stale"
    assert env.reason is not None and "gap" in env.reason


async def test_freshness_failed_when_any_source_has_error(factory):
    now = datetime.now(UTC)
    async with factory() as s:
        # Even if the received/processed pair looks healthy, a live
        # error on ANY of the sources dominates.
        row_r = SyncStatus(source="hubspot_webhook_received", received_at=now)
        row_p = SyncStatus(source="hubspot_webhook_processed", processed_at=now)
        row_reconcile = SyncStatus(
            source="hubspot_reconcile", last_error="hubspot 500"
        )
        s.add_all([row_r, row_p, row_reconcile])
        await s.commit()
    async with factory() as s:
        env = await get_hubspot_freshness(s, now=now)
    assert env.state == "Failed"
    assert env.reason == "hubspot 500"


async def test_freshness_unknown_when_no_events_yet(factory):
    async with factory() as s:
        env = await get_hubspot_freshness(s)
    assert env.state == "Unknown"
    assert env.reason == "No HubSpot events observed yet"


async def test_claim_scan_generation_is_monotonic_and_clears_completion(factory):
    async with factory() as s:
        first = await claim_scan_generation(s, source="hubspot_backfill")
        await s.commit()
    async with factory() as s:
        # Mark completion, then claim again — a new generation must not
        # inherit the previous "completed" stamp.
        await mark_scan_completed(s, source="hubspot_backfill", generation=first)
        await s.commit()

    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row is not None
    assert row.scan_generation == first
    assert row.scan_completed_at is not None

    async with factory() as s:
        second = await claim_scan_generation(s, source="hubspot_backfill")
        await s.commit()
    assert second == first + 1

    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row is not None
    assert row.scan_generation == second
    # NEW generation → completion cleared until mark_scan_completed fires
    assert row.scan_completed_at is None


async def test_mark_scan_completed_ignored_when_generation_stale(factory):
    async with factory() as s:
        first = await claim_scan_generation(s, source="hubspot_backfill")
        await s.commit()
    async with factory() as s:
        second = await claim_scan_generation(s, source="hubspot_backfill")
        await s.commit()

    # An older generation trying to mark completion is a no-op — the
    # in-flight NEW generation must not be prematurely gated.
    async with factory() as s:
        await mark_scan_completed(s, source="hubspot_backfill", generation=first)
        await s.commit()
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row is not None
    assert row.scan_generation == second
    assert row.scan_completed_at is None
