"""Saved-view service (S20 · W6).

Seeds seven built-in views the first time a user opens the app (or
calls ``list_views`` for the first time). Users can add more via
``POST /saved-views``.

The built-in filter shapes echo ``docs/reports/s20/contracts.md`` §4
so W2's pipeline query interprets them without translation.
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
from app.models.saved_view import (
    BUILTIN_VIEW_KEYS,
    VALID_VIEW_VISIBILITIES,
    SavedView,
)


LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "HR", "SystemAdmin"}
)


# --- Built-in shapes ------------------------------------------------------


def _builtin_definitions(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return the seven built-in views for a specific user.

    Each entry is a ``dict`` matching :class:`SavedView` column
    signatures, minus ``owner_id`` / ``id`` / timestamps.
    """

    uid = str(user_id)
    return [
        {
            "key": "my_opportunities",
            "name": "My opportunities",
            "filter_json": {"deal_owner": [uid], "open_closed": "open"},
            "sort_json": {"column": "close_date", "descending": False},
            "display_order": 10,
        },
        {
            "key": "my_actions",
            "name": "My actions",
            "filter_json": {
                "deal_owner": [uid],
                "attention": ["has_open_action"],
                "open_closed": "open",
            },
            "sort_json": {"column": "next_action_due", "descending": False},
            "display_order": 20,
        },
        {
            "key": "waiting_on_others",
            "name": "Waiting on others",
            "filter_json": {
                "deal_owner": [uid],
                "attention": ["action_blocked"],
                "open_closed": "open",
            },
            "sort_json": {"column": "next_action_due", "descending": False},
            "display_order": 30,
        },
        {
            "key": "closing_soon",
            "name": "Closing soon",
            "filter_json": {
                "date_field": "close",
                "date_preset": "next30",
                "open_closed": "open",
            },
            "sort_json": {"column": "close_date", "descending": False},
            "display_order": 40,
        },
        {
            "key": "no_next_action",
            "name": "No next action",
            "filter_json": {
                "attention": ["no_next_action"],
                "open_closed": "open",
            },
            "sort_json": {"column": "close_date", "descending": False},
            "display_order": 50,
        },
        {
            "key": "stale_contact",
            "name": "Stale contact",
            "filter_json": {
                "attention": ["stale_contact"],
                "open_closed": "open",
            },
            "sort_json": {"column": "last_activity", "descending": False},
            "display_order": 60,
        },
        {
            "key": "my_approvals",
            "name": "My approvals",
            "filter_json": {
                "attention": ["awaiting_my_approval"],
                "open_closed": "open",
            },
            "sort_json": {"column": "attention", "descending": True},
            "display_order": 70,
        },
    ]


@dataclass(frozen=True)
class SavedViewCreate:
    name: str
    filter_json: dict[str, Any]
    sort_json: dict[str, Any] | None = None
    visibility: str = "private"


@dataclass(frozen=True)
class SavedViewPatch:
    name: str | None = None
    filter_json: dict[str, Any] | None = None
    sort_json: dict[str, Any] | None = None
    visibility: str | None = None
    display_order: int | None = None
    clear_sort: bool = False


def _is_leader(user: AuthUser) -> bool:
    return any(r in LEADER_ROLES for r in user.groups)


def _row_to_dict(v: SavedView) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "owner_id": str(v.owner_id),
        "key": v.key,
        "name": v.name,
        "filter_json": v.filter_json,
        "sort_json": v.sort_json,
        "visibility": v.visibility,
        "is_builtin": bool(v.is_builtin),
        "display_order": v.display_order,
    }


# --- Seeding --------------------------------------------------------------


async def ensure_builtins(
    session: AsyncSession, *, user_id: uuid.UUID
) -> tuple[SavedView, ...]:
    """Idempotently seed the seven built-ins for a user.

    Uses the ``uq_saved_view_owner_key_builtin`` unique constraint —
    a re-run inserts nothing.
    """

    stmt = select(SavedView).where(
        (SavedView.owner_id == user_id) & (SavedView.is_builtin.is_(True))
    )
    result = await session.execute(stmt)
    existing = {v.key: v for v in result.scalars()}

    inserted: list[SavedView] = []
    for definition in _builtin_definitions(user_id):
        if definition["key"] in existing:
            continue
        v = SavedView(
            id=uuid.uuid4(),
            owner_id=user_id,
            key=definition["key"],
            name=definition["name"],
            filter_json=definition["filter_json"],
            sort_json=definition["sort_json"],
            display_order=definition["display_order"],
            visibility="private",
            is_builtin=True,
        )
        session.add(v)
        inserted.append(v)
    if inserted:
        await session.flush()
        # One audit entry for the batch keeps the chain compact.
        await append_audit(
            session,
            actor_id=user_id,
            action="saved_view.builtins_seeded",
            entity="user",
            entity_id=str(user_id),
            before=None,
            after={"seeded_keys": [v.key for v in inserted]},
        )
    return tuple(inserted)


