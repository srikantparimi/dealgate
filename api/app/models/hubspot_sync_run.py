"""S23-PL1 item 1 — one row per HubSpot deal sync run.

``kind`` is ``nightly`` (the EventBridge reconcile), ``manual`` (the
SystemAdmin ``POST /integrations/hubspot/backfill`` trigger) or ``test`` (a
reconcile started with ``--test-failure``, which reads and writes nothing).
A row is inserted as ``running`` before HubSpot is read and finished as
``ok``, ``partial`` or ``failed``. ``errors`` keeps at most five entries of
``{"hubspot_id", "reason"}``; reasons are built by the sync, never copied
from a provider payload, so they carry no names.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB

RUN_KINDS = ("nightly", "manual", "test")
RUN_STATUSES = ("running", "ok", "partial", "failed")


class HubspotSyncRun(Base):
    __tablename__ = "hubspot_sync_run"
    __table_args__ = (
        CheckConstraint("kind IN ('nightly','manual','test')", name="ck_hubspot_sync_run_kind"),
        CheckConstraint(
            "status IN ('running','ok','partial','failed')", name="ck_hubspot_sync_run_status"
        ),
        CheckConstraint(
            "deals_seen >= 0 AND deals_written >= 0 AND error_count >= 0",
            name="ck_hubspot_sync_run_counts",
        ),
        Index("ix_hubspot_sync_run_started_at", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    deals_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    deals_written: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JsonB, nullable=False, default=list)
    fatal_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counts: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
