"""S23-PL2 B14 — the web app reads the HubSpot portal id from GET /config.

Terraform already puts HUBSPOT_PORTAL_ID in the API task's environment; the
three hard-coded copies in the web app are gone.
"""

from __future__ import annotations

import httpx
import pytest

from app.main import app as main_app


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


def _client():
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=main_app), base_url="http://t")


async def test_config_returns_the_portal_id_from_the_environment(monkeypatch):
    monkeypatch.setenv("HUBSPOT_PORTAL_ID", "48656168")
    async with _client() as c:
        r = await c.get("/config", headers={"X-Test-User": "rep@example.test"})
    assert r.status_code == 200
    assert r.json() == {"hubspot_portal_id": "48656168"}


@pytest.mark.parametrize("value", [None, "", "   "])
async def test_config_without_a_portal_id_says_null(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("HUBSPOT_PORTAL_ID", raising=False)
    else:
        monkeypatch.setenv("HUBSPOT_PORTAL_ID", value)
    async with _client() as c:
        r = await c.get("/config", headers={"X-Test-User": "rep@example.test"})
    assert r.status_code == 200
    assert r.json() == {"hubspot_portal_id": None}


async def test_config_is_for_signed_in_users_only(monkeypatch):
    monkeypatch.setenv("HUBSPOT_PORTAL_ID", "48656168")
    async with _client() as c:
        r = await c.get("/config")
    assert r.status_code == 401


async def test_any_signed_in_role_may_read_it(monkeypatch):
    monkeypatch.setenv("HUBSPOT_PORTAL_ID", "48656168")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    async with _client() as c:
        r = await c.get("/config", headers={"X-Test-User": "marketing@example.test"})
    assert r.status_code == 200
