"""``/saved-views`` router (S20 · W6).

Seeds the seven built-ins on first list. Users add custom views via
``POST``. Filter/sort JSON matches ``contracts.md`` §4.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.saved_view import (
    SavedViewCreate,
    SavedViewPatch,
    archive_view,
    create_view,
    list_views,
    load_view,
    patch_view,
)


router = APIRouter(prefix="/saved-views", tags=["saved-views"])


class SavedViewRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    key: str
    name: str
    filter_json: dict[str, Any]
    sort_json: dict[str, Any] | None
    visibility: str
    is_builtin: bool
    display_order: int


class SavedViewListResponse(BaseModel):
    items: list[SavedViewRow]


class SavedViewCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    filter_json: dict[str, Any]
    sort_json: dict[str, Any] | None = None
    visibility: str = "private"


class SavedViewPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    filter_json: dict[str, Any] | None = None
    sort_json: dict[str, Any] | None = None
    visibility: str | None = None
    display_order: int | None = None
    clear_sort: bool = False


def _to_row(v) -> SavedViewRow:
    return SavedViewRow.model_validate(v)


@router.get("", response_model=SavedViewListResponse)
async def list_views_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedViewListResponse:
    rows = await list_views(session, actor=user)
    await session.commit()  # persist any seeded built-ins
    return SavedViewListResponse(items=[_to_row(v) for v in rows])


@router.post(
    "", response_model=SavedViewRow, status_code=status.HTTP_201_CREATED
)
async def create_view_endpoint(
    body: SavedViewCreateBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedViewRow:
    v = await create_view(
        session,
        actor=user,
        payload=SavedViewCreate(
            name=body.name,
            filter_json=body.filter_json,
            sort_json=body.sort_json,
            visibility=body.visibility,
        ),
    )
    await session.commit()
    return _to_row(v)


@router.get("/{view_id}", response_model=SavedViewRow)
async def get_view_endpoint(
    view_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedViewRow:
    v = await load_view(session, actor=user, view_id=view_id)
    return _to_row(v)


@router.patch("/{view_id}", response_model=SavedViewRow)
async def patch_view_endpoint(
    view_id: uuid.UUID,
    body: SavedViewPatchBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SavedViewRow:
    v = await load_view(session, actor=user, view_id=view_id)
    v = await patch_view(
        session,
        actor=user,
        view=v,
        patch=SavedViewPatch(
            name=body.name,
            filter_json=body.filter_json,
            sort_json=body.sort_json,
            visibility=body.visibility,
            display_order=body.display_order,
            clear_sort=body.clear_sort,
        ),
    )
    await session.commit()
    return _to_row(v)


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_view_endpoint(
    view_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    v = await load_view(session, actor=user, view_id=view_id)
    await archive_view(session, actor=user, view=v)
    await session.commit()
    return None
