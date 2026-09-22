"""S4 E7 — approval packages (sequential + parallel review).

Freezes the sow_version + gm_model + policy_version behind a sha256
package_hash and drives them through the state machine described in
build-guide §6.5 / §6.6:

    pending_delivery_hr
      └── delivery.approve + hr.approve
             ▼
    pending_finance_legal
      └── finance.approve + legal.approve
             ▼           ▼
    (floors pass)   (any floor fails / incomplete)
             ▼           ▼
     ready_to_sign   pending_ceo_exception

Reject / request_changes on any pending state routes back to
``SOWDraft`` (owner notified via :func:`app.services.notifications.queue_notification`).

Blueprint §13 forbids backfilling fake approvals — legacy sow_versions
are blocked here via :func:`app.services.legacy_import.assert_not_legacy_for_approval`.

Rule 4 (CLAUDE.md): every row is set-once except ``ApprovalPackage.status``
which is the state-machine field. No PATCH ever hits ``approval``.
Rule 5: every transition writes an ``audit_event`` in the same
transaction as the state change.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.audit import append_audit
from app.models.approval import (
    APPROVAL_DECISIONS,
    APPROVAL_FUNCTIONS,
    Approval,
    ApprovalPackage,
)
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.business_days import add_business_days
from app.services.coverage_gate import check_msa_and_nda_executed
from app.services.legacy_import import assert_not_legacy_for_approval
from app.services.notifications import queue_notification
from app.services.policy import active_policy


# Terminal statuses cannot receive decisions or new voids.
_TERMINAL_STATUSES: frozenset[str] = frozenset({"ready_to_sign", "voided", "rejected"})

# The two "pending review" states + which functions must land in each.
_STATE_TO_FUNCTIONS: dict[str, frozenset[str]] = {
    "pending_delivery_hr": frozenset({"delivery", "hr"}),
    "pending_finance_legal": frozenset({"finance", "legal"}),
}


# ---- errors --------------------------------------------------------------


class ApprovalError(HTTPException):
    """Base error the router turns into a JSON response."""


# ---- helpers -------------------------------------------------------------


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _resource_line_snapshot(line: Any) -> dict[str, Any]:
    return {
        "role": line.role,
        "seniority": line.seniority,
        "location": line.location,
        "person_name": line.person_name,
        "allocation_pct": str(line.allocation_pct),
        "start_date": line.start_date.isoformat(),
        "end_date": line.end_date.isoformat(),
        "billable_hours": str(line.billable_hours),
        "hourly_bill_rate": str(line.hourly_bill_rate),
        "hourly_cost": (str(line.hourly_cost) if line.hourly_cost is not None else None),
    }


def _cost_line_snapshot(line: Any) -> dict[str, Any]:
    legacy = line.basis_value is None and not line.reimbursable and (
        line.basis in (None, "amount") and line.provenance in (None, "manual") and line.source_ref is None
    )
    snapshot = {
        "category": line.category,
        "amount": format(line.amount, ".2f") if legacy else str(line.amount),
        "location": line.location,
        "note": line.note,
    }
    if legacy:
        return snapshot
    return {**snapshot,
        "basis": line.basis or "amount",
        "basis_value": str(line.basis_value) if line.basis_value is not None else None,
        "reimbursable": line.reimbursable or False,
        "provenance": line.provenance or "manual",
        "source_ref": line.source_ref,
    }


def _gm_model_snapshot(model: GmModel) -> dict[str, Any]:
    """Canonical JSON of a gm_model's frozen inputs — feeds the sha256 hash."""

    return {
        "id": str(model.id),
        "engagement_type": model.engagement_type,
        "delivery_pattern": model.delivery_pattern,
        "contingency_pct": (
            str(model.contingency_pct) if model.contingency_pct is not None else None
        ),
        "warranty_days": model.warranty_days,
        "revenue_us": str(model.revenue_us),
        "revenue_india": str(model.revenue_india),
        "resource_lines": [
            _resource_line_snapshot(r) for r in model.resource_lines
        ],
        "cost_lines": [_cost_line_snapshot(c) for c in model.cost_lines],
    }


