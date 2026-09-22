"""S13b: configurable categories are shared, validated and Finance-owned."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import get_session
from app.main import app
from app.models.audit import AuditEvent


@pytest_asyncio.fixture
async def client(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
            headers={"X-Test-User": "settings-finance@example.com"},
        ) as http:
            yield http
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize("role", ["Finance", "SystemAdmin"])
async def test_categories_default_roundtrip_and_audit(client, session, monkeypatch, role):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
    default = await client.get("/settings/direct-cost-categories")
    assert default.status_code == 200
    assert default.json()["categories"] == [
        "Travel", "Meals & lodging", "Software/licenses", "Subcontractor", "Equipment", "Other",
    ]
    body = {"categories": ["Travel", "Software", "Other"]}
    saved = await client.put("/settings/direct-cost-categories", json=body)
    assert saved.status_code == 200, saved.text
    assert (await client.get("/settings/direct-cost-categories")).json() == body
    event = (await session.execute(select(AuditEvent).where(
        AuditEvent.action == "direct_cost_categories.updated"
    ))).scalar_one()
    assert event.before == default.json()
    assert event.after == body


@pytest.mark.parametrize("role", ["Sales", "Delivery", "CEO", "Legal", "HR"])
async def test_categories_write_requires_finance_or_admin(client, monkeypatch, role):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
    assert (await client.get("/settings/direct-cost-categories")).status_code == 200
    assert (await client.put("/settings/direct-cost-categories", json={
        "categories": ["Other"],
    })).status_code == 403


async def test_categories_require_authentication(client):
    client.headers.pop("X-Test-User")
    assert (await client.get("/settings/direct-cost-categories")).status_code == 401


@pytest.mark.parametrize("categories", [[], [" "], ["Travel", " travel "], ["x" * 33]])
async def test_categories_reject_invalid_list(client, categories):
    response = await client.put("/settings/direct-cost-categories", json={"categories": categories})
    assert response.status_code == 422
