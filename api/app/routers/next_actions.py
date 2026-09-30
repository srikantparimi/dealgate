"""``/next-actions`` router (S20 · W6).

Thin router — all validation, permissions, transitions and audit
emission live in :mod:`app.services.next_action`.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.next_action import (
    NextActionCreate,
    NextActionPatch,
    create_action,
    list_actions,
    list_events,
    load_action,
    patch_action,
)


router = APIRouter(prefix="/next-actions", tags=["next-actions"])


class NextActionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    title: str | None
    description: str
    assignee_user_id: uuid.UUID | None
    owner_user_id: uuid.UUID
    due_date: date | None
    status: str
    blocker: str | None
    outcome: str | None
    approval_package_id: uuid.UUID | None


class NextActionListResponse(BaseModel):
    items: list[NextActionRow]


class NextActionCreateBody(BaseModel):
    opportunity_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=255)
    assignee_user_id: uuid.UUID
    due_date: date | None = None
    blocker: str | None = None
    outcome: str | None = None
    approval_package_id: uuid.UUID | None = None


class NextActionPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    assignee_user_id: uuid.UUID | None = None
    due_date: date | None = None
    status: str | None = Field(default=None, max_length=16)
    blocker: str | None = None
    outcome: str | None = None
    clear_due_date: bool = False
    clear_blocker: bool = False
    clear_outcome: bool = False


class NextActionEventRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ts: Any
    actor_id: uuid.UUID | None
    kind: str
    from_status: str | None
    to_status: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    note: str | None


class NextActionEventList(BaseModel):
    items: list[NextActionEventRow]


def _to_row(a) -> NextActionRow:
    return NextActionRow.model_validate(a)


@router.get("", response_model=NextActionListResponse)
async def list_next_actions_endpoint(
    opportunity_id: uuid.UUID | None = Query(default=None),
    assignee_user_id: uuid.UUID | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionListResponse:
    status_tuple: tuple[str, ...] = tuple(
        s.strip() for s in (status_.split(",") if status_ else []) if s.strip()
    )
    rows = await list_actions(
        session,
        opportunity_id=opportunity_id,
        assignee_user_id=assignee_user_id,
        status_in=status_tuple,
    )
    return NextActionListResponse(items=[_to_row(a) for a in rows])


@router.post("", response_model=NextActionRow, status_code=status.HTTP_201_CREATED)
async def create_next_action_endpoint(
    body: NextActionCreateBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionRow:
    action = await create_action(
        session,
        actor=user,
        payload=NextActionCreate(
            opportunity_id=body.opportunity_id,
            title=body.title,
            assignee_user_id=body.assignee_user_id,
            due_date=body.due_date,
            blocker=body.blocker,
            outcome=body.outcome,
            approval_package_id=body.approval_package_id,
        ),
    )
    await session.commit()
    return _to_row(action)


@router.get("/{action_id}", response_model=NextActionRow)
async def get_next_action_endpoint(
    action_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionRow:
    action = await load_action(session, action_id)
    return _to_row(action)


@router.patch("/{action_id}", response_model=NextActionRow)
async def patch_next_action_endpoint(
    action_id: uuid.UUID,
    body: NextActionPatchBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionRow:
    action = await load_action(session, action_id)
    action = await patch_action(
        session,
        actor=user,
        action=action,
        patch=NextActionPatch(
            title=body.title,
            assignee_user_id=body.assignee_user_id,
            due_date=body.due_date,
            status=body.status,
            blocker=body.blocker,
            outcome=body.outcome,
            clear_due_date=body.clear_due_date,
            clear_blocker=body.clear_blocker,
            clear_outcome=body.clear_outcome,
        ),
    )
    await session.commit()
    return _to_row(action)


@router.get("/{action_id}/events", response_model=NextActionEventList)
async def get_next_action_events_endpoint(
    action_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionEventList:
    _ = await load_action(session, action_id)
    events = await list_events(session, action_id)
    return NextActionEventList(
        items=[NextActionEventRow.model_validate(e) for e in events]
    )
