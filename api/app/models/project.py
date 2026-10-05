"""S20 W7 · project model.

The Project row is created (or linked, idempotently) at release. It
carries explicit provenance to the deal / SOW / GM model / approval
package, plus a frozen baseline snapshot. Forecast + actuals join on
`project_id`; the snapshot itself never mutates.

Rule 4 (CLAUDE.md): the row is set-once. The service layer refuses
UPDATE on `baseline_snapshot_json`. `UNIQUE (package_id)` provides the
idempotency guard called out in T23.
Rule 5: creation writes a `project.created` audit line; a link (same
package re-releases) writes `project.linked` and does not touch the
baseline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class Project(Base):
    __tablename__ = "project"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("opportunity.id", ondelete="SET NULL"), nullable=True
    )
    sow_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sow_version.id", ondelete="SET NULL"), nullable=True
    )
    gm_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("gm_model.id", ondelete="SET NULL"), nullable=True
    )
    package_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("approval_package.id", ondelete="SET NULL"), nullable=True
    )
    client_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("client.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retained_source: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    # Frozen at release. Stores approved GM totals, resource lines,
    # scope summary, price, term dates, currency. Never mutates.
    baseline_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_reason: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    __table_args__ = (
        UniqueConstraint("package_id", name="uq_project_package"),
    )


__all__ = ["Project"]