def package_hash(sow_version: SowVersion, gm_model: GmModel) -> str:
    """sha256 of the pinned sow_version.extracted_fields + gm_model snapshot.

    The hash is what pins the package — a resubmission with the exact same
    inputs collapses to a 409 (see :func:`submit_package`). Any change to
    the frozen inputs produces a fresh hash so a repeat submission after a
    void becomes a distinct row.
    """

    payload = {
        "sow_version_id": str(sow_version.id),
        "extracted_fields": sow_version.extracted_fields or {},
        "gm_model": _gm_model_snapshot(gm_model),
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---- read helpers --------------------------------------------------------


async def _load_gm_model(
    session: AsyncSession, gm_model_id: uuid.UUID
) -> GmModel:
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
        )
        .where(GmModel.id == gm_model_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ApprovalError(status_code=404, detail=f"gm_model {gm_model_id} not found")
    return row


async def _latest_confirmed_sow_version(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> SowVersion | None:
    """Newest ``sow_version`` for the opportunity where ``confirmed_at`` is set."""

    from app.models.sow import Sow

    sow_row = (
        await session.execute(select(Sow).where(Sow.opportunity_id == opportunity_id))
    ).scalar_one_or_none()
    if sow_row is None:
        return None
    stmt = (
        select(SowVersion)
        .where(SowVersion.sow_id == sow_row.id)
        .where(SowVersion.confirmed_at.is_not(None))
        .order_by(SowVersion.uploaded_at.desc(), SowVersion.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _latest_gm_model(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> GmModel | None:
    stmt = (
        select(GmModel)
        .options(
            selectinload(GmModel.resource_lines),
            selectinload(GmModel.cost_lines),
        )
        .where(GmModel.opportunity_id == opportunity_id)
        .order_by(GmModel.created_at.desc(), GmModel.version.desc(), GmModel.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def load_package(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    """Load a package + its approvals. Expires any cached copy so the
    ``approvals`` collection is fresh — the session may have populated it
    before a sibling ``Approval`` row was added, which would otherwise
    give the state machine a stale view (see the ``decide`` flow)."""

    # Drop any cached ORM identity so ``selectinload`` re-queries children.
    cached = await session.get(ApprovalPackage, package_id)
    if cached is not None:
        await session.refresh(cached, attribute_names=["approvals"])
        return cached
    stmt = (
        select(ApprovalPackage)
        .options(selectinload(ApprovalPackage.approvals))
        .where(ApprovalPackage.id == package_id)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise ApprovalError(status_code=404, detail="approval_package not found")
    return row


async def active_package_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> ApprovalPackage | None:
    """Return the newest non-terminal package for an opportunity, if any.

    "Active" = status not in {``voided``, ``rejected``}. ``ready_to_sign``
    still counts because a subsequent scope change should void it too.
    """

    stmt = (
        select(ApprovalPackage)
        .options(selectinload(ApprovalPackage.approvals))
        .where(ApprovalPackage.opportunity_id == opportunity_id)
        .where(~ApprovalPackage.status.in_(("voided", "rejected")))
        .order_by(ApprovalPackage.submitted_at.desc(), ApprovalPackage.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def latest_package_summary(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> dict[str, Any] | None:
    """Compact summary for the deal-detail card. ``None`` when no package
    has ever been submitted for the opportunity."""

    stmt = (
        select(ApprovalPackage)
        .where(ApprovalPackage.opportunity_id == opportunity_id)
        .order_by(ApprovalPackage.submitted_at.desc(), ApprovalPackage.id.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": str(row.id),
        "status": row.status,
        "package_hash": row.package_hash,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "submitted_by": str(row.submitted_by),
    }


# ---- SLA task creation (S7 C) --------------------------------------------


_APPROVAL_SLA_BUSINESS_DAYS: int = 2

# Which roles get an approver task per pending state. Matches
# ``_STATE_TO_FUNCTIONS`` — this map exists so we can find real User rows
# by group membership without extra plumbing.
_STATE_TO_APPROVER_GROUPS: dict[str, tuple[str, ...]] = {
    "pending_delivery_hr": ("Delivery", "HR"),
    "pending_finance_legal": ("Finance", "Legal"),
}


async def _users_in_group(session: AsyncSession, group: str) -> list[User]:
    """Return every User carrying ``group`` in their ``groups`` list.

    SQLite (used in tests) does not support JSONB containment ops, so we
    fetch all rows and filter in Python. The user table is small; this is
    fine for the alert scheduler + submit_package hot path.
    """

    rows = list(
        (await session.execute(select(User))).scalars().all()
    )
    return [u for u in rows if group in (u.groups or [])]


async def _create_approval_tasks(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package: ApprovalPackage,
    state: str,
) -> list[Task]:
    """File ``approval.awaiting`` tasks for the approvers of ``state``.

    One task per user in each approver group. If a group has no user we
    create a single unassigned task carrying the group name in its
    subject — the alert scheduler will escalate to the function head via
    :func:`app.scheduler.resolve_head_for_role`.

    Every task write emits a ``task.created`` audit row (rule 5) in the
    same transaction as the caller's package transition.
    """

    groups = _STATE_TO_APPROVER_GROUPS.get(state, ())
    if not groups:
        return []

    now = datetime.now(UTC)
    due = add_business_days(now.date(), _APPROVAL_SLA_BUSINESS_DAYS)

    created: list[Task] = []
    for group in groups:
        approvers = await _users_in_group(session, group)
        if approvers:
            targets: list[User | None] = list(approvers)
        else:
            # No user in the DB carrying this group — file an unassigned
            # task so the scheduler still surfaces the SLA breach to the
            # function head via routing.
            targets = [None]

        for owner in targets:
            subject = (
                f"{group} approval awaiting on package {package.id} "
                f"(due {due.isoformat()})"
            )
            task = Task(
                id=uuid.uuid4(),
                owner_id=owner.id if owner else None,
                subject=subject,
                due_date=due,
                category="approval.awaiting",
                status="assigned",
            )
            session.add(task)
            await session.flush()
            await append_audit(
                session,
                actor_id=actor_id,
                action="task.created",
                entity="task",
                entity_id=str(task.id),
                before=None,
                after={
                    "owner_id": str(owner.id) if owner else None,
                    "subject": subject,
                    "category": "approval.awaiting",
                    "due_date": due.isoformat(),
                    "related_entity": "approval_package",
                    "related_entity_id": str(package.id),
                    "source": f"approvals.{state}",
                    "approver_group": group,
                },
            )
            created.append(task)

    return created


# ---- submit --------------------------------------------------------------


async def _duplicate_hash_exists(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    hash_value: str,
) -> bool:
    stmt = (
        select(ApprovalPackage.id)
        .where(ApprovalPackage.opportunity_id == opportunity_id)
        .where(ApprovalPackage.package_hash == hash_value)
        .where(~ApprovalPackage.status.in_(("voided", "rejected")))
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def submit_package(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    opportunity_id: uuid.UUID,
) -> ApprovalPackage:
    """Freeze the latest confirmed SOW + latest GM model into an
    :class:`ApprovalPackage` in status ``pending_delivery_hr``.

    Fails with:
      - 404 if the opportunity has no confirmed sow_version yet.
      - 404 if the opportunity has no gm_model yet.
      - 403 if the confirmed sow_version is a legacy row (§13 rollout).
      - 409 if an active package with the same package_hash exists.
    """

    # S5 E9: block new commitments on a churned SOW. Import lazily to
    # avoid an app.services.renewals ↔ app.services.approvals import cycle.
    from app.services.renewals import has_churn as _renewal_has_churn

    if await _renewal_has_churn(session, opportunity_id):
        raise ApprovalError(
            status_code=409,
            detail="SOW churned — new commitments blocked",
        )

    sow_version = await _latest_confirmed_sow_version(session, opportunity_id)
    if sow_version is None:
        raise ApprovalError(
            status_code=404,
            detail="no confirmed sow_version for opportunity",
        )
    # 403 for legacy — deliberate rollout rule (blueprint §13).
    assert_not_legacy_for_approval(sow_version)

    gm_model = await _latest_gm_model(session, opportunity_id)
    if gm_model is None:
        raise ApprovalError(
            status_code=404,
            detail="no gm_model for opportunity — build one before submitting",
        )

    # S7 A: hard-block on missing NDA + MSA. Runs before any write so a
    # 409 leaves the transaction clean (no partial approval_package row).
    opportunity = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opportunity is None:
        raise ApprovalError(status_code=404, detail="opportunity not found")
    await check_msa_and_nda_executed(session, opportunity)

    hash_value = package_hash(sow_version, gm_model)
    if await _duplicate_hash_exists(
        session, opportunity_id=opportunity_id, hash_value=hash_value
    ):
        raise ApprovalError(
            status_code=409,
            detail="an active approval_package with the same content already exists",
        )

    policy = await active_policy(session)

    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opportunity_id,
        sow_version_id=sow_version.id,
        gm_model_id=gm_model.id,
        package_hash=hash_value,
        status="pending_delivery_hr",
        submitted_by=actor_id,
        policy_version_id=policy.id,
    )
    session.add(package)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="package.submitted",
        entity="approval_package",
        entity_id=str(package.id),
        before=None,
        after={
            "opportunity_id": str(opportunity_id),
            "sow_version_id": str(sow_version.id),
            "gm_model_id": str(gm_model.id),
            "package_hash": hash_value,
            "policy_version_id": (str(policy.id) if policy.id else None),
            "status": package.status,
        },
    )

    # S7 C: file "approval awaiting" tasks for the Delivery + HR approver
    # groups with a 2-business-day due date. Runs same transaction so the
    # SLA clock is anchored to the state change (rule 5).
    await _create_approval_tasks(
        session,
        actor_id=actor_id,
        package=package,
        state="pending_delivery_hr",
    )

    await session.commit()
    return await load_package(session, package.id)


# ---- decide --------------------------------------------------------------


def _validate_function(function: str) -> None:
    if function not in APPROVAL_FUNCTIONS:
        raise ApprovalError(
            status_code=422,
            detail=f"function must be one of {list(APPROVAL_FUNCTIONS)}",
        )


def _validate_decision(decision: str) -> None:
    if decision not in APPROVAL_DECISIONS:
        raise ApprovalError(
            status_code=422,
            detail=f"decision must be one of {list(APPROVAL_DECISIONS)}",
        )


def _expected_functions(status_: str) -> frozenset[str]:
    return _STATE_TO_FUNCTIONS.get(status_, frozenset())


async def _load_policy_snapshot(
    session: AsyncSession, package: ApprovalPackage
) -> tuple[Decimal, Decimal]:
    """Return the (us_floor, india_floor) frozen on this package's policy_version.

    ``policy_version_id=None`` falls back to the blueprint sentinel via
    :func:`active_policy`.
    """

    if package.policy_version_id is not None:
        from app.models.policy import PolicyVersion

        row = (
            await session.execute(
                select(PolicyVersion).where(PolicyVersion.id == package.policy_version_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.us_floor, row.india_floor
    policy = await active_policy(session)
    return policy.us_floor, policy.india_floor


async def _floor_check(
    session: AsyncSession, package: ApprovalPackage
) -> dict[str, Any]:
    """Re-run the GM engine against the pinned gm_model + policy_version.

    Returns the ``check_floors`` dict (us_pass / india_pass / requires_ceo /
    failing). ``requires_ceo=True`` means at least one component is under
    floor, or the gm_model is incomplete — either way the package escalates.
    """

    gm_model = await _load_gm_model(session, package.gm_model_id)
    us_floor, india_floor = await _load_policy_snapshot(session, package)

    # Reuse the ratified compute path from services.delivery_model so a
    # persisted model recomputes byte-for-byte the same numbers the Builder
    # showed at save time.
    from app.services.delivery_model import (
        DeliveryModelInputError,
        _extra_inputs_for_model,
        _model_to_payload,
        build_compute_response,
        compute_live,
    )
    from app.services.gm_sandbox import SandboxInputError

    payload = _model_to_payload(gm_model)
    try:
        result = compute_live(payload, extra_inputs=_extra_inputs_for_model(gm_model))
    except (DeliveryModelInputError, SandboxInputError) as exc:
        # A gm_model that no longer computes is treated as incomplete —
        # requires_ceo=True. Numbers stay opaque; the CEO brief formatter
        # will highlight the missing pieces.
        return {
            "us_pass": True,
            "india_pass": True,
            "requires_ceo": True,
            "failing": [],
            "error": str(exc),
        }
    response = build_compute_response(result, us_floor=us_floor, india_floor=india_floor)
    return {
        **response["policy"],
        "gm_model_id": str(gm_model.id), "gm_version": gm_model.version,
        "gm_us": response["gm_us"], "gm_india": response["gm_india"],
        "gm_blended": response["gm_blended"], "complete": response["complete"],
        "finance_summary": response["finance_summary"],
    }


async def _notify_owner_of_rejection(
    session: AsyncSession,
    *,
    package: ApprovalPackage,
    function: str,
    decision: str,
    reason: str | None,
) -> None:
    """Owner (submitter) gets an inbox notification when review turns south."""

    subject = f"Approval package {decision.replace('_', ' ')} by {function}"
    body = (
        f"Package `{package.id}` was `{decision}` by the {function} reviewer."
    )
    if reason:
        body += f"\n\nReason: {reason}"
    await queue_notification(
        session,
        user_id=package.submitted_by,
        category="approval_pending",
        subject=subject,
        body_md=body,
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )


async def _revert_owner_to_sowdraft(
    session: AsyncSession, *, actor_id: uuid.UUID, package: ApprovalPackage
) -> None:
    """After a rejection, drop the opportunity back to SOWDraft so the
    account owner can revise and resubmit."""

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == package.opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        return
    old = opp.governance_status
    opp.governance_status = "SOWDraft"
    await append_audit(
        session,
        actor_id=actor_id,
        action="package.reverted_to_draft",
        entity="opportunity",
        entity_id=str(opp.id),
        before={"governance_status": old},
        after={"governance_status": "SOWDraft", "package_id": str(package.id)},
    )


async def decide(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package_id: uuid.UUID,
    function: str,
    decision: str,
    reason: str | None = None,
) -> ApprovalPackage:
    """Record a decision on ``package_id`` for ``function``.

    * 403 when the actor is the submitter (separation of duties).
    * 409 when the package is already in a terminal state.
    * 409 when the requested function is not one of the expected functions
      for the package's current status.
    * 409 when the actor (or any actor) has already recorded an approval
      for this (package, function) or when the actor already recorded any
      approval on this package.
    """

    _validate_function(function)
    _validate_decision(decision)

    package = await load_package(session, package_id)

    if package.status in _TERMINAL_STATUSES:
        raise ApprovalError(
            status_code=409,
            detail=f"package is {package.status!r}; no more decisions accepted",
        )

    if actor_id == package.submitted_by:
        raise ApprovalError(
            status_code=403,
            detail="separation of duties: submitter cannot approve their own package",
        )

    expected = _expected_functions(package.status)
    if function not in expected:
        raise ApprovalError(
            status_code=409,
            detail=(
                f"function {function!r} not expected in {package.status!r}; "
                f"expected {sorted(expected)}"
            ),
        )

    # Unique-per-(package, function): another approver already covered this.
    dup_function = (
        await session.execute(
            select(Approval.id)
            .where(Approval.package_id == package.id)
            .where(Approval.function == function)
            .limit(1)
        )
    ).scalar_one_or_none()
    if dup_function is not None:
        raise ApprovalError(
            status_code=409,
            detail=f"{function!r} approval already recorded for this package",
        )

    # A user holding two roles may only approve once per package (any function).
    dup_actor = (
        await session.execute(
            select(Approval.id)
            .where(Approval.package_id == package.id)
            .where(Approval.approver_id == actor_id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if dup_actor is not None:
        raise ApprovalError(
            status_code=409,
            detail="you have already recorded an approval on this package",
        )

    row = Approval(
        id=uuid.uuid4(),
        package_id=package.id,
        function=function,
        approver_id=actor_id,
        decision=decision,
        reason=reason,
        decided_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action=f"approval.{function}.{decision}",
        entity="approval",
        entity_id=str(row.id),
        before=None,
        after={
            "package_id": str(package.id),
            "function": function,
            "decision": decision,
            "reason": reason,
        },
    )

    # A reject / request_changes on any pending state drops the whole
    # package back to the account owner (governance_status → SOWDraft) and
    # notifies the submitter. The package itself lands in ``rejected``.
    if decision in ("reject", "request_changes"):
        old_status = package.status
        package.status = "rejected"
        await append_audit(
            session,
            actor_id=actor_id,
            action="package.rejected",
            entity="approval_package",
            entity_id=str(package.id),
            before={"status": old_status},
            after={
                "status": package.status,
                "by_function": function,
                "reason": reason,
            },
        )
        await _revert_owner_to_sowdraft(session, actor_id=actor_id, package=package)
        await _notify_owner_of_rejection(
            session,
            package=package,
            function=function,
            decision=decision,
            reason=reason,
        )
        await session.commit()
        return await load_package(session, package.id)

    # All approvals present for the current state → advance.
    present_functions = {a.function for a in package.approvals}
    present_functions.add(function)  # newly-added row (not refreshed yet)
    if expected.issubset(present_functions):
        await _advance(session, actor_id=actor_id, package=package)

    await session.commit()
    return await load_package(session, package.id)


async def _advance(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package: ApprovalPackage,
) -> None:
    """Move the package to the next state once all required approvals landed."""

    old = package.status
    if old == "pending_delivery_hr":
        package.status = "pending_finance_legal"
        await append_audit(
            session,
            actor_id=actor_id,
            action="package.delivery_hr_passed",
            entity="approval_package",
            entity_id=str(package.id),
            before={"status": old},
            after={"status": package.status},
        )
        # S7 C: fresh SLA timer for the Finance + Legal reviewers.
        await _create_approval_tasks(
            session,
            actor_id=actor_id,
            package=package,
            state="pending_finance_legal",
        )
        return

    if old == "pending_finance_legal":
        floors = await _floor_check(session, package)
        if floors.get("requires_ceo"):
            package.status = "pending_ceo_exception"
            await append_audit(
                session,
                actor_id=actor_id,
                action="package.escalated_to_ceo",
                entity="approval_package",
                entity_id=str(package.id),
                before={"status": old},
                after={
                    "status": package.status,
                    "failing": floors.get("failing", []),
                    "us_pass": floors.get("us_pass", True),
                    "india_pass": floors.get("india_pass", True),
                },
            )
            return
        package.status = "ready_to_sign"
        package.released_at = datetime.now(UTC)
        await append_audit(
            session,
            actor_id=actor_id,
            action="package.ready_to_sign",
            entity="approval_package",
            entity_id=str(package.id),
            before={"status": old},
            after={
                "status": package.status,
                "released_at": package.released_at.isoformat(),
            },
        )
        return


# ---- void-on-change ------------------------------------------------------


async def void_on_change(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    reason: str,
    actor_id: uuid.UUID | None = None,
) -> ApprovalPackage | None:
    """Mark the active package voided when the underlying SOW / GM changes.

    Idempotent: if the opportunity has no active package the call is a
    no-op. On void, the submitter is notified and the transition writes
    ``package.voided`` in the same transaction (rule 5).

    Callers pass ``reason`` describing which underlying version changed —
    the string lands in ``voided_reason`` verbatim so the audit stream
    reads well without any extra join.
    """

    package = await active_package_for(session, opportunity_id)
    if package is None:
        return None
    old = package.status
    package.status = "voided"
    package.voided_at = datetime.now(UTC)
    package.voided_reason = reason
    await append_audit(
        session,
        actor_id=actor_id,
        action="package.voided",
        entity="approval_package",
        entity_id=str(package.id),
        before={"status": old},
        after={
            "status": package.status,
            "voided_reason": reason,
            "voided_at": package.voided_at.isoformat(),
        },
    )
    # Notify the submitter their in-flight package is dead.
    await queue_notification(
        session,
        user_id=package.submitted_by,
        category="approval_pending",
        subject="Approval package voided",
        body_md=(
            f"Package `{package.id}` was voided because {reason}. "
            "Submit a fresh package once the change is settled."
        ),
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )
    await session.commit()
    return package


# ---- manual void (SystemAdmin escape hatch) ------------------------------


async def manual_void(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package_id: uuid.UUID,
    reason: str,
) -> ApprovalPackage:
    package = await load_package(session, package_id)
    if package.status in _TERMINAL_STATUSES:
        raise ApprovalError(
            status_code=409,
            detail=f"package is {package.status!r}; cannot void",
        )
    old = package.status
    package.status = "voided"
    package.voided_at = datetime.now(UTC)
    package.voided_reason = reason
    await append_audit(
        session,
        actor_id=actor_id,
        action="package.voided",
        entity="approval_package",
        entity_id=str(package.id),
        before={"status": old},
        after={
            "status": package.status,
            "voided_reason": reason,
            "manual": True,
        },
    )
    await queue_notification(
        session,
        user_id=package.submitted_by,
        category="approval_pending",
        subject="Approval package voided",
        body_md=(
            f"Package `{package.id}` was manually voided by an admin. "
            f"Reason: {reason}"
        ),
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )
    await session.commit()
    return await load_package(session, package.id)


# ---- list ---------------------------------------------------------------


@dataclass(frozen=True)
class ListFilters:
    status: str | None = None
    opportunity_id: uuid.UUID | None = None
    page: int = 1
    size: int = 25


async def list_packages(
    session: AsyncSession, filters: ListFilters
) -> tuple[list[ApprovalPackage], int]:
    from sqlalchemy import func as sa_func

    stmt = (
        select(ApprovalPackage)
        .options(selectinload(ApprovalPackage.approvals))
        .order_by(ApprovalPackage.submitted_at.desc(), ApprovalPackage.id.desc())
    )
    count_stmt = select(sa_func.count(ApprovalPackage.id))
    if filters.status:
        stmt = stmt.where(ApprovalPackage.status == filters.status)
        count_stmt = count_stmt.where(ApprovalPackage.status == filters.status)
    if filters.opportunity_id is not None:
        stmt = stmt.where(ApprovalPackage.opportunity_id == filters.opportunity_id)
        count_stmt = count_stmt.where(
            ApprovalPackage.opportunity_id == filters.opportunity_id
        )
    offset = max(0, (filters.page - 1) * filters.size)
    stmt = stmt.offset(offset).limit(filters.size)
    rows = list((await session.execute(stmt)).scalars().all())
    total = (await session.execute(count_stmt)).scalar_one()
    return rows, int(total)


# ---- serialisation -------------------------------------------------------


def serialize_approval(row: Approval) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "package_id": str(row.package_id),
        "function": row.function,
        "approver_id": str(row.approver_id),
        "decision": row.decision,
        "reason": row.reason,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def serialize_package(row: ApprovalPackage) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "opportunity_id": str(row.opportunity_id),
        "sow_version_id": str(row.sow_version_id),
        "gm_model_id": str(row.gm_model_id),
        "package_hash": row.package_hash,
        "status": row.status,
        "submitted_by": str(row.submitted_by),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "released_at": row.released_at.isoformat() if row.released_at else None,
        "voided_at": row.voided_at.isoformat() if row.voided_at else None,
        "voided_reason": row.voided_reason,
        "policy_version_id": (
            str(row.policy_version_id) if row.policy_version_id else None
        ),
        "approvals": [serialize_approval(a) for a in row.approvals],
    }


async def serialize_package_with_floors(
    session: AsyncSession, package: ApprovalPackage
) -> dict[str, Any]:
    """Detail response — includes floor pass/fail per component."""

    payload = serialize_package(package)
    payload["floors"] = await _floor_check(session, package)
    from app.services.delivery_model import serialize_cost_line
    model = await _load_gm_model(session, package.gm_model_id)
    payload["cost_lines"] = [serialize_cost_line(line) for line in model.cost_lines]
    return payload


# ---- released transition (S5 E8 hook) -----------------------------------


async def mark_released(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package: ApprovalPackage,
) -> ApprovalPackage:
    """Move a ``ready_to_sign`` package to ``released``.

    Called from :mod:`app.services.signed_sow` once the distribution email
    has been sent + kickoff/billing tasks are filed. Kept tight so the
    caller owns the transaction — this helper flips ``status`` +
    ``released_at`` and audits the change (rule 5). A call on a
    non-``ready_to_sign`` package surfaces as 409.
    """

    if package.status != "ready_to_sign":
        raise ApprovalError(
            status_code=409,
            detail=(
                f"package is {package.status!r}; "
                "only 'ready_to_sign' can be released"
            ),
        )
    old = package.status
    package.status = "released"
    if package.released_at is None:
        package.released_at = datetime.now(UTC)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="package.released",
        entity="approval_package",
        entity_id=str(package.id),
        before={"status": old},
        after={
            "status": package.status,
            "released_at": package.released_at.isoformat(),
        },
    )
    return package


__all__ = [
    "ApprovalError",
    "ListFilters",
    "active_package_for",
    "decide",
    "latest_package_summary",
    "list_packages",
    "load_package",
    "manual_void",
    "mark_released",
    "package_hash",
    "serialize_approval",
    "serialize_package",
    "serialize_package_with_floors",
    "submit_package",
    "void_on_change",
]
