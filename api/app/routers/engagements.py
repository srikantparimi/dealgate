"""S22 — Portfolio & Forecast endpoints, exactly as docs/reference/openapi-forecast.yaml.

Thin router: role gate → delegate to :mod:`app.services.engagement_forecast`
→ commit. Every forecast response is a serialisation of the engine's
``Forecast``; validation failures are 422 with ``body.missing`` carrying the
engine's own strings.

Role model (blueprint §3 — Sales never sees an individual's cost):

- read:     Delivery, Finance, CEO, SystemAdmin, HR, Sales, SalesLeader, Presales
- write:    Delivery, Finance, SystemAdmin, Sales, SalesLeader
- settings: GET for the cost-allowed roles (the rate card is individual cost);
            PUT for SystemAdmin, Finance.

Callers outside :data:`app.services.redact.ROLES_ALLOWED_COST` receive the
same payloads with per-person cost keys removed; engagement-level totals
stay, because the deal's margin is already theirs to see.
"""

from __future__ import annotations

import copy
import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.client import Client
from app.models.engagement import EngagementCost
from app.services import engagement_forecast as svc
from app.services.redact import ROLES_ALLOWED_COST, redact_costs
from app.services.user_provisioning import ensure_user

router = APIRouter(tags=["forecast"])

READ_ROLES: frozenset[str] = frozenset(
    {"Delivery", "Finance", "CEO", "SystemAdmin", "HR", "Sales", "SalesLeader", "Presales"}
)
WRITE_ROLES: frozenset[str] = frozenset({"Delivery", "Finance", "SystemAdmin", "Sales", "SalesLeader"})
SETTINGS_WRITE_ROLES: frozenset[str] = frozenset({"SystemAdmin", "Finance"})


def _gate(roles: frozenset[str]):
    async def dependency(user: AuthUser = Depends(current_user)) -> AuthUser:
        if not any(group in roles for group in user.groups):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return user

    return dependency


require_read = _gate(READ_ROLES)
require_write = _gate(WRITE_ROLES)
require_cost_read = _gate(ROLES_ALLOWED_COST)
require_settings_write = _gate(SETTINGS_WRITE_ROLES)


async def _actor(session: AsyncSession, user: AuthUser) -> AuthUser:
    """The persisted user row for ``user`` (FKs on created_by / owner need it)."""

    row = await ensure_user(session, user)
    return AuthUser(row.id, row.email, row.name, tuple(row.groups))


# ---- cost redaction for non-cost roles -------------------------------------

_ALLOCATION_ROW_COST_KEYS = ("cost_per_hour", "cost_per_hour_effective", "burden_pct")
_ALLOCATION_TOTAL_COST_KEYS = ("loaded_cost", "row_gm_pct", "under_resource_floor")


