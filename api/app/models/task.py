from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class Task(Base):
    __tablename__ = "task"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    # escalation_level: 0 = normal, higher values drive alerts (see build-guide §9).
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Lifecycle state (S2-E3). See `app.services.tasks.TASK_TRANSITIONS`.
    # Values: assigned | in_progress | snoozed | done | cancelled | reassigned.
    # Legacy `Open` rows created by S1 intake still exist in some environments;
    # `transition_task` treats them as `assigned` when evaluating transitions.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="assigned")
    # Category groups tasks for filters + notification routing (intake, coverage,
    # approval, expiry, ...). Nullable so pre-S2 tasks stay valid.
    category: Mapped[str | None] = mapped_column(String(32))
    # When set, the task is hidden from "My tasks" until `wake_at` is reached.
    wake_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
