"""Notifications API: in-app inbox + per-user delivery settings (S2-E3).

Read-only for the outbox itself — nobody dispatches from the API. The worker
(Agent N) drains rows via `pending_notifications`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.notification import Notification
from app.services.notifications import (
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_CHANNELS,
    STATUS_SUPPRESSED,
    get_settings_matrix,
    upsert_setting,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


# --- schemas -------------------------------------------------------------


class NotificationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    channel: str
    subject: str
    body_md: str
    related_entity: str | None
    related_entity_id: str | None
    status: str
    created_at: datetime
    read_at: datetime | None


class InboxResponse(BaseModel):
    items: list[NotificationRow]
    unread_count: int


class SettingRow(BaseModel):
    category: str
    channel: str
    enabled: bool


class SettingsResponse(BaseModel):
    items: list[SettingRow]
    categories: list[str]
    channels: list[str]


class SettingPatch(BaseModel):
    category: str
    channel: str
    enabled: bool


# --- endpoints -----------------------------------------------------------


@router.get("/inbox", response_model=InboxResponse)
async def get_inbox(
    limit: int = 50,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> InboxResponse:
    """Return this user's in-app notifications, newest first, and unread count."""

    stmt = (
        select(Notification)
        .where(Notification.user_id == user.id)
        .where(Notification.channel == "inapp")
        .where(Notification.status != STATUS_SUPPRESSED)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(max(1, min(200, limit)))
    )
    rows = list((await session.execute(stmt)).scalars().all())

    unread_stmt = (
        select(func.count(Notification.id))
        .where(Notification.user_id == user.id)
        .where(Notification.channel == "inapp")
        .where(Notification.status != STATUS_SUPPRESSED)
        .where(Notification.read_at.is_(None))
    )
    unread = int((await session.execute(unread_stmt)).scalar_one() or 0)
    return InboxResponse(
        items=[NotificationRow.model_validate(r) for r in rows],
        unread_count=unread,
    )


@router.post("/{notification_id}/read", response_model=NotificationRow)
async def mark_read(
    notification_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> NotificationRow:
    row = (
        await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not authorised")
    if row.channel != "inapp":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="only inapp notifications may be marked read",
        )
    if row.read_at is None:
        row.read_at = datetime.now(UTC)
        await session.flush()
        await append_audit(
            session,
            actor_id=user.id,
            action="notification.read",
            entity="notification",
            entity_id=str(row.id),
            before={"read_at": None},
            after={"read_at": row.read_at.isoformat()},
        )
        await session.commit()
        await session.refresh(row)
    return NotificationRow.model_validate(row)


@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SettingsResponse:
    matrix = await get_settings_matrix(session, user.id)
    return SettingsResponse(
        items=[SettingRow(**row) for row in matrix],
        categories=list(NOTIFICATION_CATEGORIES),
        channels=list(NOTIFICATION_CHANNELS),
    )


@router.patch("/settings", response_model=SettingRow)
async def patch_setting(
    body: SettingPatch,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> SettingRow:
    row = await upsert_setting(
        session,
        user_id=user.id,
        category=body.category,
        channel=body.channel,
        enabled=body.enabled,
    )
    return SettingRow(category=row.category, channel=row.channel, enabled=bool(row.enabled))
