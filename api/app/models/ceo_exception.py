"""S4 E7 — CEO exception + delegate ORM models (Agent V, wave 3).

Two tables live here:

- :class:`CeoException`: one row per approval package that entered
  ``pending_ceo_exception``. Rows are set-once (rule 4). The service
  layer fills the brief at draft time, the account owner writes the
  rationale in-place, and the CEO / delegate stamps the decision. There
  is only ever one row per package — approvals are never reused
  (blueprint §6.6).
- :class:`CeoDelegate`: append-only ledger of time-bound delegations.
  Row overlap is allowed (multiple delegates active in the same window)
  and resolved at read time by :func:`app.services.ceo_exception.active_delegate`.

Money never lands here — the brief is stored as opaque JSON that the
GM engine has already computed. LLMs never touch a number (blueprint
§2, CLAUDE.md rule 2).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class CeoException(Base):
    __tablename__ = "ceo_exception"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Agent U owns approval_package. FK is nullable in the migration when
    # the parent table isn't there yet; the service layer guards against
    # orphans and 404s on missing packages.
    package_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Structured GM/policy snapshot the CEO reads. Shape defined by
    # :func:`app.integrations.bedrock_ceo_brief.draft_brief`.
    brief_json: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    # Account owner's business rationale — human words, verbatim. Bedrock
    # may tidy the wording into ``rationale_tidied_text``, but the
    # original text is always kept so audit sees what a human wrote.
    rationale_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_tidied_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_set_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    rationale_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    conditions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 'approve' | 'reject' | 'return_for_changes'. Null until the CEO acts.
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    drafted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CeoDelegate(Base):
    __tablename__ = "ceo_delegate"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    delegate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    expiry: Mapped[date] = mapped_column(Date, nullable=False)
    granted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


__all__ = ["CeoDelegate", "CeoException"]
