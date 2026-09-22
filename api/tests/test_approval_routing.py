"""S14b routing contracts, including hostile assignment/decision inputs."""

import uuid

import pytest
from sqlalchemy import select

from app.models.approval_routing import ApprovalAssignment
from app.models.task import Task
from app.services import approval_routing as routing
from app.services.approvals import ApprovalError, decide, submit_package
from app.services.delivery_model import create_gm_model_version
from tests.test_approvals import _seed_owner, _seed_user, _seed_opp_with_sow, _passing_payload
from tests.test_approvals import _failing_payload, _client, app_with_session  # noqa: F401


async def fixture(session):
    owner = await _seed_owner(session)
    opp, sow = await _seed_opp_with_sow(session, owner, with_coverage=False)
    gm = await create_gm_model_version(
        session, actor_id=owner.id, opportunity_id=opp.id, payload=_passing_payload(sow.id)
    )
    people = {}
    for fn in routing.FUNCTIONS:
        person = await _seed_user(session, email=f"{fn}@routing.test", groups=())
        people[fn] = person
        await routing.save_group(
            session,
            actor_id=owner.id,
            function=fn,
            member_ids=[str(person.id)],
            backup_ids=[],
            default_approver_id=person.id,
        )
    return owner, opp, sow, gm, people


@pytest.mark.asyncio
async def test_below_floor_generates_brief_after_all_functions_and_closes_tasks(session):
    from app.models.ceo_exception import CeoException
    from app.services.approval_workflow import review_projection

    owner, opp, sow, _, people = await fixture(session)
    ceo = await _seed_user(session, email="ceo@routing.test", groups=["CEO"])
    await create_gm_model_version(
        session, actor_id=owner.id, opportunity_id=opp.id, payload=_failing_payload(sow.id)
    )
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    assert plan["executive"]["approver_id"] == str(ceo.id)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    assert await session.scalar(select(CeoException)) is None
    for fn in routing.FUNCTIONS:
        pkg = await decide(
            session,
            actor_id=people[fn].id,
            package_id=pkg.id,
            function=fn,
            decision="approve",
            reason="Reviewed",
        )
    assert pkg.status == "pending_ceo_exception"
    assert (await session.scalar(select(CeoException))).package_id == pkg.id
    projection = await review_projection(session, pkg, owner.id)
    assert projection["pending_with"] == [ceo.name]
    assert len(projection["assignments"]) == 4
    tasks = list((await session.scalars(select(Task))).all())
    assert sum(t.status == "done" for t in tasks) == 4
    assert next(t for t in tasks if t.owner_id == ceo.id).status == "assigned"


@pytest.mark.asyncio
async def test_signature_still_requires_coverage_and_void_cancels_work(session):
    from app.services.approval_workflow import require_signature_eligibility
    from app.services.approvals import void_on_change

    owner, opp, _, _, _ = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    with pytest.raises(ApprovalError, match="NDA"):
        await require_signature_eligibility(session, pkg)
    await void_on_change(session, actor_id=owner.id, opportunity_id=opp.id, reason="Scope revised")
    assert all(t.status == "cancelled" for t in (await session.scalars(select(Task))).all())


@pytest.mark.asyncio
async def test_owner_can_read_redacted_model_and_packages_but_not_other_owners(
    app_with_session,  # noqa: F811 - imported pytest fixture
    session,
    monkeypatch,
):
    owner, opp, _, _, _ = await fixture(session)
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as client:
        headers = {"X-Test-User": owner.email}
        response = await client.get(f"/delivery-model/{opp.id}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["gm_model"]["computed"]["complete"] is True
        assert "hourly_cost" not in response.json()["gm_model"]["resource_lines"][0]
        pkg = await client.post(f"/approvals/packages/{opp.id}", headers=headers)
        assert pkg.status_code == 201, pkg.text
        response = await client.get(f"/approvals/packages/{pkg.json()['id']}", headers=headers)
        assert response.status_code == 200
        assert "finance_summary" not in response.json()["floors"]
        outsider = {"X-Test-User": "outside@routing.test"}
        assert (
            await client.get(f"/approvals/packages/{pkg.json()['id']}", headers=outsider)
        ).status_code == 403
        assert (await client.get(f"/delivery-model/{opp.id}", headers=outsider)).status_code == 403
        denied = await client.put(
            "/approvals/groups/delivery",
            headers=headers,
            json={"member_ids": [], "backup_ids": [], "default_approver_id": None},
        )
        assert denied.status_code == 403


@pytest.mark.asyncio
async def test_review_without_coverage_routes_to_selected_members(session):
    owner, opp, sow, gm, people = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    rows = list((await session.scalars(select(ApprovalAssignment))).all())
    assert len(rows) == 4
    assert {r.approver_id for r in rows} == {u.id for u in people.values()}
    tasks = list((await session.scalars(select(Task))).all())
    assert {t.owner_id for t in tasks} == {people["delivery"].id, people["hr"].id}
    with pytest.raises(ApprovalError, match="reason"):
        await decide(
            session,
            actor_id=people["delivery"].id,
            package_id=pkg.id,
            function="delivery",
            decision="approve",
        )
    await decide(
        session,
        actor_id=people["delivery"].id,
        package_id=pkg.id,
        function="delivery",
        decision="approve",
        reason="Scope and staffing reviewed",
    )
    assert (await session.get(Task, rows[0].task_id)).status == "done"


@pytest.mark.asyncio
async def test_nonmember_assignment_and_stale_versions_rejected(session):
    owner, opp, sow, gm, people = await fixture(session)
    with pytest.raises(ApprovalError, match="member"):
        await routing.submission_plan(
            session,
            opportunity_id=opp.id,
            actor_id=owner.id,
            choices={"delivery": {"approver_id": str(owner.id)}},
        )
    with pytest.raises(ApprovalError, match="changed"):
        await routing.submission_plan(
            session, opportunity_id=opp.id, actor_id=owner.id, expected_sow_version_id=uuid.uuid4()
        )


@pytest.mark.asyncio
async def test_explicit_empty_group_stays_empty_and_admin_owns_gap(session):
    owner, opp, sow, gm, people = await fixture(session)
    admin = await _seed_user(session, email="admin@routing.test", groups=("SystemAdmin",))
    await routing.save_group(
        session,
        actor_id=admin.id,
        function="delivery",
        member_ids=[],
        backup_ids=[],
        default_approver_id=None,
    )
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    assert plan["rows"][0]["approver_id"] is None
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    task = await session.scalar(select(Task).where(Task.category == "approval.routing"))
    assert task.owner_id == admin.id
    with pytest.raises(ApprovalError, match="member"):
        await decide(
            session,
            actor_id=people["delivery"].id,
            package_id=pkg.id,
            function="delivery",
            decision="approve",
            reason="Reviewed",
        )
    await routing.save_group(
        session,
        actor_id=admin.id,
        function="delivery",
        member_ids=[str(people["delivery"].id)],
        backup_ids=[],
        default_approver_id=people["delivery"].id,
    )
    await routing.route_missing(session, actor_id=owner.id, package_id=pkg.id)
    assignment = await session.get(ApprovalAssignment, (pkg.id, "delivery"))
    assert assignment.approver_id == people["delivery"].id
