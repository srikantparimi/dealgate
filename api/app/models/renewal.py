"""Renewal model (S5 E9 — Agent Y2).

One ``renewal`` per SOW that has (or approaches) a term end. The scheduler
opens the row at ``term_end - 60d`` and the account owner closes it via
``outcome_summary`` (extended | closed | churn) once the client decision
lands.

Rule 4 (CLAUDE.md): the row is set-once on the identity columns
(opportunity_id, term_end, opened_at). ``status``, ``outcome_summary``
and ``replacement_sow_version_id`` are the fields the state machine
mutates — every mutation goes through
``app.services.renewals`` which pairs the change with an ``audit_event``
in the same transaction (rule 5).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


# Kept in lock-step with the alembic 0016 CHECK constraint and the
# ``app.services.renewals.RENEWAL_STATUSES`` tuple.
RENEWAL_STATUSES: tuple[str, ...] = ("open", "closed", "extended", "churn")


class Renewal(Base):
    __tablename__ = "renewal"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=False
    )
    term_end: Mapped[date] = mapped_column(Date, nullable=False)
    trigger_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    replacement_sow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=True
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


__all__ = ["RENEWAL_STATUSES", "Renewal"]
