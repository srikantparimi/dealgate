"""S21F:T07.05/T07.06 — repair pending contamination; quarantine recorded
invalid decisions separately.

A contaminated *pending* assignment is repaired in place: the admin
reassigns it to a legitimate reviewer and the audit trail keeps the
whole history. An *already-recorded* invalid decision is a different
object: the Approval row is immutable evidence, so remediation never
deletes or edits it — it quarantines the package (void + explicit
audit naming the preserved rows) so the business resubmits cleanly.
The repair path refuses once a decision exists; that refusal is the
"separate handling" the scenario demands.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.audit import verify_chain
from app.models.approval import Approval
from app.models.approval_routing import ApprovalAssignment
from app.models.task import Task
from app.services import approval_routing as routing
from app.services import test_fixtures as fixtures
from app.services.approval_remediation import (
    RemediationError,
    quarantine_recorded_decision,
    repair_pending_assignment,
)
from app.services.approvals import load_package, submit_package
from tests.test_approval_routing import fixture
from tests.test_approvals import _seed_user


async def _submitted(session):
    owner, opp, sow, gm, people = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    package = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id, routing=plan)
    admin = await _seed_user(session, "remediation-admin@smartek21.com", ["SystemAdmin"])
    bot = await _seed_user(session, "bot-reviewer@isolation.test", [fixtures.E2E_USER_GROUP])
    return owner, opp, package, people, admin, bot


@pytest.mark.asyncio
async def test_pending_contamination_is_repaired_in_place(session):
    owner, _, package, people, admin, bot = await _submitted(session)
    assignment = await session.get(ApprovalAssignment, (package.id, "delivery"))
    legitimate = assignment.approver_id
    assignment.approver_id = bot.id
    await session.commit()

    result = await repair_pending_assignment(
        session,
        actor=admin,
        package_id=package.id,
        function="delivery",
        new_approver_id=legitimate,
        reason="Contaminated by a test identity before containment",
    )
    assert result["approver_id"] == str(legitimate)

    await session.refresh(assignment)
    assert assignment.approver_id == legitimate
    package = await load_package(session, package.id)
    assert package.status == "pending_delivery_hr"  # repair never advances state
    tasks = (
        await session.scalars(select(Task).where(Task.owner_id == legitimate))
    ).all()
    assert any(t.status == "assigned" for t in tasks)
    assert await verify_chain(session) is True


@pytest.mark.asyncio
async def test_repair_refuses_once_a_decision_is_recorded(session):
    owner, _, package, people, admin, bot = await _submitted(session)
    session.add(
        Approval(
            id=uuid.uuid4(),
            package_id=package.id,
            function="delivery",
            approver_id=bot.id,
            decision="approve",
            reason="historically recorded by a test identity",
        )
    )
    await session.commit()

    with pytest.raises(RemediationError) as error:
        await repair_pending_assignment(
            session,
            actor=admin,
            package_id=package.id,
            function="delivery",
            new_approver_id=people["delivery"].id,
            reason="attempted pending repair",
        )
    assert error.value.status_code == 409
    assert "recorded" in str(error.value.detail)


@pytest.mark.asyncio
async def test_recorded_invalid_decision_is_quarantined_not_erased(session):
    owner, _, package, people, admin, bot = await _submitted(session)
    invalid = Approval(
        id=uuid.uuid4(),
        package_id=package.id,
        function="delivery",
        approver_id=bot.id,
        decision="approve",
        reason="recorded before containment landed",
    )
    session.add(invalid)
    await session.commit()

    result = await quarantine_recorded_decision(
        session,
        actor=admin,
        package_id=package.id,
        function="delivery",
        reason="Test identity decided a real package",
    )
    assert result["status"] == "voided"
    assert str(invalid.id) in result["quarantined_approval_ids"]

    # The immutable evidence survives; only the package authority is dead.
    survivor = await session.get(Approval, invalid.id)
    assert survivor is not None
    assert survivor.decision == "approve"
    package = await load_package(session, package.id)
    assert package.status == "voided"
    assert "quarantined" in (package.voided_reason or "")
    assert await verify_chain(session) is True


@pytest.mark.asyncio
async def test_quarantine_refuses_a_legitimate_decision(session):
    owner, _, package, people, admin, _ = await _submitted(session)
    session.add(
        Approval(
            id=uuid.uuid4(),
            package_id=package.id,
            function="delivery",
            approver_id=people["delivery"].id,
            decision="approve",
            reason="legitimate review",
        )
    )
    await session.commit()

    with pytest.raises(RemediationError) as error:
        await quarantine_recorded_decision(
            session,
            actor=admin,
            package_id=package.id,
            function="delivery",
            reason="nothing is actually wrong",
        )
    assert error.value.status_code == 409
    package = await load_package(session, package.id)
    assert package.status != "voided"


@pytest.mark.asyncio
async def test_both_paths_require_system_admin(session):
    owner, _, package, people, _, bot = await _submitted(session)
    from app.auth import AuthUser

    sales = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=("Sales",))
    with pytest.raises(RemediationError) as first:
        await repair_pending_assignment(
            session, actor=sales, package_id=package.id, function="delivery",
            new_approver_id=people["delivery"].id, reason="not an admin",
        )
    assert first.value.status_code == 403
    with pytest.raises(RemediationError) as second:
        await quarantine_recorded_decision(
            session, actor=sales, package_id=package.id, function="delivery",
            reason="not an admin",
        )
    assert second.value.status_code == 403


@pytest.mark.asyncio
async def test_endpoints_enforce_system_admin_and_work_end_to_end(
    session, monkeypatch
):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)
    owner, _, package, people, admin, bot = await _submitted(session)
    assignment = await session.get(ApprovalAssignment, (package.id, "delivery"))
    legitimate = assignment.approver_id
    assignment.approver_id = bot.id
    await session.commit()

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
            denied = await client.post(
                f"/admin/approvals/{package.id}/repair-assignment",
                headers={"X-Test-User": owner.email},
                json={"function": "delivery", "new_approver_id": str(legitimate),
                      "reason": "non-admin attempt"},
            )
            assert denied.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
            repaired = await client.post(
                f"/admin/approvals/{package.id}/repair-assignment",
                headers={"X-Test-User": admin.email},
                json={"function": "delivery", "new_approver_id": str(legitimate),
                      "reason": "contaminated pending assignment"},
            )
            assert repaired.status_code == 200, repaired.text
            assert repaired.json()["approver_id"] == str(legitimate)

            session.add(Approval(id=uuid.uuid4(), package_id=package.id,
                                 function="hr", approver_id=bot.id,
                                 decision="approve", reason="contaminated"))
            await session.commit()
            quarantined = await client.post(
                f"/admin/approvals/{package.id}/quarantine-decision",
                headers={"X-Test-User": admin.email},
                json={"function": "hr", "reason": "test identity decided"},
            )
            assert quarantined.status_code == 200, quarantined.text
            assert quarantined.json()["status"] == "voided"
    finally:
        main_app.dependency_overrides.pop(get_session, None)
