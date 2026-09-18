"""Notification outbox service (S2-E3).

Writers of the outbox live here; the delivery worker (Agent N) is a pure
reader that calls :func:`pending_notifications` / :func:`mark_sent` /
:func:`mark_failed`. Every mutation writes an ``audit_event`` in the caller's
transaction so the chain covers the notification lifecycle end-to-end.

Design rules:

- One `queue_notification` call fans out to one row per enabled channel.
- Settings default to enabled: an absent `notification_setting` row means the
  user has never touched their preferences, so we opt them in.
- Suppressed rows still get written (status = ``suppressed``) so the audit trail
  can prove *why* a user did not receive a notification.
- Retry back-off is exponential in minutes: 1, 2, 4, 8, 16, capped at 60.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.notification import Notification, NotificationSetting

# Single source of truth. Router responses + settings matrix consume these.
NOTIFICATION_CATEGORIES: tuple[str, ...] = (
    "task_assigned",
    "approval_pending",
    "expiry_warning",
    "escalation",
    "daily_digest",
)

NOTIFICATION_CHANNELS: tuple[str, ...] = (
    "email",
    "teams",
    "slack",
    "inapp",
)

_CATEGORY_SET: frozenset[str] = frozenset(NOTIFICATION_CATEGORIES)
_CHANNEL_SET: frozenset[str] = frozenset(NOTIFICATION_CHANNELS)

# Statuses (kept as strings on the model for portability).
STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_SUPPRESSED = "suppressed"

# Back-off schedule in minutes. Index = attempt number after the failed try.
_BACKOFF_MINUTES: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 60)
MAX_ATTEMPTS = 5


def _validate_category(category: str) -> None:
    if category not in _CATEGORY_SET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown category: {category!r}",
        )


def _validate_channel(channel: str) -> None:
    if channel not in _CHANNEL_SET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown channel: {channel!r}",
        )


async def _channel_enabled(
    session: AsyncSession, user_id: uuid.UUID, category: str, channel: str
) -> bool:
    """Default true when no row exists; else the row's ``enabled`` flag."""

    stmt = select(NotificationSetting).where(
        NotificationSetting.user_id == user_id,
        NotificationSetting.category == category,
        NotificationSetting.channel == channel,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return True
    return bool(row.enabled)


async def get_settings_matrix(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Return one row per (category, channel) with the effective ``enabled`` value.

    Missing rows default to True. The response is ordered by category then
    channel so the UI matrix is deterministic across renders.
    """

    stmt = select(NotificationSetting).where(NotificationSetting.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()
    by_key = {(r.category, r.channel): r.enabled for r in rows}
    matrix: list[dict[str, Any]] = []
    for category in NOTIFICATION_CATEGORIES:
        for channel in NOTIFICATION_CHANNELS:
            matrix.append(
                {
                    "category": category,
                    "channel": channel,
                    "enabled": by_key.get((category, channel), True),
                }
            )
    return matrix


async def upsert_setting(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: str,
    channel: str,
    enabled: bool,
) -> NotificationSetting:
    """Insert or update the row; audit if the effective value changes."""

    _validate_category(category)
    _validate_channel(channel)

    stmt = select(NotificationSetting).where(
        NotificationSetting.user_id == user_id,
        NotificationSetting.category == category,
        NotificationSetting.channel == channel,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()

    before_val = True if row is None else bool(row.enabled)
    if row is None:
        row = NotificationSetting(
            user_id=user_id,
            category=category,
            channel=channel,
            enabled=enabled,
        )
        session.add(row)
        await session.flush()
    else:
        row.enabled = enabled
        await session.flush()

    if before_val != enabled:
        await append_audit(
            session,
            actor_id=user_id,
            action="notification_setting.changed",
            entity="notification_setting",
            entity_id=str(row.id),
            before={"enabled": before_val},
            after={
                "user_id": str(user_id),
                "category": category,
                "channel": channel,
                "enabled": enabled,
            },
        )
    await session.commit()
    await session.refresh(row)
    return row


async def queue_notification(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: str,
    subject: str,
    body_md: str,
    related_entity: str | None = None,
    related_entity_id: str | None = None,
    channels: tuple[str, ...] | None = None,
) -> list[Notification]:
    """Fan out one logical notification into one row per enabled channel.

    ``channels`` defaults to every channel in :data:`NOTIFICATION_CHANNELS`.
    Rows whose channel is disabled land as ``suppressed`` so the audit + admin
    tools can see the intent even when nothing was sent.

    Caller owns the transaction — this function flushes but does not commit.
    That keeps the notification row atomic with whatever state transition
    produced it (CLAUDE.md rule 5).
    """

    _validate_category(category)
    target_channels = channels if channels is not None else NOTIFICATION_CHANNELS
    for ch in target_channels:
        _validate_channel(ch)

    now = datetime.now(UTC)
    created: list[Notification] = []
    for channel in target_channels:
        enabled = await _channel_enabled(session, user_id, category, channel)
        row = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            category=category,
            channel=channel,
            subject=subject,
            body_md=body_md,
            related_entity=related_entity,
            related_entity_id=related_entity_id,
            status=STATUS_PENDING if enabled else STATUS_SUPPRESSED,
            attempts=0,
            next_attempt_at=now if enabled else None,
            last_error=None if enabled else "channel disabled by user setting",
        )
        session.add(row)
        await session.flush()
        await append_audit(
            session,
            actor_id=user_id,
            action="notification.queued",
            entity="notification",
            entity_id=str(row.id),
            before=None,
            after={
                "user_id": str(user_id),
                "category": category,
                "channel": channel,
                "status": row.status,
                "related_entity": related_entity,
                "related_entity_id": related_entity_id,
            },
        )
        created.append(row)
    return created


async def pending_notifications(
    session: AsyncSession, *, limit: int = 50
) -> list[Notification]:
    """Fetch rows the worker should attempt now, oldest ``next_attempt_at`` first.

    Rows where ``next_attempt_at`` is in the future are skipped so the back-off
    is honoured. `attempts >= MAX_ATTEMPTS` rows are not returned even if their
    status was left `pending` due to bugs — the worker cannot loop on them.
    """

    now = datetime.now(UTC)
    stmt = (
        select(Notification)
        .where(Notification.status == STATUS_PENDING)
        .where(Notification.attempts < MAX_ATTEMPTS)
        .order_by(Notification.next_attempt_at.asc().nulls_first(), Notification.created_at.asc())
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    ready: list[Notification] = []
    for r in rows:
        if r.next_attempt_at is None:
            ready.append(r)
            continue
        # SQLite strips tzinfo on reload; treat naive values as UTC so the
        # comparison stays timezone-consistent across dialects.
        na = r.next_attempt_at
        if na.tzinfo is None:
            na = na.replace(tzinfo=UTC)
        if na <= now:
            ready.append(r)
    return ready


def _backoff_for(attempts: int) -> timedelta:
    idx = min(attempts, len(_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=_BACKOFF_MINUTES[idx])


async def mark_sent(
    session: AsyncSession, notification_id: uuid.UUID
) -> Notification:
    """Flip a pending row to ``sent`` and stamp ``sent_at``. Audits the send."""

    row = await _load(session, notification_id)
    before = {"status": row.status, "attempts": row.attempts}
    row.status = STATUS_SENT
    row.attempts = row.attempts + 1
    row.sent_at = datetime.now(UTC)
    row.next_attempt_at = None
    row.last_error = None
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="notification.sent",
        entity="notification",
        entity_id=str(row.id),
        before=before,
        after={"status": row.status, "attempts": row.attempts},
    )
    await session.commit()
    await session.refresh(row)
    row.next_attempt_at = _ensure_utc(row.next_attempt_at)
    row.sent_at = _ensure_utc(row.sent_at)
    return row


async def mark_failed(
    session: AsyncSession, notification_id: uuid.UUID, *, error: str
) -> Notification:
    """Record a failed attempt; schedule the next try with exponential back-off.

    After ``MAX_ATTEMPTS`` the row is left in status ``failed`` and the worker
    stops picking it up. Callers may reset ``attempts`` manually to retry.
    """

    row = await _load(session, notification_id)
    before = {"status": row.status, "attempts": row.attempts}
    row.attempts = row.attempts + 1
    row.last_error = (error or "").strip()[:1000] or "unknown error"
    if row.attempts >= MAX_ATTEMPTS:
        row.status = STATUS_FAILED
        row.next_attempt_at = None
    else:
        row.status = STATUS_PENDING
        row.next_attempt_at = datetime.now(UTC) + _backoff_for(row.attempts)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="notification.failed",
        entity="notification",
        entity_id=str(row.id),
        before=before,
        after={
            "status": row.status,
            "attempts": row.attempts,
            "next_attempt_at": (
                row.next_attempt_at.isoformat() if row.next_attempt_at else None
            ),
            "last_error": row.last_error,
        },
    )
    await session.commit()
    await session.refresh(row)
    row.next_attempt_at = _ensure_utc(row.next_attempt_at)
    row.sent_at = _ensure_utc(row.sent_at)
    return row


async def _load(session: AsyncSession, notification_id: uuid.UUID) -> Notification:
    row = (
        await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return row


def _ensure_utc(ts: datetime | None) -> datetime | None:
    """Attach UTC tzinfo when the driver (SQLite) stripped it on reload."""

    if ts is None:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


__all__ = [
    "MAX_ATTEMPTS",
    "NOTIFICATION_CATEGORIES",
    "NOTIFICATION_CHANNELS",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SENT",
    "STATUS_SUPPRESSED",
    "get_settings_matrix",
    "mark_failed",
    "mark_sent",
    "pending_notifications",
    "queue_notification",
    "upsert_setting",
]
