from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base

_JsonB = JSON().with_variant(JSONB(), "postgresql")


class Opportunity(Base):
    __tablename__ = "opportunity"

    # S10-01: partial unique index — only NON-NULL hubspot_deal_id values
    # must be unique. Postgres uses `postgresql_where`; SQLite supports
    # `sqlite_where`. Both are honoured by `Base.metadata.create_all` and
    # by the alembic migration.
    __table_args__ = (
        Index(
            "ux_opportunity_hubspot_deal_id_not_null",
            "hubspot_deal_id",
            unique=True,
            postgresql_where=text("hubspot_deal_id IS NOT NULL"),
            sqlite_where=text("hubspot_deal_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # S10-01: `hubspot_deal_id` is nullable now because a SOW-upload
    # opportunity can exist without a HubSpot deal. Uniqueness is enforced
    # by the partial index `ux_opportunity_hubspot_deal_id_not_null` (see
    # migration 20260921_0028_sow_upload_pipeline.py), so NULLs never collide.
    hubspot_deal_id: Mapped[str | None] = mapped_column(
        String(64), unique=False, nullable=True
    )
    # S10-01: provenance of the row — HubSpot webhook, SOW upload, bulk
    # import, or a manual create. The check constraint lives in the
    # migration; the app-level validator is a str-in-set assertion.
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="hubspot", server_default="hubspot"
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    # S2 E3: opportunity -> client link. Nullable during backfill; the intake
    # worker sets it going forward. Sprint 3 will migrate this to NOT NULL
    # once historical rows are backfilled from HubSpot associations.
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=True
    )
    engagement_type: Mapped[str | None] = mapped_column(String(64))
    sales_stage: Mapped[str | None] = mapped_column(String(64))
    # governance_status is the DealGate-owned state (Intake → Coverage → SOWDraft → ...).
    governance_status: Mapped[str] = mapped_column(String(64), nullable=False, default="Intake")
    next_client_action: Mapped[str | None] = mapped_column(String(255))
    next_client_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # S13a — archive columns; see app.services.deletion.
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    archived_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # S18 §2 — HubSpot cache. Populated on backfill / webhook / reconcile.
    # Pipeline reads these directly; SOW-upload opportunities leave them null.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    stage_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # S20 W2 · L04. `name` mirrors HubSpot's `dealname` so the Pipeline
    # + list surfaces render the real deal title instead of the stage
    # label fallback (S19 slice-1 renderer used stage_label when name
    # was missing; that path is now the true fallback for non-HubSpot
    # sources like SOW-upload). Nullable because SOW-upload records can
    # still legitimately have no dealname.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hubspot_last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # S19 slice 1 — pipeline mirror keys + closed flags + currency +
    # HubSpot timestamps + multi-company support. Every non-boolean nullable
    # so SOW-upload opportunities can leave them all empty.
    hubspot_pipeline_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hubspot_stage_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    stage_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_closed_won: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    is_closed_lost: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hubspot_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hubspot_last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    hubspot_last_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    primary_client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("client.id"), nullable=True
    )
    hubspot_secondary_client_ids: Mapped[Any | None] = mapped_column(
        _JsonB, nullable=True
    )
