"""Assigned review tasks and the shared pending-with projection."""

import uuid
import os
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models.approval_routing import ApprovalAssignment, ApprovalConditionEvidence
from app.models.ceo_exception import CeoException
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.approval_routing import groups, person, fail, LABELS
from app.audit import append_audit
from app.services.notifications import queue_notification

ACTIVE = {
    "pending_delivery_hr": ("delivery", "hr"),
    "pending_finance_legal": ("finance", "legal"),
    "pending_ceo_exception": ("executive",),
}


def review_url(opportunity_id):
    default = (
        "http://localhost:5173"
        if os.environ.get("DEALGATE_ENV", "local") == "local"
        else "https://dealgate.smartek21.com"
    )
    return f"{os.environ.get('DEALGATE_PUBLIC_URL', default).rstrip('/')}/sows/{opportunity_id}/approvals"


async def assignments_for(session, package_id):
    return list(
        (
            await session.scalars(
                select(ApprovalAssignment).where(ApprovalAssignment.package_id == package_id)
            )
        ).all()
    )


async def create_tasks(session, *, actor_id, package, state):
    assignments = await assignments_for(session, package.id)
    if not assignments:
        return None  # Pre-S14b package: retain the legacy task path.
    admins = [
        u
        for u in (await session.scalars(select(User).order_by(User.email))).all()
        if "SystemAdmin" in (u.groups or [])
    ]
    tasks = []
    for a in assignments:
        if a.task_id or (a.approver_id and a.function not in ACTIVE.get(state, ())):
            continue
        if a.use_sla:
            from app.services.business_days import add_business_days

            due = add_business_days(datetime.now(UTC).date(), 2)
            if due != a.due_date:
                await append_audit(
                    session,
                    actor_id=actor_id,
                    action="approval.sla_started",
                    entity="approval_package",
                    entity_id=str(package.id),
                    before={"function": a.function, "due_date": str(a.due_date)},
                    after={"function": a.function, "due_date": str(due)},
                )
                a.due_date = due
        owner_id = a.approver_id or (admins[0].id if admins else None)
        subject = (
            f"{LABELS[a.function]} review"
            if a.approver_id
            else f"Routing blocked: configure {LABELS[a.function]} group (SystemAdmin)"
        )
        task = Task(
            id=uuid.uuid4(),
            owner_id=owner_id,
            subject=subject,
            due_date=a.due_date,
            category="approval.awaiting" if a.approver_id else "approval.routing",
            status="assigned",
        )
        session.add(task)
        await session.flush()
        a.task_id = task.id
        await append_audit(
            session,
            actor_id=actor_id,
            action="task.created",
            entity="task",
            entity_id=str(task.id),
            before=None,
            after={
                "owner_id": str(owner_id) if owner_id else None,
                "subject": subject,
                "category": task.category,
                "due_date": str(task.due_date),
                "related_entity": "approval_package",
                "related_entity_id": str(package.id),
                "source": f"approvals.{state}",
                "approver_group": LABELS[a.function],
            },
        )
        if owner_id:
            await queue_notification(
                session,
                user_id=owner_id,
                category="approval_pending",
                subject=subject,
                body_md=f"{subject}. Due {a.due_date}. [Open review]({review_url(package.opportunity_id)}).",
                related_entity="approval_package",
                related_entity_id=str(package.id),
            )
        tasks.append(task)
    return tasks


async def finish_task(session, assignment, actor_id, status):
    task = await session.get(Task, assignment.task_id) if assignment.task_id else None
    if not task or task.status in ("done", "cancelled"):
        return
    before = task.status
    task.status = status
    task.completed_at, task.completed_by = datetime.now(UTC), actor_id
    await append_audit(
        session,
        actor_id=actor_id,
        action="task.transitioned",
        entity="task",
        entity_id=str(task.id),
        before={"status": before},
        after={"status": status, "source": "approval.decision"},
    )


async def close_tasks(session, package_id, actor_id):
    for assignment in await assignments_for(session, package_id):
        await finish_task(session, assignment, actor_id, "cancelled")


