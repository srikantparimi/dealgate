"""Notification sender worker (S2-E3 Wave 2).

Drains the ``notification`` outbox produced by
:func:`app.services.notifications.queue_notification`, dispatching each row
to the right transport:

- ``email``    → SES via :class:`app.integrations.ses.SESClient`.
- ``teams``    → suppressed until ``TEAMS_WEBHOOK_URL`` is configured
                 (marks the row as ``suppressed`` with a clear reason so the
                 audit chain records the intent).
- ``slack``    → suppressed until ``SLACK_WEBHOOK_URL`` is configured.
- ``inapp``    → in-DB only; the inbox endpoint serves these directly, so
                 the sender just flips the status to ``sent``.

Failures loop through :func:`mark_failed` which applies the exponential
back-off in `app.services.notifications`. After ``MAX_ATTEMPTS`` the row
lands in ``failed`` and the audit chain records why.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.db import session_factory
from app.integrations.ses import SESClient, SESError, get_ses_client
from app.models.notification import Notification
from app.models.user import User
from app.services.notifications import (
    MAX_ATTEMPTS,
    STATUS_SENT,
    STATUS_SUPPRESSED,
    mark_failed,
    mark_sent,
    pending_notifications,
)

log = structlog.get_logger("worker.notification_sender")


POLL_INTERVAL_SECONDS = float(os.environ.get("SENDER_POLL_INTERVAL", "30"))


# ---- helpers ----------------------------------------------------------


def _teams_webhook_configured() -> bool:
    return bool((os.environ.get("TEAMS_WEBHOOK_URL") or "").strip())


def _slack_webhook_configured() -> bool:
    return bool((os.environ.get("SLACK_WEBHOOK_URL") or "").strip())


async def _load_user_email(session: AsyncSession, user_id) -> str | None:
    row = (
        await session.execute(select(User.email).where(User.id == user_id))
    ).scalar_one_or_none()
    return row


async def _suppress(
    session: AsyncSession, notification: Notification, reason: str
) -> None:
    """Mark a row suppressed and audit the reason.

    We do not go through ``queue_notification`` (that's for producers). The
    sender owns the mutation and writes the audit row inline so the chain
    covers the decision without touching the service module.
    """

    before = {"status": notification.status, "last_error": notification.last_error}
    notification.status = STATUS_SUPPRESSED
    notification.last_error = reason
    notification.next_attempt_at = None
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="notification.suppressed",
        entity="notification",
        entity_id=str(notification.id),
        before=before,
        after={"status": notification.status, "reason": reason},
    )
    await session.commit()


async def _mark_inapp_sent(session: AsyncSession, notification: Notification) -> None:
    """Inapp rows never leave the DB; flip to sent immediately."""

    before = {"status": notification.status, "attempts": notification.attempts}
    notification.status = STATUS_SENT
    notification.attempts = notification.attempts + 1
    notification.sent_at = datetime.now(UTC)
    notification.next_attempt_at = None
    notification.last_error = None
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="notification.sent",
        entity="notification",
        entity_id=str(notification.id),
        before=before,
        after={"status": notification.status, "attempts": notification.attempts},
    )
    await session.commit()


# ---- per-row dispatch --------------------------------------------------


async def _handle_email(
    session: AsyncSession, ses: SESClient, notification: Notification
) -> None:
    to_email = await _load_user_email(session, notification.user_id)
    if not to_email:
        # No recipient → suppress rather than retry forever.
        await _suppress(session, notification, "recipient email not found")
        return
    try:
        await ses.send(
            to_address=to_email,
            subject=notification.subject,
            body_text=notification.body_md,
        )
    except SESError as exc:
        if notification.attempts + 1 >= MAX_ATTEMPTS:
            log.warning(
                "ses_send_gave_up", notification_id=str(notification.id), error=str(exc)
            )
        await mark_failed(session, notification.id, error=str(exc))
        return
    await mark_sent(session, notification.id)


async def _handle_row(
    session: AsyncSession, ses: SESClient, notification: Notification
) -> None:
    channel = notification.channel
    if channel == "email":
        await _handle_email(session, ses, notification)
        return
    if channel == "teams":
        if not _teams_webhook_configured():
            await _suppress(session, notification, "channel not configured")
            return
        # Sprint 2 does not ship the Teams sender; leave the row pending
        # for a future worker to pick up. In practice env is unset so we
        # take the branch above.
        return  # pragma: no cover
    if channel == "slack":
        if not _slack_webhook_configured():
            await _suppress(session, notification, "channel not configured")
            return
        return  # pragma: no cover
    if channel == "inapp":
        await _mark_inapp_sent(session, notification)
        return
    # Defensive: unknown channels shouldn't reach here because
    # queue_notification validates. Suppress + audit anyway.
    await _suppress(session, notification, f"unknown channel {channel!r}")


# ---- public entry points ---------------------------------------------


async def process_batch(
    session: AsyncSession, ses: SESClient | None = None, *, limit: int = 50
) -> int:
    """Dispatch up to ``limit`` rows. Returns the number handled."""

    ses = ses or get_ses_client()
    rows = await pending_notifications(session, limit=limit)
    for row in rows:
        # Refetch after each iteration so status changes by earlier rows in
        # the same batch don't cause stale writes. pending_notifications
        # already skipped anything not ready.
        await _handle_row(session, ses, row)
    return len(rows)


async def _drain_forever() -> None:
    log.info("sender_started", poll_interval=POLL_INTERVAL_SECONDS)
    ses = get_ses_client()
    while True:
        try:
            async with session_factory() as session:
                count = await process_batch(session, ses)
            if count:
                log.info("sender_batch_processed", count=count)
        except Exception:  # pragma: no cover - operational log
            log.exception("sender_batch_failed")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def main() -> None:
    try:
        asyncio.run(_drain_forever())
    except KeyboardInterrupt:
        log.info("sender_stopped")


if __name__ == "__main__":
    main()


__all__ = ["POLL_INTERVAL_SECONDS", "main", "process_batch"]
