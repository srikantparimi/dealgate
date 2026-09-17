"""Users & roles admin — single source of truth for allowed groups, invariant
checks and the audit-emitting mutations behind `/admin/users`.

The router is deliberately thin: it does auth + shape-conversion. Every
validation and every write that changes group membership goes through this
module so the "at least one SystemAdmin" rule and the audit hook stay in one
place.

Rule 5 (CLAUDE.md): every group change writes an `audit_event` in the same
transaction as the SQL write — `append_audit` is called without committing;
callers commit once at the end.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.audit import AuditEvent
from app.models.user import User

# Blueprint §3 role list. Single source of truth: the router / UI both consume
# this. Anything not in the set is rejected with 422.
ALLOWED_GROUPS: tuple[str, ...] = (
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

_ALLOWED_SET: frozenset[str] = frozenset(ALLOWED_GROUPS)

SYSTEM_ADMIN = "SystemAdmin"


# --- helpers ---------------------------------------------------------------


def _validate_groups(groups: list[str]) -> list[str]:
    """Reject unknown groups; de-dup while preserving the caller's order.

    Raises 422 with a message that lists the offending value(s) so the UI can
    surface a concrete error next to the field.
    """

    unknown = [g for g in groups if g not in _ALLOWED_SET]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown group(s): {sorted(set(unknown))}",
        )
    seen: set[str] = set()
    deduped: list[str] = []
    for g in groups:
        if g in seen:
            continue
        seen.add(g)
        deduped.append(g)
    return deduped


async def _count_system_admins(session: AsyncSession, *, exclude_id: uuid.UUID | None) -> int:
    """Return the number of users whose groups contain `SystemAdmin`.

    JSON containment isn't portable across SQLite and Postgres, so we scan the
    (small) user table in Python. Sprint 1 volumes are tiny; when this table
    grows we can switch to `jsonb_array_elements_text` on Postgres.
    """

    stmt = select(User)
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    rows = (await session.execute(stmt)).scalars().all()
    return sum(1 for u in rows if SYSTEM_ADMIN in (u.groups or []))


# --- request payloads ------------------------------------------------------


@dataclass(frozen=True)
class InviteUserPayload:
    email: str
    name: str
    groups: list[str]


@dataclass(frozen=True)
class PatchGroupsPayload:
    add: list[str]
    remove: list[str]


# --- list / read -----------------------------------------------------------


@dataclass(frozen=True)
class UserListFilters:
    search: str | None = None
    group: str | None = None
    page: int = 1
    size: int = 25


async def list_users(
    session: AsyncSession, filters: UserListFilters
) -> tuple[list[User], int]:
    """Return `(rows, total)` for the users admin table.

    - `search` matches email OR name (case-insensitive substring).
    - `group` narrows to users containing the group in `groups`.
    - `group` values not in ALLOWED_GROUPS raise 422 (helps the UI notice a
      broken filter early rather than silently returning zero rows).
    """

    if filters.group is not None:
        _validate_groups([filters.group])

    base = select(User)
    if filters.search:
        needle = f"%{filters.search.strip().lower()}%"
        base = base.where(
            or_(
                func.lower(User.email).like(needle),
                func.lower(User.name).like(needle),
            )
        )

    # Materialise then filter by group in Python — see `_count_system_admins`
    # for the portability reasoning.
    rows = (await session.execute(base.order_by(User.email.asc()))).scalars().all()
    if filters.group is not None:
        rows = [u for u in rows if filters.group in (u.groups or [])]
    total = len(rows)
    offset = max(0, (filters.page - 1) * filters.size)
    return list(rows[offset : offset + filters.size]), total


async def get_role_history(
    session: AsyncSession, user_id: uuid.UUID, *, limit: int = 50
) -> list[AuditEvent]:
    """Return this user's `user.*` audit rows, newest first, capped at `limit`.

    Sprint 1 doesn't paginate role history — the audit trail per user is tiny
    and we'd rather ship one panel that shows everything than build a pager
    for zero users. The 50-row cap is defensive.
    """

    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.entity == "user",
            AuditEvent.entity_id == str(user_id),
            AuditEvent.action.like("user.%"),
        )
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


# --- mutations -------------------------------------------------------------


async def invite_user(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    payload: InviteUserPayload,
) -> User:
    """Create a user row + emit `user.invited`. 409 on duplicate email.

    The audit row's `after` payload includes `email`, `name` and the final
    (validated) `groups` so the trail is self-describing without needing to
    join back to the user table at read time.
    """

    email = payload.email.strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required"
        )
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="name is required"
        )

    groups = _validate_groups(list(payload.groups))

    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"user with email {email!r} already exists",
        )

    user = User(id=uuid.uuid4(), email=email, name=name, groups=groups)
    session.add(user)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="user.invited",
        entity="user",
        entity_id=str(user.id),
        before=None,
        after={"email": email, "name": name, "groups": groups},
    )
    await session.commit()
    await session.refresh(user)
    return user


async def patch_user_groups(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    user_id: uuid.UUID,
    payload: PatchGroupsPayload,
) -> User:
    """Apply add/remove to `user.groups` and emit `user.groups_changed`.

    Invariants:
    - `add` and `remove` group names must be in ALLOWED_GROUPS (422 otherwise).
    - The org must retain at least one SystemAdmin after the change (409).
    - If the effective group set is unchanged, no write and no audit row.
    """

    add = _validate_groups(list(payload.add))
    remove = _validate_groups(list(payload.remove))

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    before = list(user.groups or [])
    working = list(before)
    for g in add:
        if g not in working:
            working.append(g)
    for g in remove:
        if g in working:
            working.remove(g)

    added = [g for g in working if g not in before]
    removed = [g for g in before if g not in working]

    if not added and not removed:
        # No-op: return the user as-is without an audit row.
        return user

    # Enforce "at least one SystemAdmin" if this change removes the role from
    # this user. Count admins other than this user; if zero, refuse.
    if SYSTEM_ADMIN in before and SYSTEM_ADMIN not in working:
        other_admins = await _count_system_admins(session, exclude_id=user.id)
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="cannot remove the last SystemAdmin",
            )

    user.groups = working
    session.add(user)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="user.groups_changed",
        entity="user",
        entity_id=str(user.id),
        before={"groups": before},
        after={
            "groups": working,
            "added": added,
            "removed": removed,
        },
    )
    await session.commit()
    await session.refresh(user)
    return user


def serialize_user(user: User) -> dict[str, Any]:
    """Shape used by list + create responses. Excludes `updated_at`."""

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "groups": list(user.groups or []),
        "last_login": user.last_login,
        "created_at": user.created_at,
    }


def serialize_audit(row: AuditEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "ts": row.ts,
        "actor_id": row.actor_id,
        "action": row.action,
        "before": row.before,
        "after": row.after,
    }


__all__ = [
    "ALLOWED_GROUPS",
    "InviteUserPayload",
    "PatchGroupsPayload",
    "UserListFilters",
    "get_role_history",
    "invite_user",
    "list_users",
    "patch_user_groups",
    "serialize_audit",
    "serialize_user",
]


# Silence unused-import warnings for `datetime` when linted stand-alone; kept
# so future callers can annotate returned timestamps without extra imports.
_ = datetime
