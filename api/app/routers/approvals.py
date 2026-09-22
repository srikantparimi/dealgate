"""S4 E7 — approval packages API.

Router stays thin: role-gate + shape conversion + delegate to
:mod:`app.services.approvals`. Every state change through the service
already writes an ``audit_event`` (CLAUDE.md rule 5).

Endpoints:

- ``POST /approvals/packages/{opportunity_id}``   — submit (owner/admin).
- ``GET  /approvals/packages/{package_id}``       — full detail.
- ``POST /approvals/packages/{package_id}/decisions/{function}`` — approve/reject.
- ``POST /approvals/packages/{package_id}/void``  — manual void (admin).
- ``GET  /approvals/packages``                    — list (governance roles).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.opportunity import Opportunity
from app.services.redact import redact_costs
from app.services.approvals import (
    ApprovalError,
    ListFilters,
    decide,
    list_packages,
    load_package,
    manual_void,
    serialize_package,
    serialize_package_with_floors,
    submit_package,
)


router = APIRouter(prefix="/approvals", tags=["approvals"])


# ---- role gates ---------------------------------------------------------

# Every governance function that reads packages. Kept broad — the story
# says "any governance role reads".
_READ_ROLES: frozenset[str] = frozenset(
    {"Delivery", "HR", "Finance", "Legal", "CEO", "SalesLeader", "SystemAdmin"}
)

# Functions → the role that owns each decision (blueprint §6.5).
_FUNCTION_ROLES: dict[str, frozenset[str]] = {
    "delivery": frozenset({"Delivery", "SystemAdmin"}),
    "hr": frozenset({"HR", "SystemAdmin"}),
    "finance": frozenset({"Finance", "SystemAdmin"}),
    "legal": frozenset({"Legal", "SystemAdmin"}),
}


def _has_any(user: AuthUser, roles: frozenset[str]) -> bool:
    return any(g in roles for g in user.groups)


async def _require_read(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not _has_any(user, _READ_ROLES):
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


async def _require_submit(
    session: AsyncSession, user: AuthUser, opportunity_id: uuid.UUID
) -> None:
    """SystemAdmin or the deal's account owner may submit."""

    if "SystemAdmin" in user.groups:
        return
    opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    if opp.owner_id is not None and opp.owner_id == user.id:
        return
    raise HTTPException(
        status_code=403,
        detail="only the account owner or SystemAdmin may submit an approval package",
    )


def _require_function_role(user: AuthUser, function: str) -> None:
    roles = _FUNCTION_ROLES.get(function)
    if roles is None:
        raise HTTPException(
            status_code=422, detail=f"unknown function {function!r}"
        )
    if not _has_any(user, roles):
        raise HTTPException(
            status_code=403,
            detail=f"role required for {function!r} approval: {sorted(roles)}",
        )


# ---- schemas ------------------------------------------------------------


class DecisionBody(BaseModel):
    decision: str = Field(examples=["approve", "reject", "request_changes"])
    reason: str | None = None


class VoidBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1024)


class PackageListResponse(BaseModel):
    items: list[dict[str, Any]]
    page: int
    size: int
    total: int


# ---- helpers ------------------------------------------------------------


def _wrap(exc: ApprovalError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# ---- endpoints ----------------------------------------------------------


@router.post("/packages/{opportunity_id}", status_code=201)
async def submit_endpoint(
    opportunity_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_submit(session, user, opportunity_id)
    try:
        pkg = await submit_package(
            session, actor_id=user.id, opportunity_id=opportunity_id
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return redact_costs(await serialize_package_with_floors(session, pkg), set(user.groups))


@router.get("/packages/{package_id}")
async def get_endpoint(
    package_id: uuid.UUID,
    _user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        pkg = await load_package(session, package_id)
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return redact_costs(await serialize_package_with_floors(session, pkg), set(_user.groups))


@router.post("/packages/{package_id}/decisions/{function}")
async def decide_endpoint(
    package_id: uuid.UUID,
    function: str,
    body: DecisionBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_function_role(user, function)
    try:
        pkg = await decide(
            session,
            actor_id=user.id,
            package_id=package_id,
            function=function,
            decision=body.decision,
            reason=body.reason,
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return redact_costs(await serialize_package_with_floors(session, pkg), set(user.groups))


@router.post("/packages/{package_id}/void")
async def void_endpoint(
    package_id: uuid.UUID,
    body: VoidBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=403, detail="only SystemAdmin may manually void a package"
        )
    try:
        pkg = await manual_void(
            session, actor_id=user.id, package_id=package_id, reason=body.reason
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return redact_costs(await serialize_package_with_floors(session, pkg), set(user.groups))


@router.get("/packages", response_model=PackageListResponse)
async def list_endpoint(
    status_: str | None = Query(default=None, alias="status"),
    opportunity_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(_require_read),
    session: AsyncSession = Depends(get_session),
) -> PackageListResponse:
    filters = ListFilters(
        status=status_, opportunity_id=opportunity_id, page=page, size=size
    )
    rows, total = await list_packages(session, filters)
    return PackageListResponse(
        items=[serialize_package(r) for r in rows],
        page=page,
        size=size,
        total=total,
    )
