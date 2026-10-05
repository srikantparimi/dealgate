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
    action_revision,
    _is_leader,
)
from app.services.tracking_access import assignable_users, require_deal_access, visible_deal_ids


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
    revision: str = ""
    can_edit: bool = False


class NextActionListResponse(BaseModel):
    items: list[NextActionRow]
    can_create: bool = False
    assignees: list[dict[str, str]] = Field(default_factory=list)


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
    expected_revision: str | None = None


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


async def _to_row(session, user, a) -> NextActionRow:
    return NextActionRow.model_validate(a).model_copy(update={
        "revision": await action_revision(session, a),
        "can_edit": _is_leader(user) or user.id in {a.assignee_user_id, a.owner_user_id, a.created_by},
    })


@router.get("", response_model=NextActionListResponse)
async def list_next_actions_endpoint(
    opportunity_id: uuid.UUID | None = Query(default=None),
    assignee_user_id: uuid.UUID | None = Query(default=None),
    status_: str | None = Query(default=None, alias="status"),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionListResponse:
    candidates = []
    if opportunity_id is not None:
        await require_deal_access(session, user, opportunity_id)
        allowed = {opportunity_id}
        candidates = await assignable_users(session, user, opportunity_id)
    else:
        allowed = set(await visible_deal_ids(session, user))
    status_tuple: tuple[str, ...] = tuple(
        s.strip() for s in (status_.split(",") if status_ else []) if s.strip()
    )
    rows = await list_actions(
        session,
        opportunity_id=opportunity_id,
        assignee_user_id=assignee_user_id,
        status_in=status_tuple,
    )
    return NextActionListResponse(
        items=[await _to_row(session, user, a) for a in rows if a.opportunity_id in allowed],
        can_create=opportunity_id is not None,
        assignees=[{"id": str(person.id), "name": person.name or person.email} for person in candidates],
    )


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
    return await _to_row(session, user, action)


@router.get("/{action_id}", response_model=NextActionRow)
async def get_next_action_endpoint(
    action_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionRow:
    action = await load_action(session, action_id)
    await require_deal_access(session, user, action.opportunity_id)
    return await _to_row(session, user, action)


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
            expected_revision=body.expected_revision,
        ),
    )
    await session.commit()
    return await _to_row(session, user, action)


@router.get("/{action_id}/events", response_model=NextActionEventList)
async def get_next_action_events_endpoint(
    action_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NextActionEventList:
    action = await load_action(session, action_id)
    await require_deal_access(session, user, action.opportunity_id)
    events = await list_events(session, action_id)
    return NextActionEventList(
        items=[NextActionEventRow.model_validate(e) for e in events]
    )
