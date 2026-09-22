"""Application-managed routing, separate from identity-provider role claims."""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Text, func, true
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class ApprovalGroup(Base):
    __tablename__ = "approval_group"

    function: Mapped[str] = mapped_column(String(32), primary_key=True)
    member_ids: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    backup_ids: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    default_approver_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))


class ApprovalAssignment(Base):
    __tablename__ = "approval_assignment"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), primary_key=True
    )
    function: Mapped[str] = mapped_column(String(32), primary_key=True)
    approver_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    use_sla: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("task.id"))


class ApprovalConditionEvidence(Base):
    __tablename__ = "approval_condition_evidence"

    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), primary_key=True
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
