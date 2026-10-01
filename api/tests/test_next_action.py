"""S20 · W6 · pytest — structured next-action service + router + T16."""

from __future__ import annotations

import uuid
from datetime import date

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.gm_model import GmModel
from app.models.next_action import NextAction, NextActionEvent
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.next_action import (
    ApprovalCompletionForbidden,
    NextActionCreate,
    NextActionPatch,
    complete_via_approval,
    create_action,
    list_actions,
    patch_action,
)
from app.auth import AuthUser


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _fake_user_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def seeded(session):
    sales = User(email="sales@smartek21.com", name="Sales One", groups=["Sales"])
    sales.id = _fake_user_id("sales@smartek21.com")
    other = User(email="rep2@smartek21.com", name="Sales Two", groups=["Sales"])
    other.id = _fake_user_id("rep2@smartek21.com")
    leader = User(
        email="lead@smartek21.com", name="Sales Leader", groups=["SalesLeader"]
    )
    leader.id = _fake_user_id("lead@smartek21.com")
    session.add_all([sales, other, leader])
    await session.flush()

    opp = Opportunity(
        hubspot_deal_id="H-901",
        owner_id=sales.id,
        engagement_type="Fixed",
        sales_stage="Qualified",
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return {"sales": sales, "other": other, "leader": leader, "opp": opp}


def _auth(user: User) -> AuthUser:
    return AuthUser(
        id=user.id, email=user.email, name=user.name, groups=tuple(user.groups)
    )


# --- service ---------------------------------------------------------------


async def test_create_writes_row_event_and_audit(session, seeded):
    actor = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=actor,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Send NDA",
            assignee_user_id=seeded["sales"].id,
            due_date=date(2026, 10, 15),
        ),
    )
    await session.commit()

    # Row landed with mirrored description.
    fetched = await session.get(NextAction, a.id)
    assert fetched.title == "Send NDA"
    assert fetched.description == "Send NDA"
    assert fetched.assignee_user_id == seeded["sales"].id
    assert fetched.owner_user_id == seeded["sales"].id  # S19 backcompat
    assert fetched.status == "open"

    # Exactly one history event.
    events = (
        await session.execute(
            select(NextActionEvent).where(NextActionEvent.next_action_id == a.id)
        )
    ).scalars().all()
    assert len(events) == 1
    assert events[0].kind == "created"
    assert events[0].to_status == "open"

    # Audit chain got a row.
    audits = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity == "next_action")
        )
    ).scalars().all()
    assert any(x.action == "next_action.created" for x in audits)


async def test_patch_reassigns_and_records_event(session, seeded):
    actor = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=actor,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Send NDA",
            assignee_user_id=seeded["sales"].id,
        ),
    )
    await session.commit()

    a = await patch_action(
        session,
        actor=actor,
        action=a,
        patch=NextActionPatch(assignee_user_id=seeded["other"].id),
    )
    await session.commit()

    assert a.assignee_user_id == seeded["other"].id
    assert a.owner_user_id == seeded["other"].id
    events = (
        await session.execute(
            select(NextActionEvent).where(NextActionEvent.next_action_id == a.id)
        )
    ).scalars().all()
    assert [e.kind for e in events] == ["created", "reassigned"]


async def test_status_change_writes_from_and_to(session, seeded):
    actor = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=actor,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Send NDA",
            assignee_user_id=seeded["sales"].id,
        ),
    )
    await session.commit()

    await patch_action(
        session,
        actor=actor,
        action=a,
        patch=NextActionPatch(status="in_progress"),
    )
    await session.commit()

    events = (
        await session.execute(
            select(NextActionEvent)
            .where(NextActionEvent.next_action_id == a.id)
            .order_by(NextActionEvent.ts)
        )
    ).scalars().all()
    assert events[-1].kind == "status_change"
    assert events[-1].from_status == "open"
    assert events[-1].to_status == "in_progress"


async def test_unauthorised_third_party_cannot_edit(session, seeded):
    creator = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=creator,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Send NDA",
            assignee_user_id=seeded["sales"].id,
        ),
    )
    await session.commit()

    # Another sales user, not the assignee, cannot edit.
    other_user = User(email="third@smartek21.com", name="Third", groups=["Sales"])
    other_user.id = _fake_user_id("third@smartek21.com")
    session.add(other_user)
    await session.commit()
    third = _auth(other_user)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await patch_action(
            session,
            actor=third,
            action=a,
            patch=NextActionPatch(status="in_progress"),
        )
    assert exc.value.status_code == 403


