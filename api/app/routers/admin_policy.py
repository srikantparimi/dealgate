"""Admin margin policy API — S2 E4.

Governance roles (Finance/Delivery/HR/Legal/CEO/SystemAdmin) can read the
current + historic floors. Only Finance/SystemAdmin can publish. PATCH is
409 — versions are immutable by policy.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.policy import (
    ALLOWED_FX_CONVENTIONS,
    active_policy,
    list_policies,
    publish_policy,
)

READ_ROLES = ("Finance", "Delivery", "HR", "Legal", "CEO", "SystemAdmin")
WRITE_ROLES = ("Finance", "SystemAdmin")

router = APIRouter(prefix="/admin/policy", tags=["admin"])


# --- schemas ---------------------------------------------------------------


class PolicyVersionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    effective_from: date
    us_floor: Decimal
    india_floor: Decimal
    fx_convention: str
    published_at: datetime
    published_by: uuid.UUID | None
    notes: str | None
    is_active: bool = False


class ActivePolicySchema(BaseModel):
    """Convenience payload for the UI's "current policy" chip.

    Mirrors :class:`app.services.policy.ActivePolicy` — ``id`` is ``None``
    when Finance has not published a version yet and the blueprint sentinel
    (US 0.35 / India 0.50) is in effect.
    """

    id: uuid.UUID | None
    effective_from: date | None
    us_floor: Decimal
    india_floor: Decimal
    fx_convention: str
    is_default: bool


class PolicyListResponse(BaseModel):
    items: list[PolicyVersionSchema]
    active: ActivePolicySchema
    allowed_fx_conventions: list[str] = Field(
        default_factory=lambda: sorted(ALLOWED_FX_CONVENTIONS)
    )


class PublishPolicyRequest(BaseModel):
    effective_from: date
    us_floor: Decimal
    india_floor: Decimal
    fx_convention: str
    notes: str | None = Field(default=None, max_length=1024)


# --- helpers ---------------------------------------------------------------


def _serialize_version(version, *, active_id: uuid.UUID | None) -> PolicyVersionSchema:
    return PolicyVersionSchema(
        id=version.id,
        effective_from=version.effective_from,
        us_floor=version.us_floor,
        india_floor=version.india_floor,
        fx_convention=version.fx_convention,
        published_at=version.published_at,
        published_by=version.published_by,
        notes=version.notes,
        is_active=(active_id is not None and version.id == active_id),
    )


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=PolicyListResponse)
async def list_policies_endpoint(
    _user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> PolicyListResponse:
    versions = await list_policies(session)
    active = await active_policy(session)
    return PolicyListResponse(
        items=[_serialize_version(v, active_id=active.id) for v in versions],
        active=ActivePolicySchema(
            id=active.id,
            effective_from=active.effective_from,
            us_floor=active.us_floor,
            india_floor=active.india_floor,
            fx_convention=active.fx_convention,
            is_default=active.is_default,
        ),
    )


@router.post("", response_model=PolicyVersionSchema, status_code=201)
async def publish_policy_endpoint(
    body: PublishPolicyRequest,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> PolicyVersionSchema:
    version = await publish_policy(
        session,
        actor_id=actor.id,
        us_floor=body.us_floor,
        india_floor=body.india_floor,
        fx_convention=body.fx_convention,
        effective_from=body.effective_from,
        notes=body.notes,
    )
    active = await active_policy(session)
    return _serialize_version(version, active_id=active.id)


@router.patch("/{version_id}")
async def patch_policy_endpoint(
    version_id: uuid.UUID,  # noqa: ARG001 — accepted for URL shape, always rejected.
    _user: AuthUser = Depends(require_role(*WRITE_ROLES)),
) -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="policy versions are immutable — publish a new version instead",
    )
