"""Admin users API — permissions, invite, groups patch, role history.

Every endpoint requires the `SystemAdmin` group. Every group-changing write
emits an `audit_event` in the same transaction (CLAUDE.md rule 5) and the
audit rows are the source of truth for who did what and when.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.user import User


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


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
    """Two admins + a plain sales user so at-least-one-admin cases are exercisable."""

    admin = User(
        id=_fake_user_id("admin@smartek21.com"),
        email="admin@smartek21.com",
        name="Admin One",
        groups=["SystemAdmin"],
    )
    admin2 = User(
        id=_fake_user_id("admin2@smartek21.com"),
        email="admin2@smartek21.com",
        name="Admin Two",
        groups=["SystemAdmin"],
    )
    sales = User(
        id=_fake_user_id("sales@smartek21.com"),
        email="sales@smartek21.com",
        name="Sales One",
        groups=["Sales"],
    )
    session.add_all([admin, admin2, sales])
    await session.commit()
    return {"admin": admin, "admin2": admin2, "sales": sales}


async def _audit_rows_for(session, user_id):
    return (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity == "user", AuditEvent.entity_id == str(user_id))
            .order_by(AuditEvent.ts.asc(), AuditEvent.id.asc())
        )
    ).scalars().all()


# --- permission tests -----------------------------------------------------


async def test_list_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/admin/users")
    assert r.status_code == 401


async def test_list_forbidden_for_non_admin(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get("/admin/users", headers={"X-Test-User": "sales@smartek21.com"})
    assert r.status_code == 403


async def test_invite_forbidden_for_non_admin(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/users",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"email": "x@y.com", "name": "X", "groups": ["Sales"]},
        )
    assert r.status_code == 403


async def test_patch_forbidden_for_non_admin(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    target = seeded["sales"].id
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"add": ["Marketing"], "remove": []},
        )
    assert r.status_code == 403


async def test_role_history_forbidden_for_non_admin(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    target = seeded["sales"].id
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/admin/users/{target}/role_history",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


# --- list ------------------------------------------------------------------


async def test_list_returns_paginated_users(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.get("/admin/users", headers={"X-Test-User": "admin@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    emails = {row["email"] for row in body["items"]}
    assert emails == {
        "admin@smartek21.com",
        "admin2@smartek21.com",
        "sales@smartek21.com",
    }
    assert "SystemAdmin" in body["allowed_groups"]


async def test_list_search_matches_email_and_name(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/users?search=sales",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    emails = {row["email"] for row in r.json()["items"]}
    assert emails == {"sales@smartek21.com"}


async def test_list_group_filter(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/users?group=SystemAdmin",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    emails = {row["email"] for row in r.json()["items"]}
    assert emails == {"admin@smartek21.com", "admin2@smartek21.com"}


# --- invite ----------------------------------------------------------------


async def test_invite_creates_user_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/users",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={
                "email": "new.person@smartek21.com",
                "name": "New Person",
                "groups": ["Sales", "Presales"],
            },
        )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new.person@smartek21.com"
    assert body["groups"] == ["Sales", "Presales"]

    fresh = (
        await session.execute(
            select(User).where(User.email == "new.person@smartek21.com")
        )
    ).scalar_one()
    rows = await _audit_rows_for(session, fresh.id)
    assert len(rows) == 1
    assert rows[0].action == "user.invited"
    assert rows[0].after == {
        "email": "new.person@smartek21.com",
        "name": "New Person",
        "groups": ["Sales", "Presales"],
    }
    assert rows[0].actor_id == _fake_user_id("admin@smartek21.com")
    assert await verify_chain(session) is True


async def test_invite_duplicate_email_returns_409_no_audit(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/users",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={
                "email": "sales@smartek21.com",
                "name": "Sales Dup",
                "groups": ["Sales"],
            },
        )
    assert r.status_code == 409
    # No audit row was written for the existing user's id.
    rows = await _audit_rows_for(session, seeded["sales"].id)
    assert rows == []


async def test_invite_unknown_group_returns_422_no_audit(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/users",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={
                "email": "someone@smartek21.com",
                "name": "Some One",
                "groups": ["Sales", "GrandPoobah"],
            },
        )
    assert r.status_code == 422
    # No user created, no audit row.
    fresh = (
        await session.execute(select(User).where(User.email == "someone@smartek21.com"))
    ).scalar_one_or_none()
    assert fresh is None
    total_audits = (await session.execute(select(AuditEvent))).scalars().all()
    assert total_audits == []


# --- patch groups ----------------------------------------------------------


async def test_patch_adds_and_removes_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    target = seeded["sales"].id
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": ["Marketing"], "remove": ["Sales"]},
        )
    assert r.status_code == 200
    assert set(r.json()["groups"]) == {"Marketing"}

    rows = await _audit_rows_for(session, target)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "user.groups_changed"
    assert row.actor_id == _fake_user_id("admin@smartek21.com")
    assert row.before == {"groups": ["Sales"]}
    assert row.after == {
        "groups": ["Marketing"],
        "added": ["Marketing"],
        "removed": ["Sales"],
    }
    assert await verify_chain(session) is True


async def test_patch_removing_last_system_admin_returns_409(
    app_with_session, session, monkeypatch
):
    """Only one SystemAdmin in the org — refuse to remove the role."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    sole = User(
        id=_fake_user_id("sole.admin@smartek21.com"),
        email="sole.admin@smartek21.com",
        name="Sole Admin",
        groups=["SystemAdmin"],
    )
    session.add(sole)
    await session.commit()

    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{sole.id}/groups",
            headers={"X-Test-User": "sole.admin@smartek21.com"},
            json={"add": [], "remove": ["SystemAdmin"]},
        )
    assert r.status_code == 409
    assert "last SystemAdmin" in r.json()["detail"]
    rows = await _audit_rows_for(session, sole.id)
    assert rows == []
    fresh = (
        await session.execute(select(User).where(User.id == sole.id))
    ).scalar_one()
    assert fresh.groups == ["SystemAdmin"]


