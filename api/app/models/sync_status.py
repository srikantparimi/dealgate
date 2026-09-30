"""Sync status per source (S19 slice 1 A6).

The `hubspot_backfill`, `hubspot_webhook` and `hubspot_reconcile` sources
write here after every run. Pipeline UI reads `lag_seconds` for the amber
"delayed sync" banner. `cursor` persists the last-known `after=` for the
paged backfill so a resumed run doesn't restart from scratch (G14).
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
