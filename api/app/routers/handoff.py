"""S20 W7 · handoff / release-gate API (T23).

Endpoints:

- ``GET  /handoff/{package_id}/gate``        — gate status (three-event
  breakdown) so the UI can render the checklist without inferring state.
- ``POST /handoff/{package_id}/accept``      — file the delivery_acceptance
  row. Delivery / SystemAdmin only.
- ``GET  /handoff/{package_id}/acceptance``  — the current
  delivery_acceptance row (or 404).

Role gates are UX + audit — the service re-checks server-side and
audits every transition (CLAUDE.md rule 5).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.approval import ApprovalPackage
from app.services.delivery_acceptance import (
    DeliveryAcceptanceError,
    latest_for as latest_acceptance,
    record as record_acceptance,
    serialize as serialize_acceptance,
)
from app.services.handoff import check_release_gate


router = APIRouter(prefix="/handoff", tags=["handoff"])


_READ_ROLES: frozenset[str] = frozenset(
    {
        "Marketing",
        "Sales",
        "SalesLeader",
        "Presales",
        "Delivery",
        "HR",
        "Finance",
        "Legal",
        "CEO",
        "SystemAdmin",
    }
)


def _require_read(user: AuthUser) -> None:
    if not any(g in _READ_ROLES for g in user.groups):
        raise HTTPException(status_code=403, detail="insufficient role")


async def _load_package(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    row = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="approval_package not found")
    return row


class AcceptanceBody(BaseModel):
    notes: str | None = Field(default=None, max_length=2048)
    staffing_confirmed: bool = False
    billing_setup_confirmed: bool = False
    po_confirmed: bool = False


@router.get("/{package_id}/gate")
async def gate_endpoint(
    package_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_read(user)
    package = await _load_package(session, package_id)
    gate = await check_release_gate(session, package)
    return gate.to_json()


@router.get("/{package_id}/acceptance")
async def acceptance_get(
    package_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any] | None:
    _require_read(user)
    await _load_package(session, package_id)
    row = await latest_acceptance(session, package_id)
    if row is None:
        return None
    return serialize_acceptance(row)


@router.post("/{package_id}/accept", status_code=201)
async def acceptance_post(
    package_id: uuid.UUID,
    body: AcceptanceBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # Server enforces the Delivery / SystemAdmin gate — we don't rely on
    # the UI's disabled-button here (§0.5). `record` raises 403 if the
    # actor is not in the Delivery group.
    await _load_package(session, package_id)
    try:
        row = await record_acceptance(
            session,
            actor_id=user.id,
            package_id=package_id,
            notes=body.notes,
            staffing_confirmed=body.staffing_confirmed,
            billing_setup_confirmed=body.billing_setup_confirmed,
            po_confirmed=body.po_confirmed,
        )
    except DeliveryAcceptanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return serialize_acceptance(row)