async def authorize_decision(session, package, actor_id, function, reason):
    roster = next(g for g in await groups(session) if g["function"] == function)
    if str(actor_id) not in {m["id"] for m in roster["members"]}:
        fail(f"Only a {LABELS[function]} group member may decide", 403)
    assignment = await session.get(ApprovalAssignment, (package.id, function))
    if assignment:
        if assignment.approver_id != actor_id:
            fail("Only the assigned reviewer may decide this function", 403)
        if not (reason or "").strip():
            fail("A reason is required for every review decision")
    return assignment


async def review_projection(session, package, actor_id=None):
    from app.services.approvals import serialize_package

    data = serialize_package(package)
    users = {str(u.id): person(u) for u in (await session.scalars(select(User))).all()}
    sow = await session.get(SowVersion, package.sow_version_id)
    gm = await session.get(GmModel, package.gm_model_id)
    opp = await session.get(Opportunity, package.opportunity_id)
    data.update(
        sow_version=sow.version_no if sow else None,
        gm_version=gm.version if gm else None,
        submitted_by_name=users.get(str(package.submitted_by), {}).get("name", "Name unavailable"),
        owner=users.get(str(opp.owner_id)) if opp else None,
    )
    for approval in data["approvals"]:
        approval["approver_name"] = users.get(approval["approver_id"], {}).get(
            "name", "Name unavailable"
        )
    roster = {g["function"]: g for g in await groups(session)}
    decisions = {a.function for a in package.approvals}
    actor_used = any(a.approver_id == actor_id for a in package.approvals)
    data["assignments"] = []
    for a in await assignments_for(session, package.id):
        member = str(a.approver_id) in {m["id"] for m in roster[a.function]["members"]}
        active = a.function in ACTIVE.get(package.status, ()) and a.function not in decisions
        blocked = a.function not in decisions and (not a.approver_id or not member)
        data["assignments"].append(
            {
                "function": a.function,
                "approver_id": str(a.approver_id) if a.approver_id else None,
                "approver_name": users.get(str(a.approver_id), {}).get("name", "SystemAdmin"),
                "due_date": str(a.due_date),
                "active": active,
                "blocked": blocked,
                "can_decide": active
                and member
                and actor_id == a.approver_id
                and actor_id != package.submitted_by
                and not actor_used,
            }
        )
    data["pending_with"] = [
        a["approver_name"] for a in data["assignments"] if a["active"] and not a["blocked"]
    ]
    data["routing_blockers"] = [
        f"{LABELS[a['function']]}: no eligible reviewer. Owner: SystemAdmin"
        for a in data["assignments"]
        if a["blocked"] and package.status in ACTIVE
    ]
    exception = await session.scalar(
        select(CeoException).where(CeoException.package_id == package.id)
    )
    evidence = await session.get(ApprovalConditionEvidence, package.id)
    executive = next((a for a in data["assignments"] if a["function"] == "executive"), None)
    data["assignments"] = [a for a in data["assignments"] if a["function"] != "executive"]
    data["ceo_pending_with"] = executive["approver_name"] if executive else None
    data["ceo_exception"] = (
        None
        if not exception
        else {
            "id": str(exception.id),
            "decision": exception.decision,
            "decided_at": exception.decided_at.isoformat() if exception.decided_at else None,
            "decided_by_name": users.get(str(exception.decided_by), {}).get("name"),
            "conditions_text": exception.conditions_text,
            "rationale_text": exception.rationale_text,
            "valid_until": str(exception.valid_until) if exception.valid_until else None,
            "evidence": evidence.evidence if evidence else None,
            "conditions_unmet": bool(exception.conditions_text and not evidence),
            "expired": bool(exception.valid_until and exception.valid_until < date.today()),
        }
    )
    return data


async def require_signature_eligibility(session, package):
    from app.services.coverage_gate import check_msa_and_nda_executed

    opp = await session.get(Opportunity, package.opportunity_id)
    if not opp:
        fail("Opportunity not found", 404)
    await check_msa_and_nda_executed(session, opp)
    exception = await session.scalar(
        select(CeoException).where(CeoException.package_id == package.id)
    )
    if exception and exception.decision == "approve":
        if exception.valid_until and exception.valid_until < date.today():
            fail("CEO exception has expired; a new review is required", 409)
        if exception.conditions_text and not await session.get(
            ApprovalConditionEvidence, package.id
        ):
            fail(
                f"CEO conditions need owner evidence before signature: {exception.conditions_text}",
                409,
            )
