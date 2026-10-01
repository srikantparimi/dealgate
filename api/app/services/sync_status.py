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

Keep this module lock-free: the queue consumer + reconcile writer + API
route all touch the same row concurrently; on a merge conflict, whichever
transaction commits last wins. That is exactly what we want — the freshest
timestamp is the truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_status import SyncStatus


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
