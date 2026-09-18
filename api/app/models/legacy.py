"""S6 (user-added scope) legacy import models.

Two responsibilities:

1. Ship the ``LegacyImportBatch`` mapper for the new
   ``legacy_import_batch`` table.
2. Extend the existing ``Sow`` (Agent P) and ``SowVersion`` (Agent P) and
   ``GmModel`` (Agent R) mappers with the columns migration 0009 adds — done
   via ``__table__.append_column`` so we don't duplicate class definitions
   or touch files owned by other agents.

Money stays ``NUMERIC`` end-to-end (CLAUDE.md rule 2). Legacy rows
**never** get ``approval_evidenced=True`` — the rollout rule (§13) forbids
backfilling fake approvals.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class LegacyImportBatch(Base):
    __tablename__ = "legacy_import_batch"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sow_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resource_line_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    errors: Mapped[list[dict[str, Any]] | None] = mapped_column(JsonB)
    # uploading -> reviewing -> approved (see CHECK in migration 0009).
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="uploading"
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---- ORM extensions for Agent P / Agent R models -------------------------
# Attach the columns migration 0009 introduces so the ORM classes reflect
# the new shape without editing files owned by other agents. Idempotent: if
# the attribute already exists (later merge), we skip.

from app.models.gm_model import GmModel  # noqa: E402
from app.models.sow import Sow, SowVersion  # noqa: E402


def _add_column(cls, name: str, column: Column) -> None:
    if hasattr(cls, name):
        return
    column.name = name
    cls.__table__.append_column(column)
    cls.__mapper__.add_property(name, cls.__table__.c[name])


_add_column(Sow, "sow_ref", Column(String(128), nullable=True))
_add_column(Sow, "client_id", Column(Uuid, ForeignKey("client.id"), nullable=True))
_add_column(Sow, "filename", Column(String(512), nullable=True))
_add_column(
    Sow,
    "legacy_batch_id",
    Column(Uuid, ForeignKey("legacy_import_batch.id"), nullable=True),
)

_add_column(
    SowVersion,
    "legacy",
    Column(Boolean, nullable=False, default=False, server_default="0"),
)
_add_column(
    SowVersion,
    "approval_evidenced",
    Column(Boolean, nullable=False, default=False, server_default="0"),
)

_add_column(GmModel, "sow_id", Column(Uuid, ForeignKey("sow.id"), nullable=True))


__all__ = ["LegacyImportBatch"]
