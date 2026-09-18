"""S4 E7 — CEO exception HTTP surface (Agent V, wave 3).

Endpoints (all under ``/ceo-exceptions`` or ``/admin/ceo-delegates``):

- ``GET /ceo-exceptions`` — CEO / delegate / SystemAdmin inbox.
- ``GET /ceo-exceptions/{id}`` — full brief + rationale + decision.
  Any governance role reads.
- ``PATCH /ceo-exceptions/{id}/rationale`` — account owner writes the
  business rationale. ``tidy=true`` asks Bedrock to lightly copyedit
  the wording (raw text always stored verbatim).
- ``POST /ceo-exceptions/{id}/decisions`` — CEO or an active CEO
  delegate records the final decision.
- ``POST /admin/ceo-delegates`` — SystemAdmin grants a time-bound
  delegation.

Every state change is audited by the service layer (rule 5). Money never
lives on this surface — the brief already contains the numbers the GM
engine computed.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.services.ceo_exception import (
    DECISIONS,
    active_delegate,
    can_decide,
    decide,
    grant_delegate,
    list_exceptions,
    load_exception,
    set_rationale,
)

router = APIRouter(tags=["ceo-exception"])


# --- role sets --------------------------------------------------------------

# Any governance role can read the brief. Matches the adviser's read set
# so a Legal or HR reader working the file can see the CEO's context.
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

# CEO + SystemAdmin can always see the inbox. Delegates are resolved at
# request time — a caller in the "any" set who happens to be the active
# delegate also passes the runtime check inside the endpoint.
INBOX_ROLES = ("CEO", "SystemAdmin")

DECIDE_ROLES = ("CEO", "SystemAdmin")


# --- schemas ----------------------------------------------------------------


class RationaleBody(BaseModel):
    rationale_text: str = Field(min_length=1, max_length=4000)
    tidy: bool = False


class DecisionBody(BaseModel):
    decision: str = Field(pattern="^(approve|reject|return_for_changes)$")
    conditions_text: str | None = Field(default=None, max_length=4000)
    valid_until: date | None = None


class DelegateBody(BaseModel):
    delegate_id: uuid.UUID
    effective_from: date
    expiry: date


def _serialize(row) -> dict:
    return {
        "id": str(row.id),
        "package_id": str(row.package_id),
        "brief_json": row.brief_json,
        "rationale_text": row.rationale_text,
        "rationale_tidied_text": row.rationale_tidied_text,
        "rationale_set_by": (
            str(row.rationale_set_by) if row.rationale_set_by else None
        ),
        "rationale_set_at": (
            row.rationale_set_at.isoformat() if row.rationale_set_at else None
        ),
        "conditions_text": row.conditions_text,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "decision": row.decision,
        "decided_by": str(row.decided_by) if row.decided_by else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "drafted_at": row.drafted_at.isoformat() if row.drafted_at else None,
    }


# --- endpoints --------------------------------------------------------------


@router.get("/ceo-exceptions")
async def list_endpoint(
    status_filter: str = Query(default="pending", alias="status"),
    actor: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # CEO, SystemAdmin, or the currently-active delegate can see the inbox.
    permitted = actor.has_any_role(INBOX_ROLES)
    if not permitted:
        delegate = await active_delegate(session)
        permitted = delegate is not None and delegate.delegate_id == actor.id
    if not permitted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role"
        )
    pending_only = status_filter == "pending"
    rows = await list_exceptions(session, pending_only=pending_only)
    return {"items": [_serialize(r) for r in rows]}


@router.get("/ceo-exceptions/{exception_id}")
async def get_endpoint(
    exception_id: uuid.UUID,
    _actor: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await load_exception(session, exception_id)
    return _serialize(row)


@router.patch("/ceo-exceptions/{exception_id}/rationale")
async def patch_rationale_endpoint(
    exception_id: uuid.UUID,
    body: RationaleBody,
    actor: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # Owner check happens inside the service, but re-auth up front so an
    # unauthenticated caller sees 401 rather than an implicit 403.
    row = await set_rationale(
        session,
        actor_id=actor.id,
        exception_id=exception_id,
        rationale_text=body.rationale_text,
        tidy=body.tidy,
    )
    return _serialize(row)


@router.post(
    "/ceo-exceptions/{exception_id}/decisions",
    status_code=status.HTTP_201_CREATED,
)
async def post_decision_endpoint(
    exception_id: uuid.UUID,
    body: DecisionBody,
    actor: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    # can_decide() handles the CEO + delegate check inside the service.
    row = await decide(
        session,
        actor_id=actor.id,
        actor_groups=tuple(actor.groups),
        exception_id=exception_id,
        decision=body.decision,
        conditions_text=body.conditions_text,
        valid_until=body.valid_until,
    )
    return _serialize(row)


@router.post(
    "/admin/ceo-delegates", status_code=status.HTTP_201_CREATED
)
async def grant_delegate_endpoint(
    body: DelegateBody,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> dict:
    row = await grant_delegate(
        session,
        actor_id=actor.id,
        delegate_id=body.delegate_id,
        effective_from=body.effective_from,
        expiry=body.expiry,
    )
    return {
        "id": str(row.id),
        "delegate_id": str(row.delegate_id),
        "effective_from": row.effective_from.isoformat(),
        "expiry": row.expiry.isoformat(),
        "granted_by": str(row.granted_by),
        "granted_at": row.granted_at.isoformat() if row.granted_at else None,
    }


__all__ = [
    "DECIDE_ROLES",
    "INBOX_ROLES",
    "READ_ROLES",
    "can_decide",
    "router",
]