def _strip_individual_costs(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_individual_costs(item) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    is_allocation = "resource_id" in value and "totals" in value
    for key, item in value.items():
        if is_allocation and key in _ALLOCATION_ROW_COST_KEYS:
            continue
        if is_allocation and key == "totals":
            out[key] = {k: v for k, v in item.items() if k not in _ALLOCATION_TOTAL_COST_KEYS}
            continue
        if key == "allocation_months":
            out[key] = [{k: v for k, v in am.items() if k != "loaded_cost"} for am in item]
            continue
        if key in ("staffing_totals",) or key == "by_assignment_totals":
            out[key] = (
                {k: v for k, v in item.items() if k not in ("loaded_cost", "gm_pct")}
                if key == "staffing_totals"
                else {asg: {k: v for k, v in tot.items() if k not in ("loaded_cost", "gm_pct")} for asg, tot in item.items()}
            )
            continue
        if key == "by_assignment":
            out[key] = {
                asg: {m: {k: v for k, v in line.items() if k not in ("loaded_cost", "gm_pct")} for m, line in months.items()}
                for asg, months in item.items()
            }
            continue
        out[key] = _strip_individual_costs(item)
    return out


def _for_user(payload: Any, user: AuthUser) -> Any:
    if any(group in ROLES_ALLOWED_COST for group in user.groups):
        return payload
    return redact_costs(_strip_individual_costs(copy.deepcopy(payload)), set(user.groups))


# ---- schemas ----------------------------------------------------------------

EngagementType = Literal["fixed_cost", "assessment", "msp", "time_and_materials", "staff_augmentation"]
EmploymentType = Literal["w2_employee", "contractor_1099"]
Seniority = Literal["Junior", "Mid", "Senior", "Principal"]


class EngagementIn(BaseModel):
    client_id: uuid.UUID
    hubspot_deal_id: str | None = None
    opportunity_id: uuid.UUID | None = None
    name: str = Field(..., max_length=255)
    type: EngagementType
    start: date
    end: date
    total_price: Decimal | None = None
    monthly_fee: Decimal | None = None
    currency: str = Field(default="USD", max_length=8)
    additional_costs_flag: bool
    same_dates_for_all: bool
    owner_user_id: uuid.UUID | None = None


class EngagementPatch(BaseModel):
    client_id: uuid.UUID | None = None
    hubspot_deal_id: str | None = None
    opportunity_id: uuid.UUID | None = None
    name: str | None = Field(default=None, max_length=255)
    type: EngagementType | None = None
    start: date | None = None
    end: date | None = None
    total_price: Decimal | None = None
    monthly_fee: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    additional_costs_flag: bool | None = None
    same_dates_for_all: bool | None = None
    owner_user_id: uuid.UUID | None = None


class AllocationIn(BaseModel):
    resource_id: uuid.UUID
    role: str | None = Field(default=None, max_length=255)
    seniority: Seniority | None = None
    location: str | None = Field(default=None, max_length=64)
    employment_type: EmploymentType | None = None
    assignment: str | None = Field(default=None, max_length=255)
    utilization: Decimal = Decimal("1")
    bill_rate: Decimal | None = None
    cost_per_hour: Decimal | None = None
    start: date | None = None
    end: date | None = None
    hours_override: Decimal | None = None


class AllocationPatch(BaseModel):
    role: str | None = Field(default=None, max_length=255)
    seniority: Seniority | None = None
    location: str | None = Field(default=None, max_length=64)
    employment_type: EmploymentType | None = None
    assignment: str | None = Field(default=None, max_length=255)
    utilization: Decimal | None = None
    bill_rate: Decimal | None = None
    cost_per_hour: Decimal | None = None
    start: date | None = None
    end: date | None = None
    hours_override: Decimal | None = None


class CloseIn(BaseModel):
    end: date | None = None


class RehireIn(BaseModel):
    start: date | None = None
    bill_rate: Decimal | None = None
    cost_per_hour: Decimal | None = None


class EngagementCostIn(BaseModel):
    description: str = Field(..., max_length=255)
    category: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=64)
    amount: Decimal
    frequency: Literal["one_time", "monthly"] = "one_time"
    billed_to_client: bool


class ClientIn(BaseModel):
    name: str = Field(..., max_length=255)


class ResourceIn(BaseModel):
    name: str = Field(..., max_length=255)
    location: str = Field(..., max_length=64)
    employment_type: EmploymentType
    seniority: Seniority | None = None
    email: str | None = Field(default=None, max_length=320)


class LocationIn(BaseModel):
    name: str = Field(..., max_length=64)
    burden_pct_w2: Decimal
    burden_pct_1099: Decimal
    resource_floor_pct: Decimal


class RateCellIn(BaseModel):
    seniority: Seniority
    location: str
    employment_type: EmploymentType
    cost_per_hour: Decimal


class CalendarIn(BaseModel):
    hours_per_day: Decimal
    project_floor_pct: Decimal
    locations: list[LocationIn]
    rate_card: list[RateCellIn] = Field(default_factory=list)
    holidays: dict[str, list[str]] = Field(default_factory=dict)


def _dump(model: BaseModel, *, patch: bool = False) -> dict[str, Any]:
    return model.model_dump(exclude_unset=patch)


# ---- engagements -------------------------------------------------------------


