"""S20 W1 (D4, contracts §§3, 5): consolidated HubSpot sync watermark reader.

Every settings/integrations health card and the freshness envelope on the
Pipeline response reads through :func:`get_watermarks`. It hides the
storage layout — right now every watermark is a column on ``sync_status``,
but the API this module exposes is stable so a future move to a wide
``watermark`` table doesn't ripple.

The freshness state is derived here, not on the UI. Rules from
contracts §3:

- ``verified working`` — ``processed_at`` ≤ 2 min behind ``received_at``
  and last error nil.
- ``Stale`` — the gap > 2 min.
- ``Failed`` — the last worker run had a non-null error.

W4 (settings integrations page) is the primary read consumer. W2's
pipeline list responses embed the same object in their meta.freshness
key.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_status import SyncStatus
from app.services.sync_status import WATERMARK_KEYS

# The freshness envelope calls the tolerable event-to-processed gap
# "typically under 2 minutes" (D4). 120 s is the operative threshold; the
# Stale UI banner turns amber at 120s + 1s.
STALE_AFTER_SECONDS: int = 120


@dataclass(frozen=True)
class SourceWatermark:
    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    received_at: datetime | None
    processed_at: datetime | None
    reconciled_at: datetime | None
    scan_generation: int | None
    scan_started_at: datetime | None
    scan_completed_at: datetime | None
    backlog_age_seconds: int | None
    dlq_age_seconds: int | None
    last_error: str | None
    cursor: str | None

    def as_dict(self) -> dict[str, Any]:
        def _iso(dt: datetime | None) -> str | None:
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).isoformat()

        return {
            "source": self.source,
            "last_success_at": _iso(self.last_success_at),
            "last_attempt_at": _iso(self.last_attempt_at),
            "received_at": _iso(self.received_at),
            "processed_at": _iso(self.processed_at),
            "reconciled_at": _iso(self.reconciled_at),
            "scan_generation": self.scan_generation,
            "scan_started_at": _iso(self.scan_started_at),
            "scan_completed_at": _iso(self.scan_completed_at),
            "backlog_age_seconds": self.backlog_age_seconds,
            "dlq_age_seconds": self.dlq_age_seconds,
            "last_error": self.last_error,
            "cursor": self.cursor,
        }


@dataclass(frozen=True)
class FreshnessEnvelope:
    """Contract §3 freshness object embedded in every list response."""

    source: str  # "hubspot_mirror" or "local_workflow"
    received_at: datetime | None
    processed_at: datetime | None
    reconciled_at: datetime | None
    state: str  # "verified working" | "Stale" | "Failed" | "Unknown"
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        def _iso(dt: datetime | None) -> str | None:
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).isoformat()

        return {
            "source": self.source,
            "received_at": _iso(self.received_at),
            "processed_at": _iso(self.processed_at),
            "reconciled_at": _iso(self.reconciled_at),
            "state": self.state,
            "reason": self.reason,
        }


def _read_attr(row: SyncStatus, name: str) -> Any:
    """Feature-detected getter — the D4 columns land in a Lead migration.

    Until that lands on staging, reading a missing attribute would raise;
    the model always declares the columns because
    ``Base.metadata.create_all`` covers SQLite tests, but the running
    Postgres schema may still be pre-migration for a short window.
    """

    return getattr(row, name, None)


async def get_watermarks(
    session: AsyncSession,
    *,
    sources: tuple[str, ...] | None = None,
) -> list[SourceWatermark]:
    """Return watermarks for the requested sources.

    ``sources=None`` returns the full set enumerated in contracts §5.
    Missing rows are returned as blank-timestamp entries so the UI can
    still render "Not observed yet" instead of dropping the tile.
    """

    wanted = tuple(sources) if sources else WATERMARK_KEYS
    rows = (
        await session.execute(
            select(SyncStatus).where(SyncStatus.source.in_(wanted))
        )
    ).scalars().all()
    by_source = {row.source: row for row in rows}
    out: list[SourceWatermark] = []
    for source in wanted:
        row = by_source.get(source)
        if row is None:
            out.append(
                SourceWatermark(
                    source=source,
                    last_success_at=None,
                    last_attempt_at=None,
                    received_at=None,
                    processed_at=None,
                    reconciled_at=None,
                    scan_generation=None,
                    scan_started_at=None,
                    scan_completed_at=None,
                    backlog_age_seconds=None,
                    dlq_age_seconds=None,
                    last_error=None,
                    cursor=None,
                )
            )
            continue
        out.append(
            SourceWatermark(
                source=row.source,
                last_success_at=row.last_success_at,
                last_attempt_at=row.last_attempt_at,
                received_at=_read_attr(row, "received_at"),
                processed_at=_read_attr(row, "processed_at"),
                reconciled_at=_read_attr(row, "reconciled_at"),
                scan_generation=_read_attr(row, "scan_generation"),
                scan_started_at=_read_attr(row, "scan_started_at"),
                scan_completed_at=_read_attr(row, "scan_completed_at"),
                backlog_age_seconds=_read_attr(row, "backlog_age_seconds"),
                dlq_age_seconds=_read_attr(row, "dlq_age_seconds"),
                last_error=row.last_error,
                cursor=row.cursor,
            )
        )
    return out


def _normalise_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(UTC) if dt.tzinfo else dt.replace(tzinfo=UTC)


async def get_hubspot_freshness(
    session: AsyncSession, *, now: datetime | None = None
) -> FreshnessEnvelope:
    """Compute the ``meta.freshness`` object for a HubSpot-sourced list.

    Rolls up the webhook/reconcile watermarks into the contract §3 shape.
    Called from W2's pipeline endpoints and W4's health page.
    """

    now = now or datetime.now(tz=UTC)
    marks = await get_watermarks(
        session,
        sources=(
            "hubspot_webhook_received",
            "hubspot_webhook_processed",
            "hubspot_reconcile",
        ),
    )
    by_source = {m.source: m for m in marks}

    received = _normalise_utc(
        by_source["hubspot_webhook_received"].received_at
        if "hubspot_webhook_received" in by_source
        else None
    )
    processed = _normalise_utc(
        by_source["hubspot_webhook_processed"].processed_at
        if "hubspot_webhook_processed" in by_source
        else None
    )
    reconciled = _normalise_utc(
        by_source["hubspot_reconcile"].reconciled_at
        if "hubspot_reconcile" in by_source
        else None
    )

    # If any watermark reports a live error, surface Failed.
    for mark in marks:
        if mark.last_error:
            return FreshnessEnvelope(
                source="hubspot_mirror",
                received_at=received,
                processed_at=processed,
                reconciled_at=reconciled,
                state="Failed",
                reason=mark.last_error[:255],
            )

    # No events yet — Unknown rather than a misleading "verified working".
    if received is None and processed is None:
        return FreshnessEnvelope(
            source="hubspot_mirror",
            received_at=None,
            processed_at=None,
            reconciled_at=reconciled,
            state="Unknown",
            reason="No HubSpot events observed yet",
        )

    if received is not None and processed is not None:
        gap = received - processed
        if gap > timedelta(seconds=STALE_AFTER_SECONDS):
            return FreshnessEnvelope(
                source="hubspot_mirror",
                received_at=received,
                processed_at=processed,
                reconciled_at=reconciled,
                state="Stale",
                reason=(
                    f"received→processed gap {int(gap.total_seconds())}s > "
                    f"{STALE_AFTER_SECONDS}s"
                ),
            )

    return FreshnessEnvelope(
        source="hubspot_mirror",
        received_at=received,
        processed_at=processed,
        reconciled_at=reconciled,
        state="verified working",
        reason=None,
    )
