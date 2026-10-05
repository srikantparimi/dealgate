"""Versioned sourcing proposals, never staffing reservations or hiring authority."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB


class SourcingRuleSet(Base):
    __tablename__ = "sourcing_rule_set"
    __table_args__ = (UniqueConstraint("tenant_id", "environment", "test_fixture", name="uq_sourcing_rule_scope"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, server_default="false", default=False)


class SourcingRuleVersion(Base):
    __tablename__ = "sourcing_rule_version"
    __table_args__ = (
        UniqueConstraint("rule_set_id", "revision", name="uq_sourcing_rule_revision"),
        UniqueConstraint("rule_set_id", "request_key", name="uq_sourcing_rule_request"),
        CheckConstraint("revision > 0", name="ck_sourcing_rule_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_set_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sourcing_rule_set.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rules: Mapped[list[dict]] = mapped_column(JsonB, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SourcingDraft(Base):
    __tablename__ = "sourcing_draft"
    __table_args__ = (UniqueConstraint("publication_id", name="uq_sourcing_draft_publication"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(Uuid,
        ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False)


class SourcingDraftVersion(Base):
    __tablename__ = "sourcing_draft_version"
    __table_args__ = (
        UniqueConstraint("draft_id", "revision", name="uq_sourcing_draft_revision"),
        UniqueConstraint("draft_id", "request_key", name="uq_sourcing_draft_request"),
        CheckConstraint("revision > 0", name="ck_sourcing_draft_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sourcing_draft.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    demand_version_id: Mapped[uuid.UUID] = mapped_column(Uuid,
        ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("sourcing_rule_version.id"), nullable=False)
    source_watermark: Mapped[str] = mapped_column(String(64), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot: Mapped[dict] = mapped_column(JsonB, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
