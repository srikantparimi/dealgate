"""Immutable cost-free demand publications owned by plans or retained projects."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB
from app.db.decimal import ExactNumeric


class DemandPublication(Base):
    __tablename__ = "demand_publication"
    __table_args__ = (
        UniqueConstraint("tenant_id", "environment", "plan_id", name="uq_demand_publication_plan"),
        UniqueConstraint("tenant_id", "environment", "project_id", name="uq_demand_publication_project"),
        CheckConstraint("(plan_id IS NOT NULL AND project_id IS NULL) OR (plan_id IS NULL AND project_id IS NOT NULL)", name="ck_demand_publication_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("forecast_plan.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("project.id", ondelete="CASCADE"))
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("client.id", ondelete="SET NULL"))
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DemandPublicationVersion(Base):
    __tablename__ = "demand_publication_version"
    __table_args__ = (
        UniqueConstraint("publication_id", "version", name="uq_demand_publication_version"),
        UniqueConstraint("publication_id", "request_key", name="uq_demand_publication_request"),
        CheckConstraint("version > 0", name="ck_demand_publication_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    publication_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_metadata: Mapped[dict] = mapped_column(JsonB, nullable=False)
    missing: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DemandLine(Base):
    __tablename__ = "demand_line"
    __table_args__ = (
        UniqueConstraint("version_id", "line_key", name="uq_demand_line_version_key"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_demand_line_quantity"),
        CheckConstraint("allocation IS NULL OR (CAST(allocation AS NUMERIC) > 0 AND CAST(allocation AS NUMERIC) <= 1)", name="ck_demand_line_allocation"),
        CheckConstraint("start_date IS NULL OR end_date IS NULL OR end_date >= start_date", name="ck_demand_line_dates"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False, index=True)
    line_key: Mapped[str] = mapped_column(String(255), nullable=False)
    component_id: Mapped[str] = mapped_column(String(255), nullable=False)
    assignment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    skills: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    level: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer)
    allocation: Mapped[Decimal | None] = mapped_column(ExactNumeric())
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    delivery_model: Mapped[str] = mapped_column(String(64), nullable=False)
    retained_person_ids: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    missing: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
