"""S20 L18/T42 · approval turnaround aggregation.

Feeds synthetic ``package.*`` audit rows into the audit log, runs the
service, and asserts per-stage averages / medians / p90 are computed
from the timestamps — with an honest ``sample_size=0`` for stages that
saw no traffic in the window.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import append_audit
from app.models.audit import AuditEvent
from app.services.reports import (
    compute_approval_turnaround,
)


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


async def _audit(
    session,
    *,
    pkg_id: str,
    action: str,
    before_status: str | None,
    after_status: str,
    ts: datetime,
) -> None:
    """Append one package.* audit row at ``ts``.

    The service reads ``ts`` off the row, so we set it directly via a
    manual insert after ``append_audit`` writes the row_hash chain
    correctly. Keeps the tests independent of ``server_default=now()``.
    """

    await append_audit(
        session,
        actor_id=None,
        action=action,
        entity="approval_package",
        entity_id=pkg_id,
        before={"status": before_status} if before_status else None,
        after={"status": after_status},
    )
    # Reach in and correct the timestamp so per-stage math works in a
    # frozen test.
    row = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity_id == pkg_id)
            .where(AuditEvent.action == action)
            .order_by(AuditEvent.ts.desc())
            .limit(1)
        )
    ).scalar_one()
    row.ts = ts
    await session.flush()


@pytest.mark.asyncio
async def test_empty_window_returns_null_metrics_and_zero_samples(session):
    report = await compute_approval_turnaround(session, window="30d", now=NOW)
    assert report.total_transitions == 0
    assert report.overall_median_hours is None
    for stage in report.per_stage:
        assert stage.sample_size == 0
        assert stage.avg_hours is None
        assert stage.median_hours is None
        assert stage.p90_hours is None


@pytest.mark.asyncio
async def test_single_package_flows_through_delivery_hr_and_finance(session):
    pkg = str(uuid.uuid4())
    submitted_at = NOW - timedelta(hours=48)
    delivery_hr_passed_at = submitted_at + timedelta(hours=6)
    ready_to_sign_at = delivery_hr_passed_at + timedelta(hours=18)

    await _audit(
        session,
        pkg_id=pkg,
        action="package.submitted",
        before_status=None,
        after_status="pending_delivery_hr",
        ts=submitted_at,
    )
    await _audit(
        session,
        pkg_id=pkg,
        action="package.delivery_hr_passed",
        before_status="pending_delivery_hr",
        after_status="pending_finance_legal",
        ts=delivery_hr_passed_at,
    )
    await _audit(
        session,
        pkg_id=pkg,
        action="package.ready_to_sign",
        before_status="pending_finance_legal",
        after_status="ready_to_sign",
        ts=ready_to_sign_at,
    )

    report = await compute_approval_turnaround(session, window="30d", now=NOW)
    # Two intervals: delivery_hr = 6h, finance_legal = 18h.
    assert report.total_transitions == 2
    by_stage = {s.stage: s for s in report.per_stage}
    assert by_stage["pending_delivery_hr"].sample_size == 1
    assert by_stage["pending_delivery_hr"].avg_hours == pytest.approx(6.0)
    assert by_stage["pending_delivery_hr"].median_hours == pytest.approx(6.0)
    assert by_stage["pending_finance_legal"].sample_size == 1
    assert by_stage["pending_finance_legal"].avg_hours == pytest.approx(18.0)
    # Untouched stages stay honest.
    assert by_stage["pending_ceo_exception"].sample_size == 0
    assert by_stage["pending_ceo_exception"].avg_hours is None


@pytest.mark.asyncio
async def test_events_older_than_window_are_excluded(session):
    pkg = str(uuid.uuid4())
    old_submit = NOW - timedelta(days=60)
    old_passed = old_submit + timedelta(hours=10)
    # 60 days ago, entirely outside a 30d window.
    await _audit(
        session,
        pkg_id=pkg,
        action="package.submitted",
        before_status=None,
        after_status="pending_delivery_hr",
        ts=old_submit,
    )
    await _audit(
        session,
        pkg_id=pkg,
        action="package.delivery_hr_passed",
        before_status="pending_delivery_hr",
        after_status="pending_finance_legal",
        ts=old_passed,
    )

    report = await compute_approval_turnaround(session, window="30d", now=NOW)
    assert report.total_transitions == 0


@pytest.mark.asyncio
async def test_median_computed_across_multiple_samples(session):
    # Three packages, each with a delivery_hr interval of 4h, 8h, 16h.
    for hours in (4, 8, 16):
        pkg = str(uuid.uuid4())
        t0 = NOW - timedelta(hours=hours + 1)
        t1 = t0 + timedelta(hours=hours)
        await _audit(
            session,
            pkg_id=pkg,
            action="package.submitted",
            before_status=None,
            after_status="pending_delivery_hr",
            ts=t0,
        )
        await _audit(
            session,
            pkg_id=pkg,
            action="package.delivery_hr_passed",
            before_status="pending_delivery_hr",
            after_status="pending_finance_legal",
            ts=t1,
        )

    report = await compute_approval_turnaround(session, window="30d", now=NOW)
    by_stage = {s.stage: s for s in report.per_stage}
    dh = by_stage["pending_delivery_hr"]
    assert dh.sample_size == 3
    assert dh.avg_hours == pytest.approx((4 + 8 + 16) / 3.0)
    # Median of [4, 8, 16] = 8.
    assert dh.median_hours == pytest.approx(8.0)


@pytest.mark.asyncio
async def test_invalid_window_raises(session):
    with pytest.raises(ValueError):
        await compute_approval_turnaround(session, window="bogus")
    with pytest.raises(ValueError):
        await compute_approval_turnaround(session, window="0d")


@pytest_asyncio.fixture
async def session():
    """Local pared-down session — full conftest is heavy, this test only
    needs the audit table."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()
