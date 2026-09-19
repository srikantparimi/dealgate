"""S7 — nightly S3 Object-Lock audit export.

Covers the acceptance tests in ``docs/backlog/s7-audit-hardening.md``:

- Seed 10 rows for yesterday + 3 for today; ``run(session, stub, yday)``
  ships exactly 10 rows sorted by ``(ts, id)``.
- Second call the same day is a no-op (HEAD matches).
- HEAD returning a different ``Content-MD5`` writes an ``-r1.jsonl.gz``
  sidecar and audits ``audit_export.reprocessed``.
- Empty day → empty gzip still uploaded + ``audit_export.written`` with
  ``row_count=0``.
- Post-export, ``verify_chain`` still returns ``True``.
"""

from __future__ import annotations

import gzip
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.audit import append_audit, verify_chain
from app.integrations.s3_audit import StubAuditExportS3
from app.models.audit import AuditEvent
from worker.audit_export import _key_for, _sidecar_key, run


_YESTERDAY = date(2026, 9, 17)
_TODAY = date(2026, 9, 18)


async def _seed_row(
    session, *, ts: datetime, action: str, entity_id: str
) -> None:
    """Insert one audit row with a fixed timestamp (bypass ``append_audit``)."""

    # Bypass ``append_audit`` so we can pin ``ts`` — the app helper stamps
    # ``datetime.now(UTC)`` which the export test can't control.
    row = AuditEvent(
        id=uuid.uuid4(),
        ts=ts,
        actor_id=None,
        action=action,
        entity="test",
        entity_id=entity_id,
        before=None,
        after={"seq": entity_id},
        correlation_id=None,
        prev_hash=None,
        row_hash="0" * 64,
    )
    session.add(row)
    await session.flush()


async def _seed_chain_row(session) -> None:
    """Insert one hash-chained row through the real ``append_audit`` path."""

    await append_audit(
        session,
        actor_id=None,
        action="seed.chain",
        entity="test",
        entity_id="chain-1",
        before=None,
        after={"seed": True},
        correlation_id="seed",
    )


@pytest.mark.asyncio
async def test_exports_only_the_target_days_rows_sorted(session):
    # 10 rows yesterday, 3 rows today.
    base_yday = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    for i in range(10):
        await _seed_row(
            session,
            ts=base_yday + timedelta(minutes=i),
            action="test.row",
            entity_id=f"y-{i:02d}",
        )
    base_today = datetime(2026, 9, 18, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        await _seed_row(
            session,
            ts=base_today + timedelta(minutes=i),
            action="test.row",
            entity_id=f"t-{i:02d}",
        )
    await session.commit()

    s3 = StubAuditExportS3()
    result = await run(session, s3, _YESTERDAY)

    key = _key_for(_YESTERDAY)
    assert result.action == "written"
    assert result.row_count == 10
    assert result.s3_key == key
    assert key in s3.objects

    body, ctype, _md5 = s3.objects[key]
    assert ctype == "application/gzip"

    lines = gzip.decompress(body).decode("utf-8").splitlines()
    assert len(lines) == 10
    payloads = [json.loads(line) for line in lines]
    # Sorted by (ts, id) — ts alone is enough here because our seeds are
    # 1-minute apart.
    ts_seq = [datetime.fromisoformat(p["ts"]) for p in payloads]
    assert ts_seq == sorted(ts_seq)
    # None of today's rows leaked in.
    assert all(p["entity_id"].startswith("y-") for p in payloads)


@pytest.mark.asyncio
async def test_second_call_same_day_is_noop(session):
    base = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    for i in range(3):
        await _seed_row(
            session,
            ts=base + timedelta(minutes=i),
            action="test.row",
            entity_id=f"y-{i}",
        )
    await session.commit()

    s3 = StubAuditExportS3()
    first = await run(session, s3, _YESTERDAY)
    assert first.action == "written"
    assert len(s3.put_calls) == 1

    second = await run(session, s3, _YESTERDAY)
    assert second.action == "skipped"
    # No second PUT — HEAD matched and we exited early.
    assert len(s3.put_calls) == 1
    # The skipped tick is still auditable — one written + one skipped row.
    rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity == "audit_export")
        )
    ).scalars().all()
    actions = sorted(r.action for r in rows)
    assert actions == ["audit_export.skipped", "audit_export.written"]


@pytest.mark.asyncio
async def test_head_md5_mismatch_writes_sidecar(session):
    base = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    for i in range(2):
        await _seed_row(
            session,
            ts=base + timedelta(minutes=i),
            action="test.row",
            entity_id=f"y-{i}",
        )
    await session.commit()

    s3 = StubAuditExportS3()
    key = _key_for(_YESTERDAY)
    # Simulate: something is already at ``key`` but with a different md5.
    s3.md5_override[key] = "AAAAAAAAAAAAAAAAAAAAAA=="

    result = await run(session, s3, _YESTERDAY)

    sidecar = _sidecar_key(_YESTERDAY, 1)
    assert result.action == "reprocessed"
    assert result.s3_key == sidecar
    # The sidecar body actually landed; the base key stays under the
    # (tampered) prior version so we don't destroy evidence.
    assert sidecar in s3.objects
    assert key not in s3.objects

    audit_row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "audit_export.reprocessed")
        )
    ).scalar_one()
    assert audit_row.after == {
        "day": _YESTERDAY.isoformat(),
        "row_count": 2,
        "s3_key": sidecar,
        "sha256": result.sha256,
    }


@pytest.mark.asyncio
async def test_empty_day_still_uploads_empty_gzip(session):
    # No rows at all — the export must still write the empty file so the
    # "did last night's export run?" query is answerable.
    s3 = StubAuditExportS3()
    result = await run(session, s3, _YESTERDAY)

    key = _key_for(_YESTERDAY)
    assert result.action == "written"
    assert result.row_count == 0
    assert key in s3.objects
    body, _ctype, _md5 = s3.objects[key]
    assert gzip.decompress(body) == b""

    audit_row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "audit_export.written")
        )
    ).scalar_one()
    assert audit_row.after["row_count"] == 0


@pytest.mark.asyncio
async def test_chain_still_verifies_after_export(session):
    # Seed one chained row so ``verify_chain`` walks a non-empty chain.
    await _seed_chain_row(session)
    await session.commit()

    s3 = StubAuditExportS3()
    # Yesterday has no rows in this test — the export writes an empty
    # payload + one ``audit_export.written`` row via ``append_audit`` (so
    # the chain grows by one link).
    result = await run(session, s3, _YESTERDAY)
    assert result.action == "written"

    assert await verify_chain(session) is True
