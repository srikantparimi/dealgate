"""Admin users API — S1-E1 admin surface.

Every endpoint is gated behind `require_role("SystemAdmin")`. The router
converts between HTTP shapes and the service module; all validation,
invariant enforcement and audit writes live in `app.services.admin_users`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.admin_users import (
    ALLOWED_GROUPS,
    InviteUserPayload,
    PatchGroupsPayload,
    UserListFilters,
    get_role_history,
    invite_user,
    list_users,
    patch_user_groups,
)

router = APIRouter(prefix="/admin/users", tags=["admin"])


# --- schemas ---------------------------------------------------------------


class UserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    groups: list[str]
    last_login: datetime | None
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserRow]
    page: int
    size: int
    total: int
    allowed_groups: list[str] = Field(default_factory=lambda: list(ALLOWED_GROUPS))


class InviteRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    groups: list[str] = Field(default_factory=list)


class PatchGroupsRequest(BaseModel):
    add: list[str] = Field(default_factory=list)
    remove: list[str] = Field(default_factory=list)


class RoleHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ts: datetime
    actor_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class RoleHistoryResponse(BaseModel):
    items: list[RoleHistoryRow]


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=UserListResponse)
async def list_users_endpoint(
    search: str | None = Query(default=None),
    group: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> UserListResponse:
    filters = UserListFilters(search=search, group=group, page=page, size=size)
    rows, total = await list_users(session, filters)
    return UserListResponse(
        items=[UserRow.model_validate(u) for u in rows],
        page=page,
        size=size,
        total=total,
    )


@router.post("", response_model=UserRow, status_code=201)
async def invite_user_endpoint(
    body: InviteRequest,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> UserRow:
    payload = InviteUserPayload(email=str(body.email), name=body.name, groups=body.groups)
    user = await invite_user(session, actor_id=actor.id, payload=payload)
    return UserRow.model_validate(user)


@router.patch("/{user_id}/groups", response_model=UserRow)
async def patch_user_groups_endpoint(
    user_id: uuid.UUID,
    body: PatchGroupsRequest,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> UserRow:
    payload = PatchGroupsPayload(add=body.add, remove=body.remove)
    user = await patch_user_groups(
        session, actor_id=actor.id, user_id=user_id, payload=payload
    )
    return UserRow.model_validate(user)


@router.get("/{user_id}/role_history", response_model=RoleHistoryResponse)
async def get_user_role_history(
    user_id: uuid.UUID,
    _user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> RoleHistoryResponse:
    rows = await get_role_history(session, user_id)
    return RoleHistoryResponse(items=[RoleHistoryRow.model_validate(r) for r in rows])
