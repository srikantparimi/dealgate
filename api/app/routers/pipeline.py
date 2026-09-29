"""Pipeline API (S18 §2) — HubSpot-sourced deals for the Pipeline UI.

Every SPA surface that shows deal lists reads through this router:

- ``/pipeline``                        (Pipeline page)
- ``/command`` pipeline card
- SOW upload deal picker
- SOW detail "linked HubSpot deal" panel

Role gating mirrors the client read set: any leader role plus Sales /
Presales can list; Sales sees only rows they own, per the base filter in
``hubspot_pipeline`` — which returns HubSpot rows regardless of ownership
so leaders can see the whole board.

Read-only in this slice (S18 §2). No POST/PATCH here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.deals import LEADER_ROLES
from app.services.hubspot_pipeline import (
    PipelineDeal,
    get_pipeline_deal,
    list_pipeline_deals,
    search_pipeline_deals,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

# The same read roles the /clients list uses (leader roles + Presales +
# Sales — Sales sees the row because HubSpot is the master of ownership,
# and leaders review the board).
PIPELINE_READ_ROLES: frozenset[str] = frozenset(LEADER_ROLES | {"Presales", "Sales"})


def _require_reader(user: AuthUser) -> None:
    if not any(role in PIPELINE_READ_ROLES for role in user.groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="pipeline read requires a sales or leader role",
        )


class LinkedSowRow(BaseModel):
    sow_id: uuid.UUID
    created_at: datetime


class PipelineDealRow(BaseModel):
    opportunity_id: uuid.UUID
    hubspot_deal_id: str | None
    name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    stage: str | None
    stage_label: str | None
    amount: Decimal | None
    owner_id: uuid.UUID | None
    owner_email: str | None
    owner_name: str | None
    close_date: date | None
    hubspot_last_seen_at: datetime | None
    linked_sows: list[LinkedSowRow] = Field(default_factory=list)


class PipelineListResponse(BaseModel):
    items: list[PipelineDealRow]
    total_open: int
    total_closed_lost: int
    page: int
    size: int


def _to_row(deal: PipelineDeal) -> PipelineDealRow:
    return PipelineDealRow(
        opportunity_id=deal.opportunity_id,
        hubspot_deal_id=deal.hubspot_deal_id,
        name=deal.name,
        client_id=deal.client_id,
        client_name=deal.client_name,
        stage=deal.stage,
        stage_label=deal.stage_label,
        amount=deal.amount,
        owner_id=deal.owner_id,
        owner_email=deal.owner_email,
        owner_name=deal.owner_name,
        close_date=deal.close_date,
        hubspot_last_seen_at=deal.hubspot_last_seen_at,
        linked_sows=[
            LinkedSowRow(sow_id=s.sow_id, created_at=s.created_at) for s in deal.linked_sows
        ],
    )


@router.get("/deals", response_model=PipelineListResponse)
async def list_deals(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    include_closed_lost: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> PipelineListResponse:
    _require_reader(user)
    deals, total_open, total_closed_lost = await list_pipeline_deals(
        session,
        include_closed_lost=include_closed_lost,
        page=page,
        size=size,
    )
    return PipelineListResponse(
        items=[_to_row(d) for d in deals],
        total_open=total_open,
        total_closed_lost=total_closed_lost,
        page=page,
        size=size,
    )


@router.get("/deals/{opportunity_id}", response_model=PipelineDealRow)
async def get_deal(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PipelineDealRow:
    _require_reader(user)
    deal = await get_pipeline_deal(session, opportunity_id)
    if deal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")
    return _to_row(deal)


@router.get("/deals/search", response_model=list[PipelineDealRow])
async def search_deals(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> list[PipelineDealRow]:
    """Feeds the SOW-upload picker's HubSpot-deal dropdown."""

    _require_reader(user)
    deals = await search_pipeline_deals(session, q=q, limit=limit)
    return [_to_row(d) for d in deals]
