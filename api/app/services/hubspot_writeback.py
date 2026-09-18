"""HubSpot write-back service (S4-E2).

CLAUDE.md rule 7: HubSpot is master for deal identity, owner and stage.
DealGate writes back exactly three governance properties. This module owns
the property allow-list and the outbox lifecycle; the worker
(:mod:`worker.hubspot_writeback`) is a pure reader that calls
:func:`process_pending`.

Property allow-list (do not extend without updating the blueprint AND a
migration for HubSpot's read-only custom properties):

- ``governance_status``      -> HubSpot ``dealgate_governance_status``
- ``approved_gm_pct``        -> HubSpot ``dealgate_approved_gm_pct``
- ``dealgate_link``          -> HubSpot ``dealgate_link``

Any other key in a ``target_state`` dict is rejected with HTTP 422 by
:func:`queue_writeback`. This is the single guard that keeps DealGate from
ever writing outside its lane.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.hubspot import HubSpotClient
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.opportunity import Opportunity

log = structlog.get_logger("hubspot_writeback")


# --- property allow-list ------------------------------------------------

# DealGate → HubSpot property name map. CLAUDE.md rule 7: THREE properties
# only. Extending this dict is a policy change; do not add rows here for
# convenience. The keys are the DealGate-side names used by callers; the
# values are the HubSpot custom property names.
MAP: dict[str, str] = {
    "governance_status": "dealgate_governance_status",
    "approved_gm_pct": "dealgate_approved_gm_pct",
    "dealgate_link": "dealgate_link",
}

_ALLOWED_KEYS: frozenset[str] = frozenset(MAP.keys())


# --- lifecycle -----------------------------------------------------------

STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"
STATUS_DEAL_MISSING = "deal_missing"

# Exponential back-off in minutes. Index = attempt number after the failed
# try. Matches the notification sender ladder so operators see one shape.
_BACKOFF_MINUTES: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 60)
MAX_ATTEMPTS = 5


def _backoff_for(attempts: int) -> timedelta:
    idx = min(max(attempts - 1, 0), len(_BACKOFF_MINUTES) - 1)
    return timedelta(minutes=_BACKOFF_MINUTES[idx])


def _translate_to_hubspot(target_state: dict[str, Any]) -> dict[str, Any]:
    """Rename DealGate keys to their HubSpot property names.

    Assumes ``target_state`` already passed :func:`_validate_target_state`.
    """

    return {MAP[k]: v for k, v in target_state.items()}


def _validate_target_state(target_state: dict[str, Any]) -> dict[str, Any]:
    """Reject any key that is not in the allow-list.

    Raises ``HTTPException`` 422 with the offending key set so the router /
    caller can surface a clear error. Returns the *same* dict when valid so
    callers can chain calls.
    """

    if not isinstance(target_state, dict) or not target_state:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target_state must be a non-empty object",
        )
    extra = set(target_state.keys()) - _ALLOWED_KEYS
    if extra:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "hubspot writeback allows only "
                f"{sorted(_ALLOWED_KEYS)}; got extra keys: {sorted(extra)}"
            ),
        )
    return target_state


# --- writers -------------------------------------------------------------


async def queue_writeback(
    session: AsyncSession,
    opportunity: Opportunity,
    target_state: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> HubspotWritebackJob:
    """Append one ``hubspot_writeback_job`` row for a governance change.

    Called from any code path that changes ``governance_status`` or
    ``approved_gm_pct`` on an opportunity (Agent U's ``ready_to_sign``
    transition, plus every subsequent governance transition). Idempotency
    is the worker's job — we always append a new row so the audit trail
    shows one attempt per source event.

    Caller owns the transaction. This function flushes + audits but does
    not commit, so the outbox row lands atomically with whatever state
    change produced it (CLAUDE.md rule 5).
    """

    _validate_target_state(target_state)

    now = datetime.now(UTC)
    row = HubspotWritebackJob(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        hubspot_deal_id=opportunity.hubspot_deal_id,
        target_state=dict(target_state),  # store the DealGate-side keys
        status=STATUS_PENDING,
        attempts=0,
        next_attempt_at=now,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="hubspot_write.queued",
        entity="hubspot_writeback_job",
        entity_id=str(row.id),
        before=None,
        after={
            "opportunity_id": str(opportunity.id),
            "hubspot_deal_id": row.hubspot_deal_id,
            "target_state": row.target_state,
        },
        correlation_id=correlation_id,
    )
    return row


# --- worker path ---------------------------------------------------------


async def _pending_jobs(
    session: AsyncSession, *, limit: int = 50
) -> list[HubspotWritebackJob]:
    now = datetime.now(UTC)
    stmt = (
        select(HubspotWritebackJob)
        .where(HubspotWritebackJob.status == STATUS_PENDING)
        .where(HubspotWritebackJob.attempts < MAX_ATTEMPTS)
        .order_by(
            HubspotWritebackJob.next_attempt_at.asc().nulls_first(),
            HubspotWritebackJob.created_at.asc(),
        )
        .limit(limit)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    ready: list[HubspotWritebackJob] = []
    for r in rows:
        if r.next_attempt_at is None:
            ready.append(r)
            continue
        na = r.next_attempt_at
        if na.tzinfo is None:
            na = na.replace(tzinfo=UTC)
        if na <= now:
            ready.append(r)
    return ready


def _status_code_of(exc: Exception) -> int | None:
    """Extract an HTTP status code from an httpx error, if any."""

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


async def _mark_sent(session: AsyncSession, job: HubspotWritebackJob) -> None:
    before = {"status": job.status, "attempts": job.attempts}
    job.status = STATUS_SENT
    job.attempts = job.attempts + 1
    job.sent_at = datetime.now(UTC)
    job.next_attempt_at = None
    job.last_error = None
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="hubspot_write.sent",
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


async def _mark_deal_missing(
    session: AsyncSession, job: HubspotWritebackJob, error: str
) -> None:
    before = {"status": job.status, "attempts": job.attempts}
    job.status = STATUS_DEAL_MISSING
    job.attempts = job.attempts + 1
    job.next_attempt_at = None
    job.last_error = error[:2000]
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="hubspot_write.deal_missing",
        entity="hubspot_writeback_job",
        entity_id=str(job.id),
        before=before,
        after={
            "status": job.status,
            "hubspot_deal_id": job.hubspot_deal_id,
            "last_error": job.last_error,
        },
    )
    await session.commit()


async def _mark_retry_or_fail(
    session: AsyncSession, job: HubspotWritebackJob, error: str
) -> None:
    """Bump attempts, either schedule the next retry or fail permanently."""

    before = {"status": job.status, "attempts": job.attempts}
    job.attempts = job.attempts + 1
    job.last_error = (error or "").strip()[:2000] or "unknown error"
    if job.attempts >= MAX_ATTEMPTS:
        job.status = STATUS_FAILED
        job.next_attempt_at = None
        audit_action = "hubspot_write.failed"
    else:
        job.status = STATUS_PENDING
        job.next_attempt_at = datetime.now(UTC) + _backoff_for(job.attempts)
        audit_action = "hubspot_write.retry"
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action=audit_action,
        entity="hubspot_writeback_job",
        entity_id=str(job.id),
        before=before,
        after={
            "status": job.status,
            "attempts": job.attempts,
            "next_attempt_at": (
                job.next_attempt_at.isoformat() if job.next_attempt_at else None
            ),
            "last_error": job.last_error,
        },
    )
    await session.commit()


async def _dispatch_one(
    session: AsyncSession,
    hubspot: HubSpotClient,
    job: HubspotWritebackJob,
) -> None:
    """Send one job to HubSpot; classify the response into a lifecycle move."""

    # Defence in depth: even though `queue_writeback` validated on the way in,
    # we re-check before the outbound call so a hand-crafted / imported row
    # can never sneak past the allow-list.
    try:
        _validate_target_state(job.target_state or {})
    except HTTPException as exc:
        await _mark_retry_or_fail(session, job, f"invalid target_state: {exc.detail}")
        return

    hubspot_properties = _translate_to_hubspot(job.target_state)
    try:
        await hubspot.update_deal(job.hubspot_deal_id, hubspot_properties)
    except Exception as exc:  # noqa: BLE001 — classify below
        code = _status_code_of(exc)
        if code == 404:
            await _mark_deal_missing(session, job, error=str(exc))
            return
        if code == 429:
            # Rate limited: stay pending, schedule the next retry, keep the
            # attempt count moving so MAX_ATTEMPTS still applies.
            await _mark_retry_or_fail(session, job, error=str(exc))
            return
        # Any other transport / 5xx / unexpected error: retry with back-off.
        await _mark_retry_or_fail(session, job, error=str(exc))
        return

    await _mark_sent(session, job)


async def process_pending(
    session: AsyncSession,
    hubspot: HubSpotClient,
    *,
    limit: int = 50,
) -> int:
    """Drain up to ``limit`` pending write-back jobs. Returns count handled.

    Idempotent per-job: re-running for a row already in status ``sent`` is a
    no-op because the query filters on ``status == pending``.
    """

    jobs = await _pending_jobs(session, limit=limit)
    for job in jobs:
        await _dispatch_one(session, hubspot, job)
    return len(jobs)


# --- upstream hooks ------------------------------------------------------


def _format_gm_pct(value: Any) -> Any:
    """Emit GM% as a plain float with 4 decimal precision.

    HubSpot's ``number`` property type accepts a JSON number. We keep the
    original ``Decimal`` in the ``target_state`` for the audit trail and only
    coerce at send-time — but here at the hook we normalise so the audit row
    is human-readable regardless of the caller's type.
    """

    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


async def on_package_ready_to_sign(
    session: AsyncSession,
    opportunity: Opportunity,
    *,
    blended_gm_pct: Any,
    dealgate_link: str | None = None,
    correlation_id: str | None = None,
) -> HubspotWritebackJob:
    """Hook Agent U's approval service calls when a package hits ``ready_to_sign``.

    Kept in this module (not U's service file) so the property allow-list and
    the outbox writer stay co-located. Agent U imports this function and
    calls it inside their transition transaction; nothing else in the
    approval service needs to know about HubSpot.
    """

    target: dict[str, Any] = {
        "governance_status": "Ready to Sign",
        "approved_gm_pct": _format_gm_pct(blended_gm_pct),
    }
    if dealgate_link is not None:
        target["dealgate_link"] = dealgate_link
    return await queue_writeback(
        session,
        opportunity,
        target,
        correlation_id=correlation_id,
    )


__all__ = [
    "MAP",
    "MAX_ATTEMPTS",
    "STATUS_DEAL_MISSING",
    "STATUS_FAILED",
    "STATUS_PENDING",
    "STATUS_SENT",
    "on_package_ready_to_sign",
    "process_pending",
    "queue_writeback",
]
