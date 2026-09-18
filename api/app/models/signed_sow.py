"""S5 E8 — signed SOW upload ORM model (Agent X2).

One :class:`SignedSowUpload` per ``approval_package`` that has landed
in ``ready_to_sign``. The row is set-once (rule 4) on the identity
columns — file pointer, hash, uploader. The state-machine fields
(``verify_status``, ``diff_json``, ``verified_at``, ``released_at``)
are touched by :mod:`app.services.signed_sow`, which pairs every
change with an ``audit_event`` (rule 5).

Re-uploading a different executed pdf **creates a new row** (audits
``signed_sow.replaced``) — the previous row is left as-is so the
audit trail can reconstruct the sequence. See the service docstring
for the transition rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


# Kept in lock-step with alembic 0015's CHECK constraint and the
# ``VERIFY_STATUSES`` tuple in ``app.services.signed_sow``.
VERIFY_STATUSES: tuple[str, ...] = ("pending", "verified", "blocked")


class SignedSowUpload(Base):
    __tablename__ = "signed_sow_upload"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), nullable=False
    )
    file_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    verify_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    diff_json: Mapped[dict[str, Any] | None] = mapped_column(JsonB, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["VERIFY_STATUSES", "SignedSowUpload"]
