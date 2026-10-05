"""S21-07 remediation: pending contamination vs recorded invalid decisions.

Two explicitly different repairs (T07.05 / T07.06):

* ``repair_pending_assignment`` — a contaminated assignment with NO
  recorded decision is reassigned in place to a legitimate reviewer.
  Package state never advances; the audit keeps the whole history.
* ``quarantine_recorded_decision`` — an Approval row already written by
  an identity outside the package's trusted scope is immutable evidence
  (rule 4). It is never edited or deleted: the package is voided with an
  explicit quarantine reason naming the preserved rows, and the business
  resubmits a fresh package.

Both paths are SystemAdmin-only and write their audit in the same
transaction (rule 5). A released package is refused here: unwinding a
released contract is an OP-03 class recovery with its own review.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.approval import Approval
from app.models.approval_routing import ApprovalAssignment
from app.models.task import Task
from app.models.user import User
from app.services.approvals import load_package
from app.services.notifications import queue_notification
from app.services.test_fixtures import allowed_for_package


class RemediationError(HTTPException):
    pass


def _require_admin(actor: AuthUser) -> None:
    if "SystemAdmin" not in actor.groups:
        raise RemediationError(403, "approval remediation requires SystemAdmin")


async def _recorded(session: AsyncSession, package_id: uuid.UUID, function: str) -> list[Approval]:
    return list(
        (
            await session.scalars(
                select(Approval).where(
                    Approval.package_id == package_id, Approval.function == function
                )
            )
        ).all()
    )


async def repair_pending_assignment(
    session: AsyncSession,
    *,
    actor: AuthUser,
    package_id: uuid.UUID,
    function: str,
    new_approver_id: uuid.UUID,
    reason: str,
) -> dict[str, Any]:
    _require_admin(actor)
    if not reason.strip():
        raise RemediationError(422, "a written remediation reason is required")
    package = await load_package(session, package_id)
    if package.status in ("voided", "rejected", "released"):
        raise RemediationError(409, f"package is {package.status!r}; nothing is pending")
    assignment = await session.get(ApprovalAssignment, (package_id, function))
    if assignment is None:
        raise RemediationError(404, "no assignment exists for this function")
    if await _recorded(session, package_id, function):
        raise RemediationError(
            409,
            "a decision is already recorded for this function; recorded "
            "decisions are handled separately via quarantine",
        )
    replacement = await session.get(User, new_approver_id)
    if replacement is None or not await allowed_for_package(session, new_approver_id, package):
        raise RemediationError(422, "replacement approver is outside the package's trusted scope")

    before = {"approver_id": str(assignment.approver_id) if assignment.approver_id else None,
              "task_id": str(assignment.task_id) if assignment.task_id else None}
    if assignment.task_id is not None:
        stale_task = await session.get(Task, assignment.task_id)
        if stale_task is not None and stale_task.status in ("assigned", "in_progress", "snoozed"):
            stale_task.status = "reassigned"
    task = Task(
        id=uuid.uuid4(),
        owner_id=new_approver_id,
        subject=f"Approval — {function} (reassigned after contamination repair)",
        category="approval",
        due_date=assignment.due_date,
        status="assigned",
    )
    session.add(task)
    assignment.approver_id = new_approver_id
    assignment.task_id = task.id
    await session.flush()
    await append_audit(
        session,
        actor_id=actor.id,
        action="approval.assignment_repaired",
        entity="approval_package",
        entity_id=str(package.id),
        before=before,
        after={"function": function, "approver_id": str(new_approver_id),
               "task_id": str(task.id), "reason": reason.strip()},
    )
    await queue_notification(
        session,
        user_id=new_approver_id,
        category="approval_pending",
        subject=f"Approval reassigned to you — {function}",
        body_md=f"An admin repaired a contaminated assignment. Reason: {reason.strip()}",
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )
    await session.commit()
    return {"package_id": str(package.id), "function": function,
            "approver_id": str(new_approver_id), "task_id": str(task.id)}


async def quarantine_recorded_decision(
    session: AsyncSession,
    *,
    actor: AuthUser,
    package_id: uuid.UUID,
    function: str,
    reason: str,
) -> dict[str, Any]:
    _require_admin(actor)
    if not reason.strip():
        raise RemediationError(422, "a written quarantine reason is required")
    package = await load_package(session, package_id)
    if package.status == "released":
        raise RemediationError(
            409,
            "package is released; unwinding a released contract is an "
            "OP-03 recovery and needs its own reviewed procedure",
        )
    if package.status == "voided":
        raise RemediationError(409, "package is already voided")
    recorded = await _recorded(session, package_id, function)
    if not recorded:
        raise RemediationError(404, "no recorded decision exists for this function")
    invalid = [
        row for row in recorded
        if not await allowed_for_package(session, row.approver_id, package)
    ]
    if not invalid:
        raise RemediationError(
            409,
            "every recorded decision for this function is inside the "
            "package's trusted scope; nothing to quarantine",
        )

    old_status = package.status
    package.status = "voided"
    package.voided_at = datetime.now(UTC)
    package.voided_reason = (
        f"contaminated decision quarantined ({function}): {reason.strip()}"
    )
    from app.services.approval_workflow import close_tasks

    await close_tasks(session, package.id, actor.id)
    quarantined = [str(row.id) for row in invalid]
    await append_audit(
        session,
        actor_id=actor.id,
        action="approval.decision_quarantined",
        entity="approval_package",
        entity_id=str(package.id),
        before={"status": old_status},
        after={"status": "voided", "function": function,
               "quarantined_approval_ids": quarantined,
               "approval_rows_preserved": True, "reason": reason.strip()},
    )
    await queue_notification(
        session,
        user_id=package.submitted_by,
        category="approval_pending",
        subject="Approval package quarantined",
        body_md=(
            f"Package `{package.id}` was quarantined because a recorded "
            f"{function} decision came from outside its trusted scope. "
            "The recorded rows are preserved as evidence; submit a fresh "
            f"package. Reason: {reason.strip()}"
        ),
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )
    await session.commit()
    return {"package_id": str(package.id), "status": "voided",
            "quarantined_approval_ids": quarantined}
