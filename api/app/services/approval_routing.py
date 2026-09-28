"""Group configuration and frozen reviewer selection for S14b."""

import uuid
from datetime import date

from sqlalchemy import select

from app.models.approval_routing import ApprovalAssignment, ApprovalGroup
from app.models.ceo_exception import CeoDelegate
from app.models.function_owner import FunctionOwner
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.audit import append_audit
from app.services.user_identity import display_user_name

FUNCTIONS = ("delivery", "hr", "finance", "legal")
LABELS = {
    "delivery": "Delivery",
    "hr": "HR",
    "finance": "Finance",
    "legal": "Legal",
    "executive": "Executive",
}


def fail(message, status=422):
    from app.services.approvals import ApprovalError

    raise ApprovalError(status_code=status, detail=message)


def person(user):
    return {
        "id": str(user.id),
        "name": display_user_name(user.name, user.email),
        "email": user.email,
    }


async def groups(session):
    users = list((await session.scalars(select(User).order_by(User.email))).all())
    configured = {r.function: r for r in (await session.scalars(select(ApprovalGroup))).all()}
    owners = list(
        (
            await session.scalars(
                select(FunctionOwner)
                .where(FunctionOwner.business_unit.is_(None))
                .order_by(FunctionOwner.created_at.desc())
            )
        ).all()
    )
    from app.services.ceo_exception import active_delegate

    delegate = await active_delegate(session)
    grants = list(
        (await session.scalars(select(CeoDelegate).order_by(CeoDelegate.granted_at.desc()))).all()
    )
    result = []
    for fn, label in LABELS.items():
        row = configured.get(fn)
        if fn == "executive":
            members = [
                u
                for u in users
                if "CEO" in (u.groups or []) or (delegate and u.id == delegate.delegate_id)
            ]
            default = next((str(u.id) for u in members if "CEO" in (u.groups or [])), None)
        else:
            # Until explicitly configured, import existing role membership virtually.
            # A saved empty roster is authoritative, never repopulated at login.
            members = (
                [u for u in users if str(u.id) in row.member_ids]
                if row
                else [u for u in users if label in (u.groups or [])]
            )
            ids = {str(u.id) for u in members}
            default = (
                str(row.default_approver_id)
                if row and row.default_approver_id
                else next(
                    (
                        str(o.user_id)
                        for o in owners
                        if o.function == fn and o.is_default and str(o.user_id) in ids
                    ),
                    None,
                )
            )
            default = default or (str(members[0].id) if members else None)
        result.append(
            {
                "function": fn,
                "label": label,
                "members": [person(u) for u in members],
                "default_approver_id": default,
                "backup_ids": row.backup_ids if row else [],
                "delegations": [
                    {
                        "delegate_id": str(g.delegate_id),
                        "effective_from": str(g.effective_from),
                        "expiry": str(g.expiry),
                    }
                    for g in grants
                ]
                if fn == "executive"
                else [],
            }
        )
    return result


async def save_group(session, *, actor_id, function, member_ids, backup_ids, default_approver_id):
    if function not in FUNCTIONS:
        fail(
            "Executive membership is controlled by CEO identity and recorded time-bound delegation"
        )
    members = {str(uuid.UUID(str(i))) for i in member_ids}
    backups = {str(uuid.UUID(str(i))) for i in backup_ids}
    default = str(default_approver_id) if default_approver_id else None
    known = {str(i) for i in (await session.scalars(select(User.id))).all()}
    if not members <= known or not backups <= members or (default and default not in members):
        fail("Default and backup approvers must be members of the group and known users")
    if members and not default:
        fail("Choose one default approver for a nonempty group")
    row = await session.get(ApprovalGroup, function)
    before = (
        {
            "member_ids": row.member_ids,
            "backup_ids": row.backup_ids,
            "default_approver_id": str(row.default_approver_id)
            if row.default_approver_id
            else None,
        }
        if row
        else None
    )
    if row is None:
        row = ApprovalGroup(function=function)
        session.add(row)
    row.member_ids, row.backup_ids = sorted(members), sorted(backups)
    row.default_approver_id = uuid.UUID(default) if default else None
    await append_audit(
        session,
        actor_id=actor_id,
        action="approval_group.updated",
        entity="approval_group",
        entity_id=function,
        before=before,
        after={
            "member_ids": row.member_ids,
            "backup_ids": row.backup_ids,
            "default_approver_id": default,
        },
    )
    await session.commit()
    return next(g for g in await groups(session) if g["function"] == function)