# --- Public API -----------------------------------------------------------


async def list_views(
    session: AsyncSession, *, actor: AuthUser
) -> tuple[SavedView, ...]:
    """Return every saved view the caller can see.

    Seeds the built-ins on first call. Both the caller's own private
    views and every ``team`` view are returned.
    """

    await ensure_builtins(session, user_id=actor.id)

    stmt = (
        select(SavedView)
        .where(SavedView.archived_at.is_(None))
        .where(
            (SavedView.owner_id == actor.id)
            | (SavedView.visibility == "team")
        )
        .order_by(SavedView.display_order.asc(), SavedView.name.asc())
    )
    result = await session.execute(stmt)
    return tuple(result.scalars())


async def load_view(
    session: AsyncSession, *, actor: AuthUser, view_id: uuid.UUID
) -> SavedView:
    v = await session.get(SavedView, view_id)
    if v is None or v.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="view not found"
        )
    if v.visibility == "private" and v.owner_id != actor.id and not _is_leader(actor):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="view not found"
        )
    return v


async def create_view(
    session: AsyncSession,
    *,
    actor: AuthUser,
    payload: SavedViewCreate,
) -> SavedView:
    if not payload.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="name is required",
        )
    if payload.visibility not in VALID_VIEW_VISIBILITIES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"visibility must be one of {sorted(VALID_VIEW_VISIBILITIES)}",
        )

    v = SavedView(
        id=uuid.uuid4(),
        owner_id=actor.id,
        key="custom",
        name=payload.name.strip()[:255],
        filter_json=payload.filter_json,
        sort_json=payload.sort_json,
        visibility=payload.visibility,
        is_builtin=False,
        display_order=1000,
    )
    session.add(v)
    await session.flush()
    after = _row_to_dict(v)
    await append_audit(
        session,
        actor_id=actor.id,
        action="saved_view.created",
        entity="saved_view",
        entity_id=str(v.id),
        before=None,
        after=after,
    )
    return v


async def _authorize_mutation(v: SavedView, actor: AuthUser) -> None:
    if _is_leader(actor):
        return
    if v.owner_id == actor.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="not authorised to modify this view",
    )


async def patch_view(
    session: AsyncSession,
    *,
    actor: AuthUser,
    view: SavedView,
    patch: SavedViewPatch,
) -> SavedView:
    await _authorize_mutation(view, actor)
    before = _row_to_dict(view)
    changed = False

    if patch.name is not None:
        stripped = patch.name.strip()[:255]
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="name cannot be blank",
            )
        if stripped != view.name:
            view.name = stripped
            changed = True

    if patch.filter_json is not None:
        if view.filter_json != patch.filter_json:
            view.filter_json = patch.filter_json
            changed = True

    if patch.clear_sort:
        if view.sort_json is not None:
            view.sort_json = None
            changed = True
    elif patch.sort_json is not None:
        if view.sort_json != patch.sort_json:
            view.sort_json = patch.sort_json
            changed = True

    if patch.visibility is not None:
        if patch.visibility not in VALID_VIEW_VISIBILITIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"visibility must be one of {sorted(VALID_VIEW_VISIBILITIES)}",
            )
        if view.visibility != patch.visibility:
            view.visibility = patch.visibility
            changed = True

    if patch.display_order is not None:
        if view.display_order != patch.display_order:
            view.display_order = int(patch.display_order)
            changed = True

    if not changed:
        return view

    after = _row_to_dict(view)
    await append_audit(
        session,
        actor_id=actor.id,
        action="saved_view.edited",
        entity="saved_view",
        entity_id=str(view.id),
        before=before,
        after=after,
    )
    return view


async def archive_view(
    session: AsyncSession, *, actor: AuthUser, view: SavedView
) -> SavedView:
    await _authorize_mutation(view, actor)
    if view.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="built-in views cannot be archived",
        )
    if view.archived_at is not None:
        return view
    from datetime import UTC, datetime

    before = _row_to_dict(view)
    view.archived_at = datetime.now(UTC)
    after = _row_to_dict(view)
    await append_audit(
        session,
        actor_id=actor.id,
        action="saved_view.archived",
        entity="saved_view",
        entity_id=str(view.id),
        before=before,
        after=after,
    )
    return view


__all__ = [
    "BUILTIN_VIEW_KEYS",
    "SavedViewCreate",
    "SavedViewPatch",
    "archive_view",
    "create_view",
    "ensure_builtins",
    "list_views",
    "load_view",
    "patch_view",
]
