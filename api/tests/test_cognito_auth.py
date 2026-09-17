"""Cognito auth path: verifier is mocked (JWKS is never fetched).

Covers:
- production env + valid Bearer token -> `/me` returns the mapped user.
- production env + no Authorization header -> 401.
- `cognito:groups` propagates to `require_role` so a Finance-only endpoint
  rejects a token whose claims lack the Finance group.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI

from app.auth import AuthUser, current_user, deps as auth_deps, require_role
from app.auth.cognito import CognitoAuthError
from app.main import app as main_app


@pytest.fixture
def prod_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "production")
    # Guard: the local X-Test-User shortcut must be inert here.
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest.fixture
def stub_verifier(monkeypatch):
    """Replace `verify_cognito_jwt` in the deps module with a canned dict.

    Tests set `stub_verifier.claims` (or call `stub_verifier.set(...)`) to
    control what the fake returns. Any call inspects the last-used token.
    """

    class _Stub:
        def __init__(self) -> None:
            self.claims: dict | None = None
            self.raises: Exception | None = None
            self.last_token: str | None = None

        def set(self, claims: dict) -> None:
            self.claims = claims
            self.raises = None

        def fail(self, exc: Exception) -> None:
            self.raises = exc
            self.claims = None

        def __call__(self, token: str) -> dict:
            self.last_token = token
            if self.raises is not None:
                raise self.raises
            assert self.claims is not None, "stub_verifier not configured"
            return self.claims

    stub = _Stub()
    monkeypatch.setattr(auth_deps, "verify_cognito_jwt", stub)
    return stub


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_valid_bearer_token_returns_user(prod_env, stub_verifier):
    stub_verifier.set(
        {
            "sub": "11111111-1111-1111-1111-111111111111",
            "email": "sales@smartek21.com",
            "name": "Sales One",
            "cognito:groups": ["Sales"],
            "token_use": "id",
        }
    )
    async with _client(main_app) as c:
        r = await c.get("/me", headers={"Authorization": "Bearer real-looking-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "sales@smartek21.com"
    assert body["groups"] == ["Sales"]
    assert body["id"] == "11111111-1111-1111-1111-111111111111"
    assert stub_verifier.last_token == "real-looking-token"


async def test_no_bearer_token_is_401(prod_env, stub_verifier):
    async with _client(main_app) as c:
        r = await c.get("/me")
    assert r.status_code == 401


async def test_malformed_authorization_header_is_401(prod_env, stub_verifier):
    async with _client(main_app) as c:
        r = await c.get("/me", headers={"Authorization": "NotBearer whatever"})
    assert r.status_code == 401


async def test_verifier_rejection_is_401(prod_env, stub_verifier):
    stub_verifier.fail(CognitoAuthError("expired"))
    async with _client(main_app) as c:
        r = await c.get("/me", headers={"Authorization": "Bearer x"})
    assert r.status_code == 401


async def test_cognito_groups_propagate_to_role_check(prod_env, stub_verifier):
    # Token without Finance -> a Finance-only endpoint returns 403.
    stub_verifier.set(
        {
            "sub": "22222222-2222-2222-2222-222222222222",
            "email": "sales@smartek21.com",
            "cognito:groups": ["Sales"],
            "token_use": "id",
        }
    )

    app = FastAPI()

    @app.get("/finance-only")
    async def finance(_u: AuthUser = Depends(require_role("Finance"))):
        return {"ok": True}

    async with _client(app) as c:
        r = await c.get("/finance-only", headers={"Authorization": "Bearer t"})
    assert r.status_code == 403

    # Same endpoint accepts a token whose claims include Finance.
    stub_verifier.set(
        {
            "sub": "33333333-3333-3333-3333-333333333333",
            "email": "fin@smartek21.com",
            "cognito:groups": ["Finance", "Legal"],
            "token_use": "id",
        }
    )
    async with _client(app) as c:
        r = await c.get("/finance-only", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


async def test_access_token_maps_username_when_email_missing(prod_env, stub_verifier):
    # Access tokens omit `email`; fall back to `username` / `cognito:username`.
    stub_verifier.set(
        {
            "sub": "44444444-4444-4444-4444-444444444444",
            "username": "svc-account",
            "cognito:groups": ["SystemAdmin"],
            "token_use": "access",
            "client_id": "irrelevant-here-because-verifier-is-stubbed",
        }
    )
    async with _client(main_app) as c:
        r = await c.get("/me", headers={"Authorization": "Bearer access"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == "svc-account"
    assert body["groups"] == ["SystemAdmin"]


async def test_current_user_is_configured(prod_env, stub_verifier):
    # Belt-and-braces: FastAPI resolved the dependency without swapping it.
    assert current_user is auth_deps.current_user
