"""Opportunity Adviser API — S3 E11.

Thin router: schema validation + role check + delegate to
:mod:`app.services.adviser`. Every persisted row is immutable (no PATCH,
no DELETE). No PDF export endpoint (§15 risk mitigation — the label alone
is the deliverable; a polished PDF invites human misuse).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.services.adviser import (
    Estimate,
    Questions,
    estimate as run_estimate,
    list_estimates,
    load_estimate,
    serialize_row,
)
from app.services.redact import redact_costs

router = APIRouter(prefix="/adviser", tags=["adviser"])


# Marketing/Sales/Presales/SystemAdmin can submit an estimate; every
# governance role can read one back. Mirrors backlog §S3-E11.
WRITE_ROLES = ("Marketing", "Sales", "Presales", "SystemAdmin")
READ_ROLES = (
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
)


# --- schemas ---------------------------------------------------------------


class AdviserIntake(BaseModel):
    client_name: str = Field(min_length=1, max_length=255)
    problem: str = Field(min_length=1, max_length=4000)
    website: str | None = Field(default=None, max_length=512)
    functions: list[str] | None = None
    users_count: int | None = Field(default=None, ge=0)
    systems: list[str] | None = None
    geography: str | None = Field(default=None, max_length=128)
    timeline: str | None = Field(default=None, max_length=128)
    budget: str | None = Field(default=None, max_length=128)


# --- endpoints -------------------------------------------------------------


@router.post("/estimates", status_code=status.HTTP_201_CREATED)
async def create_estimate(
    body: AdviserIntake,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    inputs = body.model_dump(exclude_none=True)
    result: Estimate | Questions = await run_estimate(
        session, actor_id=actor.id, inputs=inputs
    )
    return result.serialize()


@router.get("/estimates")
async def list_estimates_endpoint(
    owner: str = Query(default="me"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    owner_id: uuid.UUID | None
    if owner == "me":
        owner_id = user.id
    elif owner in ("all", "*"):
        # Any governance-role reader may see the org's estimates. Fine-grained
        # scoping (e.g. Marketing sees only Marketing drafts) lands in a
        # if the leadership asks for it.
        owner_id = None
    else:
        try:
            owner_id = uuid.UUID(owner)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="owner must be 'me', 'all', or a UUID",
            ) from exc

    rows, total = await list_estimates(
        session, owner_id=owner_id, page=page, size=size
    )
    payload = {
        "items": [serialize_row(r) for r in rows],
        "page": page,
        "size": size,
        "total": total,
    }
    # S7 B: strip cost bands for readers without a cost-authorized role
    # (Sales / SalesLeader / Marketing / Presales / Legal).
    return redact_costs(payload, set(user.groups))


@router.get("/estimates/{estimate_id}")
async def get_estimate(
    estimate_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await load_estimate(session, estimate_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="adviser estimate not found"
        )
    return redact_costs(serialize_row(row), set(user.groups))


# NOTE: There is deliberately no `GET /adviser/estimates/{id}/pdf` route.
# §15 risk mitigation: a PDF export invites the number to be forwarded as if
# it were a quote. The UI shows the label and the "Send to Presales" button
# instead. Tests assert the 404 explicitly.
