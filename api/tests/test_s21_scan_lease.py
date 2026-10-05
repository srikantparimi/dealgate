"""Transactional scan checkpoint contract, before provider orchestration."""
from datetime import UTC, datetime, timedelta

import pytest

from app.models.sync_status import SyncStatus
from app.services import sync_status as scans

CONTEXT = {"schema_version": 1, "tenant": "synthetic", "environment": "local",
    "portal_id": "fixture", "properties": ["dealname"], "mapping_version": 1}


@pytest.fixture
def clock(monkeypatch):
    values = [datetime(2026, 10, 2, tzinfo=UTC)]
    async def now(session):
        return values[0]
    monkeypatch.setattr(scans, "_scan_now", now, raising=False)
    return values


async def acquire(session, context=None):
    return await scans.acquire_scan(session, source="synthetic-scan",
        context=context or CONTEXT, lease_seconds=60)


@pytest.mark.asyncio
async def test_acquire_does_not_claim_success_or_allow_concurrent_owner(session, clock):
    lease = await acquire(session)
    await session.commit()
    row = await session.get(SyncStatus, "synthetic-scan")
    assert row.last_success_at is None
    assert row.scan_completed_at is None
    assert row.scan_phase == "scanning"
    assert lease.generation == 1 and lease.cursor is None
    with pytest.raises(scans.ScanConflict, match="leased"):
        await acquire(session)


@pytest.mark.asyncio
async def test_expired_owner_resumes_same_generation_cursor_with_new_token(session, clock):
    old = await acquire(session)
    await scans.checkpoint_scan(session, old, expected_cursor=None, next_cursor="page-2")
    await session.commit()
    clock[0] += timedelta(seconds=61)
    resumed = await acquire(session)
    assert resumed.generation == old.generation
    assert resumed.cursor == "page-2"
    assert resumed.token != old.token
    with pytest.raises(scans.ScanConflict):
        await scans.checkpoint_scan(session, old, expected_cursor="page-2", next_cursor=None)


@pytest.mark.asyncio
async def test_changed_context_starts_new_generation_without_success(session, clock):
    old = await acquire(session)
    await session.commit()
    clock[0] += timedelta(seconds=61)
    new = await acquire(session, {**CONTEXT, "mapping_version": 2})
    assert new.generation == old.generation + 1
    assert new.cursor is None
    assert (await session.get(SyncStatus, old.source)).last_success_at is None


@pytest.mark.asyncio
async def test_final_page_only_allows_owned_atomic_completion(session, clock):
    lease = await acquire(session)
    with pytest.raises(scans.ScanConflict, match="phase"):
        await scans.complete_scan(session, lease)
    await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor=None)
    row = await session.get(SyncStatus, lease.source)
    assert row.scan_phase == "finalizing" and row.last_success_at is None
    await scans.complete_scan(session, lease)
    await session.commit()
    assert row.scan_phase == "completed"
    assert row.scan_completed_at == clock[0]
    assert row.reconciled_at == clock[0]
    assert row.last_success_at == clock[0]
    assert row.scan_lease_token is None
    with pytest.raises(scans.ScanConflict):
        await scans.complete_scan(session, lease)


@pytest.mark.asyncio
async def test_rollback_does_not_advance_page(session, clock):
    lease = await acquire(session)
    await session.commit()
    await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
    await session.rollback()
    session.expunge_all()
    row = await session.get(SyncStatus, lease.source)
    assert row.cursor is None and row.scan_phase == "scanning"


@pytest.mark.asyncio
async def test_failed_scan_preserves_cursor_and_resumes_with_failure_evidence(session, clock):
    lease = await acquire(session)
    await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
    await scans.fail_scan(session, lease, error="provider_timeout")
    await session.commit()
    row = await session.get(SyncStatus, lease.source)
    assert row.scan_failure_count == 1
    assert row.cursor == "page-2" and row.last_success_at is None
    resumed = await acquire(session)
    assert resumed.generation == lease.generation and resumed.cursor == "page-2"
    assert row.scan_failure_count == 1
    with pytest.raises(scans.ScanConflict):
        await scans.fail_scan(session, lease, error="stale failure")


@pytest.mark.asyncio
@pytest.mark.parametrize("next_cursor", ["page-2", "x" * 256])
async def test_invalid_cursor_cannot_advance(session, clock, next_cursor):
    lease = await acquire(session)
    await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
    with pytest.raises(ValueError):
        await scans.checkpoint_scan(session, lease, expected_cursor="page-2", next_cursor=next_cursor)


@pytest.mark.asyncio
async def test_stale_cursor_and_expired_lease_cannot_checkpoint(session, clock):
    lease = await acquire(session)
    await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-2")
    with pytest.raises(scans.ScanConflict, match="cursor"):
        await scans.checkpoint_scan(session, lease, expected_cursor=None, next_cursor="page-3")
    clock[0] += timedelta(seconds=61)
    with pytest.raises(scans.ScanConflict, match="expired"):
        await scans.checkpoint_scan(session, lease, expected_cursor="page-2", next_cursor=None)