async def submission_plan(
    session,
    *,
    opportunity_id,
    actor_id,
    choices=None,
    expected_sow_version_id=None,
    expected_gm_model_id=None,
):
    from app.models.approval import ApprovalPackage
    from app.services.approvals import (
        _latest_gm_model,
        _floor_check,
        assert_not_legacy_for_approval,
    )
    from app.services.policy import active_policy
    from app.services.business_days import add_business_days

    sow = await session.scalar(
        select(SowVersion)
        .join(Sow, Sow.id == SowVersion.sow_id)
        .where(
            Sow.opportunity_id == opportunity_id,
            SowVersion.discarded_at.is_(None),
            SowVersion.superseded_by.is_(None),
        )
        .order_by(SowVersion.version_no.desc(), SowVersion.uploaded_at.desc())
        .limit(1)
    )
    if not sow or not sow.confirmed_at:
        fail("Complete scope before submitting for review", 409)
    assert_not_legacy_for_approval(sow)
    gm = await _latest_gm_model(session, opportunity_id)
    if not gm:
        fail("Complete Staffing & GM before submitting for review", 409)
    if (expected_sow_version_id and sow.id != expected_sow_version_id) or (
        expected_gm_model_id and gm.id != expected_gm_model_id
    ):
        fail("SOW or GM version changed; reopen the submission dialog", 409)
    if gm.sow_version_id and gm.sow_version_id != sow.id:
        fail("GM is linked to an older SOW version; rebuild Staffing & GM", 409)
    policy = await active_policy(session)
    preview = ApprovalPackage(gm_model_id=gm.id, policy_version_id=policy.id)
    floors = await _floor_check(session, preview)
    if not floors.get("complete"):
        fail("GM incomplete: validate staffing costs and revenue before review", 409)
    choices = choices or {}
    if set(choices) - set(FUNCTIONS):
        fail("Unknown approval function")
    rows, used = [], set()
    for group in await groups(session):
        fn = group["function"]
        eligible = [m for m in group["members"] if m["id"] != str(actor_id)]
        if fn == "executive":
            executive = {**group, "members": eligible}
            executive["approver_id"] = next(
                (m["id"] for m in eligible if m["id"] == group["default_approver_id"]),
                eligible[0]["id"] if eligible else None,
            )
            continue
        choice = choices.get(fn, {})
        selected = (
            choice.get("approver_id")
            if "approver_id" in choice
            else next(
                (
                    m["id"]
                    for m in eligible
                    if m["id"] == group["default_approver_id"] and m["id"] not in used
                ),
                next((m["id"] for m in eligible if m["id"] not in used), None),
            )
        )
        if selected and str(selected) not in {m["id"] for m in eligible}:
            fail(f"{LABELS[fn]} approver must be a group member other than the submitter")
        if selected and str(selected) in used:
            fail("Separation of duties: select a different person for each function")
        if selected:
            used.add(str(selected))
        due = choice.get("due_date") or add_business_days(date.today(), 2)
        due = date.fromisoformat(due) if isinstance(due, str) else due
        if due < date.today():
            fail("Approval due date cannot be in the past")
        rows.append(
            {
                **group,
                "members": eligible,
                "approver_id": str(selected) if selected else None,
                "due_date": due.isoformat(),
                "use_sla": choice.get("use_sla", True),
                "blocker": None
                if selected
                else f"{LABELS[fn]} has no eligible reviewer. Owner: SystemAdmin.",
            }
        )
    return {
        "sow_version_id": str(sow.id),
        "sow_version": sow.version_no,
        "gm_model_id": str(gm.id),
        "gm_version": gm.version,
        "rows": rows,
        "executive": executive if floors.get("requires_ceo") else None,
        "floors": floors,
        "submitter_excluded": True,
    }


async def route_missing(session, *, actor_id, package_id):
    from app.services.approvals import load_package, _create_approval_tasks
    from app.services.approval_workflow import finish_task

    package = await load_package(session, package_id)
    if package.status not in (
        "pending_delivery_hr",
        "pending_finance_legal",
        "pending_ceo_exception",
    ):
        fail("Package is no longer awaiting review", 409)
    roster = {g["function"]: g for g in await groups(session)}
    assignments = list(
        (
            await session.scalars(
                select(ApprovalAssignment).where(ApprovalAssignment.package_id == package_id)
            )
        ).all()
    )
    decided = {a.function for a in package.approvals}
    used = {
        str(a.approver_id)
        for a in assignments
        if a.approver_id
        and (
            a.function in decided
            or str(a.approver_id) in {m["id"] for m in roster[a.function]["members"]}
        )
    }
    for assignment in assignments:
        group = roster[assignment.function]
        if assignment.function in decided or (
            assignment.approver_id
            and str(assignment.approver_id) in {m["id"] for m in group["members"]}
        ):
            continue
        eligible = [
            m
            for m in group["members"]
            if m["id"] != str(package.submitted_by)
            and (assignment.function == "executive" or m["id"] not in used)
        ]
        target = next(
            (m for m in eligible if m["id"] == group["default_approver_id"]),
            eligible[0] if eligible else None,
        )
        if not target:
            continue
        before = {"approver_id": str(assignment.approver_id) if assignment.approver_id else None}
        await finish_task(
            session, assignment, actor_id, "cancelled" if assignment.approver_id else "done"
        )
        assignment.approver_id = uuid.UUID(target["id"])
        assignment.task_id = None
        used.add(target["id"])
        await append_audit(
            session,
            actor_id=actor_id,
            action="approval.assigned",
            entity="approval_package",
            entity_id=str(package.id),
            before=before,
            after={
                "function": assignment.function,
                "approver_id": target["id"],
                "due_date": str(assignment.due_date),
            },
        )
    if package.status == "pending_ceo_exception":
        from app.services.approval_workflow import create_tasks

        await create_tasks(session, actor_id=actor_id, package=package, state=package.status)
    else:
        await _create_approval_tasks(
            session, actor_id=actor_id, package=package, state=package.status
        )
    await session.commit()
