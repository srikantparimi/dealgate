"""S19 slice 1 §H1/H2 → S20 W1 D4: sync_status watermark writer.

Every worker (backfill, webhook consumer, nightly reconcile, owner
mirror, pipeline mirror, property mirror) calls :func:`touch_source` at
the end of each run. The Pipeline UI's amber banner and the settings
integration health page read the ``last_success_at`` and typed
watermarks (``received_at`` / ``processed_at`` / ``reconciled_at``).

S20 W1 replaces the "worker heartbeat means freshness" story with typed
watermarks per D4. Callers name the exact clock they want to advance:

- ``received_at`` — webhook accepted + row durably enqueued.
- ``processed_at`` — event fully handled + audit committed (D7 atomic
  boundary; this is the value the Pipeline UI shows as "Synced N ago").
- ``reconciled_at`` — nightly full-scan pass completed.
- ``scan_generation`` / ``scan_started_at`` / ``scan_completed_at`` —
  A3/T33 scan-generation persistence (a mid-scan failure never
  archives; see :func:`app.services.hubspot_backfill.run_backfill`).
- ``backlog_age_seconds`` / ``dlq_age_seconds`` — queue-depth telemetry
  the freshness alarms sample.

Legacy heartbeat helpers remain separate from the scan lease protocol below.
Scan acquisition, page checkpoints and completion use row locks and explicit
owner checks; a heartbeat or stale generation must never authorize archiving.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import copy
import json
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_status import SyncStatus
from app.models.audit import AuditEvent
from app.audit import append_audit


# Contracts §5 watermark keys — kept as a tuple so the settings
# integration health page + the freshness envelope in the pipeline
# response can enumerate the same set without drift.
WATERMARK_KEYS: tuple[str, ...] = (
    "hubspot_backfill",
    "hubspot_webhook_received",
    "hubspot_webhook_processed",
    "hubspot_reconcile",
    "hubspot_owner_mirror",
    "hubspot_pipeline_mirror",
    "hubspot_property_business_unit",
    "hubspot_dlq_oldest_age_seconds",
    "hubspot_queue_backlog_seconds",
)


def _has_column(row: SyncStatus, name: str) -> bool:
    """Feature-detect the new watermark columns.

    Until the Lead lands the D4 migration on staging (see
    ``requests.md`` W1-...-01), the columns won't exist on the running
    Postgres schema even though the model declares them. SQLite tests
    always have them because ``Base.metadata.create_all`` uses the model.
    """

    try:
        getattr(row, name)
    except (AttributeError, Exception):
        return False
    return True


async def _get_or_create(session: AsyncSession, source: str) -> SyncStatus:
    row = await session.get(SyncStatus, source)
    if row is None:
        row = SyncStatus(source=source)
        session.add(row)
    return row


async def touch_source(
    session: AsyncSession,
    *,
    source: str,
    success: bool,
    error: str | None,
    cursor: str | None = None,
    # ---- S20 W1 typed watermark toggles (contracts §5) -------------------
    # Every keyword defaults False so existing callers keep the S19 shape;
    # newer callers pick the exact clock they advance.
    mark_received: bool = False,
    mark_processed: bool = False,
    mark_reconciled: bool = False,
    scan_generation: int | None = None,
    scan_started: bool = False,
    scan_completed: bool = False,
    backlog_age_seconds: int | None = None,
    dlq_age_seconds: int | None = None,
) -> SyncStatus:
    """Upsert the ``sync_status`` row for ``source``.

    ``success=True`` clears ``last_error`` and bumps ``last_success_at``
    to now (and ``lag_seconds`` to 0). ``success=False`` sets
    ``last_error`` but leaves ``last_success_at`` untouched so the UI
    still knows when the source was last healthy.

    The S20 typed watermarks are set independently — a webhook receiver
    can call ``touch_source(mark_received=True, success=True)`` and the
    intake consumer follows with ``touch_source(mark_processed=True,
    success=True)``. Neither overwrites the other's clock.
    """

    now = datetime.now(tz=UTC)
    row = await _get_or_create(session, source)
    row.last_attempt_at = now
    if success:
        row.last_success_at = now
        row.last_error = None
        row.lag_seconds = 0
    else:
        row.last_error = (error or "unknown")[:1024]
        if row.last_success_at is not None:
            # SQLite drops tz info on DateTime(timezone=True) round-trips;
            # normalise both sides to UTC-aware so the diff is well-defined.
            last = row.last_success_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            row.lag_seconds = int((now - last).total_seconds())
    if cursor is not None:
        row.cursor = cursor[:255]

    # ---- Typed watermarks --------------------------------------------------
    # Assign only when the column exists in the running schema; feature-
    # detected so a service call in a partially-migrated staging window
    # never blows up (D5 backward-compat).
    if mark_received and hasattr(row, "received_at"):
        row.received_at = now
    if mark_processed and hasattr(row, "processed_at"):
        row.processed_at = now
    if mark_reconciled and hasattr(row, "reconciled_at"):
        row.reconciled_at = now
    if scan_generation is not None and hasattr(row, "scan_generation"):
        row.scan_generation = int(scan_generation)
    if scan_started and hasattr(row, "scan_started_at"):
        row.scan_started_at = now
    if scan_completed and hasattr(row, "scan_completed_at"):
        row.scan_completed_at = now
    if backlog_age_seconds is not None and hasattr(row, "backlog_age_seconds"):
        row.backlog_age_seconds = int(backlog_age_seconds)
    if dlq_age_seconds is not None and hasattr(row, "dlq_age_seconds"):
        row.dlq_age_seconds = int(dlq_age_seconds)

    return row


async def claim_scan_generation(
    session: AsyncSession, *, source: str
) -> int:
    """A3 · T33 — increment and persist a new scan generation for ``source``.

    Called at the start of ``run_backfill``. The generation is stamped on
    every row seen during the scan; archive-not-seen only runs after
    :func:`mark_scan_completed` stamps ``scan_completed_at``.

    Falls back to a heartbeat-only touch when the new column isn't yet in
    the schema — the archive suppression still holds because the caller
    also checks the completed timestamp.
    """

    row = await _get_or_create(session, source)
    now = datetime.now(tz=UTC)
    row.last_attempt_at = now
    current = getattr(row, "scan_generation", None) or 0
    next_gen = current + 1
    if hasattr(row, "scan_generation"):
        row.scan_generation = next_gen
    if hasattr(row, "scan_started_at"):
        row.scan_started_at = now
    if hasattr(row, "scan_completed_at"):
        # A generation in flight means the previous completion no longer
        # applies to *this* run. Clear it so the archive gate is closed
        # until we finish.
        row.scan_completed_at = None
    return next_gen


async def mark_scan_completed(
    session: AsyncSession, *, source: str, generation: int
) -> None:
    """Stamp ``scan_completed_at`` for the current generation.

    Only called from the archive-sweep path AFTER pagination + every
    per-deal upsert has succeeded. If the current row's generation no
    longer matches (e.g. a newer scan started concurrently), the caller
    must skip the archive sweep.
    """

    row = await _get_or_create(session, source)
    if hasattr(row, "scan_generation") and row.scan_generation not in (generation, None):
        return
    if hasattr(row, "scan_completed_at"):
        row.scan_completed_at = datetime.now(tz=UTC)


class ScanConflict(RuntimeError):
    """A scan owner, phase or checkpoint no longer matches persisted state."""


@dataclass(frozen=True)
class ScanLease:
    source: str
    generation: int
    token: uuid.UUID
    context_json: str
    cursor: str | None
    phase: str
    lease_seconds: int


def _context_json(context: dict) -> str:
    required = ("schema_version", "tenant", "environment", "portal_id")
    if not isinstance(context, dict) or any(not context.get(key) for key in required):
        raise ValueError("Scan context requires version, tenant, environment and portal")
    return json.dumps(context, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


async def _scan_now(session: AsyncSession) -> datetime:
    # PostgreSQL now() is transaction-start time, unsuitable after waiting for a lock.
    if session.bind.dialect.name == "postgresql":
        return _utc((await session.execute(select(func.clock_timestamp()))).scalar_one())
    return datetime.now(UTC)


async def _locked_scan(session: AsyncSession, source: str) -> SyncStatus:
    row = (await session.execute(select(SyncStatus).where(SyncStatus.source == source)
        .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None:
        raise ScanConflict("Scan state no longer exists")
    return row


async def _ensure_scan(session: AsyncSession, source: str) -> SyncStatus:
    # ON CONFLICT serializes first acquisition too; a select-then-insert races.
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    await session.execute(insert(SyncStatus).values(source=source).on_conflict_do_nothing(index_elements=["source"]))
    return await _locked_scan(session, source)


async def record_scan_attempt_failure(session: AsyncSession, *, source: str, scope: dict, error: str) -> bool:
    """Expose pre-lease failures without overwriting another owner's active work."""
    row = await _ensure_scan(session, source)
    now = await _scan_now(session)
    if row.scan_context and any(row.scan_context.get(key) != scope.get(key)
        for key in ("tenant", "environment", "portal_id")):
        return False
    if row.scan_lease_token and row.scan_lease_expires_at and _utc(row.scan_lease_expires_at) > now:
        return False
    row.last_attempt_at = now
    row.last_error = error[:1024]
    if row.last_success_at:
        row.lag_seconds = max(0, int((now - _utc(row.last_success_at)).total_seconds()))
    await session.flush()
    return True


