"""Just-in-time provisioning of a `user` row for an authenticated principal.

Why this exists
---------------
``app/auth/deps.py`` builds an :class:`AuthUser` straight from the verified
Cognito token — id (the ``sub``), email, name, groups — and never touches the
database. Nothing else provisions users either: before S10-04 the only inserts
were the admin console (``admin_users.py``) and the HubSpot intake worker.

Several tables carry a foreign key to ``user.id``. ``sow_upload_job.uploader_id``
is ``NOT NULL`` with an FK, so the first upload by anyone who signed in through
SSO but was never invited through the admin console raises an
``IntegrityError`` — an unhandled 500 at the worst possible moment, on someone's
first real use of the product.

Why the service layer and not the auth dependency
-------------------------------------------------
``current_user`` is a pure token-verification dependency with no session. Doing
a write there would open a transaction on every request including plain reads,
and would blur an auth failure into a database failure. Instead the services
that are about to write a user-referencing row call :func:`ensure_user` first,
inside the transaction that write belongs to.

Audit (CLAUDE.md rule 5)
------------------------
Provisioning a user is a state change, so it writes an ``audit_event`` in the
same transaction. It is strictly idempotent: an existing user produces no audit
row, or every upload would write one. A group change produces one
``user.groups_synced`` row recording the before/after.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.user import User

__all__ = ["ensure_user"]


async def ensure_user(session: AsyncSession, actor: AuthUser) -> User:
    """Return the ``user`` row for ``actor``, creating it if absent.

    Resolution order is id, then email. The email fallback matters: an admin
    may have invited someone (creating a row with a fresh uuid) before they
    ever signed in, and their Cognito ``sub`` will not match that id. Adopting
    the existing row keeps one person to one row rather than silently creating
    a duplicate that splits their task list and audit trail.
    """

    existing = (
        await session.execute(select(User).where(User.id == actor.id))
    ).scalar_one_or_none()

    if existing is None and actor.email:
        existing = (
            await session.execute(
                select(User).where(User.email == actor.email)
            )
        ).scalar_one_or_none()

    now = datetime.now(UTC)

    if existing is not None:
        # Keep group membership in step with the token, and audit it when it
        # actually moves — an IdP group change is a permission change.
        token_groups = sorted(actor.groups or [])
        current_groups = sorted(existing.groups or [])
        if token_groups != current_groups:
            await append_audit(
                session,
                actor_id=existing.id,
                action="user.groups_synced",
                entity="user",
                entity_id=str(existing.id),
                before={"groups": current_groups},
                after={"groups": token_groups, "source": "cognito_token"},
            )
            existing.groups = list(actor.groups or [])
        existing.last_login = now
        await session.flush()
        return existing

    user = User(
        id=actor.id,
        email=actor.email,
        name=actor.name or actor.email,
        groups=list(actor.groups or []),
        last_login=now,
    )
    session.add(user)
    await session.flush()
    await append_audit(
        session,
        actor_id=user.id,
        action="user.provisioned",
        entity="user",
        entity_id=str(user.id),
        before=None,
        after={
            "email": user.email,
            "name": user.name,
            "groups": list(user.groups or []),
            "source": "cognito_jit",
        },
    )
    return user
