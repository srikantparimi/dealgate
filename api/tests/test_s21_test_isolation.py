"""S21F:T07/T32: real persisted routing/task/decision/outbox boundaries.

The SES sink isolates delivery only; no feature-service response is mocked.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.audit import verify_chain
from app.integrations.ses import StubSES
from app.models.approval_routing import ApprovalAssignment
from app.models.notification import Notification
from app.models.sow import Sow
from app.models.task import Task
from app.services import approval_routing as routing
from app.services import test_fixtures as fixtures
from app.services.approval_workflow import authorize_decision, create_tasks
from app.services.approvals import ApprovalError, decide, submit_package
from app.services.notifications import queue_notification
from tests.test_approval_routing import fixture
from tests.test_approvals import _seed_user
from worker.notification_sender import _handle_row


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "test")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "s21-isolation-tests")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")


async def trusted_setup(session):
    owner, old_deal, version, gm, people = await fixture(session)
    owner.groups = ["Sales", "SystemAdmin", fixtures.E2E_USER_GROUP]
    for user in people.values():
        user.groups = [fixtures.E2E_USER_GROUP]
    issued = await fixtures.create_fixture(
        session,
        actor_id=owner.id,
        label="isolated review",
        reviewer_ids=[u.id for u in people.values()],
    )
    # Arrange a submitted document in the newly issued fixture's isolated deal.
    # Full upload/storage proof belongs to T41; no approval decision is seeded.
    sow = await session.get(Sow, version.sow_id)
    sow.opportunity_id = issued["opportunity_id"]
    gm.opportunity_id = issued["opportunity_id"]
    await session.commit()
    return owner, issued, version, people


async def test_trusted_scope_routes_and_decides_without_business_reviewers(session):
    owner, issued, version, people = await trusted_setup(session)
    real = await _seed_user(session, email="real@isolation.test", groups=["Finance"])
    outsider = await _seed_user(
        session, email="other-run@isolation.test", groups=["Finance", fixtures.E2E_USER_GROUP]
    )
    await routing.save_group(
        session,
        actor_id=owner.id,
        function="finance",
        member_ids=[str(people["finance"].id), str(real.id), str(outsider.id)],
        backup_ids=[],
        default_approver_id=people["finance"].id,
    )
    plan = await routing.submission_plan(
        session, opportunity_id=issued["opportunity_id"], actor_id=owner.id
    )
    finance = next(r for r in plan["rows"] if r["function"] == "finance")
    assert {m["id"] for m in finance["members"]} == {str(people["finance"].id)}
    assert all(row["approver_id"] == str(people[row["function"]].id) for row in plan["rows"])
    package = await submit_package(
        session, actor_id=owner.id, opportunity_id=issued["opportunity_id"], routing=plan
    )
    package = await decide(
        session,
        actor_id=people["delivery"].id,
        package_id=package.id,
        function="delivery",
        decision="approve",
        reason="Fixture terms reviewed",
    )
    assert [a.approver_id for a in package.approvals] == [people["delivery"].id]
    assert await verify_chain(session)


@pytest.mark.parametrize(
    "environment,tenant", [("staging", "s21-isolation-tests"), ("test", "other"), ("test", "")]
)
async def test_foreign_or_missing_runtime_blocks_all_fixture_reviewers(
    session, monkeypatch, environment, tenant
):
    _, _, version, _ = await trusted_setup(session)
    monkeypatch.setenv("DEALGATE_ENV", environment)
    monkeypatch.setenv("DEALGATE_TENANT_ID", tenant)
    assert await fixtures.reviewer_scope(session, version) == frozenset()
    assert all(not g["members"] for g in await routing.groups(session, sow_version=version))


async def test_expired_fixture_does_not_fall_back_to_real_users(session, monkeypatch):
    _, _, version, _ = await trusted_setup(session)

    class Future(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(UTC) + timedelta(hours=5)

    monkeypatch.setattr(fixtures, "datetime", Future)
    assert await fixtures.reviewer_scope(session, version) == frozenset()
    assert all(not g["members"] for g in await routing.groups(session, sow_version=version))


@pytest.mark.parametrize(
    "case", ["human", "not-admin", "prod", "no-tenant", "real-reviewer", "negative-age"]
)
async def test_fixture_issuance_rejects_invalid_authority_and_scope(session, monkeypatch, case):
    actor = await _seed_user(
        session, email="issuer@isolation.test", groups=["SystemAdmin", fixtures.E2E_USER_GROUP]
    )
    reviewer = await _seed_user(
        session, email="reviewer@isolation.test", groups=[fixtures.E2E_USER_GROUP]
    )
    if case == "human":
        actor.groups = ["SystemAdmin"]
    elif case == "not-admin":
        actor.groups = [fixtures.E2E_USER_GROUP]
    elif case == "prod":
        monkeypatch.setenv("DEALGATE_ENV", "prod")
    elif case == "no-tenant":
        monkeypatch.delenv("DEALGATE_TENANT_ID")
    elif case == "real-reviewer":
        reviewer.groups = ["Finance"]
    with pytest.raises(HTTPException):
        await fixtures.create_fixture(
            session,
            actor_id=actor.id,
            label="forged",
            reviewer_ids=[reviewer.id],
            hours=-1 if case == "negative-age" else 4,
        )


async def test_contaminated_pending_assignment_cannot_execute_decide_or_queue(session):
    owner, deal, _, _, people = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=deal.id, actor_id=owner.id)
    package = await submit_package(session, actor_id=owner.id, opportunity_id=deal.id, routing=plan)
    bot = await _seed_user(
        session, email="bad-reviewer@isolation.test", groups=[fixtures.E2E_USER_GROUP]
    )
    assignment = await session.get(ApprovalAssignment, (package.id, "delivery"))
    assignment.approver_id = bot.id
    await session.commit()
    before_tasks = list((await session.scalars(select(Task.id))).all())
    with pytest.raises(ApprovalError, match="trusted approval scope"):
        await create_tasks(session, actor_id=owner.id, package=package, state=package.status)
    with pytest.raises(ApprovalError, match="member"):
        await authorize_decision(session, package, bot.id, "delivery", "forged")
    before_notifications = list((await session.scalars(select(Notification.id))).all())
    with pytest.raises(HTTPException, match="trusted approval scope"):
        await queue_notification(
            session,
            user_id=bot.id,
            category="approval_pending",
            subject="forged",
            body_md="",
            related_entity="approval_package",
            related_entity_id=str(package.id),
        )
    assert list((await session.scalars(select(Task.id))).all()) == before_tasks
    assert list((await session.scalars(select(Notification.id))).all()) == before_notifications
    assert not package.approvals


async def test_sender_rechecks_existing_queued_contamination_before_provider(session):
    owner, deal, _, _, _ = await fixture(session)
    plan = await routing.submission_plan(session, opportunity_id=deal.id, actor_id=owner.id)
    package = await submit_package(session, actor_id=owner.id, opportunity_id=deal.id, routing=plan)
    bot = await _seed_user(
        session, email="historic-bot@isolation.test", groups=[fixtures.E2E_USER_GROUP]
    )
    row = Notification(
        id=uuid.uuid4(),
        user_id=bot.id,
        category="approval_pending",
        channel="email",
        subject="historic contaminated review",
        body_md="",
        status="pending",
        attempts=0,
        related_entity="approval_package",
        related_entity_id=str(package.id),
    )
    session.add(row)
    await session.commit()
    sink = StubSES()
    await _handle_row(session, sink, row)
    assert row.status == "suppressed"
    assert "trusted approval scope" in row.last_error
    assert sink.sent == []
    assert await verify_chain(session)


@pytest.mark.asyncio
async def test_internal_signatories_exclude_test_identities(session, monkeypatch):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    human = await _seed_user(session, email="ceo-signer@isolation.test", groups=["CEO"])
    await _seed_user(
        session,
        email="bot-signer@isolation.test",
        groups=["CEO", fixtures.E2E_USER_GROUP],
    )

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            rows = (
                await c.get("/signatories/internal",
                            headers={"X-Test-User": human.email})
            ).json()
        emails = {r["email"] for r in rows}
        assert human.email in emails
        assert "bot-signer@isolation.test" not in emails
    finally:
        main_app.dependency_overrides.pop(get_session, None)
