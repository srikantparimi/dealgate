"""S23-PL2 B4/B11 — who the caller is in DealGate's own tables.

``AuthUser.id`` is the login id (the Cognito ``sub``). A user first created by
HubSpot intake or by an admin invite has a DealGate row with a different id,
and every personal row (saved views, groups, watches, next actions) is keyed
on the DealGate id. Reads resolve that row in one statement and never write;
writes go through :func:`canonical_actor`, which provisions or adopts the row
the same way ``ensure_user`` always has.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth import AuthUser
from app.models.user import User
from app.services.hubspot_owners import HubspotOwner
from app.services import user_provisioning
from app.services.user_provisioning import ensure_user


@dataclass(frozen=True)
class Viewer:
    """The caller as the Pipeline sees them.

    ``user_id`` is the DealGate user id (None before the first login wrote a
    row). ``hubspot_owner_id`` is the effective link: the stored one once it
    has been decided (``link`` is ``email`` or ``admin``; an admin may have
    decided "no owner"), otherwise the exact-email match with an active
    HubSpot owner, if exactly one exists.
    """

    user_id: uuid.UUID | None
    hubspot_owner_id: str | None
    link: str | None

    @property
    def mine_available(self) -> bool:
        return self.hubspot_owner_id is not None


# Cognito answers for logins whose access token carries no email: sub → (email, expires).
_EMAIL_BY_SUB: dict[str, tuple[str | None, float]] = {}
_EMAIL_TTL_S = 15 * 60
_MISS_TTL_S = 60


async def _email_from_cognito(sub: str) -> str | None:
    """The login's email, as ensure_user would find it; cached, off the event loop."""

    hit = _EMAIL_BY_SUB.get(sub)
    now = time.monotonic()
    if hit is not None and hit[1] > now:
        return hit[0]
    email, _name = await asyncio.to_thread(user_provisioning.hydrate_from_cognito, sub)
    usable = email if email and not user_provisioning._looks_like_uuid(email) else None
    _EMAIL_BY_SUB[sub] = (usable, now + (_EMAIL_TTL_S if usable else _MISS_TTL_S))
    return usable


async def _viewer_rows(session: AsyncSession, *conditions):
    owner = aliased(HubspotOwner)
    other = aliased(User)
    # An owner already linked to someone else is not this user's email match.
    linked_elsewhere = (
        select(other.id)
        .where(other.hubspot_owner_id == owner.id, other.id != User.id)
        .correlate(owner, User)
        .exists()
    )
    return (
        await session.execute(
            select(User.id, User.hubspot_owner_id, User.hubspot_owner_link, owner.id, User.cognito_sub)
            .outerjoin(
                owner,
                and_(
                    func.lower(owner.email) == func.lower(User.email),
                    owner.archived.is_(False),
                    ~linked_elsewhere,
                ),
            )
            .where(or_(*conditions))
        )
    ).all()


async def resolve_viewer(session: AsyncSession, actor: AuthUser) -> Viewer:
    sub = str(actor.id)
    # Access tokens carry no email: AuthUser.email is then the sub itself.
    email = None if user_provisioning._looks_like_uuid(actor.email) else actor.email
    conditions = [User.id == actor.id, User.cognito_sub == sub]
    if email:
        conditions.append(User.email == email)
    rows = await _viewer_rows(session, *conditions)
    if not rows and email is None:
        # A row adopted by email that has not been told this login yet (no write
        # since): find it the way ensure_user does, by the email Cognito holds.
        email = await _email_from_cognito(sub)
        if email:
            rows = await _viewer_rows(session, User.email == email)
    if not rows:
        return Viewer(user_id=None, hubspot_owner_id=None, link=None)
    # Same resolution order as ensure_user: id, then the remembered login, then email.
    chosen = ([r for r in rows if r[0] == actor.id]
              or [r for r in rows if r[4] == sub]
              or rows)
    user_id, stored_owner, link = chosen[0][0], chosen[0][1], chosen[0][2]
    if link in ("email", "admin"):
        return Viewer(user_id=user_id, hubspot_owner_id=stored_owner, link=link)
    matches = {r[3] for r in chosen if r[0] == user_id and r[3] is not None}
    return Viewer(
        user_id=user_id,
        hubspot_owner_id=next(iter(matches)) if len(matches) == 1 else None,
        link=None,
    )


async def canonical_actor(session: AsyncSession, actor: AuthUser) -> AuthUser:
    """The caller re-keyed on their DealGate user id, for writes.

    Provisions or adopts the user row (``ensure_user``) and returns an
    ``AuthUser`` whose ``id`` is that row's id, keeping the token's groups.
    """

    user = await ensure_user(session, actor)
    return AuthUser(user.id, user.email, user.name, tuple(actor.groups or ()))
