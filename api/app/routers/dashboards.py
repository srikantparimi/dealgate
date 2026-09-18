"""Role dashboards + Client SOW/GM view — S5 E10.

Router is thin: role-gate on the way in, delegate the aggregation to
:mod:`app.services.dashboards`, return the JSON verbatim. No math or role
inference happens client-side (CLAUDE.md rule 2, blueprint §2 / §9).

Endpoints:

- ``GET /dashboards/ceo``               — CEO / SystemAdmin.
- ``GET /dashboards/finance``           — Finance / SystemAdmin.
- ``GET /dashboards/delivery``          — Delivery / SystemAdmin.
- ``GET /dashboards/sales``             — Sales / SalesLeader / Marketing / SystemAdmin.
- ``GET /dashboards/hr``                — HR / SystemAdmin.
- ``GET /dashboards/legal``             — Legal / SystemAdmin.
- ``GET /dashboards/client/{client_id}`` — any governance role.

Read-only; no state changes, no audit rows emitted (rule 5 doesn't apply
to pure reads).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.dashboards import (
    ceo_view,
    client_sow_gm_view,
    delivery_view,
    finance_view,
    hr_view,
    legal_view,
    sales_view,
)


router = APIRouter(prefix="/dashboards", tags=["dashboards"])


# ---- role gates ---------------------------------------------------------

# Client SOW GM view is readable by any governance role. Matches the
# blueprint §3 leader read set plus Sales who owns the deal — but the
# service does not filter by ownership, so gate on the leader set here.
_CLIENT_SOW_READ_ROLES: frozenset[str] = frozenset(
    {"CEO", "Finance", "Delivery", "Legal", "HR", "SalesLeader", "SystemAdmin"}
)


def _require_any(user: AuthUser, roles: tuple[str, ...]) -> None:
    if not any(role in user.groups for role in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
        )


# ---- endpoints ----------------------------------------------------------


@router.get("/ceo")
async def get_ceo_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("CEO", "SystemAdmin"))
    return await ceo_view(session)


@router.get("/finance")
async def get_finance_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("Finance", "SystemAdmin"))
    return await finance_view(session)


@router.get("/delivery")
async def get_delivery_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("Delivery", "SystemAdmin"))
    return await delivery_view(session)


@router.get("/sales")
async def get_sales_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("Sales", "SalesLeader", "Marketing", "SystemAdmin"))
    return await sales_view(session, user)


@router.get("/hr")
async def get_hr_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("HR", "SystemAdmin"))
    return await hr_view(session)


@router.get("/legal")
async def get_legal_dashboard(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_any(user, ("Legal", "SystemAdmin"))
    return await legal_view(session)


@router.get("/client/{client_id}")
async def get_client_sow_dashboard(
    client_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not any(role in user.groups for role in _CLIENT_SOW_READ_ROLES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
        )
    return await client_sow_gm_view(session, client_id)
