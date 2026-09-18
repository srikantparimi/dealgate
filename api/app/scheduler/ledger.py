"""``scheduler_fired`` — the alert-scheduler idempotency ledger.

The scheduler runs every few minutes and must never dupe a task or a
notification. Instead of chasing "did we already write this row?" queries
against `task` / `notification` (whose subjects are human copy, not stable
keys), each trigger computes a deterministic ``trigger_key`` and tries to
insert it. A UNIQUE constraint on the column turns "already fired" into a
cheap IntegrityError the caller catches and skips.

Design notes:

- Model lives outside ``app.models`` (which is a closed set for other agents)
  but still binds to :data:`app.db.base.Base` so `create_all` in tests picks
  it up. Importing this module is a no-op beyond the mapper registration.
- The service function is intentionally minimal: the scheduler owns the key
  format and the audit hook so the caller can pair the ledger insert with
  its task/notification writes in one transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class SchedulerFired(Base):
    __tablename__ = "scheduler_fired"
    __table_args__ = (
        UniqueConstraint("trigger_key", name="uq_scheduler_fired_trigger_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    trigger_key: Mapped[str] = mapped_column(String(256), nullable=False)
    trigger_name: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def record_trigger(
    session: AsyncSession,
    *,
    trigger_key: str,
    trigger_name: str,
    entity: str,
    entity_id: str,
) -> bool:
    """Best-effort insert of the ledger row. Return True when the caller
    should proceed with side effects; False when the trigger already fired.

    We use a SAVEPOINT so the caller's outer transaction survives the
    conflict — the scheduler processes multiple triggers per tick and one
    duplicate must not poison the whole batch.
    """

    row = SchedulerFired(
        trigger_key=trigger_key,
        trigger_name=trigger_name,
        entity=entity,
        entity_id=entity_id,
    )
    try:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    except IntegrityError:
        return False
    return True


__all__ = ["SchedulerFired", "record_trigger"]
