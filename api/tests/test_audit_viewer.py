"""S1-E1 audit viewer: role gate, filters, pagination, verification."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, text

from app.audit import append_audit
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
async def actors(session):
    """Create a Finance and a Sales user in the DB so joins resolve to email."""

    finance = User(email="finance@smartek21.com", name="Finance One", groups=["Finance"])
    finance.id = _fake_user_id("finance@smartek21.com")
    sales = User(email="sales@smartek21.com", name="Sales One", groups=["Sales"])
    sales.id = _fake_user_id("sales@smartek21.com")
    session.add_all([finance, sales])
    await session.commit()
    return {"finance": finance, "sales": sales}


@pytest_asyncio.fixture
async def small_chain(session, actors):
    """Three-row chain across two entities, so filters have something to bite."""

    await append_audit(
        session,
        actor_id=actors["sales"].id,
        action="opportunity.create",
        entity="opportunity",
        entity_id="O-1",
        before=None,
        after={"governance_status": "Intake"},
        correlation_id="corr-1",
    )
    await append_audit(
        session,
        actor_id=actors["sales"].id,
        action="opportunity.owner_changed",
        entity="opportunity",
        entity_id="O-1",
        before={"owner_id": None},
        after={"owner_id": str(actors["sales"].id)},
        correlation_id="corr-2",
    )
    await append_audit(
        session,
        actor_id=actors["finance"].id,
        action="task.create",
        entity="task",
        entity_id="T-1",
        before=None,
        after={"subject": "Chase NDA"},
        correlation_id="corr-3",
    )
    await session.commit()


# --- role gate --------------------------------------------------------------


async def test_list_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/audit")
    assert r.status_code == 401


async def test_list_forbidden_for_sales(app_with_session, actors, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get("/audit", headers={"X-Test-User": "sales@smartek21.com"})
    assert r.status_code == 403


async def test_list_allowed_for_finance(app_with_session, actors, small_chain, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get("/audit", headers={"X-Test-User": "finance@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    # Newest first, actor_email joined.
    assert body["items"][0]["action"] == "task.create"
    assert body["items"][0]["actor_email"] == "finance@smartek21.com"
    assert body["items"][-1]["actor_email"] == "sales@smartek21.com"
    # Response row shape includes chain hashes + correlation id.
    top = body["items"][0]
    for key in (
        "id",
        "ts",
        "actor_id",
        "actor_email",
        "action",
        "entity",
        "entity_id",
        "before",
        "after",
        "correlation_id",
        "prev_hash",
        "row_hash",
    ):
        assert key in top


async def test_list_allowed_for_legal_ceo_admin(
    app_with_session, actors, small_chain, monkeypatch
):
    for role in ("Legal", "CEO", "SystemAdmin"):
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
        async with _client(app_with_session) as c:
            r = await c.get(
                "/audit", headers={"X-Test-User": "finance@smartek21.com"}
            )
        assert r.status_code == 200, role


# --- filters + pagination ---------------------------------------------------


async def test_filters_combine(app_with_session, actors, small_chain, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit",
            headers={"X-Test-User": "finance@smartek21.com"},
            params={
                "entity": "opportunity",
                "actor_id": str(actors["sales"].id),
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    entities = {row["entity"] for row in body["items"]}
    assert entities == {"opportunity"}
    actor_ids = {row["actor_id"] for row in body["items"]}
    assert actor_ids == {str(actors["sales"].id)}


async def test_since_filter(app_with_session, actors, small_chain, monkeypatch, session):
    # Only the last row should survive `since = latest_ts`.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    latest_ts = (
        await session.execute(select(func.max(AuditEvent.ts)))
    ).scalar_one()
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit",
            headers={"X-Test-User": "finance@smartek21.com"},
            params={"since": latest_ts.isoformat()},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["action"] == "task.create"


@pytest_asyncio.fixture
async def big_chain(session, actors):
    """Fifty rows so we can exercise pagination."""

    for i in range(50):
        await append_audit(
            session,
            actor_id=actors["sales"].id,
            action="opportunity.owner_changed",
            entity="opportunity",
            entity_id=f"O-{i:02d}",
            before=None,
            after={"i": i},
        )
    await session.commit()


async def test_pagination_across_50_rows(app_with_session, actors, big_chain, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    seen: set[str] = set()
    async with _client(app_with_session) as c:
        for page in (1, 2, 3):
            r = await c.get(
                "/audit",
                headers={"X-Test-User": "finance@smartek21.com"},
                params={"page": page, "size": 20},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["total"] == 50
            assert body["page"] == page
            assert body["size"] == 20
            page_ids = [row["id"] for row in body["items"]]
            # No overlap across pages.
            assert not (set(page_ids) & seen)
            seen.update(page_ids)
    assert len(seen) == 50


# --- verification -----------------------------------------------------------


async def test_verify_full_chain_ok(app_with_session, actors, small_chain, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify", headers={"X-Test-User": "finance@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["first_broken_row"] is None
    assert body["checked"] == 3


async def test_verify_filtered_slice_ok(
    app_with_session, actors, small_chain, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify",
            headers={"X-Test-User": "finance@smartek21.com"},
            params={"entity": "opportunity", "entity_id": "O-1"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checked"] == 2


async def test_verify_detects_after_payload_tamper(
    app_with_session, actors, small_chain, monkeypatch, session
):
    """Tamper via raw SQL — SQLite has no UPDATE grant enforcement, so this
    simulates a DB-level intruder bypassing the ORM.
    """

    row = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == "O-1").order_by(AuditEvent.ts)
        )
    ).scalars().first()
    tampered_after = json.dumps({"governance_status": "Approved"})
    # SQLite stores UUIDs as unhyphenated hex; pass the raw hex so WHERE matches.
    await session.execute(
        text("UPDATE audit_event SET after = :a WHERE id = :i").bindparams(
            a=tampered_after, i=row.id.hex
        )
    )
    await session.commit()
    # Force the ORM to re-read from the tampered row rather than serve it out
    # of the identity map (the raw SQL bypassed the session).
    session.expire_all()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify", headers={"X-Test-User": "finance@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["first_broken_row"] == str(row.id)
    assert "row_hash" in body["message"] or "prev_hash" in body["message"]


async def test_verify_is_view_only(
    app_with_session, actors, small_chain, monkeypatch, session
):
    """Verification must never append new audit_event rows."""

    before_count = (
        await session.execute(select(func.count(AuditEvent.id)))
    ).scalar_one()
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify", headers={"X-Test-User": "finance@smartek21.com"}
        )
    assert r.status_code == 200
    after_count = (
        await session.execute(select(func.count(AuditEvent.id)))
    ).scalar_one()
    assert after_count == before_count


async def test_verify_forbidden_for_sales(app_with_session, actors, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 403


async def test_verify_empty_chain(app_with_session, actors, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit/verify", headers={"X-Test-User": "finance@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["checked"] == 0


# --- boundary: `until` -----------------------------------------------------


async def test_until_filter(app_with_session, actors, small_chain, monkeypatch, session):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    rows = (
        await session.execute(select(AuditEvent).order_by(AuditEvent.ts))
    ).scalars().all()
    cutoff = rows[0].ts + timedelta(microseconds=1)
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=UTC)
    async with _client(app_with_session) as c:
        r = await c.get(
            "/audit",
            headers={"X-Test-User": "finance@smartek21.com"},
            params={"until": cutoff.isoformat()},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(rows[0].id)
