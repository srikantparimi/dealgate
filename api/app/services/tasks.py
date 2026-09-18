"""Task lifecycle state machine + audited transitions (S2-E3).

Rules:

- The router is thin: it does auth + shape conversion. Every transition, snooze
  or reassignment goes through this module so the audit + role check stay in
  one place.
- Every state change writes an ``audit_event`` in the same transaction as the
  row update (CLAUDE.md rule 5).
- Row-level access:
    - Owner may transition their own task (assigned <-> in_progress <-> done,
      snooze, cancel).
    - Leaders (Sales leader / HR leader / SystemAdmin) may transition any task
      and are the only role that can reassign.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.task import Task
from app.models.user import User

# --- roles ----------------------------------------------------------------

# Roles that may reassign any task or transition someone else's task.
LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "HR", "SystemAdmin"}
)

# --- state machine --------------------------------------------------------

# Legacy S1 tasks used 'Open' — normalise on read for the state machine so we
# don't need a data migration to update every existing row.
_LEGACY_TO_CURRENT = {"Open": "assigned"}

TASK_STATUSES: tuple[str, ...] = (
    "assigned",
    "in_progress",
    "snoozed",
    "done",
    "cancelled",
    "reassigned",
)

# Allowed transitions. `*` (any live status) may cancel; `snoozed` wakes back to
# `assigned` via `snooze_task`. `reassigned` is a terminal audit-only status set
# by `reassign_task` — the new task is a fresh row for the new owner.
TASK_TRANSITIONS: dict[str, set[str]] = {
    "assigned": {"in_progress", "snoozed", "done", "cancelled", "reassigned"},
    "in_progress": {"assigned", "snoozed", "done", "cancelled", "reassigned"},
    "snoozed": {"assigned", "in_progress", "cancelled", "reassigned"},
    "done": set(),
    "cancelled": set(),
    "reassigned": set(),
}

# Human-friendly action names for the audit trail. Anything not listed falls
# back to `task.transitioned`.
_TRANSITION_ACTIONS: dict[tuple[str, str], str] = {
    ("assigned", "in_progress"): "task.started",
    ("in_progress", "assigned"): "task.reopened",
    ("assigned", "snoozed"): "task.snoozed",
    ("in_progress", "snoozed"): "task.snoozed",
    ("snoozed", "assigned"): "task.woke",
    ("snoozed", "in_progress"): "task.woke",
    ("assigned", "done"): "task.completed",
    ("in_progress", "done"): "task.completed",
    ("assigned", "cancelled"): "task.cancelled",
    ("in_progress", "cancelled"): "task.cancelled",
    ("snoozed", "cancelled"): "task.cancelled",
    ("assigned", "reassigned"): "task.reassigned",
    ("in_progress", "reassigned"): "task.reassigned",
    ("snoozed", "reassigned"): "task.reassigned",
}


def _current_status(task: Task) -> str:
    return _LEGACY_TO_CURRENT.get(task.status, task.status)


def is_leader(user: AuthUser) -> bool:
    return any(r in LEADER_ROLES for r in user.groups)


def _actor_can_transition(user: AuthUser, task: Task) -> bool:
    if is_leader(user):
        return True
    return task.owner_id is not None and task.owner_id == user.id


# --- query helpers --------------------------------------------------------


@dataclass(frozen=True)
class TaskListFilters:
    owner: str | None = "me"  # "me", a user-id, or None (leaders only)
    status: str | None = None
    category: str | None = None
    include_snoozed: bool = False
    page: int = 1
    size: int = 25


async def list_tasks(
    session: AsyncSession, user: AuthUser, filters: TaskListFilters
) -> tuple[list[Task], int]:
    """Return `(rows, total)` for "My tasks" style queries.

    - Non-leaders may only query their own tasks (`owner=me`); passing any
      other owner value raises 403.
    - Snoozed tasks are hidden until ``wake_at`` <= now unless
      ``include_snoozed`` is set (used by the leader "all tasks" view).
    - Sort: due_date ASC NULLS LAST, id ASC as a stable tiebreaker.
    """

    stmt = select(Task)

    if filters.owner == "me" or filters.owner is None and not is_leader(user):
        stmt = stmt.where(Task.owner_id == user.id)
    elif filters.owner and filters.owner != "me":
        if not is_leader(user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="not authorised",
            )
        try:
            uid = uuid.UUID(filters.owner)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="owner must be 'me' or a UUID",
            ) from exc
        stmt = stmt.where(Task.owner_id == uid)
    # owner=None + leader ⇒ no owner filter.

    if filters.status:
        stmt = stmt.where(Task.status == filters.status)
    if filters.category:
        stmt = stmt.where(Task.category == filters.category)
    if not filters.include_snoozed:
        now = datetime.now(UTC)
        # Hide rows in status='snoozed' whose wake_at is still in the future.
        stmt = stmt.where(
            ~(
                (Task.status == "snoozed")
                & (Task.wake_at.is_not(None))
                & (Task.wake_at > now)
            )
        )

    null_key = Task.due_date.is_(None)
    stmt = stmt.order_by(null_key.asc(), Task.due_date.asc(), Task.id.asc())

    rows = list((await session.execute(stmt)).scalars().all())
    total = len(rows)
    offset = max(0, (filters.page - 1) * filters.size)
    return rows[offset : offset + filters.size], total


async def load_task(session: AsyncSession, task_id: uuid.UUID) -> Task:
    row = (
        await session.execute(select(Task).where(Task.id == task_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return row


# --- mutations ------------------------------------------------------------


def _audit_action(from_status: str, to_status: str) -> str:
    return _TRANSITION_ACTIONS.get((from_status, to_status), "task.transitioned")


async def transition_task(
    session: AsyncSession,
    *,
    actor: AuthUser,
    task: Task,
    to_status: str,
) -> Task:
    """Move ``task`` to ``to_status``; validates + audits + commits.

    Raises:
        403 when the caller may not act on this task.
        422 when the transition is not in :data:`TASK_TRANSITIONS`.
    """

    if to_status not in TASK_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown status: {to_status!r}",
        )
    if not _actor_can_transition(actor, task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")

    from_status = _current_status(task)
    allowed = TASK_TRANSITIONS.get(from_status, set())
    if to_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid transition {from_status} -> {to_status}",
        )

    before: dict[str, Any] = {
        "status": from_status,
        "escalation_level": task.escalation_level,
    }

    task.status = to_status
    after: dict[str, Any] = {"status": to_status}

    now = datetime.now(UTC)
    if to_status == "done":
        task.completed_at = now
        task.completed_by = actor.id
        after["completed_by"] = str(actor.id)
        after["completed_at"] = now.isoformat()
        # Rule from AC: record escalation level at the moment of completion so
        # the "was this closed after an escalation?" question is answerable
        # without re-deriving history.
        after["escalation_at_completion"] = task.escalation_level
    if to_status in {"assigned", "in_progress"}:
        # Leaving snoozed clears wake_at so the row stops being hidden.
        task.wake_at = None
        after["wake_at"] = None

    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action=_audit_action(from_status, to_status),
        entity="task",
        entity_id=str(task.id),
        before=before,
        after=after,
    )
    await session.commit()
    await session.refresh(task)
    return task


async def snooze_task(
    session: AsyncSession,
    *,
    actor: AuthUser,
    task: Task,
    wake_at: datetime,
) -> Task:
    """Snooze ``task`` until ``wake_at``; audits and commits.

    ``wake_at`` must be in the future; naive datetimes are assumed UTC.
    """

    if wake_at.tzinfo is None:
        wake_at = wake_at.replace(tzinfo=UTC)
    if wake_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="wake_at must be in the future",
        )
    if not _actor_can_transition(actor, task):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")

    from_status = _current_status(task)
    if "snoozed" not in TASK_TRANSITIONS.get(from_status, set()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"cannot snooze from status {from_status!r}",
        )

    before = {"status": from_status, "wake_at": None}
    task.status = "snoozed"
    task.wake_at = wake_at
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="task.snoozed",
        entity="task",
        entity_id=str(task.id),
        before=before,
        after={"status": "snoozed", "wake_at": wake_at.isoformat()},
    )
    await session.commit()
    await session.refresh(task)
    return task


async def reassign_task(
    session: AsyncSession,
    *,
    actor: AuthUser,
    task: Task,
    new_owner_id: uuid.UUID,
) -> Task:
    """Reassign the task's owner. Leader-only. Emits ``task.reassigned``.

    The row's status stays live (assigned) so the new owner sees it in their
    inbox immediately.
    """

    if not is_leader(actor):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")

    new_owner = (
        await session.execute(select(User).where(User.id == new_owner_id))
    ).scalar_one_or_none()
    if new_owner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="new owner not found"
        )
    if task.owner_id == new_owner_id:
        # No-op reassignment: return as-is without an audit row.
        return task

    before = {
        "owner_id": str(task.owner_id) if task.owner_id else None,
        "status": _current_status(task),
    }
    task.owner_id = new_owner_id
    # Reassignment revives snoozed tasks so the new owner isn't stuck.
    if _current_status(task) == "snoozed":
        task.status = "assigned"
        task.wake_at = None
    elif _current_status(task) not in {"assigned", "in_progress"}:
        # Completed / cancelled tasks cannot be reassigned.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"cannot reassign a task in status {_current_status(task)!r}",
        )
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="task.reassigned",
        entity="task",
        entity_id=str(task.id),
        before=before,
        after={
            "owner_id": str(new_owner_id),
            "status": _current_status(task),
        },
    )
    await session.commit()
    await session.refresh(task)
    return task


__all__ = [
    "LEADER_ROLES",
    "TASK_STATUSES",
    "TASK_TRANSITIONS",
    "TaskListFilters",
    "is_leader",
    "list_tasks",
    "load_task",
    "reassign_task",
    "snooze_task",
    "transition_task",
]
