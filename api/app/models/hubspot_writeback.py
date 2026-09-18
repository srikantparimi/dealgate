"""HubSpot write-back outbox (S4-E2).

Immutable outbox in the classic pattern: one row per governance change we
promised to reflect in HubSpot. The write-back worker
(:mod:`worker.hubspot_writeback`) drains rows in status ``pending``. Rows
themselves are append-only in intent — only the mutable lifecycle columns
(``status``, ``attempts``, ``next_attempt_at``, ``last_error``, ``sent_at``)
are updated as the worker retries.

Blueprint rule (CLAUDE.md #7): HubSpot is master; DealGate writes back only
the three governance properties. See
:data:`app.services.hubspot_writeback.MAP` for the allow-list.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class HubspotWritebackJob(Base):
    __tablename__ = "hubspot_writeback_job"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=False
    )
    hubspot_deal_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSONB payload — the *validated* target state, i.e. only keys allowed
    # by ``app.services.hubspot_writeback.MAP``.
    target_state: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    # pending | sent | failed | deal_missing.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


__all__ = ["HubspotWritebackJob"]
