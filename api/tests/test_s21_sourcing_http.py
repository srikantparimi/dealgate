"""HTTP validation and permission boundaries with actual sourcing persistence."""
import httpx
import pytest
from fastapi import FastAPI

from app.auth import current_user
from app.db import get_session
from app.routers.people import router
from tests.test_s21_sourcing_rules import setup


@pytest.mark.parametrize("role,status", [("HR", 201), ("SystemAdmin", 201), ("Finance", 403), ("Sales", 403)])
async def test_http_rules_permissions_persist_only_authorized_writes(session, monkeypatch, role, status):
    actor = await setup(session, monkeypatch, (role,))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/people/sourcing/rules", json={"expected_version_id": None,
            "request_key": "http", "reason": "Synthetic HR configuration",
            "rules": [{"skill": "python", "location": "US", "lead_days": 45}]})
        assert response.status_code == status
        if status == 201:
            persisted = await client.get("/people/sourcing/rules")
            assert persisted.status_code == 200
            assert persisted.json()["id"] == response.json()["id"]
            assert persisted.json()["rules"] == [{"skill": "python", "location": "US", "lead_days": 45}]


@pytest.mark.parametrize("extra", [{"salary": "100"}, {"lead_days": 1.5}, {"lead_days": True}])
async def test_http_refuses_financial_or_inexact_lead_time_inputs(session, monkeypatch, extra):
    actor = await setup(session, monkeypatch)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: actor

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/people/sourcing/rules", json={"expected_version_id": None,
            "request_key": "invalid", "reason": "Invalid synthetic input",
            "rules": [{"skill": "python", "location": "US", "lead_days": 45} | extra]})
        assert response.status_code == 422
        assert (await client.get("/people/sourcing/rules")).json()["state"] == "unconfigured"
