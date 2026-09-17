"""Auth stub: 401 unauthenticated, 403 wrong role, 200 right role."""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.auth import AuthUser, current_user, require_role
from app.main import app as main_app


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_me_requires_auth():
    async with _client(main_app) as c:
        r = await c.get("/me")
    assert r.status_code == 401


async def test_me_returns_user(monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales,SystemAdmin")
    async with _client(main_app) as c:
        r = await c.get("/me", headers={"X-Test-User": "sales@smartek21.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "sales@smartek21.com"
    assert set(body["groups"]) == {"Sales", "SystemAdmin"}


async def test_require_role_forbids_wrong_group(monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")

    app = FastAPI()

    @app.get("/audit")
    async def audit(_u: AuthUser = Depends(require_role("Finance", "Legal", "CEO", "SystemAdmin"))):
        return {"ok": True}

    async with _client(app) as c:
        r = await c.get("/audit", headers={"X-Test-User": "sales@smartek21.com"})
    assert r.status_code == 403


async def test_require_role_allows_matching_group(monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")

    app = FastAPI()

    @app.get("/audit")
    async def audit(_u: AuthUser = Depends(require_role("Finance", "Legal", "CEO", "SystemAdmin"))):
        return {"ok": True}

    async with _client(app) as c:
        r = await c.get("/audit", headers={"X-Test-User": "fin@smartek21.com"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_bearer_jwt_path_used_outside_local(monkeypatch):
    # Prove the JWT path is reached when not in local env. Signature
    # verification is Cognito's job and is covered in test_cognito_auth;
    # here we mock the verifier so this test stays a pure routing check.
    from app.auth import deps as auth_deps

    monkeypatch.setenv("DEALGATE_ENV", "staging")

    def fake_verify(token: str) -> dict:
        assert token == "opaque-token"
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": "ceo@smartek21.com",
            "name": "CEO One",
            "cognito:groups": ["CEO"],
            "token_use": "id",
        }

    monkeypatch.setattr(auth_deps, "verify_cognito_jwt", fake_verify)

    async with _client(main_app) as c:
        r = await c.get("/me", headers={"Authorization": "Bearer opaque-token"})
    assert r.status_code == 200
    assert r.json()["email"] == "ceo@smartek21.com"
    assert r.json()["groups"] == ["CEO"]
