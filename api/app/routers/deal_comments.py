"""``/deals/{opportunity_id}/comments`` router (S20 · W6).

Internal comments are user-writable; hubspot_note rows are read-only
mirrors maintained by W1's sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.deal_comment import (
    CommentCreate,
    CommentPatch,
    create_comment,
    delete_comment,
    latest_visible_comment,
    list_comments,
    load_comment,
    patch_comment,
)


router = APIRouter(tags=["deal-comments"])


class CommentRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    author_id: uuid.UUID | None
    author_name_fallback: str | None
    body: str
    pinned: bool
    source: str
    hubspot_note_id: str | None
    created_at: datetime
    edited_at: datetime | None
    deleted_at: datetime | None


class CommentList(BaseModel):
    items: list[CommentRow]
    latest: CommentRow | None


class CommentCreateBody(BaseModel):
    body: str = Field(..., min_length=1)
    pinned: bool = False


class CommentPatchBody(BaseModel):
    body: str | None = None
    pinned: bool | None = None


def _to_row(c) -> CommentRow:
    return CommentRow.model_validate(c)


@router.get(
    "/deals/{opportunity_id}/comments", response_model=CommentList
)
async def list_comments_endpoint(
    opportunity_id: uuid.UUID,
    include_deleted: bool = Query(default=False),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentList:
    rows = await list_comments(
        session,
        opportunity_id=opportunity_id,
        include_deleted=include_deleted,
    )
    latest = await latest_visible_comment(session, opportunity_id=opportunity_id)
    return CommentList(
        items=[_to_row(c) for c in rows],
        latest=_to_row(latest) if latest is not None else None,
    )


@router.post(
    "/deals/{opportunity_id}/comments",
    response_model=CommentRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment_endpoint(
    opportunity_id: uuid.UUID,
    body: CommentCreateBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentRow:
    c = await create_comment(
        session,
        actor=user,
        payload=CommentCreate(
            opportunity_id=opportunity_id,
            body=body.body,
            pinned=body.pinned,
        ),
    )
    await session.commit()
    return _to_row(c)


@router.patch("/deal-comments/{comment_id}", response_model=CommentRow)
async def patch_comment_endpoint(
    comment_id: uuid.UUID,
    body: CommentPatchBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentRow:
    c = await load_comment(session, comment_id)
    c = await patch_comment(
        session,
        actor=user,
        comment=c,
        patch=CommentPatch(body=body.body, pinned=body.pinned),
    )
    await session.commit()
    return _to_row(c)


@router.delete(
    "/deal-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment_endpoint(
    comment_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    c = await load_comment(session, comment_id)
    await delete_comment(session, actor=user, comment=c)
    await session.commit()
    return None
