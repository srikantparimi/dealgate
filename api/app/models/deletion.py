"""Durable cleanup work and payload-free stale-subject fences."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class DeletionJob(Base):
    __tablename__ = "deletion_job"
    __table_args__ = (
        UniqueConstraint("tenant_id", "environment", "sow_id", name="uq_deletion_sow"),
        UniqueConstraint("tenant_id", "environment", "subject_type", "subject_id", name="uq_deletion_subject"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    sow_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, default="sow", server_default="sow")
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False,
        default=lambda context: context.get_current_parameters()["sow_id"])
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    summary: Mapped[dict] = mapped_column(JsonB, nullable=False)
    objects: Mapped[list] = mapped_column(JsonB, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(1024))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeletionFence(Base):
    __tablename__ = "deletion_fence"
    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("deletion_job.id"), nullable=False)
