"""`audit_event`: append-only chain.

Blueprint §12 requires that the application DB user hold no `UPDATE` or
`DELETE` grant on this table. The grant is enforced in infra (not the ORM).
The row hash chain in `app.audit` provides tamper-evidence on top of the grant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base, JsonB


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonB)
    correlation_id: Mapped[str | None] = mapped_column(String(128))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False)
