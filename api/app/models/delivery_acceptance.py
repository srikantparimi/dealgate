"""S20 W7 · delivery_acceptance model.

One row per approved package, filed by Delivery ops after the executed
document is verified. Distinct from the approval-workflow decisions and
from client execution — the release gate requires ALL THREE events, not
just the CRM stage or the signed pdf (see review T23).

Rule 4 (CLAUDE.md): the row is set-once. A superseded package never
inherits its predecessor's acceptance — `UNIQUE (package_id)` guards
against that.
Rule 5: every insert writes a `delivery.accepted` audit line (handled by
`app.services.delivery_acceptance`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class DeliveryAcceptance(Base):
    __tablename__ = "delivery_acceptance"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("approval_package.id"), nullable=False
    )
    accepted_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("user.id"), nullable=False
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    staffing_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    billing_setup_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    po_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        UniqueConstraint("package_id", name="uq_delivery_acceptance_package"),
    )


__all__ = ["DeliveryAcceptance"]
