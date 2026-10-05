"""Explicitly opted-in automation policy; immutable revisions retain authority."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutomationRule(Base):
    __tablename__ = "automation_rule"
    __table_args__ = (
        UniqueConstraint("tenant_id", "environment", "test_fixture", "domain", name="uq_automation_rule_scope"),
        CheckConstraint("domain = 'sourcing_refresh'", name="ck_automation_rule_domain"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    domain: Mapped[str] = mapped_column(String(64), nullable=False)


class AutomationRuleVersion(Base):
    __tablename__ = "automation_rule_version"
    __table_args__ = (
        UniqueConstraint("rule_id", "revision", name="uq_automation_rule_revision"),
        UniqueConstraint("rule_id", "request_key", name="uq_automation_rule_request"),
        CheckConstraint("revision > 0", name="ck_automation_rule_revision"),
        CheckConstraint("source_scope = 'authorized_sources'", name="ck_automation_rule_source_scope"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("automation_rule.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    source_scope: Mapped[str] = mapped_column(String(64), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AutomationJob(Base):
    __tablename__ = "automation_job"
    __table_args__ = (
        UniqueConstraint("rule_version_id", "source_key", "event_key", name="uq_automation_job_event"),
        CheckConstraint("(plan_version_id IS NOT NULL AND project_id IS NULL) OR "
            "(plan_version_id IS NULL AND project_id IS NOT NULL)", name="ck_automation_job_source"),
        CheckConstraint("attempts >= 0", name="ck_automation_job_attempts"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    rule_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("automation_rule_version.id"), nullable=False)
    plan_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
        ForeignKey("forecast_plan_version.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("project.id", ondelete="CASCADE"))
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(1024))
    result_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid,
        ForeignKey("sourcing_draft_version.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
