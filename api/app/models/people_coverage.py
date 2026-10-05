"""Explicit version-bound staffing coverage, independent of monetary conversion."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB


class DemandCoverageRoot(Base):
    __tablename__ = "demand_coverage"
    __table_args__ = (
        UniqueConstraint("tenant_id", "environment", "plan_publication_id", "project_publication_id", name="uq_demand_coverage_pair"),
        CheckConstraint("plan_publication_id <> project_publication_id", name="ck_demand_coverage_pair"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    plan_publication_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False)
    project_publication_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication.id", ondelete="CASCADE"), nullable=False)


class DemandCoverageVersion(Base):
    __tablename__ = "demand_coverage_version"
    __table_args__ = (
        UniqueConstraint("root_id", "revision", name="uq_demand_coverage_revision"),
        UniqueConstraint("root_id", "request_key", name="uq_demand_coverage_request"),
        CheckConstraint("revision > 0", name="ck_demand_coverage_revision"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    root_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_coverage.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False)
    project_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("demand_publication_version.id", ondelete="CASCADE"), nullable=False)
    mappings: Mapped[list[dict]] = mapped_column(JsonB, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
