"""Recruitment supply has an authenticated cost-free import/read surface."""
import pytest

from tests.test_approvals import app_with_session, _client  # noqa: F401
from tests.test_s21_people_imports import payload


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "people-http-tests")


async def test_people_http_import_history_and_read_persist(app_with_session, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
    headers = {"X-Test-User": "synthetic-hr@example.test"}
    async with _client(app_with_session) as client:
        body = payload()
        first = await client.post("/people/imports", json=body, headers=headers)
        assert first.status_code == 201, first.text
        replay = await client.post("/people/imports", json=body, headers=headers)
        assert replay.status_code == 201 and replay.json() == first.json()
        supply = await client.get("/people/availability", headers=headers)
        assert supply.status_code == 200
        assert supply.json()["people"][0]["display_name"] == "Synthetic engineer"
        history = await client.get("/people/imports", headers=headers)
        assert history.status_code == 200
        assert history.json()["items"][0]["id"] == first.json()["id"]
        assert history.json()["items"][0]["reason"] == body["reason"]
        assert history.json()["items"][0]["imported_by_name"] == "synthetic-hr"
        bad = payload()
        bad["people"][0]["cost_rate"] = "100"
        invalid = await client.post("/people/imports", json=bad, headers=headers)
        assert invalid.status_code == 422
        assert len((await client.get("/people/imports", headers=headers)).json()["items"]) == 1


@pytest.mark.parametrize("role", ["Sales", "Delivery", "Finance", "CEO", "Legal"])
async def test_people_http_denies_named_supply_and_imports_for_other_roles(app_with_session, monkeypatch, role):  # noqa: F811
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", role)
    headers = {"X-Test-User": "synthetic-denied@example.test"}
    async with _client(app_with_session) as client:
        assert (await client.post("/people/imports", json=payload(), headers=headers)).status_code == 403
        assert (await client.get("/people/imports", headers=headers)).status_code == 403
        assert (await client.get("/people/availability", headers=headers)).status_code == 403