async def test_patch_removing_admin_ok_when_another_admin_exists(
    app_with_session, seeded, session, monkeypatch
):
    """Two admins in the org — removing one is allowed."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    target = seeded["admin2"].id
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": [], "remove": ["SystemAdmin"]},
        )
    assert r.status_code == 200
    assert r.json()["groups"] == []
    rows = await _audit_rows_for(session, target)
    assert len(rows) == 1
    assert rows[0].after["removed"] == ["SystemAdmin"]


async def test_patch_unknown_group_returns_422_no_audit(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    target = seeded["sales"].id
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": ["NotAGroup"], "remove": []},
        )
    assert r.status_code == 422
    rows = await _audit_rows_for(session, target)
    assert rows == []


async def test_patch_actor_id_is_current_user(
    app_with_session, seeded, session, monkeypatch
):
    """The audit row's `actor_id` must be the caller's id, not the target's."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    target = seeded["admin2"].id  # admin2 patches their own row via admin acting
    caller = _fake_user_id("admin@smartek21.com")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": ["Presales"], "remove": []},
        )
    assert r.status_code == 200
    rows = await _audit_rows_for(session, target)
    assert len(rows) == 1
    assert rows[0].actor_id == caller
    assert rows[0].actor_id != target


# --- role history ----------------------------------------------------------


async def test_role_history_returns_only_user_events_newest_first(
    app_with_session, seeded, session, monkeypatch
):
    """Emits three group changes then confirms order + entity filter."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    target = seeded["sales"].id
    async with _client(app_with_session) as c:
        # Two group changes.
        await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": ["Marketing"], "remove": []},
        )
        await c.patch(
            f"/admin/users/{target}/groups",
            headers={"X-Test-User": "admin@smartek21.com"},
            json={"add": ["Presales"], "remove": []},
        )
        # Fetch history.
        r = await c.get(
            f"/admin/users/{target}/role_history",
            headers={"X-Test-User": "admin@smartek21.com"},
        )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2
    # Newest first: last write (added Presales) appears first.
    assert items[0]["after"]["added"] == ["Presales"]
    assert items[1]["after"]["added"] == ["Marketing"]
    for item in items:
        assert item["action"].startswith("user.")