async def acquire_scan(session: AsyncSession, *, source: str, context: dict,
    lease_seconds: int = 120) -> ScanLease:
    """Acquire or resume under a row lock; caller commits before provider I/O."""
    if not isinstance(lease_seconds, int) or isinstance(lease_seconds, bool) or not 1 <= lease_seconds <= 3600:
        raise ValueError("Scan lease must be between 1 and 3600 seconds")
    encoded = _context_json(context)
    row = await _ensure_scan(session, source)
    now = await _scan_now(session)
    if row.scan_context and any(row.scan_context.get(key) != context[key]
        for key in ("tenant", "environment", "portal_id")):
        raise ScanConflict("Scan source is bound to a different tenant, environment or portal")
    if row.scan_lease_token and row.scan_lease_expires_at and _utc(row.scan_lease_expires_at) > now:
        raise ScanConflict("Scan is already leased")
    resumable = (row.scan_phase in {"scanning", "finalizing", "failed"}
        and row.scan_context == context and row.scan_started_at is not None)
    if not resumable:
        row.scan_generation = (row.scan_generation or 0) + 1
        row.scan_started_at = now
        row.scan_completed_at = None
        row.cursor = None
        row.scan_failure_count = 0
        row.scan_context = copy.deepcopy(context)
        row.scan_phase = "scanning"
    elif row.scan_phase == "failed":
        # A failed finalizer has cursor NULL, but must refetch an end page before
        # re-entering finalizing. Never infer success from an empty cursor alone.
        row.scan_phase = "scanning"
    row.scan_lease_token = uuid.uuid4()
    row.scan_lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.last_attempt_at = now
    await session.flush()
    return ScanLease(source, row.scan_generation, row.scan_lease_token, encoded,
        row.cursor, row.scan_phase, lease_seconds)


