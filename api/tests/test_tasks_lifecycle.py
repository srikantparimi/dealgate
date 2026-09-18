"""Task lifecycle — every allowed transition and every forbidden one, plus
role-gated reassign and the "hide snoozed until wake_at" list rule.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.task import Task
from app.models.user import User
from app.services.tasks import TASK_TRANSITIONS


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


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
    owner = User(
        id=_uid("owner@smartek21.com"),
        email="owner@smartek21.com",
        name="Owner",
        groups=["Sales"],
    )
    leader = User(
        id=_uid("leader@smartek21.com"),
        email="leader@smartek21.com",
        name="Leader",
        groups=["SalesLeader"],
    )
    stranger = User(
        id=_uid("stranger@smartek21.com"),
        email="stranger@smartek21.com",
        name="Stranger",
        groups=["Sales"],
    )
    other = User(
        id=_uid("newowner@smartek21.com"),
        email="newowner@smartek21.com",
        name="New Owner",
        groups=["Sales"],
    )
    session.add_all([owner, leader, stranger, other])
    await session.commit()
    return {"owner": owner, "leader": leader, "stranger": stranger, "other": other}


async def _make_task(
    session, owner_id: uuid.UUID, *, status: str = "assigned", category: str | None = None
) -> Task:
    t = Task(
        id=uuid.uuid4(),
        owner_id=owner_id,
        subject="Do the thing",
        status=status,
        category=category,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


# --- list ordering + owner=me default ------------------------------------


async def test_list_defaults_to_owner_me_ordered_by_due_date(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    owner = seeded["owner"]
    from datetime import date

    for i, d in enumerate([date(2026, 1, 5), None, date(2026, 1, 1), date(2026, 1, 3)]):
        t = Task(id=uuid.uuid4(), owner_id=owner.id, subject=f"t{i}", due_date=d)
        session.add(t)
    # A task belonging to someone else shouldn't leak.
    session.add(Task(id=uuid.uuid4(), owner_id=seeded["stranger"].id, subject="other"))
    await session.commit()

    async with _client(app_with_session) as c:
        r = await c.get("/tasks", headers={"X-Test-User": "owner@smartek21.com"})
    assert r.status_code == 200
    subjects = [row["subject"] for row in r.json()["items"]]
    # NULLS LAST: earliest due_date first, then remainder, None-due last.
    assert subjects == ["t2", "t3", "t0", "t1"]


async def test_list_snoozed_hidden_until_wake_at(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    owner = seeded["owner"]
    future = datetime.now(UTC) + timedelta(days=1)
    past = datetime.now(UTC) - timedelta(minutes=1)

    session.add(
        Task(
            id=uuid.uuid4(),
            owner_id=owner.id,
            subject="hidden",
            status="snoozed",
            wake_at=future,
        )
    )
    session.add(
        Task(
            id=uuid.uuid4(),
            owner_id=owner.id,
            subject="woke",
            status="snoozed",
            wake_at=past,
        )
    )
    await session.commit()

    async with _client(app_with_session) as c:
        r = await c.get("/tasks", headers={"X-Test-User": "owner@smartek21.com"})
    assert r.status_code == 200
    subjects = {row["subject"] for row in r.json()["items"]}
    assert subjects == {"woke"}


# --- allowed transitions -------------------------------------------------


@pytest.mark.parametrize(
    "from_status,to_status",
    sorted(
        (fs, ts)
        for fs, allowed in TASK_TRANSITIONS.items()
        for ts in allowed
        # `reassigned` is exercised by the dedicated reassign endpoint.
        if ts != "reassigned"
    ),
)
async def test_allowed_transitions_via_patch(
    app_with_session, seeded, session, monkeypatch, from_status, to_status
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id, status=from_status)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={"status": to_status}
            if to_status != "snoozed"
            else {
                "status": "snoozed",
                "wake_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == to_status


# --- forbidden transitions (422) -----------------------------------------


@pytest.mark.parametrize(
    "from_status,to_status",
    sorted(
        (fs, ts)
        for fs in TASK_TRANSITIONS
        for ts in {"assigned", "in_progress", "snoozed", "done", "cancelled"}
        if ts not in TASK_TRANSITIONS[fs]
    ),
)
async def test_forbidden_transitions_return_422(
    app_with_session, seeded, session, monkeypatch, from_status, to_status
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id, status=from_status)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={"status": to_status}
            if to_status != "snoozed"
            else {
                "status": "snoozed",
                "wake_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
    assert r.status_code == 422, r.text


# --- role gating on transitions ------------------------------------------


async def test_non_owner_non_leader_cannot_transition(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "stranger@smartek21.com"},
            json={"status": "in_progress"},
        )
    assert r.status_code == 403


async def test_leader_may_transition_any_task(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SalesLeader")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "leader@smartek21.com"},
            json={"status": "in_progress"},
        )
    assert r.status_code == 200


# --- completion records escalation + audit chain -------------------------


async def test_completing_task_records_escalation_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id)
    task.escalation_level = 2
    await session.commit()

    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={"status": "done"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["completed_by"] == str(_uid("owner@smartek21.com"))

    rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == str(task.id))
        )
    ).scalars().all()
    actions = [r.action for r in rows]
    assert "task.completed" in actions
    completed = next(r for r in rows if r.action == "task.completed")
    assert completed.after["escalation_at_completion"] == 2
    assert await verify_chain(session) is True


# --- snooze --------------------------------------------------------------


async def test_snooze_requires_future_wake_at(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={
                "status": "snoozed",
                "wake_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            },
        )
    assert r.status_code == 422


async def test_snooze_requires_wake_at(app_with_session, seeded, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/tasks/{task.id}",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={"status": "snoozed"},
        )
    assert r.status_code == 422


# --- reassign ------------------------------------------------------------


async def test_reassign_forbidden_for_non_leader(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/tasks/{task.id}/reassign",
            headers={"X-Test-User": "owner@smartek21.com"},
            json={"new_owner_id": str(seeded["other"].id)},
        )
    assert r.status_code == 403


async def test_reassign_by_leader_updates_owner_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SalesLeader")
    task = await _make_task(session, seeded["owner"].id)
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/tasks/{task.id}/reassign",
            headers={"X-Test-User": "leader@smartek21.com"},
            json={"new_owner_id": str(seeded["other"].id)},
        )
    assert r.status_code == 200
    assert r.json()["owner_id"] == str(seeded["other"].id)

    rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == str(task.id))
        )
    ).scalars().all()
    assert any(r.action == "task.reassigned" for r in rows)


async def test_reassign_completed_task_rejected(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SalesLeader")
    task = await _make_task(session, seeded["owner"].id, status="done")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/tasks/{task.id}/reassign",
            headers={"X-Test-User": "leader@smartek21.com"},
            json={"new_owner_id": str(seeded["other"].id)},
        )
    assert r.status_code == 422


async def test_unauth_returns_401(app_with_session, seeded):
    async with _client(app_with_session) as c:
        r = await c.get("/tasks")
    assert r.status_code == 401
