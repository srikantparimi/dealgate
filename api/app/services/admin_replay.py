"""Admin replay service (S6).

Read-only wrappers over the DLQ tables owned by Agent A (integration_event),
Agent M (notification) and Agent W (hubspot_writeback_job), plus a per-row
replay path that re-invokes each owner's own worker step.

Design notes:

- The service NEVER touches the owning service files' internals. It calls
  their public entry points (:func:`handle_event`,
  :func:`process_pending`, :func:`mark_sent` / :func:`mark_failed`) so the
  replay flow enjoys the same lifecycle rules the workers do.
- Every replay writes an ``audit_event`` in the caller's transaction
  (CLAUDE.md rule 5).
- The router enforces ``SystemAdmin``; this module accepts an ``actor``
  arg so audit rows carry the admin's user id.

Listing rules:

- HubSpot writeback: ``status = failed`` OR (``status = pending`` AND
  ``attempts >= MAX_ATTEMPTS``). Includes ``deal_missing`` too because ops
  frequently want to replay after fixing the deal in HubSpot.
- Notifications: ``status = failed``.
- Integration events: ``processed_at IS NULL`` AND ``received_at`` older
  than 15 minutes — same "stuck" definition the story asks for.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.hubspot import HubSpotClient
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.integration import IntegrationEvent
from app.models.notification import Notification
from app.services.hubspot_intake import handle_event
from app.services.hubspot_writeback import (
    MAX_ATTEMPTS as HUBSPOT_MAX_ATTEMPTS,
)
from app.services.hubspot_writeback import (
    STATUS_DEAL_MISSING as HUBSPOT_STATUS_DEAL_MISSING,
)
from app.services.hubspot_writeback import (
    STATUS_FAILED as HUBSPOT_STATUS_FAILED,
)
from app.services.hubspot_writeback import (
    STATUS_PENDING as HUBSPOT_STATUS_PENDING,
)
from app.services.hubspot_writeback import (
    process_pending as hubspot_process_pending,
)
from app.services.notifications import (
    STATUS_FAILED as NOTIF_STATUS_FAILED,
)
from app.services.notifications import (
    STATUS_PENDING as NOTIF_STATUS_PENDING,
)

# Rows older than this are considered "stuck" for the integration_event queue.
STUCK_EVENT_AGE = timedelta(minutes=15)


# --- shared shapes --------------------------------------------------------


@dataclass(frozen=True)
class Page:
    items: list[Any]
    page: int
    size: int
    total: int


def _paginate(rows: list[Any], page: int, size: int) -> Page:
    total = len(rows)
    offset = max(0, (max(page, 1) - 1) * max(size, 1))
    slice_ = rows[offset : offset + size]
    return Page(items=slice_, page=page, size=size, total=total)


def _ensure_utc(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts


# --- listers --------------------------------------------------------------


async def list_failed_hubspot_writeback(
    session: AsyncSession, *, page: int = 1, size: int = 25
) -> Page:
    """Failed / DLQ hubspot_writeback_job rows.

    Includes anything with ``status = failed`` or ``deal_missing``, plus rows
    still ``pending`` that have exhausted their retry budget. Sorted so the
    oldest broken row surfaces first (``updated_at``-ish via ``sent_at`` /
    ``next_attempt_at`` / ``created_at``).
    """

    stmt = (
        select(HubspotWritebackJob)
        .where(
            or_(
                HubspotWritebackJob.status == HUBSPOT_STATUS_FAILED,
                HubspotWritebackJob.status == HUBSPOT_STATUS_DEAL_MISSING,
                (HubspotWritebackJob.status == HUBSPOT_STATUS_PENDING)
                & (HubspotWritebackJob.attempts >= HUBSPOT_MAX_ATTEMPTS),
            )
        )
        .order_by(
            HubspotWritebackJob.attempts.desc(),
            HubspotWritebackJob.created_at.asc(),
        )
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return _paginate(rows, page, size)


async def list_failed_notifications(
    session: AsyncSession, *, page: int = 1, size: int = 25
) -> Page:
    """Notifications the worker has given up on (``status = failed``)."""

    stmt = (
        select(Notification)
        .where(Notification.status == NOTIF_STATUS_FAILED)
        .order_by(Notification.attempts.desc(), Notification.created_at.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return _paginate(rows, page, size)


async def list_failed_integration_events(
    session: AsyncSession, *, page: int = 1, size: int = 25
) -> Page:
    """Integration events stuck in the queue: unprocessed AND older than 15m.

    Younger unprocessed rows are still in flight for the worker — surfacing
    them here would be noisy. The 15-minute floor keeps the admin screen
    focused on genuine DLQ material.
    """

    cutoff = datetime.now(UTC) - STUCK_EVENT_AGE
    stmt = (
        select(IntegrationEvent)
        .where(IntegrationEvent.processed_at.is_(None))
        .where(IntegrationEvent.received_at < cutoff)
        .order_by(IntegrationEvent.received_at.asc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return _paginate(rows, page, size)


# --- replay actions -------------------------------------------------------


async def _load_writeback(
    session: AsyncSession, job_id: uuid.UUID
) -> HubspotWritebackJob:
    row = (
        await session.execute(
            select(HubspotWritebackJob).where(HubspotWritebackJob.id == job_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="hubspot writeback job not found"
        )
    return row


async def replay_hubspot_writeback(
    session: AsyncSession,
    *,
    actor: uuid.UUID | None,
    job_id: uuid.UUID,
    hubspot_client: HubSpotClient,
) -> HubspotWritebackJob:
    """Reset one job and re-run the writeback worker's pending pass.

    Resetting attempts is what re-arms the job for the worker; the
    ``process_pending`` call keeps the audit-emitting lifecycle (sent /
    retry / failed / deal_missing) in :mod:`app.services.hubspot_writeback`
    where it belongs.
    """

    job = await _load_writeback(session, job_id)

    before = {
        "status": job.status,
        "attempts": job.attempts,
        "last_error": job.last_error,
    }
    job.status = HUBSPOT_STATUS_PENDING
    job.attempts = 0
    job.next_attempt_at = datetime.now(UTC)
    job.last_error = None
    await session.flush()
    await append_audit(
        session,
        actor_id=actor,
        action="hubspot_write.replayed",
        entity="hubspot_writeback_job",
        entity_id=str(job.id),
        before=before,
        after={
            "status": job.status,
            "attempts": job.attempts,
            "hubspot_deal_id": job.hubspot_deal_id,
        },
    )
    await session.commit()

    # Delegate to the owner's worker path so the sent/retry/failed lifecycle
    # + audits stay identical to the normal drain.
    await hubspot_process_pending(session, hubspot_client)
    await session.refresh(job)
    job.next_attempt_at = _ensure_utc(job.next_attempt_at)
    job.sent_at = _ensure_utc(job.sent_at)
    return job


async def _load_notification(
    session: AsyncSession, notification_id: uuid.UUID
) -> Notification:
    row = (
        await session.execute(
            select(Notification).where(Notification.id == notification_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="notification not found"
        )
    return row


async def replay_notification(
    session: AsyncSession,
    *,
    actor: uuid.UUID | None,
    notification_id: uuid.UUID,
) -> Notification:
    """Return a failed notification to the pending queue with fresh counters.

    The worker (Agent N) then picks it up on its next drain and flips it to
    ``sent`` or (retries then) ``failed`` via the notifications service. We
    do NOT call the sender ourselves — that would duplicate Agent N's
    dispatch policy and leak into their audit story.
    """

    row = await _load_notification(session, notification_id)
    before = {
        "status": row.status,
        "attempts": row.attempts,
        "last_error": row.last_error,
    }
    row.status = NOTIF_STATUS_PENDING
    row.attempts = 0
    row.next_attempt_at = datetime.now(UTC)
    row.last_error = None
    await session.flush()
    await append_audit(
        session,
        actor_id=actor,
        action="notification.replayed",
        entity="notification",
        entity_id=str(row.id),
        before=before,
        after={
            "status": row.status,
            "attempts": row.attempts,
            "category": row.category,
            "channel": row.channel,
        },
    )
    await session.commit()
    await session.refresh(row)
    row.next_attempt_at = _ensure_utc(row.next_attempt_at)
    row.sent_at = _ensure_utc(row.sent_at)
    return row


async def _load_integration_event(
    session: AsyncSession, event_id: uuid.UUID
) -> IntegrationEvent:
    row = (
        await session.execute(
            select(IntegrationEvent).where(IntegrationEvent.id == event_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="integration event not found"
        )
    return row


async def replay_integration_event(
    session: AsyncSession,
    *,
    actor: uuid.UUID | None,
    event_id: uuid.UUID,
    hubspot_client: HubSpotClient,
) -> IntegrationEvent:
    """Re-run :func:`handle_event` for a stored integration event.

    Idempotent by construction: ``handle_event`` upserts on the deal and
    only creates the intake task when the opportunity is fresh, so a
    replay is safe even if the row has already been processed. We reset
    ``processed_at`` so the full path runs again and audit the replay.
    """

    row = await _load_integration_event(session, event_id)

    before = {
        "processed_at": (
            row.processed_at.isoformat() if row.processed_at else None
        ),
        "source_event_id": row.source_event_id,
    }
    row.processed_at = None
    await session.flush()
    await append_audit(
        session,
        actor_id=actor,
        action="integration_event.replayed",
        entity="integration_event",
        entity_id=str(row.id),
        before=before,
        after={"source_event_id": row.source_event_id, "source": row.source},
        correlation_id=f"hubspot:replay:{row.source_event_id}",
    )
    await session.commit()

    # Delegate to Agent C's owner path; it commits ``processed_at`` on
    # success and emits the ``opportunity.*`` / ``task.*`` audits.
    await handle_event(session, row.payload, hubspot_client)
    await session.refresh(row)
    row.processed_at = _ensure_utc(row.processed_at)
    row.received_at = _ensure_utc(row.received_at)
    return row


# Convenience for the router: keep the count query cheap for the list badges.
async def failed_counts(session: AsyncSession) -> dict[str, int]:
    """Return `{ writeback, notifications, integration_events }` counts.

    Not called by the acceptance path — exposed so future dashboards or
    the nav badge can pull three ints without materialising every row.
    """

    cutoff = datetime.now(UTC) - STUCK_EVENT_AGE
    writeback_stmt = select(func.count(HubspotWritebackJob.id)).where(
        or_(
            HubspotWritebackJob.status == HUBSPOT_STATUS_FAILED,
            HubspotWritebackJob.status == HUBSPOT_STATUS_DEAL_MISSING,
            (HubspotWritebackJob.status == HUBSPOT_STATUS_PENDING)
            & (HubspotWritebackJob.attempts >= HUBSPOT_MAX_ATTEMPTS),
        )
    )
    notif_stmt = select(func.count(Notification.id)).where(
        Notification.status == NOTIF_STATUS_FAILED
    )
    event_stmt = (
        select(func.count(IntegrationEvent.id))
        .where(IntegrationEvent.processed_at.is_(None))
        .where(IntegrationEvent.received_at < cutoff)
    )
    return {
        "writeback": int((await session.execute(writeback_stmt)).scalar_one() or 0),
        "notifications": int((await session.execute(notif_stmt)).scalar_one() or 0),
        "integration_events": int((await session.execute(event_stmt)).scalar_one() or 0),
    }


__all__ = [
    "STUCK_EVENT_AGE",
    "Page",
    "failed_counts",
    "list_failed_hubspot_writeback",
    "list_failed_integration_events",
    "list_failed_notifications",
    "replay_hubspot_writeback",
    "replay_integration_event",
    "replay_notification",
]
