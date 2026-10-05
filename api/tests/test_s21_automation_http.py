"""Automation configuration uses real persistence and server-side permission checks."""
import httpx
import pytest
from fastapi import FastAPI

from app.auth import current_user
from app.db import get_session
from app.routers.people import router
from tests.test_s21_sourcing_rules import setup


@pytest.mark.parametrize("role,status", [("SystemAdmin", 201), ("HR", 403), ("Finance", 403), ("Sales", 403)])
async def test_http_automation_rules_permissions(session, monkeypatch, role, status):
    actor = await setup(session, monkeypatch, (role,))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/people/sourcing/automation", json={"expected_version_id": None,
            "request_key": "http", "reason": "Enable synthetic source changes", "enabled": True})
        assert response.status_code == status
        read = await client.get("/people/sourcing/automation")
        history = await client.get("/people/sourcing/automation/history")
        jobs = await client.get("/people/sourcing/automation/jobs")
        if status == 201:
            assert read.status_code == history.status_code == 200
            assert read.json()["id"] == response.json()["id"]
            assert read.json()["enabled"] is True
            assert history.json()["items"] == [read.json()]
            assert jobs.status_code == 200 and jobs.json() == {"items": [], "last_success_at": None}
            assert (await client.get("/people/sourcing/automation/history?size=10000")).status_code == 422
        else:
            assert read.status_code == history.status_code == 403
            assert jobs.status_code == 403
