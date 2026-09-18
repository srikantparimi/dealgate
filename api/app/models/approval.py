"""S4 E7 — approval_package + approval mappers.

Both tables are immutable versions (CLAUDE.md rule 4): the service layer
never issues UPDATE against them after the initial INSERT for lifecycle
columns (``status`` is the sole mutable field on ``approval_package``;
see ``app.services.approvals`` for the state machine).

Money is not stored on these tables — floor checks re-run on the pinned
``gm_model_id`` + ``policy_version_id`` snapshot so the numbers are
always reproducible from the raw inputs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.db.base import Base


# ---- status alphabet -----------------------------------------------------

PACKAGE_STATUSES: tuple[str, ...] = (
    "pending_delivery_hr",
    "pending_finance_legal",
    "pending_ceo_exception",
    "ready_to_sign",
    "voided",
    "rejected",
)

APPROVAL_FUNCTIONS: tuple[str, ...] = ("delivery", "hr", "finance", "legal")
APPROVAL_DECISIONS: tuple[str, ...] = ("approve", "reject", "request_changes")


class ApprovalPackage(Base):
    __tablename__ = "approval_package"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("opportunity.id"), nullable=False
    )
    sow_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sow_version.id"), nullable=False
    )
    gm_model_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("gm_model.id"), nullable=False
    )
    package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voided_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("policy_version.id"), nullable=True
    )

    approvals: Mapped[list["Approval"]] = relationship(
        "Approval",
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="Approval.decided_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending_delivery_hr', 'pending_finance_legal', "
            "'pending_ceo_exception', 'ready_to_sign', 'voided', 'rejected'"
            ")",
            name="ck_approval_package_status",
        ),
    )


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), nullable=False
    )
    function: Mapped[str] = mapped_column(String(16), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    package: Mapped[ApprovalPackage] = relationship(
        "ApprovalPackage", back_populates="approvals"
    )

    __table_args__ = (
        CheckConstraint(
            "function IN ('delivery', 'hr', 'finance', 'legal')",
            name="ck_approval_function",
        ),
        CheckConstraint(
            "decision IN ('approve', 'reject', 'request_changes')",
            name="ck_approval_decision",
        ),
        UniqueConstraint(
            "package_id", "function", "approver_id",
            name="uq_approval_pkg_function_approver",
        ),
    )


__all__ = [
    "APPROVAL_DECISIONS",
    "APPROVAL_FUNCTIONS",
    "Approval",
    "ApprovalPackage",
    "PACKAGE_STATUSES",
]
