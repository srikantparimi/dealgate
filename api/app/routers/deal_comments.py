"""``/deals/{opportunity_id}/comments`` router (S20 · W6).

Internal comments are user-writable; hubspot_note rows are read-only
mirrors maintained by W1's sync.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.deals import LEADER_ROLES
from app.services.deal_comment import (
    CommentCreate,
    CommentPatch,
    create_comment,
    delete_comment,
    latest_visible_comment,
    list_comments,
    load_comment,
    patch_comment,
    comment_revision,
    _is_leader,
)
from app.models.user import User
from app.services.tracking_access import require_deal_access


router = APIRouter(tags=["deal-comments"])


# S20 W6 Session 4 · Item 9. Read set matches the pipeline read set
# (leader roles + Sales + Presales). Write set is Sales/Presales/leader
# — a user with zero governance groups is a Viewer and gets 403 on
# create / patch / delete while GET returns an empty list rather than
# a 403 so the deal page doesn't blank on them.
COMMENT_READ_ROLES: frozenset[str] = frozenset(LEADER_ROLES | {"Sales", "Presales"})
COMMENT_WRITE_ROLES: frozenset[str] = frozenset(LEADER_ROLES | {"Sales", "Presales"})


def _can_read_comments(user: AuthUser) -> bool:
    return any(g in COMMENT_READ_ROLES for g in user.groups)


def _require_comment_writer(user: AuthUser) -> None:
    if not any(g in COMMENT_WRITE_ROLES for g in user.groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="comment write requires a sales, presales or leader role",
        )


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
    author_name: str | None = None
    revision: str = ""
    can_edit: bool = False
    can_delete: bool = False


class CommentList(BaseModel):
    items: list[CommentRow]
    latest: CommentRow | None
    can_create: bool = False


class CommentCreateBody(BaseModel):
    body: str = Field(..., min_length=1)
    pinned: bool = False


class CommentPatchBody(BaseModel):
    body: str | None = None
    pinned: bool | None = None
    expected_revision: str | None = None


async def _to_row(session, user, c) -> CommentRow:
    author = await session.get(User, c.author_id) if c.author_id else None
    editable = (c.source == "internal" and c.deleted_at is None
                and bool(set(user.groups or []) & COMMENT_WRITE_ROLES)
                and (_is_leader(user) or c.author_id == user.id))
    return CommentRow.model_validate(c).model_copy(update={
        "author_name": (author.name or author.email) if author else c.author_name_fallback,
        "revision": await comment_revision(session, c),
        "can_edit": editable, "can_delete": editable,
    })


@router.get(
    "/deals/{opportunity_id}/comments", response_model=CommentList
)
async def list_comments_endpoint(
    opportunity_id: uuid.UUID,
    include_deleted: bool = Query(default=False),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentList:
    if not _can_read_comments(user):
        # Item 9 · a user without comment rights sees no comments.
        return CommentList(items=[], latest=None)
    await require_deal_access(session, user, opportunity_id)
    rows = await list_comments(
        session,
        opportunity_id=opportunity_id,
        include_deleted=include_deleted,
    )
    latest = await latest_visible_comment(session, opportunity_id=opportunity_id)
    return CommentList(
        items=[await _to_row(session, user, c) for c in rows],
        latest=await _to_row(session, user, latest) if latest is not None else None,
        can_create=bool(set(user.groups or []) & COMMENT_WRITE_ROLES),
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
    _require_comment_writer(user)
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
    return await _to_row(session, user, c)


@router.patch("/deal-comments/{comment_id}", response_model=CommentRow)
async def patch_comment_endpoint(
    comment_id: uuid.UUID,
    body: CommentPatchBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> CommentRow:
    _require_comment_writer(user)
    c = await load_comment(session, comment_id)
    c = await patch_comment(
        session,
        actor=user,
        comment=c,
        patch=CommentPatch(body=body.body, pinned=body.pinned, expected_revision=body.expected_revision),
    )
    await session.commit()
    return await _to_row(session, user, c)


@router.delete(
    "/deal-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_comment_endpoint(
    comment_id: uuid.UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    _require_comment_writer(user)
    c = await load_comment(session, comment_id)
    if if_match and if_match.startswith('"') and if_match.endswith('"'):
        if_match = if_match[1:-1]
    await delete_comment(session, actor=user, comment=c, expected_revision=if_match)
    await session.commit()
    return None
