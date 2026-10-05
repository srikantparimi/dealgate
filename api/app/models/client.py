"""`client`, `legal_entity`, `agreement`.

S17 simplifies `agreement` to a flat document store: id, client_id, kind
(NDA|MSA), file_key/filename/file_size, uploaded_by/uploaded_at. States,
owner, next action, expiry dates and signatories all went with the
agreement-tracking tear-out. The file is the truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Client(Base):
    __tablename__ = "client"
    __table_args__ = (CheckConstraint("business_unit_mapping_version IS NULL OR business_unit_mapping_version > 0",
        name="ck_client_bu_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hubspot_company_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hubspot_owner_id: Mapped[str | None] = mapped_column(String(64), index=True)
    hubspot_owner_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    business_unit_value: Mapped[str | None] = mapped_column(String(255))
    business_unit_mapping_version: Mapped[int | None] = mapped_column(Integer)
    business_unit_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hubspot_last_modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hubspot_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # S13a archive column stays because non-agreement code still filters on
    # it; S17's "delete really removes" contract is enforced in the delete
    # service, not by removing this flag.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    archived_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class LegalEntity(Base):
    __tablename__ = "legal_entity"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Agreement(Base):
    __tablename__ = "agreement"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    file_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("kind IN ('NDA', 'MSA')", name="ck_agreement_kind"),
        CheckConstraint("version_no > 0", name="ck_agreement_version"),
    )


class AgreementFileVersion(Base):
    __tablename__ = "agreement_file_version"
    agreement_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agreement.id"), primary_key=True)
    version_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String(64))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint("version_no > 0", name="ck_agreement_file_version_positive"),)
