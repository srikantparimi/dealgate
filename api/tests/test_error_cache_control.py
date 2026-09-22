"""S14a: failures remain failures and must never be stored by a cache."""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

from app.main import app as main_app


@pytest.fixture
def error_app(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "production")
    app = FastAPI(
        exception_handlers=main_app.exception_handlers.copy(),
        middleware=main_app.user_middleware.copy(),
    )

    @app.get("/response/{status}")
    async def response(status: int):
        return Response(
            status_code=status,
            content=b"unchanged" if status not in (204, 304) else b"",
            headers={"Cache-Control": "public, max-age=600", "X-Origin": "preserved"},
        )

    @app.get("/handled/{status}")
    async def handled(status: int):
        raise HTTPException(status_code=status, detail="original error")

    @app.get("/validation")
    async def validation(quantity: int):
        return {"quantity": quantity}

    @app.get("/unexpected")
    async def unexpected():
        raise RuntimeError("private exception details")

    @app.get("/database/{kind}")
    async def database(kind: str):
        exceptions = {
            "integrity": IntegrityError,
            "operational": OperationalError,
            "programming": ProgrammingError,
        }
        raise exceptions[kind]("private SQL", {}, Exception("private database error"))

    @app.get("/uncached-success")
    async def uncached_success():
        return JSONResponse({"ok": True})

    return app


@pytest.mark.parametrize(
    "path,status", [("/nonexistent", 404), ("/sows", 404), ("/sows/drafts", 401)]
)
def test_real_api_errors_are_not_cacheable(path, status, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "production")
    response = TestClient(main_app).get(path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/json"
    assert "detail" in response.json()


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504])
def test_handled_errors_preserve_status_and_body(error_app, status):
    response = TestClient(error_app).get(f"/handled/{status}")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"detail": "original error"}


@pytest.mark.parametrize("status", [400, 503])
def test_error_response_overrides_existing_cache_policy(error_app, status):
    response = TestClient(error_app).get(f"/response/{status}")
    assert response.status_code == status
    assert response.headers.get_list("cache-control") == ["no-store"]
    assert response.headers["x-origin"] == "preserved"
    assert response.content == b"unchanged"


def test_validation_errors_are_not_cacheable(error_app):
    response = TestClient(error_app).get("/validation?quantity=invalid")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"][0]["type"] == "int_parsing"


@pytest.mark.parametrize("kind,status", [("integrity", 409), ("operational", 503), ("programming", 503)])
def test_database_errors_are_not_cacheable_or_exposed(error_app, kind, status):
    response = TestClient(error_app).get(f"/database/{kind}")
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert "private" not in response.text
    assert response.json()["detail"]["correlation_id"]


def test_unexpected_error_is_not_cacheable_or_exposed(error_app):
    response = TestClient(error_app, raise_server_exceptions=False).get("/unexpected")
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"]["message"] == "Something went wrong on our side."
    assert response.json()["detail"]["correlation_id"]
    assert "private exception details" not in response.text


def test_unexpected_error_still_propagates_to_server(error_app):
    with pytest.raises(RuntimeError, match="private exception details"):
        TestClient(error_app).get("/unexpected")


@pytest.mark.parametrize("status", [200, 201, 204, 301, 304])
def test_success_and_redirect_cache_policy_is_unchanged(error_app, status):
    response = TestClient(error_app).get(f"/response/{status}", follow_redirects=False)
    assert response.status_code == status
    assert response.headers["cache-control"] == "public, max-age=600"
    assert response.headers["x-origin"] == "preserved"
    assert response.content == (b"" if status in (204, 304) else b"unchanged")


def test_success_without_cache_policy_is_unchanged(error_app):
    response = TestClient(error_app).get("/uncached-success")
    assert response.status_code == 200
    assert "cache-control" not in response.headers
    assert response.json() == {"ok": True}
