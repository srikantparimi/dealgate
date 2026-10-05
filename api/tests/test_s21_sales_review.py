"""S21-05/06: mandatory Sales, preserved HR and frozen historical policy."""

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.task import Task
from app.services import approval_routing as routing
from app.services.approval_workflow import review_projection
from app.services.approval_workflow import active_functions, required_functions
from app.services.approvals import ApprovalError, decide, submit_package
from tests.test_approval_routing import fixture


def test_historical_policy_is_not_reinterpreted_as_sales_approved():
    historical = ApprovalPackage(routing_policy_version=1, status="pending_delivery_hr")
    assert required_functions(historical) == ("delivery", "hr", "finance", "legal")
    assert active_functions(historical) == ("delivery", "hr")
    current = ApprovalPackage(routing_policy_version=2, status="pending_delivery_hr")
    assert required_functions(current) == ("delivery", "hr", "sales", "finance", "legal")
    assert active_functions(current) == ("delivery", "hr", "sales")


@pytest.mark.asyncio
async def test_sales_and_hr_both_required_before_finance(session):
    owner, opp, _, _, people = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    assert [row["function"] for row in plan["rows"]] == ["delivery", "hr", "sales", "finance", "legal"]
    package = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    assert package.routing_policy_version == 2
    assignment = await session.get(ApprovalAssignment, (package.id, "sales"))
    assert (await session.get(Task, assignment.task_id)).owner_id == people["sales"].id
    for fn in ("delivery", "hr"):
        package = await decide(session, actor_id=people[fn].id, package_id=package.id,
                               function=fn, decision="approve", reason="Reviewed source")
    assert package.status == "pending_delivery_hr"
    projection = await review_projection(session, package, people["sales"].id)
    assert projection["required_functions"] == ["delivery", "hr", "sales", "finance", "legal"]
    assert next(a for a in projection["assignments"] if a["function"] == "sales")["can_decide"]
    with pytest.raises(ApprovalError, match="not expected"):
        await decide(session, actor_id=people["finance"].id, package_id=package.id,
                     function="finance", decision="approve", reason="Too early")
    package = await decide(session, actor_id=people["sales"].id, package_id=package.id,
                           function="sales", decision="approve", reason="Commercial review")
    assert package.status == "pending_finance_legal"
    for fn in ("finance", "legal"):
        package = await decide(session, actor_id=people[fn].id, package_id=package.id,
                               function=fn, decision="approve", reason="Reviewed source")
    assert package.status == "ready_to_sign"
    assert {a.function for a in package.approvals} == set(routing.FUNCTIONS)


@pytest.mark.asyncio
async def test_missing_sales_blocks_submission_without_creating_package(session):
    owner, opp, _, _, _ = await fixture(session)
    await routing.save_group(session, actor_id=owner.id, function="sales",
                             member_ids=[], backup_ids=[], default_approver_id=None)
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    assert next(r for r in plan["rows"] if r["function"] == "sales")["blocker"]
    with pytest.raises(ApprovalError, match="Sales"):
        await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    assert await session.scalar(select(ApprovalPackage)) is None


@pytest.mark.asyncio
async def test_omitting_plan_cannot_bypass_missing_reviewers(session):
    owner, opp, _, _, _ = await fixture(session)
    await routing.save_group(session, actor_id=owner.id, function="hr",
                             member_ids=[], backup_ids=[], default_approver_id=None)
    with pytest.raises(ApprovalError, match="HR"):
        await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert await session.scalar(select(ApprovalPackage)) is None
