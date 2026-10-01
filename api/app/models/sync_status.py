"""Sync status per source (S19 slice 1 A6 → S20 W1 watermarks).

The `hubspot_backfill`, `hubspot_webhook` and `hubspot_reconcile` sources
write here after every run. Pipeline UI reads `lag_seconds` for the amber
"delayed sync" banner. `cursor` persists the last-known `after=` for the
paged backfill so a resumed run doesn't restart from scratch (G14).

S20 W1 (D4, contracts §5) — this table now carries the per-source
watermarks the freshness envelope reads. Every column added is nullable
so migration is backward-compatible (D5). See
:mod:`app.services.sync_status` for the write side and
:mod:`app.services.hubspot_sync` for the consolidated read side.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncStatus(Base):
    __tablename__ = "sync_status"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    lag_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ---- S20 W1 watermarks (contracts §5, D4) -----------------------------
    #
    # Every write path — webhook receiver, intake consumer, reconcile,
    # backfill, owner mirror, pipeline mirror, property mirror — updates
    # exactly one of these columns per call. The old ``last_success_at`` is
    # kept as an "any-write" catch-all so the amber banner keeps working
    # while the freshness envelope migrates to typed keys.

    # Last event verified + persisted (source=hubspot_webhook).
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last event fully handled + audited (source=hubspot_webhook).
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last full reconcile pass (source=hubspot_reconcile).
    reconciled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # A3 · T33 — scan generation for the backfill / reconcile archive
    # policy. A generation is a monotonically-increasing counter; every
    # scan claims a new generation before it starts. Archive-not-seen is
    # only allowed AFTER ``scan_completed_at`` is set for that generation,
    # so a mid-scan failure cannot archive anything.
    scan_generation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scan_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scan_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Queue depth watermarks (source=hubspot_webhook). ``backlog_age`` is
    # the age of the oldest still-visible message; ``dlq_age`` is the age
    # of the oldest DLQ message (0 when DLQ is empty). Both drive the
    # freshness alarms in ``observability/hubspot_freshness.tf``.
    backlog_age_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dlq_age_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
