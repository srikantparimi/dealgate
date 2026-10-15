"""``/users`` — S23-PL2 B4: an admin links a DealGate user to a HubSpot owner.

Sign-in and the nightly owner sync link users automatically by exact email
match; this route overrides that (``hubspot_owner_id: null`` unlinks). The
service validates, writes the decision as ``admin`` and audits it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.canonical_user import canonical_actor
from app.services.hubspot_owners import set_owner_link

router = APIRouter(prefix="/users", tags=["users"])


class HubspotOwnerLinkIn(BaseModel):
    # Required, nullable: null records "this user has no HubSpot owner".
    hubspot_owner_id: str | None = Field(..., max_length=64)


@router.put("/{user_id}/hubspot-owner", status_code=status.HTTP_204_NO_CONTENT)
async def put_user_hubspot_owner(
    user_id: uuid.UUID,
    body: HubspotOwnerLinkIn,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await canonical_actor(session, actor)
    await set_owner_link(
        session, actor_id=admin.id, user_id=user_id, hubspot_owner_id=body.hubspot_owner_id
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
