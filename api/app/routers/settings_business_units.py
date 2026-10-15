"""``/settings/business-units`` — S23-PL2 B3: the region → business unit map.

SystemAdmin reads and replaces the map. Deal rows join it at read time, so a
saved edit shows on every deal immediately. The unmapped deal counts come from
the region-map service (no opportunity SQL in routers).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.canonical_user import canonical_actor, resolve_viewer
from app.services.region_map import region_map_view, replace_region_map

router = APIRouter(prefix="/settings/business-units", tags=["settings"])


class RegionRowIn(BaseModel):
    hubspot_value: str = Field(..., max_length=255)
    business_unit: str = Field(..., max_length=32)
    region: str = Field(..., max_length=64)
    note: str | None = Field(default=None, max_length=128)


class RegionMapIn(BaseModel):
    rows: list[RegionRowIn] = Field(..., max_length=500)


class RegionRowOut(BaseModel):
    hubspot_value: str
    business_unit: str
    region: str
    note: str | None


class UnmappedRegionOut(BaseModel):
    hubspot_value: str
    deals: int


class RegionMapOut(BaseModel):
    rows: list[RegionRowOut]
    unmapped_on_deals: list[UnmappedRegionOut]
    # Additive to the contract: deals that carry no HubSpot region at all.
    deals_without_region: int
    # Additive: the business units a row may name, in display order.
    business_units: list[str]


@router.get("", response_model=RegionMapOut)
async def get_business_unit_map(
    user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> RegionMapOut:
    viewer = await resolve_viewer(session, user)
    reader = AuthUser(viewer.user_id or user.id, user.email, user.name, tuple(user.groups))
    return RegionMapOut(**await region_map_view(session, reader))


@router.put("", response_model=RegionMapOut)
async def put_business_unit_map(
    body: RegionMapIn,
    user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> RegionMapOut:
    admin = await canonical_actor(session, user)
    await replace_region_map(session, actor_id=admin.id, rows_in=[row.model_dump() for row in body.rows])
    view = await region_map_view(session, admin)
    await session.commit()
    return RegionMapOut(**view)
