"""S23-PL2 B11 — the Pipeline's personal workspace: saved views, groups, watches.

Every row is keyed on the caller's DealGate user id (``canonical_user``), never
the login id, which differs for users that HubSpot intake or an admin invite
created. Groups and watches key on the stable deal id (``opportunity.id``).
Which deals a caller may group or watch is the Pipeline's own read boundary
(``scope_pipeline_filters`` + ``matching_opportunity_ids``).

Saved views of the new page are ``saved_view`` rows with ``key='pipeline'``
whose ``filter_json`` stores ``{tab, layout, filters}`` as sent. Groups are the
caller's manual opportunity groups. Names are unique per user in any letter
case; the services in ``saved_view`` / ``tracking_group`` enforce it.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.saved_view import SavedView
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.watchlist import WatchedItem
from app.services.canonical_user import resolve_viewer
from app.services.hubspot_pipeline import (
    PipelineFilters,
    matching_opportunity_ids,
    scope_pipeline_filters,
)
from app.services.saved_view import SavedViewCreate, archive_view, create_view
from app.services.tracking_access import require_deal_access
from app.services.tracking_group import (
    GroupCreate,
    add_members,
    create_group,
    remove_members,
)

PIPELINE_VIEW_KEY = "pipeline"
NAME_MAX = 60
EMPTY_VIEW_NAME = "Enter a name for this view."
EMPTY_GROUP_NAME = "Enter a group name."


async def reading_actor(session: AsyncSession, actor: AuthUser) -> AuthUser:
    """The caller keyed on their DealGate user id, for a read: one statement, no write.

    Before the first sign-in wrote a row there is no DealGate id; the login id
    is kept then, and it owns nothing, so personal lists read as empty.
    """

    viewer = await resolve_viewer(session, actor)
    return AuthUser(viewer.user_id or actor.id, actor.email, actor.name, tuple(actor.groups or ()))


def _clean_name(name: str, *, empty: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=empty)
    if len(cleaned) > NAME_MAX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Use at most {NAME_MAX} characters.",
        )
    return cleaned


def _unique(ids: list[uuid.UUID]) -> list[uuid.UUID]:
    return list(dict.fromkeys(ids))


async def visible_deals_among(session: AsyncSession, viewer: AuthUser, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """The subset of ``ids`` the viewer can see on the Pipeline (any status)."""

    if not ids:
        return set()
    filters = await scope_pipeline_filters(session, viewer, PipelineFilters(include_closed=True))
    return await matching_opportunity_ids(session, replace(filters, opportunity_id=tuple(ids)))


async def _require_visible(session: AsyncSession, actor: AuthUser, ids: list[uuid.UUID]) -> None:
    if ids and set(ids) - await visible_deals_among(session, actor, set(ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deal not found")


# --- saved views ---------------------------------------------------------------


def _view_out(view: SavedView) -> dict[str, Any]:
    stored = view.filter_json if isinstance(view.filter_json, dict) else {}
    filters = stored.get("filters")
    return {
        "id": view.id,
        "name": view.name,
        "tab": stored.get("tab") or "deals",
        "layout": stored.get("layout") or "list",
        "filters": filters if isinstance(filters, dict) else {},
    }


async def list_pipeline_views(session: AsyncSession, *, owner_id: uuid.UUID) -> list[dict[str, Any]]:
    """The owner's live Pipeline views, in the order they were saved."""

    views = (
        await session.scalars(
            select(SavedView)
            .where(
                SavedView.owner_id == owner_id,
                SavedView.key == PIPELINE_VIEW_KEY,
                SavedView.is_builtin.is_(False),
                SavedView.archived_at.is_(None),
            )
            .order_by(SavedView.created_at, SavedView.id)
        )
    ).all()
    return [_view_out(view) for view in views]


async def create_pipeline_view(
    session: AsyncSession, *, actor: AuthUser, name: str, tab: str, layout: str, filters: dict[str, Any]
) -> dict[str, Any]:
    view = await create_view(
        session,
        actor=actor,
        payload=SavedViewCreate(
            name=_clean_name(name, empty=EMPTY_VIEW_NAME),
            filter_json={"tab": tab, "layout": layout, "filters": filters},
            key=PIPELINE_VIEW_KEY,
        ),
    )
    return _view_out(view)


async def delete_pipeline_view(session: AsyncSession, *, actor: AuthUser, view_id: uuid.UUID) -> None:
    """Archive one of the caller's own Pipeline views (the name is free again)."""

    view = await session.get(SavedView, view_id)
    if (
        view is None
        or view.owner_id != actor.id
        or view.key != PIPELINE_VIEW_KEY
        or view.is_builtin
        or view.archived_at is not None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="view not found")
    await archive_view(session, actor=actor, view=view)


# --- tracking groups -------------------------------------------------------------


