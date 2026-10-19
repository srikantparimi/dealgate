"""S24-AG1 agreement tables: standard copies, marks, batches, settings, HubSpot map.

A standard copy is ONE stored object (``standard_agreement``); every client it
is attached to has its own ``agreement`` row of source ``standard`` pointing at
it. A mark records a kind as covered with no file. A batch is the one-time
attach (dry run first, then a resumable job with undo). ``agreements_settings``
holds the cutover date, set once by the first real batch and never moved.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB

KINDS: tuple[str, ...] = ("NDA", "MSA")
MARK_REASONS: tuple[str, ...] = (
    "signed_outside_dealgate", "covered_by_earlier_work", "confirmed_with_client", "per_hubspot", "other",
)
BATCH_STATUSES: tuple[str, ...] = ("running", "done", "failed", "undoing", "undone")


class StandardAgreement(Base):
    """One version of the standard NDA or MSA. A new version never touches copies already attached."""

    __tablename__ = "standard_agreement"
    __table_args__ = (
        CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_standard_agreement_kind"),
        CheckConstraint("version_no > 0", name="ck_standard_agreement_version"),
        UniqueConstraint("kind", "version_no", name="uq_standard_agreement_kind_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AgreementBatch(Base):
    """The one-time attach of the standard copies, run as a resumable job.

    ``label`` (AG-0001, …) is the id the API and the page show. ``target_client_ids``
    is the ordered target list frozen when the job starts; ``done_count`` is the
    cursor into it, so a killed job resumes where it stopped. ``running_guard`` is
    TRUE while the batch runs or undoes and NULL otherwise; its unique index lets at
    most one batch run at a time.
    """

    __tablename__ = "agreement_batch"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed', 'undoing', 'undone')", name="ck_agreement_batch_status"
        ),
        CheckConstraint("running_guard IS NULL OR running_guard", name="ck_agreement_batch_guard"),
        CheckConstraint(
            "target_count >= 0 AND done_count >= 0 AND attached_count >= 0 AND skipped_count >= 0 "
            "AND attached_clients >= 0 AND undone_count >= 0",
            name="ck_agreement_batch_counts",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running", server_default="running")
    kinds: Mapped[list] = mapped_column(JsonB, nullable=False)
    include_net_new: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    target_client_ids: Mapped[list] = mapped_column(JsonB, nullable=False)
    # {kind: standard_agreement id} frozen when the batch starts, so a standard uploaded while the
    # job runs (or before a resume) is never mixed in.
    standard_ids: Mapped[dict] = mapped_column(JsonB, nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    done_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    attached_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Clients that received at least one copy (attached_count counts rows; a client with both kinds is 2).
    attached_clients: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    undone_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    running_guard: Mapped[bool | None] = mapped_column(Boolean, nullable=True, unique=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"), nullable=True)


class AgreementMark(Base):
    """A kind marked covered with no file. At most one active mark per client and kind; removal is soft."""

    __tablename__ = "agreement_mark"
    __table_args__ = (
        CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_agreement_mark_kind"),
        CheckConstraint(
            "reason IN ('signed_outside_dealgate', 'covered_by_earlier_work', 'confirmed_with_client', "
            "'per_hubspot', 'other')",
            name="ck_agreement_mark_reason",
        ),
        CheckConstraint("source IN ('dealgate', 'hubspot')", name="ck_agreement_mark_source"),
        Index(
            "ux_agreement_mark_active",
            "client_id",
            "kind",
            unique=True,
            postgresql_where=text("removed_at IS NULL"),
            sqlite_where=text("removed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("client.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    marked_on: Mapped[date] = mapped_column(Date, nullable=False)
    marked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="dealgate", server_default="dealgate")
    hubspot_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    removed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"), nullable=True)


class AgreementsSettings(Base):
    """Singleton (id = 1). ``cutover_date`` is the America/Los_Angeles date of the first real batch; never moved."""

    __tablename__ = "agreements_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_agreements_settings_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    cutover_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    set_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"), nullable=True)
    set_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AgreementHubspotMap(Base):
    """Which HubSpot ``msa_type`` values mean the MSA is covered. Saved by a SystemAdmin."""

    __tablename__ = "agreement_hubspot_map"
    __table_args__ = (CheckConstraint("action IN ('covered', 'ignore')", name="ck_agreement_hubspot_map_action"),)

    value: Mapped[str] = mapped_column(String(200), primary_key=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


__all__ = [
    "AgreementBatch", "AgreementHubspotMap", "AgreementMark", "AgreementsSettings", "StandardAgreement",
    "BATCH_STATUSES", "KINDS", "MARK_REASONS",
]
