"""S24-AG1 B9 / F5 — HubSpot ``msa_type`` hints (docs/reference/openapi-agreements.yaml).

- ``GET  /agreements/hubspot-values``           every role that can see agreements (view only).
- ``PUT  /agreements/hubspot-mapping``          SystemAdmin: save which values mean the MSA is covered.
- ``POST /agreements/hubspot-mapping/apply``    SystemAdmin: dry run by default; ``dry_run=false`` marks.

Roles are enforced here (403), whatever the page shows. A test identity may read
and dry-run, but outside local/test it can neither save a mapping nor apply one:
the nightly sync applies the saved mapping to real clients, crediting whoever saved
it. The logic lives in :mod:`app.services.agreement_hubspot`.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services import agreement_hubspot as svc
from app.services.agreement_status import visibility_scope
from app.services.test_fixtures import is_test_user
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/agreements", tags=["agreements"])

# Every role views agreements (directive B11); SystemAdmin alone saves and applies the mapping.
READ_ROLES: tuple[str, ...] = (
    "Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO", "SystemAdmin",
)
ADMIN_ROLES: tuple[str, ...] = ("SystemAdmin",)
MAX_ITEMS = 500

TEST_IDENTITY_REFUSED = (
    "Test identities cannot change the HubSpot mapping here: the nightly sync would apply it to real clients."
)


class MappingItem(BaseModel):
    value: str = Field(..., max_length=200)
    action: Literal["covered", "ignore"]


class MappingRequest(BaseModel):
    items: list[MappingItem] = Field(default_factory=list, max_length=MAX_ITEMS)


def _test_writes_allowed() -> bool:
    return os.environ.get("DEALGATE_ENV", "local") in ("local", "test")


def _may_change_mapping(user: AuthUser) -> bool:
    return "SystemAdmin" in user.groups and (not is_test_user(user) or _test_writes_allowed())


def _refuse_test_identity(user: AuthUser) -> None:
    if is_test_user(user) and not _test_writes_allowed():
        raise HTTPException(status_code=403, detail=TEST_IDENTITY_REFUSED)


def _items(body: MappingRequest) -> list[tuple[str, str]]:
    seen: dict[str, str] = {}
    for item in body.items:
        value = item.value.strip()
        if not value:
            raise HTTPException(status_code=422, detail="A mapped msa_type value cannot be blank.")
        if value in seen:
            raise HTTPException(status_code=422, detail=f"“{value}” is mapped more than once.")
        seen[value] = item.action
    return list(seen.items())


@router.get("/hubspot-values")
async def get_hubspot_values(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Distinct ``msa_type`` values on the clients the caller can see, with counts and the saved mapping.

    A read: it writes nothing (no user provisioning, no audit row).
    """
    scope = await visibility_scope(session, user)
    return await svc.hubspot_values(session, scope=scope, can_edit=_may_change_mapping(user))


@router.put("/hubspot-mapping")
async def put_hubspot_mapping(
    body: MappingRequest,
    user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Replace the whole mapping. Every saved row credits the caller, so later marks credit this admin."""
    _refuse_test_identity(user)
    items = _items(body)
    actor = await ensure_user(session, user)
    # Release the identity/audit locks before the settings-row lock (lock order: settings first, audit last).
    await session.commit()
    await svc.save_mapping(session, actor_id=actor.id, items=items)
    await session.commit()
    scope = await visibility_scope(session, user)
    return await svc.hubspot_values(session, scope=scope, can_edit=True)


@router.post("/hubspot-mapping/apply")
async def apply_hubspot_mapping(
    dry_run: bool = Query(default=True),
    user: AuthUser = Depends(require_role(*ADMIN_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Mark the MSA covered for clients whose value is mapped to covered and that hold nothing for it.

    Dry run by default (counts only, writes nothing). ``dry_run=false`` marks, commits every 25 clients and
    records the run in the Activity feed.
    """
    scope = await visibility_scope(session, user)
    if dry_run:
        result = await svc.apply_mapping(session, dry_run=True, trigger="dialog", actor_id=None, scope=scope)
        return result.as_dict()
    _refuse_test_identity(user)
    actor = await ensure_user(session, user)
    await session.commit()
    result = await svc.apply_mapping(session, dry_run=False, trigger="dialog", actor_id=actor.id, scope=scope)
    return result.as_dict()


__all__ = ["router"]
