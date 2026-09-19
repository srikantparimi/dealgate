"""Admin API for the function_owner table (Sprint 9 wave 1).

SystemAdmin-only. Reads the resolver's answer so the UI can display who
would be routed today, and lets an admin add / remove rows. Every write
emits an ``audit_event`` in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, require_role
from app.db import get_session
from app.models.function_owner import ALLOWED_FUNCTIONS
from app.services.approvers import (
    delete_owner,
    list_owners,
    resolve_all,
    upsert_owner,
)


router = APIRouter(prefix="/admin/function-owners", tags=["admin"])


class OwnerRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    function: str
    business_unit: str | None
    user_id: uuid.UUID
    is_default: bool
    created_at: datetime


class SetOwnerRequest(BaseModel):
    function: str = Field(min_length=1, max_length=32)
    business_unit: str | None = Field(default=None, max_length=64)
    user_id: uuid.UUID
    is_default: bool = True


class ResolveResponse(BaseModel):
    function: str
    user_id: uuid.UUID | None
    source: str
    business_unit: str | None


@router.get("", response_model=list[OwnerRow])
async def list_owners_endpoint(
    _actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> list[OwnerRow]:
    rows = await list_owners(session)
    return [OwnerRow.model_validate(r) for r in rows]


@router.post("", response_model=OwnerRow, status_code=201)
async def set_owner_endpoint(
    body: SetOwnerRequest,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> OwnerRow:
    if body.function not in ALLOWED_FUNCTIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"function must be one of {sorted(ALLOWED_FUNCTIONS)}",
        )
    row = await upsert_owner(
        session,
        function=body.function,
        business_unit=body.business_unit,
        user_id=body.user_id,
        is_default=body.is_default,
    )
    await append_audit(
        session,
        actor_id=actor.id,
        action="function_owner.set",
        entity="function_owner",
        entity_id=str(row.id),
        before=None,
        after={
            "function": row.function,
            "business_unit": row.business_unit,
            "user_id": str(row.user_id),
            "is_default": row.is_default,
        },
    )
    await session.commit()
    return OwnerRow.model_validate(row)


@router.delete("/{owner_id}", status_code=204)
async def delete_owner_endpoint(
    owner_id: uuid.UUID,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await delete_owner(session, owner_id=owner_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="owner row not found"
        )
    await append_audit(
        session,
        actor_id=actor.id,
        action="function_owner.deleted",
        entity="function_owner",
        entity_id=str(owner_id),
        before={"id": str(owner_id)},
        after=None,
    )
    await session.commit()


@router.get("/resolve", response_model=list[ResolveResponse])
async def resolve_endpoint(
    business_unit: str | None = None,
    _actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> list[ResolveResponse]:
    """Return the resolver's answer for every function (for admin preview)."""

    resolved = await resolve_all(session, business_unit=business_unit)
    return [
        ResolveResponse(
            function=fn,
            user_id=r.user_id,
            source=r.source,
            business_unit=r.business_unit,
        )
        for fn, r in resolved.items()
    ]
