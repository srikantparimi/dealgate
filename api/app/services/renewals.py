"""Renewal service (S5 E9 — Agent Y2).

Small state-machine + query helpers backing the renewals scheduler
(``worker.renewals_scheduler``) and the ``/renewals`` inbox
(``app.routers.renewals``). Every state change writes an ``audit_event``
in the same transaction (CLAUDE.md rule 5); callers own the commit.

State model (blueprint §9):

    open ──► closed
      │
      ├──► extended (renewal signed as a fresh SOW version)
      │
      └──► churn   (term_end passed with no extension)

``open_renewal`` is idempotent per (opportunity, term_end): a repeat call
returns the existing row so the scheduler can safely re-run without
duping the account owner's task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.opportunity import Opportunity
from app.models.renewal import RENEWAL_STATUSES, Renewal
from app.models.task import Task
from app.services.notifications import queue_notification


DEFAULT_TRIGGER_LEAD_DAYS = 60


class RenewalError(HTTPException):
    """Base error the router turns into a JSON response."""


# ---- read helpers -------------------------------------------------------


async def active_renewals_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> list[Renewal]:
    """Return open renewal rows for an opportunity (most-recent first).

    "Active" = ``status = 'open'``. Callers use this both to check for an
    existing renewal before opening a new one and to expose the "at risk"
    banner on the deal detail page.
    """

    stmt = (
        select(Renewal)
        .where(Renewal.opportunity_id == opportunity_id)
        .where(Renewal.status == "open")
        .order_by(Renewal.opened_at.desc(), Renewal.id.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return rows


async def renewals_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> list[Renewal]:
    """All renewal rows for an opportunity (any status)."""

    stmt = (
        select(Renewal)
        .where(Renewal.opportunity_id == opportunity_id)
        .order_by(Renewal.opened_at.desc(), Renewal.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def load_renewal(session: AsyncSession, renewal_id: uuid.UUID) -> Renewal:
    row = (
        await session.execute(select(Renewal).where(Renewal.id == renewal_id))
    ).scalar_one_or_none()
    if row is None:
        raise RenewalError(status_code=404, detail="renewal not found")
    return row


async def has_churn(session: AsyncSession, opportunity_id: uuid.UUID) -> bool:
    """True when any renewal on the opportunity is ``churn``.

    Used by :func:`app.services.approvals.submit_package` to block new
    commitments on a churned SOW.
    """

    stmt = (
        select(Renewal.id)
        .where(Renewal.opportunity_id == opportunity_id)
        .where(Renewal.status == "churn")
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


# ---- open ---------------------------------------------------------------


async def open_renewal(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    term_end: date,
    trigger_date: date | None = None,
    correlation_id: str | None = None,
) -> tuple[Renewal, bool]:
    """Create a new ``open`` renewal + owner task.

    Idempotent per (opportunity_id, term_end): if a row already exists,
    the tuple's second element is ``False`` and no task/notification is
    written (the caller — usually the scheduler — is expected to gate on
    that flag too via its ``scheduler_fired`` ledger, so this is a
    belt-and-braces guard).

    The task lands with the account owner. The notification fans out via
    the standard channels — CLAUDE.md rule 5 is honoured by the shared
    ``queue_notification`` (it audits each row).
    """

    existing = (
        await session.execute(
            select(Renewal)
            .where(Renewal.opportunity_id == opportunity.id)
            .where(Renewal.term_end == term_end)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    trigger = trigger_date or (term_end - timedelta(days=DEFAULT_TRIGGER_LEAD_DAYS))
    row = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        term_end=term_end,
        trigger_date=trigger,
        status="open",
    )
    session.add(row)
    await session.flush()

    await append_audit(
        session,
        actor_id=None,
        action="renewal.opened",
        entity="renewal",
        entity_id=str(row.id),
        before=None,
        after={
            "opportunity_id": str(opportunity.id),
            "term_end": term_end.isoformat(),
            "trigger_date": trigger.isoformat(),
            "status": row.status,
        },
        correlation_id=correlation_id,
    )

    # Owner task — helps them find the row in "My tasks".
    task = Task(
        id=uuid.uuid4(),
        owner_id=opportunity.owner_id,
        subject=(
            f"Renewal review for {opportunity.hubspot_deal_id} — "
            f"term ends {term_end.isoformat()}"
        ),
        due_date=term_end,
        category="renewal.review",
        status="assigned",
    )
    session.add(task)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="task.created",
        entity="task",
        entity_id=str(task.id),
        before=None,
        after={
            "owner_id": (
                str(opportunity.owner_id) if opportunity.owner_id else None
            ),
            "subject": task.subject,
            "category": task.category,
            "due_date": term_end.isoformat(),
            "related_entity": "renewal",
            "related_entity_id": str(row.id),
            "source": "scheduler.renewal.review",
        },
        correlation_id=correlation_id,
    )

    # Notify the owner. ``queue_notification`` fans out per channel + audits.
    if opportunity.owner_id is not None:
        await queue_notification(
            session,
            user_id=opportunity.owner_id,
            category="expiry_warning",
            subject=task.subject,
            body_md=(
                f"SOW for `{opportunity.hubspot_deal_id}` ends on "
                f"`{term_end.isoformat()}`. Record renewal status/value/"
                "decision/next action on the renewal record."
            ),
            related_entity="renewal",
            related_entity_id=str(row.id),
        )

    return row, True


# ---- close --------------------------------------------------------------


async def close_renewal(
    session: AsyncSession,
    *,
    renewal: Renewal,
    outcome: str,
    replacement_sow_version_id: uuid.UUID | None = None,
    actor_id: uuid.UUID | None = None,
    to_status: str = "closed",
) -> Renewal:
    """Close a renewal.

    ``to_status`` must be one of ``closed`` | ``extended``. Writing a
    ``churn`` requires :func:`mark_churn` — the caller path is different
    (the scheduler picks it up, not the human).
    """

    if to_status not in ("closed", "extended"):
        raise RenewalError(
            status_code=422,
            detail="close_renewal only accepts to_status in {'closed','extended'}",
        )
    if renewal.status not in ("open",):
        raise RenewalError(
            status_code=409,
            detail=f"renewal is {renewal.status!r}; cannot close",
        )

    before = {
        "status": renewal.status,
        "outcome_summary": renewal.outcome_summary,
        "replacement_sow_version_id": (
            str(renewal.replacement_sow_version_id)
            if renewal.replacement_sow_version_id
            else None
        ),
    }
    renewal.status = to_status
    renewal.outcome_summary = outcome
    if replacement_sow_version_id is not None:
        renewal.replacement_sow_version_id = replacement_sow_version_id
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action=f"renewal.{to_status}",
        entity="renewal",
        entity_id=str(renewal.id),
        before=before,
        after={
            "status": renewal.status,
            "outcome_summary": renewal.outcome_summary,
            "replacement_sow_version_id": (
                str(renewal.replacement_sow_version_id)
                if renewal.replacement_sow_version_id
                else None
            ),
        },
    )
    return renewal


# ---- churn --------------------------------------------------------------


async def mark_churn(
    session: AsyncSession,
    *,
    renewal: Renewal,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
) -> Renewal:
    """Flip an open renewal to ``churn`` (term_end passed with no extension).

    Idempotent when the renewal is already ``churn``. Any non-open status
    other than ``churn`` refuses — closing a renewal with an extension
    then churning it later is not a real workflow.
    """

    if renewal.status == "churn":
        return renewal
    if renewal.status != "open":
        raise RenewalError(
            status_code=409,
            detail=(
                f"renewal is {renewal.status!r}; only 'open' renewals may "
                "transition to churn"
            ),
        )
    before = {"status": renewal.status, "outcome_summary": renewal.outcome_summary}
    renewal.status = "churn"
    if reason is not None:
        renewal.outcome_summary = reason
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="renewal.churn",
        entity="renewal",
        entity_id=str(renewal.id),
        before=before,
        after={
            "status": renewal.status,
            "outcome_summary": renewal.outcome_summary,
        },
    )
    return renewal


# ---- patch (owner PATCH via router) -------------------------------------


async def patch_renewal(
    session: AsyncSession,
    *,
    renewal: Renewal,
    actor_id: uuid.UUID,
    outcome_summary: str | None = None,
    to_status: str | None = None,
    replacement_sow_version_id: uuid.UUID | None = None,
    _summary_provided: bool = True,
) -> Renewal:
    """Router-friendly PATCH — update outcome_summary + optionally status.

    Status transitions accepted: ``open`` → ``closed`` | ``extended``.
    Setting ``replacement_sow_version_id`` implies ``extended`` if not
    otherwise specified.
    """

    if to_status is None and replacement_sow_version_id is not None:
        to_status = "extended"

    if to_status is not None and to_status not in ("closed", "extended"):
        raise RenewalError(
            status_code=422,
            detail=(
                f"status must be one of 'closed'|'extended' "
                f"(got {to_status!r}); use the scheduler for 'churn'"
            ),
        )

    before = {
        "status": renewal.status,
        "outcome_summary": renewal.outcome_summary,
        "replacement_sow_version_id": (
            str(renewal.replacement_sow_version_id)
            if renewal.replacement_sow_version_id
            else None
        ),
    }
    changed = False
    if _summary_provided and outcome_summary != renewal.outcome_summary:
        renewal.outcome_summary = outcome_summary
        changed = True
    if (
        replacement_sow_version_id is not None
        and replacement_sow_version_id != renewal.replacement_sow_version_id
    ):
        renewal.replacement_sow_version_id = replacement_sow_version_id
        changed = True
    if to_status is not None and to_status != renewal.status:
        if renewal.status != "open":
            raise RenewalError(
                status_code=409,
                detail=f"renewal is {renewal.status!r}; cannot transition",
            )
        renewal.status = to_status
        changed = True

    if not changed:
        return renewal

    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="renewal.updated",
        entity="renewal",
        entity_id=str(renewal.id),
        before=before,
        after={
            "status": renewal.status,
            "outcome_summary": renewal.outcome_summary,
            "replacement_sow_version_id": (
                str(renewal.replacement_sow_version_id)
                if renewal.replacement_sow_version_id
                else None
            ),
        },
    )
    return renewal


# ---- list ---------------------------------------------------------------


async def list_renewals(
    session: AsyncSession,
    *,
    status_: str | None = None,
    owner_id: uuid.UUID | None = None,
    page: int = 1,
    size: int = 25,
) -> tuple[list[tuple[Renewal, Opportunity]], int]:
    """Return renewals joined with the owning opportunity.

    Filter by ``status`` and/or the deal ``owner_id``. Ordered by
    ``trigger_date`` ascending so the "soonest to fire" rows sit at the
    top of the board.
    """

    from sqlalchemy import func as sa_func

    stmt = (
        select(Renewal, Opportunity)
        .join(Opportunity, Opportunity.id == Renewal.opportunity_id)
        .order_by(Renewal.trigger_date.asc(), Renewal.id.desc())
    )
    count_stmt = select(sa_func.count(Renewal.id)).select_from(Renewal)
    if status_:
        if status_ not in RENEWAL_STATUSES:
            raise RenewalError(
                status_code=422,
                detail=f"unknown status: {status_!r}",
            )
        stmt = stmt.where(Renewal.status == status_)
        count_stmt = count_stmt.where(Renewal.status == status_)
    if owner_id is not None:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
        count_stmt = count_stmt.join(
            Opportunity, Opportunity.id == Renewal.opportunity_id
        ).where(Opportunity.owner_id == owner_id)

    offset = max(0, (page - 1) * size)
    stmt = stmt.offset(offset).limit(size)
    rows = list((await session.execute(stmt)).all())
    total = int((await session.execute(count_stmt)).scalar_one())
    return [(r, o) for (r, o) in rows], total


# ---- serialisation ------------------------------------------------------


def _days_until(term_end: date, today: date) -> int:
    return (term_end - today).days


def serialize_renewal(
    renewal: Renewal, opportunity: Opportunity | None = None, today: date | None = None
) -> dict[str, Any]:
    ref_today = today or datetime.now(UTC).date()
    payload: dict[str, Any] = {
        "id": str(renewal.id),
        "opportunity_id": str(renewal.opportunity_id),
        "term_end": renewal.term_end.isoformat(),
        "trigger_date": renewal.trigger_date.isoformat(),
        "status": renewal.status,
        "outcome_summary": renewal.outcome_summary,
        "replacement_sow_version_id": (
            str(renewal.replacement_sow_version_id)
            if renewal.replacement_sow_version_id
            else None
        ),
        "opened_at": renewal.opened_at.isoformat() if renewal.opened_at else None,
        "updated_at": renewal.updated_at.isoformat() if renewal.updated_at else None,
        "days_until_end": _days_until(renewal.term_end, ref_today),
    }
    if opportunity is not None:
        payload["hubspot_deal_id"] = opportunity.hubspot_deal_id
        payload["owner_id"] = (
            str(opportunity.owner_id) if opportunity.owner_id else None
        )
        payload["client_id"] = (
            str(opportunity.client_id) if opportunity.client_id else None
        )
    return payload


__all__ = [
    "DEFAULT_TRIGGER_LEAD_DAYS",
    "RENEWAL_STATUSES",
    "RenewalError",
    "active_renewals_for",
    "close_renewal",
    "has_churn",
    "list_renewals",
    "load_renewal",
    "mark_churn",
    "open_renewal",
    "patch_renewal",
    "renewals_for",
    "serialize_renewal",
]