@router.get("/engagements")
async def list_engagements(
    client_id: uuid.UUID | None = Query(default=None),
    type: EngagementType | None = Query(default=None),
    status_: Literal["draft", "active", "ended"] | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25),
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if page_size not in (25, 50, 100):
        raise HTTPException(status_code=422, detail={"missing": ["page_size must be 25, 50 or 100"]})
    total, items = await svc.list_engagements(
        session, client_id=client_id, type_=type, status=status_, page=page, page_size=page_size
    )
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.post("/engagements", status_code=201)
async def create_engagement(
    body: EngagementIn,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.create_engagement(session, actor=actor, body=_dump(body))
    payload = await svc.engagement_detail(session, row)
    await session.commit()
    return payload


@router.get("/engagements/{engagement_id}")
async def get_engagement(
    engagement_id: uuid.UUID,
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await svc.load_engagement(session, engagement_id)
    return await svc.engagement_detail(session, row)


@router.patch("/engagements/{engagement_id}")
async def patch_engagement(
    engagement_id: uuid.UUID,
    body: EngagementPatch,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.load_engagement(session, engagement_id)
    row = await svc.update_engagement(session, actor=actor, row=row, body=_dump(body, patch=True))
    payload = await svc.engagement_detail(session, row)
    await session.commit()
    return payload


@router.get("/engagements/{engagement_id}/forecast")
async def engagement_forecast(
    engagement_id: uuid.UUID,
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = await svc.load_engagement(session, engagement_id)
    payload = await svc.forecast_payload(session, row)
    await session.commit()  # a fresh forecast_run may have been stored
    return _for_user(payload, user)


# ---- allocations -------------------------------------------------------------


@router.get("/engagements/{engagement_id}/allocations")
async def list_allocations(
    engagement_id: uuid.UUID,
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    row = await svc.load_engagement(session, engagement_id)
    payload = await svc.list_allocations(session, row)
    await session.commit()
    return _for_user(payload, user)


@router.post("/engagements/{engagement_id}/allocations", status_code=201)
async def add_allocation(
    engagement_id: uuid.UUID,
    body: AllocationIn,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    eng = await svc.load_engagement(session, engagement_id)
    row = await svc.add_allocation(session, actor=actor, eng=eng, body=_dump(body))
    payload = await svc.allocation_detail(session, row)
    await session.commit()
    return _for_user(payload, user)


@router.patch("/allocations/{allocation_id}")
async def patch_allocation(
    allocation_id: uuid.UUID,
    body: AllocationPatch,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.load_allocation(session, allocation_id)
    row = await svc.patch_allocation(session, actor=actor, row=row, body=_dump(body, patch=True))
    payload = await svc.allocation_detail(session, row)
    await session.commit()
    return _for_user(payload, user)


@router.delete("/allocations/{allocation_id}", status_code=204, response_class=Response)
async def delete_allocation(
    allocation_id: uuid.UUID,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> Response:
    actor = await _actor(session, user)
    row = await svc.load_allocation(session, allocation_id)
    await svc.delete_allocation(session, actor=actor, row=row)
    await session.commit()
    return Response(status_code=204)


@router.post("/allocations/{allocation_id}/close")
async def close_allocation(
    allocation_id: uuid.UUID,
    body: CloseIn | None = None,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.load_allocation(session, allocation_id)
    row = await svc.close_allocation(session, actor=actor, row=row, end=body.end if body else None)
    payload = await svc.allocation_detail(session, row)
    await session.commit()
    return _for_user(payload, user)


@router.post("/allocations/{allocation_id}/rehire", status_code=201)
async def rehire_allocation(
    allocation_id: uuid.UUID,
    body: RehireIn | None = None,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.load_allocation(session, allocation_id)
    body = body or RehireIn()
    row = await svc.rehire_allocation(
        session, actor=actor, row=row, start=body.start, bill_rate=body.bill_rate, cost_per_hour=body.cost_per_hour
    )
    payload = await svc.allocation_detail(session, row)
    await session.commit()
    return _for_user(payload, user)


@router.post("/allocations/import", status_code=201)
async def import_allocations(
    engagement_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The workbook's staffing table as CSV (its own column headers)."""

    actor = await _actor(session, user)
    eng = await svc.load_engagement(session, engagement_id)
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    result = await svc.import_allocations_csv(session, actor=actor, eng=eng, text=text)
    await session.commit()
    return result


# ---- costs ------------------------------------------------------------------


@router.get("/engagements/{engagement_id}/costs")
async def list_costs(
    engagement_id: uuid.UUID,
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    eng = await svc.load_engagement(session, engagement_id)
    return [svc.serialize_cost(row) for row in await svc.cost_rows(session, eng.id)]


@router.post("/engagements/{engagement_id}/costs", status_code=201)
async def add_cost(
    engagement_id: uuid.UUID,
    body: EngagementCostIn,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    eng = await svc.load_engagement(session, engagement_id)
    row = await svc.add_cost(session, actor=actor, eng=eng, body=_dump(body))
    payload = svc.serialize_cost(row)
    await session.commit()
    return payload


class EngagementCostPatch(BaseModel):
    description: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=64)
    amount: Decimal | None = None
    frequency: Literal["one_time", "monthly"] | None = None
    billed_to_client: bool | None = None


@router.patch("/costs/{cost_id}")
async def patch_cost(
    cost_id: uuid.UUID,
    body: EngagementCostPatch,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await session.get(EngagementCost, cost_id)
    if row is None:
        raise HTTPException(status_code=404, detail="cost not found")
    row = await svc.update_cost(session, actor=actor, row=row, body=_dump(body, patch=True))
    payload = svc.serialize_cost(row)
    await session.commit()
    return payload


@router.delete("/costs/{cost_id}", status_code=204, response_class=Response)
async def delete_cost(
    cost_id: uuid.UUID,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> Response:
    actor = await _actor(session, user)
    row = await session.get(EngagementCost, cost_id)
    if row is None:
        raise HTTPException(status_code=404, detail="cost not found")
    await svc.delete_cost(session, actor=actor, row=row)
    await session.commit()
    return Response(status_code=204)


# ---- portfolio ----------------------------------------------------------------

_MONTH = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("/portfolio/forecast")
async def portfolio_forecast(
    month: str = Query(..., pattern=_MONTH),
    type: EngagementType | None = Query(default=None),
    client_id: uuid.UUID | None = Query(default=None),
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    view = await svc.portfolio_month(session, month=month, type_=type, client_id=client_id)
    await session.commit()
    return view


@router.get("/portfolio/forecast.csv", response_class=PlainTextResponse)
async def portfolio_forecast_csv(
    month: str = Query(..., pattern=_MONTH),
    type: EngagementType | None = Query(default=None),
    client_id: uuid.UUID | None = Query(default=None),
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    view = await svc.portfolio_month(session, month=month, type_=type, client_id=client_id)
    await session.commit()
    return PlainTextResponse(
        svc.portfolio_csv(view),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="portfolio-forecast-{month}.csv"'},
    )


# ---- clients + resources --------------------------------------------------------


@router.post("/clients", status_code=201)
async def create_client(
    body: ClientIn,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.create_manual_client(session, actor=actor, name=body.name)
    await session.commit()
    return {"id": str(row.id), "name": row.name, "source": svc.client_source(row)}


@router.get("/clients/forecast-options")
async def client_options(
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Contract shape of ``GET /clients`` (id, name, source) without the legacy list envelope."""

    rows = (await session.execute(select(Client).where(Client.archived_at.is_(None)).order_by(Client.name))).scalars().all()
    return [{"id": str(c.id), "name": c.name, "source": svc.client_source(c)} for c in rows]


@router.get("/resources")
async def list_resources(
    user: AuthUser = Depends(require_read),
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    return [svc.serialize_resource(r) for r in await svc.list_resources(session)]


@router.post("/resources", status_code=201)
async def create_resource(
    body: ResourceIn,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    row = await svc.create_resource(session, actor=actor, body=_dump(body))
    await session.commit()
    return svc.serialize_resource(row)


@router.delete("/resources/{resource_id}", status_code=204, response_class=Response)
async def delete_resource(
    resource_id: uuid.UUID,
    user: AuthUser = Depends(require_write),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Remove a person who was never allocated (409 while any allocation references them)."""

    actor = await _actor(session, user)
    row = await svc.load_resource(session, resource_id)
    await svc.delete_resource(session, actor=actor, row=row)
    await session.commit()
    return Response(status_code=204)


# ---- settings ---------------------------------------------------------------------


@router.get("/settings/forecast")
async def get_forecast_settings(
    user: AuthUser = Depends(require_cost_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return (await svc.load_calendar(session)).contract()


@router.put("/settings/forecast")
async def put_forecast_settings(
    body: CalendarIn,
    user: AuthUser = Depends(require_settings_write),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    bundle = await svc.save_calendar(session, actor=actor, body=_dump(body))
    await session.commit()
    return bundle.contract()
