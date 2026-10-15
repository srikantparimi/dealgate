"""``/pipeline/views``, ``/pipeline/groups``, ``/pipeline/watching`` — S23-PL2 B11.

The Pipeline page's personal workspace (contract routes). Every route needs a
Pipeline reader role; reads resolve the caller's DealGate user id without
writing, writes provision it first (``canonical_user``). Deal visibility goes
through the Pipeline's own services; this module runs no opportunity SQL.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.routers.pipeline import _require_reader
from app.services.canonical_user import canonical_actor
from app.services.pipeline_personal import (
    NAME_MAX,
    add_pipeline_group_deals,
    create_pipeline_group,
    create_pipeline_view,
    delete_pipeline_view,
    list_pipeline_groups,
    list_pipeline_views,
    reading_actor,
    remove_pipeline_group_deals,
    set_watching,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

MAX_DEALS_PER_CALL = 500


class SavedViewIn(BaseModel):
    name: str = Field(..., max_length=NAME_MAX)
    tab: Literal["deals", "clients"]
    layout: Literal["list", "board"]
    filters: dict[str, Any]


class SavedViewOut(BaseModel):
    id: uuid.UUID
    name: str
    tab: str
    layout: str
    filters: dict[str, Any]


class GroupIn(BaseModel):
    name: str = Field(..., max_length=NAME_MAX)
    deal_ids: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_DEALS_PER_CALL)


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    deal_ids: list[uuid.UUID]


class DealIdsIn(BaseModel):
    deal_ids: list[uuid.UUID] = Field(..., max_length=MAX_DEALS_PER_CALL)


def _no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- saved views ---------------------------------------------------------------


@router.get("/views", response_model=list[SavedViewOut])
async def list_views_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_reader(user)
    viewer = await reading_actor(session, user)
    return await list_pipeline_views(session, owner_id=viewer.id)


@router.post("/views", response_model=SavedViewOut, status_code=status.HTTP_201_CREATED)
async def create_view_endpoint(
    body: SavedViewIn,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    view = await create_pipeline_view(
        session, actor=actor, name=body.name, tab=body.tab, layout=body.layout, filters=body.filters
    )
    await session.commit()
    return view


@router.delete("/views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_view_endpoint(
    view_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    await delete_pipeline_view(session, actor=actor, view_id=view_id)
    await session.commit()
    return _no_content()


# --- tracking groups -------------------------------------------------------------


@router.get("/groups", response_model=list[GroupOut])
async def list_groups_endpoint(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    _require_reader(user)
    viewer = await reading_actor(session, user)
    return await list_pipeline_groups(session, viewer=viewer)


@router.post("/groups", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group_endpoint(
    body: GroupIn,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    group = await create_pipeline_group(session, actor=actor, name=body.name, deal_ids=body.deal_ids)
    await session.commit()
    return group


@router.put("/groups/{group_id}/deals", status_code=status.HTTP_204_NO_CONTENT)
async def add_group_deals_endpoint(
    group_id: uuid.UUID,
    body: DealIdsIn,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    await add_pipeline_group_deals(session, actor=actor, group_id=group_id, deal_ids=body.deal_ids)
    await session.commit()
    return _no_content()


@router.delete("/groups/{group_id}/deals", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_deals_endpoint(
    group_id: uuid.UUID,
    body: DealIdsIn | None = None,
    deal_ids: list[uuid.UUID] | None = Query(default=None, max_length=MAX_DEALS_PER_CALL),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    # The ids may come in the body (contract) or the query string: a proxy can
    # drop a DELETE body, so the web client sends both.
    _require_reader(user)
    actor = await canonical_actor(session, user)
    ids = [*(deal_ids or []), *(body.deal_ids if body else [])]
    await remove_pipeline_group_deals(session, actor=actor, group_id=group_id, deal_ids=ids)
    await session.commit()
    return _no_content()


# --- watching ----------------------------------------------------------------------


@router.put("/watching/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def watch_deal_endpoint(
    deal_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    await set_watching(session, actor=actor, deal_id=deal_id, watching=True)
    await session.commit()
    return _no_content()


@router.delete("/watching/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unwatch_deal_endpoint(
    deal_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_reader(user)
    actor = await canonical_actor(session, user)
    await set_watching(session, actor=actor, deal_id=deal_id, watching=False)
    await session.commit()
    return _no_content()
