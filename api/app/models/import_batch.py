"""S10-02 bulk-import ORM models.

Two tables land in migration 0028: ``import_batch`` (the envelope for
one bulk-upload session) and ``import_file`` (per-file lifecycle). The
service in ``app.services.bulk_import`` is the only writer.

Also extends ``SowVersion`` with:

- ``execution_state`` (draft | executed | superseded) — imported SOWs
  with a signature page or later reviewer confirmation move to
  ``executed``, which is what triggers the renewal schedule.
- ``governance_status`` — application-side flag. Legacy imports land as
  ``legacy_not_evidenced``; the value is never ``approved`` for a
  bulk-imported row (CLAUDE.md rollout rule).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


IMPORT_BATCH_STATUSES: tuple[str, ...] = ("processing", "completed", "failed")

IMPORT_FILE_STATUSES: tuple[str, ...] = (
    "queued",
    "extracting",
    "classifying",
    "matching_client",
    "deriving_gm",
    "needs_review",
    "imported",
    "rejected",
    "duplicate",
)


class ImportBatch(Base):
    __tablename__ = "import_batch"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="processing"
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportFile(Base):
    __tablename__ = "import_file"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("import_batch.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(128), nullable=False)
    detected_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="queued"
    )
    matched_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=True
    )
    matched_confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=True
    )
    sow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=True
    )
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=True
    )
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonB, nullable=False, default=list
    )
    errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JsonB, nullable=False, default=list
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# Extend SowVersion with execution_state + governance_status without editing
# the file agent P owns. Idempotent (mirrors the legacy import pattern).
from app.models.sow import SowVersion  # noqa: E402


def _add_column(cls, name: str, column: Column) -> None:
    if hasattr(cls, name):
        return
    column.name = name
    cls.__table__.append_column(column)
    cls.__mapper__.add_property(name, cls.__table__.c[name])


_add_column(
    SowVersion,
    "execution_state",
    Column(String(16), nullable=False, default="draft", server_default="draft"),
)
_add_column(
    SowVersion,
    "governance_status",
    Column(String(48), nullable=True),
)


__all__ = [
    "IMPORT_BATCH_STATUSES",
    "IMPORT_FILE_STATUSES",
    "ImportBatch",
    "ImportFile",
]
