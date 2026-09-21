"""`client`, `legal_entity`, `agreement` — skeletons per build-guide §10.

`Agreement` grew the S2-E3 state-machine columns (§6.2) and the evidence key
alongside the original `kind` / `effective_date` / `expiry_date` fields. The
state list + allowed transitions live in `app.services.agreement_state`; the
model only persists the current value plus dates, next-action and signatories.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class Client(Base):
    __tablename__ = "client"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # S2 E3: HubSpot company id is the natural key we upsert by. Nullable
    # because the ad-hoc "Unknown company (deal <id>)" fallback clients that
    # the intake worker creates when HubSpot returns no company link have
    # no HubSpot side to point at.
    hubspot_company_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # S13a — archive (void), never hard delete once approved. NULL means
    # "live"; every default list filters `WHERE archived_at IS NULL`.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    archived_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class LegalEntity(Base):
    __tablename__ = "legal_entity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Agreement(Base):
    __tablename__ = "agreement"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("legal_entity.id"), nullable=False
    )
    # kind is "NDA" or "MSA" for Sprint 1. Constrained via app logic; enum in a later story.
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # State machine (see `app.services.agreement_state.ALLOWED_STATES`). New
    # rows default to "missing" so the coverage helper still has a value to
    # render for a legal-entity that hasn't started paperwork yet.
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="missing")
    # Ownership + next steps live on the agreement row so the Legal panel can
    # render "who is doing what" without joining `task`.
    owner_email: Mapped[str | None] = mapped_column(String(320))
    next_action: Mapped[str | None] = mapped_column(String(255))
    due_date: Mapped[date | None] = mapped_column(Date)
    # `effective_from` supersedes the original `effective_date`; both are kept
    # so callers written before S2-E3 keep working.
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    notice_days: Mapped[int | None] = mapped_column(Integer)
    # Pointer to the uploaded evidence file in the agreements S3 bucket.
    # NULL until Legal uploads a signed PDF/DOCX; required when state==executed
    # (enforced in `app.services.agreement_state.transition`).
    evidence_s3_key: Mapped[str | None] = mapped_column(String(1024))
    # Free-form list of signatories: [{"name": ..., "email": ..., "role": ...}].
    # Stored as JSONB on Postgres, JSON on SQLite via `JsonB`.
    signatories: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