async def test_leader_can_edit_any_action(session, seeded):
    creator = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=creator,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Send NDA",
            assignee_user_id=seeded["sales"].id,
        ),
    )
    await session.commit()

    leader = _auth(seeded["leader"])
    a = await patch_action(
        session,
        actor=leader,
        action=a,
        patch=NextActionPatch(status="in_progress"),
    )
    await session.commit()
    assert a.status == "in_progress"


async def _mk_approval_package(session, seeded) -> ApprovalPackage:
    """Minimal approval-package chain for T16 tests."""

    from decimal import Decimal

    sow = Sow(id=uuid.uuid4(), opportunity_id=seeded["opp"].id)
    session.add(sow)
    await session.flush()
    sv = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        file_s3_key="s3://x/a.pdf",
        file_hash="x",
        extract_status="pending",
    )
    session.add(sv)
    gm = GmModel(
        id=uuid.uuid4(),
        sow_id=sow.id,
        engagement_type="fixed",
        currency="USD",
        opportunity_id=seeded["opp"].id,
        revenue_us=Decimal("100000"),
        revenue_india=Decimal("0"),
    )
    session.add(gm)
    await session.flush()
    pkg = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=seeded["opp"].id,
        sow_version_id=sv.id,
        gm_model_id=gm.id,
        package_hash="deadbeef" + uuid.uuid4().hex[:8],
        status="pending_delivery_hr",
        submitted_by=seeded["sales"].id,
    )
    session.add(pkg)
    await session.flush()
    return pkg


async def test_complete_refused_when_tied_to_approval_package(session, seeded):
    """T16 — the review's rule: completing an approval-linked action
    must go through the approval decision, not this task."""

    pkg = await _mk_approval_package(session, seeded)

    actor = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=actor,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Approve SOW",
            assignee_user_id=seeded["sales"].id,
            approval_package_id=pkg.id,
        ),
    )
    await session.commit()

    with pytest.raises(ApprovalCompletionForbidden) as exc:
        await patch_action(
            session,
            actor=actor,
            action=a,
            patch=NextActionPatch(status="complete"),
        )
    assert exc.value.status_code == 409
    assert "approval" in str(exc.value.detail).lower()


async def test_complete_via_approval_bypasses_refusal(session, seeded):
    """Internal API path used by W3's approval decision service."""

    pkg = await _mk_approval_package(session, seeded)

    actor = _auth(seeded["sales"])
    a = await create_action(
        session,
        actor=actor,
        payload=NextActionCreate(
            opportunity_id=seeded["opp"].id,
            title="Approve SOW",
            assignee_user_id=seeded["sales"].id,
            approval_package_id=pkg.id,
        ),
    )
    await session.commit()

    a = await complete_via_approval(
        session, actor=actor, action=a, approval_decision_id=uuid.uuid4()
    )
    await session.commit()
    assert a.status == "complete"
    assert a.completed_at is not None


# --- HTTP router ----------------------------------------------------------


async def test_list_endpoint_filters_by_opportunity(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/next-actions",
            json={
                "opportunity_id": str(seeded["opp"].id),
                "title": "Ping client",
                "assignee_user_id": str(seeded["sales"].id),
            },
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 201, r.text
        payload = r.json()
        assert payload["title"] == "Ping client"
        assert payload["status"] == "open"

        r = await c.get(
            f"/next-actions?opportunity_id={seeded['opp'].id}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 1


async def test_events_endpoint_returns_history(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/next-actions",
            json={
                "opportunity_id": str(seeded["opp"].id),
                "title": "Ping",
                "assignee_user_id": str(seeded["sales"].id),
            },
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        action_id = r.json()["id"]

        r = await c.patch(
            f"/next-actions/{action_id}",
            json={"status": "in_progress"},
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 200, r.text

        r = await c.get(
            f"/next-actions/{action_id}/events",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 200
        body = r.json()
        kinds = [e["kind"] for e in body["items"]]
        assert kinds == ["created", "status_change"]
