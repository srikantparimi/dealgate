"""Persistent gap-task identity and source-backed signed agreement drafts."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class AgreementGap(Base):
    __tablename__ = "agreement_gap"
    legal_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("legal_entity.id"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    task_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("task.id"), nullable=False)


class AgreementDocument(Base):
    __tablename__ = "agreement_document"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("agreement.id"), nullable=False
    )
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_s3_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("agreement_id", "file_hash", name="uq_agreement_document_hash"),
    )
