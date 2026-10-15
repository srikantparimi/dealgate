"""S23-PL1 — HubSpot deal sync run records and sync health.

Item 1: :func:`run_deal_sync` wraps every deal reconcile (nightly worker,
SystemAdmin trigger, test run) in one ``hubspot_sync_run`` row: inserted as
``running`` before HubSpot is read, finished as ``ok`` / ``partial`` /
``failed`` with counts and the first five errors (HubSpot id + short reason).

Item 3: a run that did not succeed is never recorded or logged as success.

Item 2 / 8: :func:`compute_sync_health` derives freshness from these rows
only, never from the intake heartbeat:

- ``last_success_at`` — finish time of the latest run that completed without a
  fatal error and wrote deals (``ok`` or ``partial`` with deals_written > 0);
- ``state`` — ``failed`` when the last attempt failed or ended partial;
  otherwise ``fresh`` when the last success is within 36 hours; otherwise
  ``stale``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import literal, select, true
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.audit import append_audit
from app.db import session_factory as default_session_factory
from app.integrations.hubspot import HubSpotClient
from app.models.hubspot_sync_run import RUN_KINDS, HubspotSyncRun
from app.models.sync_status import SyncStatus
from app.services.hubspot_backfill import BackfillCounts, run_backfill, short_reason
from app.services.sync_status import touch_source

log = structlog.get_logger("hubspot_sync_runs")

FRESH_WITHIN = timedelta(hours=36)
# A run still marked ``running`` after this long did not finish (the task died);
# it counts as a failed attempt. A normal staging run takes about two minutes.
ABANDONED_AFTER = timedelta(hours=2)
MAX_LISTED_ERRORS = 5
SCHEDULE = "nightly"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def classify(*, fatal_error: str | None, deals_written: int, error_count: int) -> str:
    """ok / partial / failed (item 4).

    Fatal, or nothing written while errors happened: ``failed``. Deals written
    with errors: ``partial``. No errors: ``ok``.
    """
    if fatal_error:
        return "failed"
    if error_count and deals_written == 0:
        return "failed"
    if error_count:
        return "partial"
    return "ok"


@dataclass(frozen=True)
class SyncRunOutcome:
    run_id: uuid.UUID
    kind: str
    status: str
    deals_seen: int
    deals_written: int
    error_count: int
    errors: list[dict[str, str]] = field(default_factory=list)
    fatal_error: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)


async def start_run(factory: async_sessionmaker[AsyncSession], kind: str,
                    *, now: datetime | None = None) -> uuid.UUID:
    """Insert the ``running`` row (committed before HubSpot is read).

    Runs left ``running`` past :data:`ABANDONED_AFTER` are closed as failed
    first, so the table never claims a dead task is still working.
    """
    if kind not in RUN_KINDS:
        raise ValueError(f"unknown sync run kind: {kind}")
    now = now or datetime.now(UTC)
    async with factory() as session:
        abandoned = (await session.scalars(select(HubspotSyncRun).where(
            HubspotSyncRun.status == "running",
            HubspotSyncRun.started_at < now - ABANDONED_AFTER))).all()
        for row in abandoned:
            row.status = "failed"
            # It died at an unknown time; rank it at its start, so any run that
            # ended after that supersedes it.
            row.finished_at = row.started_at
            row.fatal_error = "run did not finish"
            row.error_count = (row.error_count or 0) + 1
            row.errors = [{"hubspot_id": "", "reason": "run did not finish"},
                *(row.errors or [])][:MAX_LISTED_ERRORS]
            await append_audit(session, actor_id=None, action="hubspot.sync_run.abandoned",
                entity="hubspot_sync_run", entity_id=str(row.id),
                before={"status": "running"}, after={"status": "failed",
                    "fatal_error": row.fatal_error})
        run = HubspotSyncRun(id=uuid.uuid4(), kind=kind, started_at=now, status="running",
            errors=[])
        session.add(run)
        await session.commit()
        return run.id


async def finish_run(factory: async_sessionmaker[AsyncSession], run_id: uuid.UUID,
                     counts: BackfillCounts, *, now: datetime | None = None) -> SyncRunOutcome:
    now = now or datetime.now(UTC)
    error_count = counts.errors
    status = classify(fatal_error=counts.fatal_error, deals_written=counts.deals_written,
        error_count=error_count)
    errors = list(counts.record_errors[:MAX_LISTED_ERRORS])
    if counts.fatal_error:
        errors = [{"hubspot_id": "", "reason": counts.fatal_error[:200]}, *errors][:MAX_LISTED_ERRORS]
    summary = {key: value for key, value in counts.as_dict().items()
        if isinstance(value, (int, bool))}
    async with factory() as session:
        run = await session.get(HubspotSyncRun, run_id, with_for_update=True)
        if run is None:  # pragma: no cover - the row is inserted by start_run
            raise RuntimeError("sync run row vanished")
        run.finished_at = now
        run.status = status
        run.deals_seen = counts.deals_seen
        run.deals_written = counts.deals_written
        run.error_count = error_count
        run.errors = errors
        run.fatal_error = counts.fatal_error[:255] if counts.fatal_error else None
        run.counts = summary
        await append_audit(session, actor_id=None, action="hubspot.sync_run.finished",
            entity="hubspot_sync_run", entity_id=str(run.id), before={"status": "running"},
            after={"kind": run.kind, "status": status, "deals_seen": run.deals_seen,
                "deals_written": run.deals_written, "error_count": error_count,
                "fatal_error": run.fatal_error})
        await session.commit()
        return SyncRunOutcome(run.id, run.kind, status, run.deals_seen, run.deals_written,
            error_count, errors, run.fatal_error, summary)


async def run_deal_sync(kind: str, client: HubSpotClient | None = None, *,
                        session_factory: async_sessionmaker[AsyncSession] | None = None,
                        ) -> SyncRunOutcome:
    """One deal reconcile with its run record (items 1, 3 and 4).

    ``run_backfill`` reports per-record and fatal errors in its counts; any
    exception that still escapes is caught here, recorded as the fatal error,
    and the run ends ``failed``. Only an ``ok`` nightly run advances the legacy
    ``hubspot_reconcile`` row's success time.
    """
    factory = session_factory or default_session_factory
    run_id = await start_run(factory, kind)
    try:
        counts = await run_backfill(client, session_factory=factory)
    except Exception as error:  # run_backfill should not raise; never call it success
        log.exception("hubspot_deal_sync_crashed", run_id=str(run_id))
        counts = BackfillCounts()
        counts.errors += 1
        counts.fatal_error = f"sync: {short_reason(error)}"
    outcome = await finish_run(factory, run_id, counts)

    if kind == "nightly":
        problem = None if outcome.status == "ok" else (
            f"{outcome.status}: {outcome.fatal_error or f'{outcome.error_count} record errors'}")
        async with factory() as session:
            await touch_source(session, source="hubspot_reconcile",
                success=outcome.status == "ok", error=problem)
            await session.commit()
    elif kind == "manual" and outcome.status == "ok":
        # A clean SystemAdmin recovery clears a failed night's error on the
        # legacy row (the old page's chip reads it) without claiming that the
        # nightly itself succeeded.
        async with factory() as session:
            row = await session.get(SyncStatus, "hubspot_reconcile")
            if row is not None and row.last_error is not None:
                row.last_error = None
                row.lag_seconds = 0
                await session.commit()

    event = {"ok": "hubspot_deal_sync_ok", "partial": "hubspot_deal_sync_partial",
        "failed": "hubspot_deal_sync_failed"}[outcome.status]
    getattr(log, "info" if outcome.status == "ok" else "error")(
        event, run_id=str(outcome.run_id), kind=kind, deals_seen=outcome.deals_seen,
        deals_written=outcome.deals_written, error_count=outcome.error_count,
        errors=outcome.errors, fatal_error=outcome.fatal_error)
    return outcome


# ---------------------------------------------------------------------------
# Sync health (item 2) — the ``Freshness`` schema in openapi-pipeline.yaml.
# ---------------------------------------------------------------------------


def _iso(value: datetime | None) -> str | None:
    value = _utc(value)
    return value.isoformat().replace("+00:00", "Z") if value else None


async def compute_sync_health(session: AsyncSession, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    # The last attempt is the run that ENDED last: a run refused because another
    # one holds the scan lease ends at once, and must not mask the real run that
    # finishes after it. A run still "running" past ABANDONED_AFTER died at an
    # unknown time; it is the last attempt only if it started after the latest
    # finished run ended (any run that ended later superseded it).
    #
    # S23-PL2 B1/B15: the three lookups and the legacy row are read in ONE
    # statement (the Pipeline workspace has a statement budget): each lookup is
    # a LIMIT-1 subquery outer-joined to a one-row anchor.
    finished_q = (
        select(HubspotSyncRun).where(HubspotSyncRun.finished_at.is_not(None))
        .order_by(HubspotSyncRun.finished_at.desc()).limit(1).subquery("finished_run"))
    abandoned_q = (
        select(HubspotSyncRun).where(HubspotSyncRun.status == "running",
            HubspotSyncRun.finished_at.is_(None),
            HubspotSyncRun.started_at < now - ABANDONED_AFTER)
        .order_by(HubspotSyncRun.started_at.desc()).limit(1).subquery("abandoned_run"))
    success_q = (
        select(HubspotSyncRun)
        .where(HubspotSyncRun.status.in_(("ok", "partial")), HubspotSyncRun.deals_written > 0,
               HubspotSyncRun.finished_at.is_not(None))
        .order_by(HubspotSyncRun.finished_at.desc()).limit(1).subquery("success_run"))
    finished_run = aliased(HubspotSyncRun, finished_q)
    abandoned_run = aliased(HubspotSyncRun, abandoned_q)
    success_run = aliased(HubspotSyncRun, success_q)
    anchor = select(literal(1).label("one")).subquery("anchor")
    finished, abandoned, success, legacy = (await session.execute(
        select(finished_run, abandoned_run, success_run, SyncStatus)
        .select_from(anchor)
        .outerjoin(finished_run, true())
        .outerjoin(abandoned_run, true())
        .outerjoin(success_run, true())
        .outerjoin(SyncStatus, SyncStatus.source == "hubspot_backfill")
    )).one()
    attempt = finished
    if abandoned is not None and (finished is None or
            _utc(abandoned.started_at) > _utc(finished.finished_at)):
        attempt = abandoned

    if attempt is None:
        return _legacy_health(legacy, now)

    last_status = attempt.status if attempt.status in ("ok", "partial", "failed") else "failed"
    errors = list(attempt.errors or [])
    if attempt.status == "running":  # abandoned and not yet closed by a later run
        errors = [{"hubspot_id": "", "reason": "run did not finish"}, *errors]
    last_success_at = _utc(success.finished_at) if success else None
    return {
        "state": _state(last_status, last_success_at, now),
        "last_success_at": _iso(last_success_at),
        # A run that died is reported at its start: when it was attempted.
        "last_attempt_at": _iso(attempt.started_at if attempt.fatal_error == "run did not finish"
            or attempt.status == "running" else (attempt.finished_at or attempt.started_at)),
        "last_status": last_status,
        "schedule": SCHEDULE,
        "deals_seen": attempt.deals_seen,
        "deals_written": attempt.deals_written,
        "error_count": attempt.error_count + (1 if attempt.status == "running" else 0),
        "errors": errors[:MAX_LISTED_ERRORS],
        "recovery": {"available": True, "admin_only": True},
    }


def _state(last_status: str, last_success_at: datetime | None, now: datetime) -> str:
    if last_status in ("failed", "partial"):
        return "failed"
    if last_success_at is not None and now - last_success_at <= FRESH_WITHIN:
        return "fresh"
    return "stale"


def _legacy_health(row: SyncStatus | None, now: datetime) -> dict[str, Any]:
    """Before the first recorded run: the last CLEAN deal scan.

    ``hubspot_backfill.last_success_at`` is moved only by a scan that completed
    without refusing a record (``complete_scan``; never by the intake
    heartbeat), so it is an honest success time until the first run row exists.
    Any ``last_error`` on the row means the latest attempt was not clean.
    ``row`` is the ``hubspot_backfill`` sync-status row (read with the runs).
    """
    success = _utc(row.last_success_at) if row is not None else None
    attempted = _utc(row.last_attempt_at) if row is not None else None
    errors: list[dict[str, str]] = []
    if row is not None and (row.last_error is not None or row.scan_phase == "failed"):
        last_status = "failed"
        errors = [{"hubspot_id": "", "reason": f"deal scan: {row.last_error or 'failed'}"[:200]}]
    elif success is None:
        last_status = "failed"
        errors = [{"hubspot_id": "", "reason": "no completed deal sync recorded"}]
    else:
        last_status = "ok"
    return {
        "state": _state(last_status, success, now),
        "last_success_at": _iso(success),
        "last_attempt_at": _iso(attempted),
        "last_status": last_status,
        "schedule": SCHEDULE,
        "error_count": len(errors),
        "errors": errors,
        "recovery": {"available": True, "admin_only": True},
    }
