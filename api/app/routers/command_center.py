from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.routers.pipeline import _require_reader
from app.services.command_center import (
    CommandAccountFilters,
    build_command_overview,
    command_accounts_csv,
    list_command_accounts,
)
from app.services.hubspot_pipeline import PipelineFilters, scope_pipeline_filters
from app.models.watchlist import WatchedItem


router = APIRouter(prefix="/command-center", tags=["command-center"])


async def _scope(
    session: AsyncSession,
    user: AuthUser,
    *,
    business_unit: str | None,
    owner_id: uuid.UUID | None,
) -> PipelineFilters:
    filters = PipelineFilters(
        business_unit=(business_unit,) if business_unit else (),
        owner=(owner_id,) if owner_id else (),
        include_closed=True,
        open_closed="any",
    )
    return await scope_pipeline_filters(session, user, filters)


async def _watched(session: AsyncSession, user: AuthUser) -> tuple[tuple[uuid.UUID, ...], tuple[uuid.UUID, ...]]:
    rows = (
        await session.scalars(select(WatchedItem).where(WatchedItem.user_id == user.id))
    ).all()
    return (
        tuple(row.item_id for row in rows if row.kind == "opportunity"),
        tuple(row.item_id for row in rows if row.kind == "client"),
    )


@router.get("/overview")
async def overview(
    business_unit: str | None = Query(default=None, max_length=255),
    owner_id: uuid.UUID | None = None,
    period: str = Query(default="this_quarter", pattern="^(this_quarter|next_two_quarters)$"),
    currency: str = Query(default="USD", min_length=3, max_length=8),
    focus: str = Query(default="leadership", pattern="^(leadership|delivery|sales|finance)$"),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_reader(user)
    result = await build_command_overview(
        session,
        scope=await _scope(
            session, user, business_unit=business_unit, owner_id=owner_id
        ),
        period=period,
        currency=currency.upper(),
        focus=focus,
    )
    return jsonable_encoder(result)


@router.get("/accounts")
async def accounts(
    search: str | None = Query(default=None, max_length=200),
    business_unit: str | None = Query(default=None, max_length=255),
    owner_id: uuid.UUID | None = None,
    period: str = Query(default="this_quarter", pattern="^(this_quarter|next_two_quarters)$"),
    health: str = Query(default="all", pattern="^(all|at_risk|watching)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_reader(user)
    watched_opportunities, watched_clients = await _watched(session, user)
    result = await list_command_accounts(
        session,
        scope=await _scope(
            session, user, business_unit=business_unit, owner_id=owner_id
        ),
        filters=CommandAccountFilters(
            search=search,
            page=page,
            page_size=page_size,
            period=period,
            health=health,
            watched_opportunity_ids=watched_opportunities,
            watched_client_ids=watched_clients,
        ),
    )
    return jsonable_encoder(asdict(result))


@router.get("/accounts.csv", response_class=PlainTextResponse)
async def accounts_csv(
    search: str | None = Query(default=None, max_length=200),
    business_unit: str | None = Query(default=None, max_length=255),
    owner_id: uuid.UUID | None = None,
    period: str = Query(default="this_quarter", pattern="^(this_quarter|next_two_quarters)$"),
    health: str = Query(default="all", pattern="^(all|at_risk|watching)$"),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    _require_reader(user)
    watched_opportunities, watched_clients = await _watched(session, user)
    text = await command_accounts_csv(
        session,
        scope=await _scope(
            session, user, business_unit=business_unit, owner_id=owner_id
        ),
        filters=CommandAccountFilters(
            search=search,
            page=1,
            page_size=100,
            period=period,
            health=health,
            watched_opportunity_ids=watched_opportunities,
            watched_client_ids=watched_clients,
        ),
    )
    return PlainTextResponse(
        text,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="dealgate-command-center.csv"'
        },
    )
