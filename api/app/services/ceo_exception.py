"""S4 E7 — CEO exception service (Agent V, wave 3).

Owns the end-to-end lifecycle of one :class:`CeoException` row:

1. :func:`draft_for_package` — called by Agent U's approvals service
   when a package enters ``pending_ceo_exception``. Builds the brief
   JSON via Bedrock (rationale left null), inserts the row, audits
   ``ceo_exception.drafted``.
2. :func:`set_rationale` — the account owner writes their business
   rationale. May optionally call Bedrock to tidy the wording; the raw
   text is always stored verbatim next to the tidied text so audit sees
   the human intent. 403 for anyone but the owner.
3. :func:`decide` — CEO or active :class:`CeoDelegate` records the
   final decision. On ``approve`` the package transitions to
   ``ready_to_sign``; on ``reject`` / ``return_for_changes`` the
   package goes back to ``SOWDraft`` and the account owner is notified.

Helpers:

- :func:`active_delegate` — the current active :class:`CeoDelegate`,
  if any. Used by the role check + surfaced on the read endpoint.
- :func:`load_exception` — read helper for the router.
- :func:`list_exceptions` — CEO/delegate/SystemAdmin inbox.
- :func:`grant_delegate` — SystemAdmin creates a time-bound delegation.

Rule 4: rows are set-once conceptually; the rationale + decision
columns are single-shot writes (guarded here — cannot overwrite a
decision, cannot rewrite a rationale after a decision). Rule 5: every
transition writes an ``audit_event`` in the same transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_ceo_brief import (
    BriefDrafter,
    draft_brief,
    tidy_rationale,
)
from app.models.approval import ApprovalPackage
from app.models.ceo_exception import CeoDelegate, CeoException
from app.models.opportunity import Opportunity
from app.services.notifications import queue_notification


# Decision alphabet — the router + service both re-validate to be safe.
DECISIONS: tuple[str, ...] = ("approve", "reject", "return_for_changes")

# Package status alphabet Agent U owns. Hard-coded here so the CEO
# service can operate even when the imports are in flux; a mismatch
# with `app.models.approval.PACKAGE_STATUSES` will trip the CHECK
# constraint on the DB, which is a real fail signal.
PKG_PENDING_CEO = "pending_ceo_exception"
PKG_READY_TO_SIGN = "ready_to_sign"
PKG_REJECTED = "rejected"


# --- read helpers ----------------------------------------------------------


async def load_exception(
    session: AsyncSession, exception_id: uuid.UUID
) -> CeoException:
    row = (
        await session.execute(
            select(CeoException).where(CeoException.id == exception_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="ceo exception not found")
    return row


async def load_exception_for_package(
    session: AsyncSession, package_id: uuid.UUID
) -> CeoException | None:
    """Return the (single) exception for a package, if drafted."""

    return (
        await session.execute(
            select(CeoException).where(CeoException.package_id == package_id)
        )
    ).scalar_one_or_none()


async def _load_package(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    row = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="approval package not found")
    return row


async def _load_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    row = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return row


async def list_exceptions(
    session: AsyncSession, *, pending_only: bool
) -> list[CeoException]:
    stmt = select(CeoException).order_by(CeoException.drafted_at.desc())
    if pending_only:
        stmt = stmt.where(CeoException.decision.is_(None))
    return list((await session.execute(stmt)).scalars().all())


# --- delegate helpers -------------------------------------------------------


async def active_delegate(
    session: AsyncSession, *, at: date | None = None
) -> CeoDelegate | None:
    """Return an active delegate at ``at`` (defaults to today), if any.

    Overlapping delegates are permitted; when more than one is active
    the most-recently-granted wins. That keeps the CEO's "override my
    old delegate" ergonomic without requiring a manual revocation.
    """

    check_date = at or datetime.now(UTC).date()
    stmt = (
        select(CeoDelegate)
        .where(CeoDelegate.effective_from <= check_date)
        .where(CeoDelegate.expiry >= check_date)
        .order_by(CeoDelegate.granted_at.desc())
    )
    return (await session.execute(stmt)).scalars().first()


async def grant_delegate(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    delegate_id: uuid.UUID,
    effective_from: date,
    expiry: date,
) -> CeoDelegate:
    """SystemAdmin creates a new time-bound delegation.

    The row is append-only — the audit trail is the historical record.
    A new grant with a wider window supersedes the older one at read
    time via :func:`active_delegate`.
    """

    if expiry < effective_from:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expiry must be on or after effective_from",
        )
    row = CeoDelegate(
        id=uuid.uuid4(),
        delegate_id=delegate_id,
        effective_from=effective_from,
        expiry=expiry,
        granted_by=actor_id,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="ceo_delegate.granted",
        entity="ceo_delegate",
        entity_id=str(row.id),
        before=None,
        after={
            "delegate_id": str(delegate_id),
            "effective_from": effective_from.isoformat(),
            "expiry": expiry.isoformat(),
            "granted_by": str(actor_id),
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


async def can_decide(
    session: AsyncSession, *, actor_id: uuid.UUID, actor_groups: tuple[str, ...]
) -> bool:
    """True if the caller is the CEO, or an active CEO delegate today."""

    if "CEO" in actor_groups:
        return True
    del_row = await active_delegate(session)
    return del_row is not None and del_row.delegate_id == actor_id


# --- draft -----------------------------------------------------------------


async def draft_for_package(
    session: AsyncSession,
    package_id: uuid.UUID,
    *,
    brief_inputs: dict[str, Any] | None = None,
    adapter: BriefDrafter | None = None,
) -> CeoException:
    """Draft the CEO brief for a package that failed policy.

    Called by Agent U's approval submission path when a package enters
    ``pending_ceo_exception``. Idempotent: a second call returns the
    existing row rather than drafting again (rule 4 — one exception
    per package).

    ``brief_inputs`` is the deterministic payload Agent U's caller
    assembled from the SOW, GM model and policy. The Bedrock adapter
    only arranges labels; every number lives in the input dict.
    """

    pkg = await _load_package(session, package_id)
    if pkg.status != PKG_PENDING_CEO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "cannot draft CEO exception for a package in status "
                f"{pkg.status!r}"
            ),
        )

    existing = await load_exception_for_package(session, package_id)
    if existing is not None:
        return existing

    brief = draft_brief(brief_inputs or {}, adapter=adapter)
    row = CeoException(
        id=uuid.uuid4(),
        package_id=package_id,
        brief_json=brief,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=pkg.submitted_by,
        action="ceo_exception.drafted",
        entity="ceo_exception",
        entity_id=str(row.id),
        before=None,
        after={
            "package_id": str(package_id),
            "model": brief.get("model"),
            "prompt_version": brief.get("prompt_version"),
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


# --- rationale --------------------------------------------------------------


async def set_rationale(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    exception_id: uuid.UUID,
    rationale_text: str,
    tidy: bool = False,
    adapter: BriefDrafter | None = None,
) -> CeoException:
    """Owner writes the business rationale. 403 for anyone else.

    ``rationale_text`` is stored verbatim. If ``tidy`` is set, Bedrock
    is asked to clean up the wording; the cleaned copy lands in
    ``rationale_tidied_text`` alongside — the raw text is never lost
    (blueprint §6.6: AI can tidy, not invent).

    Cannot be called after a decision has been recorded.
    """

    row = await load_exception(session, exception_id)
    if row.decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="rationale cannot change after a decision is recorded",
        )
    pkg = await _load_package(session, row.package_id)
    opp = await _load_opportunity(session, pkg.opportunity_id)
    if opp.owner_id is None or opp.owner_id != actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only the opportunity owner may write the rationale",
        )
    text = (rationale_text or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rationale_text is required",
        )

    before = {
        "rationale_text": row.rationale_text,
        "rationale_tidied_text": row.rationale_tidied_text,
    }
    row.rationale_text = text
    if tidy:
        tidied = tidy_rationale(text, adapter=adapter)
        row.rationale_tidied_text = tidied.text
    else:
        row.rationale_tidied_text = None
    row.rationale_set_by = actor_id
    row.rationale_set_at = datetime.now(UTC)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="ceo_exception.rationale_set",
        entity="ceo_exception",
        entity_id=str(row.id),
        before=before,
        after={
            "rationale_text": row.rationale_text,
            "rationale_tidied_text": row.rationale_tidied_text,
            "tidy_requested": bool(tidy),
        },
    )
    await session.commit()
    await session.refresh(row)
    return row


# --- decision ---------------------------------------------------------------


async def decide(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor_groups: tuple[str, ...],
    exception_id: uuid.UUID,
    decision: str,
    conditions_text: str | None = None,
    valid_until: date | None = None,
) -> CeoException:
    """CEO / active delegate records the final decision.

    - ``approve`` requires ``rationale_text``; transitions the package
      to ``ready_to_sign`` and audits ``ceo_exception.approved``.
    - ``reject`` / ``return_for_changes`` transition the package back
      to ``SOWDraft`` (blueprint §6.6 — the CEO returns the deal to
      the owner) and audit ``ceo_exception.rejected`` /
      ``ceo_exception.returned``. Notify the account owner via the
      standard notification outbox.

    Cannot be called twice — decisions are set-once (rule 4).
    """

    if decision not in DECISIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"decision must be one of {list(DECISIONS)}",
        )
    if not await can_decide(
        session, actor_id=actor_id, actor_groups=actor_groups
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only CEO or an active CEO delegate may decide",
        )

    row = await load_exception(session, exception_id)
    if row.decision is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="decision already recorded",
        )
    if decision == "approve" and not (row.rationale_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rationale_text required before approve",
        )

    pkg = await _load_package(session, row.package_id)
    if pkg.status != PKG_PENDING_CEO:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "package is not awaiting CEO exception "
                f"(current status: {pkg.status!r})"
            ),
        )
    opp = await _load_opportunity(session, pkg.opportunity_id)

    now = datetime.now(UTC)
    row.decision = decision
    row.decided_by = actor_id
    row.decided_at = now
    if decision == "approve":
        row.conditions_text = (conditions_text or None) if (conditions_text or "").strip() else None
        row.valid_until = valid_until
    else:
        # Conditions / valid_until only apply to approvals — clear if the
        # caller sent them so the row stays consistent with the decision.
        row.conditions_text = None
        row.valid_until = None
    await session.flush()

    pkg_before = {"status": pkg.status}
    action: str
    if decision == "approve":
        pkg.status = PKG_READY_TO_SIGN
        pkg.released_at = now
        action = "ceo_exception.approved"
    elif decision == "reject":
        pkg.status = PKG_REJECTED
        opp.governance_status = "SOWDraft"
        action = "ceo_exception.rejected"
    else:  # return_for_changes
        # Blueprint §6.6: returned packages go back to SOWDraft. The
        # package itself is marked rejected so a fresh submission is
        # required (approvals never reused across packages).
        pkg.status = PKG_REJECTED
        opp.governance_status = "SOWDraft"
        action = "ceo_exception.returned"
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action=action,
        entity="ceo_exception",
        entity_id=str(row.id),
        before=pkg_before,
        after={
            "package_id": str(pkg.id),
            "package_status": pkg.status,
            "decision": decision,
            "conditions_text": row.conditions_text,
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            "decided_by": str(actor_id),
        },
    )

    if decision != "approve" and opp.owner_id is not None:
        subject = (
            "CEO returned your deal for changes"
            if decision == "return_for_changes"
            else "CEO rejected your approval package"
        )
        await queue_notification(
            session,
            user_id=opp.owner_id,
            category="approval_pending",
            subject=subject,
            body_md=(
                f"Package `{pkg.id}` was **{decision}**. "
                "Open the deal to revise the SOW and resubmit."
            ),
            related_entity="approval_package",
            related_entity_id=str(pkg.id),
        )

    await session.commit()
    await session.refresh(row)
    return row


__all__ = [
    "DECISIONS",
    "PKG_PENDING_CEO",
    "PKG_READY_TO_SIGN",
    "PKG_REJECTED",
    "active_delegate",
    "can_decide",
    "decide",
    "draft_for_package",
    "grant_delegate",
    "list_exceptions",
    "load_exception",
    "load_exception_for_package",
    "set_rationale",
]