async def _live_manual_groups(session: AsyncSession, owner_id: uuid.UUID) -> list[TrackingGroup]:
    groups = (
        await session.scalars(
            select(TrackingGroup)
            .where(
                TrackingGroup.owner_id == owner_id,
                TrackingGroup.archived_at.is_(None),
                TrackingGroup.member_kind == "opportunity",
            )
            .order_by(TrackingGroup.created_at, TrackingGroup.id)
        )
    ).all()
    # A JSON null and SQL NULL both read back as None: manual groups only.
    return [group for group in groups if group.filter_json is None]


async def _own_group(session: AsyncSession, actor: AuthUser, group_id: uuid.UUID) -> TrackingGroup:
    group = await session.get(TrackingGroup, group_id)
    if (
        group is None
        or group.owner_id != actor.id
        or group.archived_at is not None
        or group.member_kind != "opportunity"
        or group.filter_json is not None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    return group


async def list_pipeline_groups(session: AsyncSession, *, viewer: AuthUser) -> list[dict[str, Any]]:
    """The viewer's groups with the member deals they can still see."""

    groups = await _live_manual_groups(session, viewer.id)
    if not groups:
        return []
    members = (
        await session.execute(
            select(TrackingGroupMember.group_id, TrackingGroupMember.member_id)
            .where(TrackingGroupMember.group_id.in_([group.id for group in groups]))
            .order_by(TrackingGroupMember.added_at, TrackingGroupMember.member_id)
        )
    ).all()
    visible = await visible_deals_among(session, viewer, {member for _, member in members})
    deal_ids: dict[uuid.UUID, list[uuid.UUID]] = {group.id: [] for group in groups}
    for group_id, member in members:
        if member in visible:
            deal_ids[group_id].append(member)
    return [{"id": group.id, "name": group.name, "deal_ids": deal_ids[group.id]} for group in groups]


async def create_pipeline_group(
    session: AsyncSession, *, actor: AuthUser, name: str, deal_ids: list[uuid.UUID]
) -> dict[str, Any]:
    group = await create_group(
        session,
        actor=actor,
        payload=GroupCreate(name=_clean_name(name, empty=EMPTY_GROUP_NAME), member_kind="opportunity"),
    )
    ids = _unique(deal_ids)
    await _require_visible(session, actor, ids)
    if ids:
        await add_members(session, actor=actor, group=group, member_ids=tuple(ids))
    return {"id": group.id, "name": group.name, "deal_ids": ids}


async def add_pipeline_group_deals(
    session: AsyncSession, *, actor: AuthUser, group_id: uuid.UUID, deal_ids: list[uuid.UUID]
) -> None:
    group = await _own_group(session, actor, group_id)
    ids = _unique(deal_ids)
    await _require_visible(session, actor, ids)
    if ids:
        await add_members(session, actor=actor, group=group, member_ids=tuple(ids))


async def remove_pipeline_group_deals(
    session: AsyncSession, *, actor: AuthUser, group_id: uuid.UUID, deal_ids: list[uuid.UUID]
) -> None:
    group = await _own_group(session, actor, group_id)
    ids = _unique(deal_ids)
    if ids:
        await remove_members(session, actor=actor, group=group, member_ids=tuple(ids))


# --- watching ----------------------------------------------------------------------


async def _watch_row(session: AsyncSession, user_id: uuid.UUID, deal_id: uuid.UUID) -> WatchedItem | None:
    return await session.scalar(
        select(WatchedItem).where(
            WatchedItem.user_id == user_id,
            WatchedItem.kind == "opportunity",
            WatchedItem.item_id == deal_id,
        )
    )


async def set_watching(session: AsyncSession, *, actor: AuthUser, deal_id: uuid.UUID, watching: bool) -> None:
    """Watch or stop watching a deal the caller can see. Idempotent; audited when it changes."""

    await require_deal_access(session, actor, deal_id)
    existing = await _watch_row(session, actor.id, deal_id)
    if watching and existing is None:
        try:
            async with session.begin_nested():
                row = WatchedItem(user_id=actor.id, kind="opportunity", item_id=deal_id)
                session.add(row)
        except IntegrityError:
            # A concurrent request watched it first: the end state is the same.
            if await _watch_row(session, actor.id, deal_id) is None:
                raise
            return
        await append_audit(
            session,
            actor_id=actor.id,
            action="watch.added",
            entity="watched_item",
            entity_id=str(row.id),
            before=None,
            after={"kind": "opportunity", "item_id": str(deal_id), "user_id": str(actor.id)},
        )
    elif not watching and existing is not None:
        before = {"kind": "opportunity", "item_id": str(deal_id), "user_id": str(actor.id)}
        await session.delete(existing)
        await session.flush()
        await append_audit(
            session,
            actor_id=actor.id,
            action="watch.removed",
            entity="watched_item",
            entity_id=str(existing.id),
            before=before,
            after=None,
        )
