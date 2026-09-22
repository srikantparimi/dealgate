"""My tasks inbox + task lifecycle API (S2-E3).

Every mutation routes through :mod:`app.services.tasks` so validation, role
checks and audit writes stay in one place. This router is intentionally thin.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.tasks import (
    TaskListFilters,
    list_tasks,
    load_task,
    reassign_task,
    snooze_task,
    transition_task,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# --- schemas -------------------------------------------------------------


class TaskRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID | None
    subject: str
    status: str
    category: str | None = None
    due_date: date | None
    wake_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: uuid.UUID | None = None
    escalation_level: int
    owner_name: str | None = None
    workflow_href: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskRow]
    page: int
    size: int
    total: int


class TaskPatch(BaseModel):
    status: str | None = Field(default=None, max_length=32)
    wake_at: datetime | None = None


class ReassignBody(BaseModel):
    new_owner_id: uuid.UUID


# --- endpoints -----------------------------------------------------------


async def _row(session, task):
    from app.models.approval import ApprovalPackage
    from app.models.approval_routing import ApprovalAssignment
    from app.models.user import User
    from app.services.user_identity import display_user_name
    row = TaskRow.model_validate(task)
    owner = await session.get(User, task.owner_id) if task.owner_id else None
    row.owner_name = display_user_name(owner.name, owner.email) if owner else "Unassigned"
    opportunity_id = await session.scalar(select(ApprovalPackage.opportunity_id).join(ApprovalAssignment, ApprovalAssignment.package_id == ApprovalPackage.id).where(ApprovalAssignment.task_id == task.id))
    if opportunity_id:
        row.workflow_href = f"/sows/{opportunity_id}/approvals"
    return row


@router.get("", response_model=TaskListResponse)
async def list_tasks_endpoint(
    owner: str = Query(default="me"),
    status_: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    include_snoozed: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskListResponse:
    filters = TaskListFilters(
        owner=owner,
        status=status_,
        category=category,
        include_snoozed=include_snoozed,
        page=page,
        size=size,
    )
    rows, total = await list_tasks(session, user, filters)
    return TaskListResponse(
        items=[await _row(session, t) for t in rows],
        page=page,
        size=size,
        total=total,
    )


@router.patch("/{task_id}", response_model=TaskRow)
async def patch_task(
    task_id: uuid.UUID,
    patch: TaskPatch,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskRow:
    provided: dict[str, Any] = patch.model_dump(exclude_unset=True)
    task = await load_task(session, task_id)

    # PATCH is a single-shape body: either a status transition (snooze uses
    # status='snoozed' + wake_at), or nothing (no-op).
    if "status" in provided and provided["status"] is not None:
        target = provided["status"]
        if target == "snoozed":
            wake_at = provided.get("wake_at")
            if wake_at is None:
                from fastapi import HTTPException, status as http_status

                raise HTTPException(
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="wake_at is required when status is 'snoozed'",
                )
            task = await snooze_task(session, actor=user, task=task, wake_at=wake_at)
        else:
            task = await transition_task(session, actor=user, task=task, to_status=target)
    return TaskRow.model_validate(task)


@router.post("/{task_id}/reassign", response_model=TaskRow)
async def reassign_task_endpoint(
    task_id: uuid.UUID,
    body: ReassignBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TaskRow:
    task = await load_task(session, task_id)
    task = await reassign_task(
        session, actor=user, task=task, new_owner_id=body.new_owner_id
    )
    return TaskRow.model_validate(task)
