"""S20 · W6 · pytest — saved-view service + router + built-in seed."""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthUser
from app.db import get_session
from app.main import app as main_app
from app.models.saved_view import BUILTIN_VIEW_KEYS, SavedView
from app.models.user import User
from app.services.saved_view import (
    SavedViewCreate,
    SavedViewPatch,
    archive_view,
    create_view,
    ensure_builtins,
    list_views,
    load_view,
    patch_view,
)


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


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
async def seeded(session):
    a = User(email="alice@smartek21.com", name="Alice", groups=["Sales"])
    a.id = _fake_user_id("alice@smartek21.com")
    session.add(a)
    await session.commit()
    return {"a": a}


def _auth(user: User) -> AuthUser:
    return AuthUser(
        id=user.id, email=user.email, name=user.name, groups=tuple(user.groups)
    )


async def test_ensure_builtins_seeds_all_seven(session, seeded):
    inserted = await ensure_builtins(session, user_id=seeded["a"].id)
    await session.commit()
    keys = {v.key for v in inserted}
    assert keys == set(BUILTIN_VIEW_KEYS)


async def test_ensure_builtins_is_idempotent(session, seeded):
    await ensure_builtins(session, user_id=seeded["a"].id)
    await session.commit()
    again = await ensure_builtins(session, user_id=seeded["a"].id)
    await session.commit()
    assert again == ()


async def test_list_views_seeds_and_returns(session, seeded):
    actor = _auth(seeded["a"])
    views = await list_views(session, actor=actor)
    await session.commit()
    keys = {v.key for v in views}
    for k in BUILTIN_VIEW_KEYS:
        assert k in keys


async def test_create_custom_view(session, seeded):
    actor = _auth(seeded["a"])
    v = await create_view(
        session,
        actor=actor,
        payload=SavedViewCreate(
            name="Only BSC",
            filter_json={"search": "BSC"},
            sort_json={"column": "close_date"},
            visibility="private",
        ),
    )
    await session.commit()
    assert v.key == "custom"
    assert v.is_builtin is False
    assert v.filter_json == {"search": "BSC"}


async def test_patch_view(session, seeded):
    actor = _auth(seeded["a"])
    v = await create_view(
        session,
        actor=actor,
        payload=SavedViewCreate(
            name="one", filter_json={}, visibility="private"
        ),
    )
    await session.commit()
    v = await patch_view(
        session,
        actor=actor,
        view=v,
        patch=SavedViewPatch(name="renamed", filter_json={"search": "x"}),
    )
    await session.commit()
    assert v.name == "renamed"
    assert v.filter_json == {"search": "x"}


async def test_builtins_cannot_be_archived(session, seeded):
    actor = _auth(seeded["a"])
    await list_views(session, actor=actor)  # seeds built-ins
    await session.commit()
    all_views = await list_views(session, actor=actor)
    builtin = next(v for v in all_views if v.is_builtin)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await archive_view(session, actor=actor, view=builtin)
    assert exc.value.status_code == 409


async def test_endpoint_seeds_builtins_on_first_get(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/saved-views",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
        assert r.status_code == 200
        keys = {row["key"] for row in r.json()["items"]}
        for k in BUILTIN_VIEW_KEYS:
            assert k in keys