async def _owned_scan(session: AsyncSession, lease: ScanLease, phases: set[str]) -> tuple[SyncStatus, datetime]:
    row = await _locked_scan(session, lease.source)
    now = await _scan_now(session)
    if (row.scan_generation != lease.generation or row.scan_lease_token != lease.token
        or _context_json(row.scan_context) != lease.context_json):
        raise ScanConflict("Scan owner or context changed")
    if row.scan_lease_expires_at is None or _utc(row.scan_lease_expires_at) <= now:
        raise ScanConflict("Scan lease expired")
    if row.scan_phase not in phases:
        raise ScanConflict("Scan phase does not permit this transition")
    return row, now


async def checkpoint_scan(session: AsyncSession, lease: ScanLease, *,
    expected_cursor: str | None, next_cursor: str | None) -> None:
    """Commit record effects and the cursor in the caller's SAME transaction."""
    if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor
        or len(next_cursor) > 255 or next_cursor == expected_cursor):
        raise ValueError("Invalid or nonadvancing scan cursor")
    row, now = await _owned_scan(session, lease, {"scanning"})
    if row.cursor != expected_cursor:
        raise ScanConflict("Scan cursor changed")
    if next_cursor is not None:
        prior = await session.scalar(select(AuditEvent.id).where(
            AuditEvent.entity == "sync_status", AuditEvent.entity_id == lease.source,
            AuditEvent.action == "hubspot.scan_page_committed",
            AuditEvent.after["scan_generation"].as_integer() == lease.generation,
            AuditEvent.after["next_cursor"].as_string() == next_cursor).limit(1))
        if prior is not None:
            raise ValueError("Scan cursor cycle detected")
    await append_audit(session, actor_id=None, action="hubspot.scan_page_committed",
        entity="sync_status", entity_id=lease.source,
        before={"cursor": expected_cursor},
        after={"scan_generation": lease.generation, "next_cursor": next_cursor},
        correlation_id=f"hubspot:scan:{lease.source}:{lease.generation}")
    row.cursor = next_cursor
    row.scan_phase = "finalizing" if next_cursor is None else "scanning"
    row.scan_lease_expires_at = now + timedelta(seconds=lease.lease_seconds)
    row.last_attempt_at = now
    await session.flush()


async def fail_scan(session: AsyncSession, lease: ScanLease, *, error: str) -> None:
    row, now = await _owned_scan(session, lease, {"scanning", "finalizing"})
    row.scan_phase = "failed"
    row.scan_failure_count += 1
    row.last_error = error[:1024]
    row.last_attempt_at = now
    row.scan_lease_token = None
    row.scan_lease_expires_at = None
    await session.flush()


async def complete_scan(session: AsyncSession, lease: ScanLease) -> None:
    """Call after validated finalization effects, before the same transaction commits."""
    row, now = await _owned_scan(session, lease, {"finalizing"})
    row.scan_phase = "completed"
    row.scan_completed_at = now
    row.reconciled_at = now
    row.last_success_at = now
    row.last_attempt_at = now
    row.last_error = None
    row.lag_seconds = 0
    row.scan_lease_token = None
    row.scan_lease_expires_at = None
    await session.flush()
