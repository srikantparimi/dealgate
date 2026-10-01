"""``/tracking-groups`` router (S20 · W6).

Manual watchlists + dynamic groups derived from saved filters.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.tracking_group import (
    GroupCreate,
    GroupPatch,
    add_members,
    archive_group,
    create_group,
    list_groups,
    list_members,
    load_group,
    patch_group,
    remove_members,
)


router = APIRouter(prefix="/tracking-groups", tags=["tracking-groups"])


class GroupRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    visibility: str
    member_kind: str
    filter_json: dict[str, Any] | None
    include_future_deals: bool


class GroupListResponse(BaseModel):
    items: list[GroupRow]


class GroupCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    member_kind: str
    visibility: str = "private"
    filter_json: dict[str, Any] | None = None
    include_future_deals: bool = True


class GroupPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    visibility: str | None = None
    filter_json: dict[str, Any] | None = None
    include_future_deals: bool | None = None
    clear_filter: bool = False


class MemberListResponse(BaseModel):
    member_kind: str
    member_ids: list[uuid.UUID]


class MemberMutation(BaseModel):
    member_ids: list[uuid.UUID]


def _to_row(g) -> GroupRow:
    return GroupRow.model_validate(g)


@router.get("", response_model=GroupListResponse)
async def list_groups_endpoint(
    member_kind: str | None = Query(default=None),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> GroupListResponse:
    groups = await list_groups(session, actor=user, member_kind=member_kind)
    return GroupListResponse(items=[_to_row(g) for g in groups])


@router.post("", response_model=GroupRow, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(
    body: GroupCreateBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> GroupRow:
    g = await create_group(
        session,
        actor=user,
        payload=GroupCreate(
            name=body.name,
            member_kind=body.member_kind,
            visibility=body.visibility,
            filter_json=body.filter_json,
            include_future_deals=body.include_future_deals,
        ),
    )
    await session.commit()
    return _to_row(g)


@router.get("/{group_id}", response_model=GroupRow)
async def get_group_endpoint(
    group_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> GroupRow:
    g = await load_group(session, actor=user, group_id=group_id)
    return _to_row(g)


@router.patch("/{group_id}", response_model=GroupRow)
async def patch_group_endpoint(
    group_id: uuid.UUID,
    body: GroupPatchBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> GroupRow:
    g = await load_group(session, actor=user, group_id=group_id)
    g = await patch_group(
        session,
        actor=user,
        group=g,
        patch=GroupPatch(
            name=body.name,
            visibility=body.visibility,
            filter_json=body.filter_json,
            include_future_deals=body.include_future_deals,
            clear_filter=body.clear_filter,
        ),
    )
    await session.commit()
    return _to_row(g)


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_group_endpoint(
    group_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    g = await load_group(session, actor=user, group_id=group_id)
    await archive_group(session, actor=user, group=g)
    await session.commit()
    return None


@router.get("/{group_id}/members", response_model=MemberListResponse)
async def list_members_endpoint(
    group_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MemberListResponse:
    g = await load_group(session, actor=user, group_id=group_id)
    members = await list_members(session, actor=user, group=g)
    return MemberListResponse(
        member_kind=g.member_kind, member_ids=list(members)
    )


@router.post("/{group_id}/members", response_model=MemberListResponse)
async def add_members_endpoint(
    group_id: uuid.UUID,
    body: MemberMutation,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MemberListResponse:
    g = await load_group(session, actor=user, group_id=group_id)
    await add_members(session, actor=user, group=g, member_ids=tuple(body.member_ids))
    await session.commit()
    members = await list_members(session, actor=user, group=g)
    return MemberListResponse(
        member_kind=g.member_kind, member_ids=list(members)
    )


# Members-removal is a POST so a request body is preserved end-to-end
# (caching proxies can strip bodies from DELETE requests).
@router.post("/{group_id}/members/remove", response_model=MemberListResponse)
async def remove_members_endpoint(
    group_id: uuid.UUID,
    body: MemberMutation,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MemberListResponse:
    g = await load_group(session, actor=user, group_id=group_id)
    await remove_members(
        session, actor=user, group=g, member_ids=tuple(body.member_ids)
    )
    await session.commit()
    members = await list_members(session, actor=user, group=g)
    return MemberListResponse(
        member_kind=g.member_kind, member_ids=list(members)
    )
