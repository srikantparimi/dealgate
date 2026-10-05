"""Cost-free managed workforce snapshots; imports never authorize hiring."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JsonB
from app.db.decimal import ExactNumeric


class PeopleSource(Base):
    __tablename__ = "people_source"
    __table_args__ = (UniqueConstraint("tenant_id", "environment", "source_system", "test_fixture", name="uq_people_source_scope"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(128), nullable=False)
    test_fixture: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PeopleImportBatch(Base):
    __tablename__ = "people_import_batch"
    __table_args__ = (
        UniqueConstraint("source_id", "revision", name="uq_people_batch_revision"),
        UniqueConstraint("source_id", "request_key", name="uq_people_batch_request"),
        UniqueConstraint("id", "source_id", name="uq_people_batch_source"),
        CheckConstraint("revision > 0 AND person_count >= 0", name="ck_people_batch_counts"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("people_source.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    imported_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(2000), nullable=False)
    person_count: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_batch_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("people_import_batch.id"))


class WorkforcePerson(Base):
    __tablename__ = "workforce_person"
    __table_args__ = (
        UniqueConstraint("source_id", "person_key", name="uq_workforce_person_source_key"),
        UniqueConstraint("id", "source_id", name="uq_workforce_person_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("people_source.id"), nullable=False)
    person_key: Mapped[str] = mapped_column(String(255), nullable=False)


class WorkforceVersion(Base):
    __tablename__ = "workforce_version"
    __table_args__ = (
        UniqueConstraint("person_id", "batch_id", name="uq_workforce_version_snapshot"),
        ForeignKeyConstraint(["person_id", "source_id"], ["workforce_person.id", "workforce_person.source_id"], name="fk_workforce_version_person_source"),
        ForeignKeyConstraint(["batch_id", "source_id"], ["people_import_batch.id", "people_import_batch.source_id"], name="fk_workforce_version_batch_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    person_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(128), nullable=False)
    skills: Mapped[list[str]] = mapped_column(JsonB, nullable=False)
    level: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[str] = mapped_column(String(128), nullable=False)
    timezone: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JsonB, nullable=False)


class WorkforceInterval(Base):
    __tablename__ = "workforce_interval"
    __table_args__ = (
        CheckConstraint("CAST(allocation AS NUMERIC) > 0 AND CAST(allocation AS NUMERIC) <= 1", name="ck_workforce_interval_allocation"),
        CheckConstraint("end_date >= start_date", name="ck_workforce_interval_dates"),
        CheckConstraint("(kind = 'gross' AND assignment_key IS NULL) OR "
            "(kind IN ('committed','reserved','hired') AND assignment_key IS NOT NULL)", name="ck_workforce_interval_basis"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("workforce_version.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    assignment_key: Mapped[str | None] = mapped_column(String(255))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    allocation: Mapped[Decimal] = mapped_column(ExactNumeric(), nullable=False)
