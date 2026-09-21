from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


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
