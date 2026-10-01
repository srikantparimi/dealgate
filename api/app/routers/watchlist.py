"""S20 W6 · watchlist router — per-user stars on deals + clients."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.watchlist import WATCH_KINDS, WatchedItem


router = APIRouter(prefix="/watchlist", tags=["watchlist"])


class WatchedItemOut(BaseModel):
    id: uuid.UUID
    kind: str
    item_id: uuid.UUID


class WatchedListOut(BaseModel):
    items: list[WatchedItemOut]
    counts: dict[str, int]


class WatchToggleBody(BaseModel):
    kind: str
    item_id: uuid.UUID


def _check_kind(kind: str) -> None:
    if kind not in WATCH_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"kind must be one of {sorted(WATCH_KINDS)}",
        )


@router.get("", response_model=WatchedListOut)
async def list_watchlist(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchedListOut:
    rows = (
        await session.execute(
            select(WatchedItem).where(WatchedItem.user_id == user.id)
        )
    ).scalars().all()
    counts: dict[str, int] = {"opportunity": 0, "client": 0}
    for r in rows:
        counts[r.kind] = counts.get(r.kind, 0) + 1
    return WatchedListOut(
        items=[WatchedItemOut(id=r.id, kind=r.kind, item_id=r.item_id) for r in rows],
        counts=counts,
    )


@router.post("", response_model=WatchedItemOut, status_code=status.HTTP_201_CREATED)
async def add_watch(
    body: WatchToggleBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WatchedItemOut:
    _check_kind(body.kind)
    row = WatchedItem(user_id=user.id, kind=body.kind, item_id=body.item_id)
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Already watching — return the existing row for idempotency.
        existing = (
            await session.execute(
                select(WatchedItem).where(
                    WatchedItem.user_id == user.id,
                    WatchedItem.kind == body.kind,
                    WatchedItem.item_id == body.item_id,
                )
            )
        ).scalar_one()
        return WatchedItemOut(
            id=existing.id, kind=existing.kind, item_id=existing.item_id
        )
    return WatchedItemOut(id=row.id, kind=row.kind, item_id=row.item_id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def remove_watch(
    kind: str,
    item_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    _check_kind(kind)
    await session.execute(
        delete(WatchedItem).where(
            WatchedItem.user_id == user.id,
            WatchedItem.kind == kind,
            WatchedItem.item_id == item_id,
        )
    )
    await session.commit()
    return None


async def watched_item_ids(
    session: AsyncSession, *, user_id: uuid.UUID, kind: str
) -> set[uuid.UUID]:
    """Helper for `list_opportunities` / `list_clients` — attach an
    is_watched flag per row without a per-row query."""
    if kind not in WATCH_KINDS:
        return set()
    rows = (
        await session.execute(
            select(WatchedItem.item_id).where(
                WatchedItem.user_id == user_id,
                WatchedItem.kind == kind,
            )
        )
    ).all()
    return {r[0] for r in rows}
