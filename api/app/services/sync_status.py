"""S19 slice 1 §H1/H2: sync_status writer.

Every worker (backfill, webhook consumer, nightly reconcile) calls
:func:`touch_source` at the end of each run. The Pipeline UI's amber
banner reads the ``lag_seconds`` column across all rows to decide when
to show "Sync delayed" (lag > 30 min) or "Sync error"
(``last_error IS NOT NULL``).

Keep this module lock-free: the queue consumer + reconcile writer + API
route all touch the same row concurrently; on a merge conflict, whichever
transaction commits last wins. That is exactly what we want — the freshest
timestamp is the truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_status import SyncStatus


async def touch_source(
    session: AsyncSession,
    *,
    source: str,
    success: bool,
    error: str | None,
    cursor: str | None = None,
) -> SyncStatus:
    """Upsert the ``sync_status`` row for ``source``.

    ``success=True`` clears ``last_error`` and bumps ``last_success_at``
    to now (and ``lag_seconds`` to 0). ``success=False`` sets
    ``last_error`` but leaves ``last_success_at`` untouched so the UI
    still knows when the source was last healthy.
    """

    now = datetime.now(tz=UTC)
    row = await session.get(SyncStatus, source)
    if row is None:
        row = SyncStatus(source=source)
        session.add(row)
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
    return row
