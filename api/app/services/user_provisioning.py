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

import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.user import User
from app.services.user_identity import is_identity_placeholder

__all__ = ["ensure_user", "hydrate_from_cognito"]

_log = logging.getLogger("dealgate.user_provisioning")


def _looks_like_uuid(value: str | None) -> bool:
    if not value:
        return True
    v = value.strip()
    return (
        len(v) == 36
        and v.count("-") == 4
        and all(c in "0123456789abcdef-" for c in v.lower())
    )


def hydrate_from_cognito(sub: str) -> tuple[str | None, str | None]:
    """Fetch (email, name) from Cognito for a user whose access token did
    not carry them.

    Called only when the caller's ``AuthUser`` fields look like the raw
    ``sub`` (i.e. no useful email/name). Silently returns ``(None, None)``
    when Cognito isn't configured or the call fails — this is best-effort
    enrichment, never a source of 500s.
    """

    pool_id = os.environ.get("COGNITO_USER_POOL_ID")
    region = os.environ.get("COGNITO_REGION", "us-east-2")
    if not pool_id:
        return None, None
    try:
        import boto3  # local import: this branch only runs on staging/prod.

        client = boto3.client("cognito-idp", region_name=region)
        resp = client.admin_get_user(UserPoolId=pool_id, Username=sub)
        attrs = {a["Name"]: a["Value"] for a in resp.get("UserAttributes", [])}
        return attrs.get("email"), attrs.get("name")
    except Exception as exc:  # noqa: BLE001 — enrichment must never break auth.
        _log.info(
            "cognito_hydrate_failed",
            extra={"sub": sub, "error": str(exc)[:200]},
        )
        return None, None


async def ensure_user(session: AsyncSession, actor: AuthUser) -> User:
    """Return the ``user`` row for ``actor``, creating it if absent.

    Resolution order is id, then email. The email fallback matters: an admin
    may have invited someone (creating a row with a fresh uuid) before they
    ever signed in, and their Cognito ``sub`` will not match that id. Adopting
    the existing row keeps one person to one row rather than silently creating
    a duplicate that splits their task list and audit trail.
    """

    # Cognito access tokens don't carry email/name, so `_user_from_claims`
    # falls back to the sub (a UUID string) for both fields. When that
    # happens, hydrate from Cognito once so the row lands with a human
    # email + name instead of the sub.
    actor_email = actor.email
    actor_name = actor.name
    if _looks_like_uuid(actor_email) or _looks_like_uuid(actor_name):
        real_email, real_name = hydrate_from_cognito(str(actor.id))
        if real_email:
            actor_email = real_email
        if real_name:
            actor_name = real_name

    existing = (
        await session.execute(select(User).where(User.id == actor.id))
    ).scalar_one_or_none()

    if existing is None and actor_email and not _looks_like_uuid(actor_email):
        existing = (
            await session.execute(
                select(User).where(User.email == actor_email)
            )
        ).scalar_one_or_none()

    now = datetime.now(UTC)

    if existing is not None:
        before_profile = {"name": existing.name, "email": existing.email}
        if is_identity_placeholder(existing.email) and not is_identity_placeholder(actor.email):
            # An invited profile may already own the email. Preserve its identity.
            email_owner = (await session.execute(
                select(User).where(User.email == actor.email, User.id != existing.id)
            )).scalar_one_or_none()
            if email_owner is None:
                existing.email = actor.email
        if (
            is_identity_placeholder(existing.name) or existing.name == before_profile["email"]
        ) and not is_identity_placeholder(actor.name):
            existing.name = actor.name
        after_profile = {"name": existing.name, "email": existing.email}
        if before_profile != after_profile:
            await append_audit(
                session, actor_id=existing.id, action="user.profile_synced",
                entity="user", entity_id=str(existing.id), before=before_profile,
                after={**after_profile, "source": "cognito_token"},
            )
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
        # Opportunistic backfill: if the stored row was provisioned before
        # the Cognito-hydrate branch existed (email/name == sub), overwrite
        # with the real values now that we have them.
        if _looks_like_uuid(existing.email) and actor_email and not _looks_like_uuid(actor_email):
            existing.email = actor_email
        if _looks_like_uuid(existing.name) and actor_name and not _looks_like_uuid(actor_name):
            existing.name = actor_name
        existing.last_login = now
        await session.flush()
        return existing

    user = User(
        id=actor.id,
        email=actor_email,
        name=actor_name or actor_email,
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
