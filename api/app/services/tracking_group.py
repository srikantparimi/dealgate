"""Tracking-group service (S20 · W6).

Manual and dynamic groups over the same base ``/pipeline`` query. The
member set is emitted as a set of uuids that W2's pipeline query
predicates against — this service never runs the filter itself
(directive constraint: W6 does not edit ``/pipeline`` routers/services).

Permissions (T27):

- ``private`` — only ``owner_id`` can list/read/mutate.
- ``team``    — every authenticated user can list/read; only
  ``owner_id`` (and leaders) can mutate. The group's members are the
  intersection of the caller's permission-aware base query with the
  group's own predicate, so a private client the caller cannot see
  never leaks into a shared count.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.tracking_group import (
    VALID_GROUP_MEMBER_KINDS,
    VALID_GROUP_VISIBILITIES,
    TrackingGroup,
    TrackingGroupMember,
)
from app.models.user import User


LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "HR", "SystemAdmin"}
)


@dataclass(frozen=True)
class GroupCreate:
    name: str
    member_kind: str
    visibility: str = "private"
    filter_json: dict[str, Any] | None = None
    include_future_deals: bool = True


@dataclass(frozen=True)
class GroupPatch:
    name: str | None = None
    visibility: str | None = None
    filter_json: dict[str, Any] | None = None
    include_future_deals: bool | None = None
    clear_filter: bool = False


def _is_leader(user: AuthUser) -> bool:
    return any(r in LEADER_ROLES for r in user.groups)


def _row_to_dict(g: TrackingGroup) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "owner_id": str(g.owner_id),
        "name": g.name,
        "visibility": g.visibility,
        "member_kind": g.member_kind,
        "filter_json": g.filter_json,
        "include_future_deals": bool(g.include_future_deals),
        "is_dynamic": g.filter_json is not None,
    }


def _visibility_predicate(user: AuthUser):
    """Rows the caller may see. Applied to every list query."""

    # Leaders see everything; other users see their own + all team groups.
    if _is_leader(user):
        return TrackingGroup.archived_at.is_(None)
    return (
        (TrackingGroup.archived_at.is_(None))
        & (
            (TrackingGroup.owner_id == user.id)
            | (TrackingGroup.visibility == "team")
        )
    )


async def load_group(
    session: AsyncSession, *, actor: AuthUser, group_id: uuid.UUID
) -> TrackingGroup:
    g = await session.get(TrackingGroup, group_id)
    if g is None or g.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="group not found"
        )
    # Enforce visibility on read.
    if g.visibility == "private" and g.owner_id != actor.id and not _is_leader(actor):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="group not found"
        )
    return g


async def list_groups(
    session: AsyncSession,
    *,
    actor: AuthUser,
    member_kind: str | None = None,
) -> tuple[TrackingGroup, ...]:
    stmt = select(TrackingGroup).where(_visibility_predicate(actor))
    if member_kind is not None:
        if member_kind not in VALID_GROUP_MEMBER_KINDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="invalid member_kind",
            )
        stmt = stmt.where(TrackingGroup.member_kind == member_kind)
    stmt = stmt.order_by(TrackingGroup.name.asc())
    result = await session.execute(stmt)
    return tuple(result.scalars())


def _validate_shape(*, member_kind: str, visibility: str) -> None:
    if member_kind not in VALID_GROUP_MEMBER_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"member_kind must be one of {sorted(VALID_GROUP_MEMBER_KINDS)}",
        )
    if visibility not in VALID_GROUP_VISIBILITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"visibility must be one of {sorted(VALID_GROUP_VISIBILITIES)}",
        )


async def create_group(
    session: AsyncSession,
    *,
    actor: AuthUser,
    payload: GroupCreate,
) -> TrackingGroup:
    _validate_shape(member_kind=payload.member_kind, visibility=payload.visibility)
    if not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )
    g = TrackingGroup(
        id=uuid.uuid4(),
        owner_id=actor.id,
        name=payload.name.strip()[:255],
        visibility=payload.visibility,
        member_kind=payload.member_kind,
        filter_json=payload.filter_json,
        include_future_deals=payload.include_future_deals,
    )
    session.add(g)
    await session.flush()
    after = _row_to_dict(g)
    await append_audit(
        session,
        actor_id=actor.id,
        action="tracking_group.created",
        entity="tracking_group",
        entity_id=str(g.id),
        before=None,
        after=after,
    )
    return g


async def _authorize_mutation(g: TrackingGroup, actor: AuthUser) -> None:
    if _is_leader(actor):
        return
    if g.owner_id == actor.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="not authorised to modify this group",
    )


async def patch_group(
    session: AsyncSession,
    *,
    actor: AuthUser,
    group: TrackingGroup,
    patch: GroupPatch,
) -> TrackingGroup:
    await _authorize_mutation(group, actor)
    before = _row_to_dict(group)
    changed = False

    if patch.name is not None:
        stripped = patch.name.strip()[:255]
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name cannot be blank",
            )
        if stripped != group.name:
            group.name = stripped
            changed = True

    if patch.visibility is not None:
        if patch.visibility not in VALID_GROUP_VISIBILITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"visibility must be one of {sorted(VALID_GROUP_VISIBILITIES)}",
            )
        if group.visibility != patch.visibility:
            group.visibility = patch.visibility
            changed = True

    if patch.clear_filter:
        if group.filter_json is not None:
            group.filter_json = None
            changed = True
    elif patch.filter_json is not None:
        # An explicit assignment (dict is present, even if empty)
        # makes the group dynamic.
        if group.filter_json != patch.filter_json:
            group.filter_json = patch.filter_json
            changed = True

    if patch.include_future_deals is not None:
        if bool(patch.include_future_deals) != bool(group.include_future_deals):
            group.include_future_deals = bool(patch.include_future_deals)
            changed = True

    if not changed:
        return group

    after = _row_to_dict(group)
    await append_audit(
        session,
        actor_id=actor.id,
        action="tracking_group.edited",
        entity="tracking_group",
        entity_id=str(group.id),
        before=before,
        after=after,
    )
    return group


async def archive_group(
    session: AsyncSession, *, actor: AuthUser, group: TrackingGroup
) -> TrackingGroup:
    await _authorize_mutation(group, actor)
    if group.archived_at is not None:
        return group
    from datetime import UTC, datetime

    before = _row_to_dict(group)
    group.archived_at = datetime.now(UTC)
    after = _row_to_dict(group)
    await append_audit(
        session,
        actor_id=actor.id,
        action="tracking_group.archived",
        entity="tracking_group",
        entity_id=str(group.id),
        before=before,
        after=after,
    )
    return group


# --- Manual membership ----------------------------------------------------


async def list_members(
    session: AsyncSession, *, actor: AuthUser, group: TrackingGroup
) -> tuple[uuid.UUID, ...]:
    """Return the manual member uuids of a group.

    Read is permission-checked against the group's visibility; the
    caller has already loaded the group so we do not re-check here.
    """

    if group.filter_json is not None:
        # Dynamic groups do not use this table.
        return ()
    stmt = (
        select(TrackingGroupMember.member_id)
        .where(TrackingGroupMember.group_id == group.id)
        .order_by(TrackingGroupMember.added_at.desc())
    )
    result = await session.execute(stmt)
    return tuple(result.scalars())


async def add_members(
    session: AsyncSession,
    *,
    actor: AuthUser,
    group: TrackingGroup,
    member_ids: tuple[uuid.UUID, ...],
) -> tuple[uuid.UUID, ...]:
    await _authorize_mutation(group, actor)
    if group.filter_json is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="dynamic groups cannot have manual members",
        )
    existing = set(await list_members(session, actor=actor, group=group))
    added: list[uuid.UUID] = []
    for mid in member_ids:
        if mid in existing:
            continue
        m = TrackingGroupMember(
            group_id=group.id,
            member_id=mid,
            added_by=actor.id,
        )
        session.add(m)
        added.append(mid)
    await session.flush()
    if added:
        await append_audit(
            session,
            actor_id=actor.id,
            action="tracking_group.members_added",
            entity="tracking_group",
            entity_id=str(group.id),
            before=None,
            after={"added": [str(m) for m in added]},
        )
    return tuple(added)


async def remove_members(
    session: AsyncSession,
    *,
    actor: AuthUser,
    group: TrackingGroup,
    member_ids: tuple[uuid.UUID, ...],
) -> tuple[uuid.UUID, ...]:
    await _authorize_mutation(group, actor)
    if group.filter_json is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="dynamic groups cannot have manual members",
        )
    if not member_ids:
        return ()

    stmt = select(TrackingGroupMember).where(
        (TrackingGroupMember.group_id == group.id)
        & (TrackingGroupMember.member_id.in_(member_ids))
    )
    result = await session.execute(stmt)
    removed: list[uuid.UUID] = []
    for row in result.scalars():
        removed.append(row.member_id)
        await session.delete(row)
    if removed:
        await append_audit(
            session,
            actor_id=actor.id,
            action="tracking_group.members_removed",
            entity="tracking_group",
            entity_id=str(group.id),
            before={"removed": [str(m) for m in removed]},
            after=None,
        )
    return tuple(removed)


__all__ = [
    "GroupCreate",
    "GroupPatch",
    "add_members",
    "archive_group",
    "create_group",
    "list_groups",
    "list_members",
    "load_group",
    "patch_group",
    "remove_members",
]
