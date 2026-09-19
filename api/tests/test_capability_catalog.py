"""Capability catalog CRUD — role gates + re-embed on description PATCH.

Every endpoint is exercised end-to-end via the FastAPI ASGI transport so
the role check + audit emission are covered in one pass. Bedrock is
never called — the router uses the deterministic ``StubEmbeddings``
adapter (via ``default_embedder`` when ``DEALGATE_ENV=local``).
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.capability import CapabilityCatalog


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _headers(email: str, groups: str) -> dict[str, str]:
    return {"X-Test-User": email}


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


def _as(env, groups: str):
    """Return an environment monkeypatcher that sets DEALGATE_TEST_GROUPS."""

    env.setenv("DEALGATE_TEST_GROUPS", groups)


# --- role gates -----------------------------------------------------------


@pytest.mark.asyncio
async def test_get_forbidden_for_non_governance_role(app_with_session, monkeypatch):
    _as(monkeypatch, "Legal")  # Legal is not in READ_ROLES
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/capability-catalog",
            headers=_headers("legal@x", "Legal"),
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_ok_for_presales(app_with_session, monkeypatch):
    _as(monkeypatch, "Presales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/admin/capability-catalog",
            headers=_headers("presales@x", "Presales"),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_post_forbidden_for_presales(app_with_session, monkeypatch):
    _as(monkeypatch, "Presales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/capability-catalog",
            headers=_headers("presales@x", "Presales"),
            json={"name": "n", "description": "d", "tags": []},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_forbidden_for_delivery(app_with_session, monkeypatch, session):
    _as(monkeypatch, "Delivery")
    row = CapabilityCatalog(
        id=uuid.uuid4(), name="X", description="Y", tags=[]
    )
    session.add(row)
    await session.commit()
    async with _client(app_with_session) as c:
        r = await c.delete(
            f"/admin/capability-catalog/{row.id}",
            headers=_headers("delivery@x", "Delivery"),
        )
    assert r.status_code == 403


# --- happy path -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_embeds_and_audits(app_with_session, monkeypatch, session):
    _as(monkeypatch, "Delivery")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/capability-catalog",
            headers=_headers("dl@x", "Delivery"),
            json={
                "name": "Salesforce implementation",
                "description": "Build custom Salesforce CRM flows for sales teams",
                "tags": ["salesforce", "crm"],
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Salesforce implementation"
    assert body["tags"] == ["salesforce", "crm"]
    assert body["has_embedding"] is True
    row_id = uuid.UUID(body["id"])

    row = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == row_id)
        )
    ).scalar_one()
    assert row.embedding
    baseline_vec = list(row.embedding)

    events = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity == "capability_catalog")
        )
    ).scalars().all()
    assert any(e.action == "capability.created" for e in events)

    # Second create with the same name must 409.
    async with _client(app_with_session) as c:
        r2 = await c.post(
            "/admin/capability-catalog",
            headers=_headers("dl@x", "Delivery"),
            json={
                "name": "Salesforce implementation",
                "description": "duplicate",
                "tags": [],
            },
        )
    assert r2.status_code == 409

    # Description-only PATCH must re-embed.
    async with _client(app_with_session) as c:
        r3 = await c.patch(
            f"/admin/capability-catalog/{row_id}",
            headers=_headers("dl@x", "Delivery"),
            json={"description": "Totally rewritten scope for Marketo instead."},
        )
    assert r3.status_code == 200
    assert r3.json()["description"].startswith("Totally rewritten")
    await session.refresh(row)
    assert row.embedding
    assert list(row.embedding) != baseline_vec

    # Tags-only PATCH does NOT re-embed.
    async with _client(app_with_session) as c:
        r4 = await c.patch(
            f"/admin/capability-catalog/{row_id}",
            headers=_headers("dl@x", "Delivery"),
            json={"tags": ["marketo"]},
        )
    assert r4.status_code == 200
    tags_vec = list(row.embedding)
    await session.refresh(row)
    assert list(row.embedding) == tags_vec


@pytest.mark.asyncio
async def test_delete_by_systemadmin(app_with_session, monkeypatch, session):
    _as(monkeypatch, "SystemAdmin")
    row = CapabilityCatalog(
        id=uuid.uuid4(), name="X", description="Y", tags=[]
    )
    session.add(row)
    await session.commit()
    async with _client(app_with_session) as c:
        r = await c.delete(
            f"/admin/capability-catalog/{row.id}",
            headers=_headers("admin@x", "SystemAdmin"),
        )
    assert r.status_code == 204

    # And it should be gone.
    absent = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == row.id)
        )
    ).scalar_one_or_none()
    assert absent is None

    # Audit row exists.
    events = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.entity == "capability_catalog")
        )
    ).scalars().all()
    assert any(e.action == "capability.deleted" for e in events)


@pytest.mark.asyncio
async def test_list_filters_by_search_and_tag(app_with_session, monkeypatch, session):
    _as(monkeypatch, "Presales")
    session.add_all(
        [
            CapabilityCatalog(
                id=uuid.uuid4(),
                name="Salesforce implementation",
                description="Sales cloud rollouts",
                tags=["salesforce"],
            ),
            CapabilityCatalog(
                id=uuid.uuid4(),
                name="Data warehouse",
                description="Modern lakehouse architecture",
                tags=["data"],
            ),
        ]
    )
    await session.commit()

    async with _client(app_with_session) as c:
        r_search = await c.get(
            "/admin/capability-catalog?search=warehouse",
            headers=_headers("p@x", "Presales"),
        )
        r_tag = await c.get(
            "/admin/capability-catalog?tag=salesforce",
            headers=_headers("p@x", "Presales"),
        )
    assert r_search.status_code == 200
    assert [i["name"] for i in r_search.json()["items"]] == ["Data warehouse"]
    assert r_tag.status_code == 200
    assert [i["name"] for i in r_tag.json()["items"]] == [
        "Salesforce implementation"
    ]
