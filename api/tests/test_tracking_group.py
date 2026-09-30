"""S20 · W6 · pytest — tracking-group service + router + permissions."""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthUser
from app.db import get_session
from app.main import app as main_app
from app.models.user import User
from app.services.tracking_group import (
    GroupCreate,
    GroupPatch,
    add_members,
    create_group,
    list_groups,
    list_members,
    load_group,
    patch_group,
    remove_members,
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
    b = User(email="bob@smartek21.com", name="Bob", groups=["Sales"])
    b.id = _fake_user_id("bob@smartek21.com")
    leader = User(
        email="lead@smartek21.com",
        name="Leader",
        groups=["SalesLeader"],
    )
    leader.id = _fake_user_id("lead@smartek21.com")
    session.add_all([a, b, leader])
    await session.commit()
    return {"a": a, "b": b, "leader": leader}


def _auth(user: User) -> AuthUser:
    return AuthUser(
        id=user.id, email=user.email, name=user.name, groups=tuple(user.groups)
    )


async def test_manual_group_membership_roundtrip(session, seeded):
    actor = _auth(seeded["a"])
    g = await create_group(
        session,
        actor=actor,
        payload=GroupCreate(
            name="Watchlist A",
            member_kind="opportunity",
            visibility="private",
        ),
    )
    await session.commit()
    assert g.filter_json is None  # manual

    m1, m2 = uuid.uuid4(), uuid.uuid4()
    added = await add_members(
        session, actor=actor, group=g, member_ids=(m1, m2)
    )
    await session.commit()
    assert set(added) == {m1, m2}

    members = await list_members(session, actor=actor, group=g)
    assert set(members) == {m1, m2}

    removed = await remove_members(
        session, actor=actor, group=g, member_ids=(m1,)
    )
    await session.commit()
    assert removed == (m1,)
    members = await list_members(session, actor=actor, group=g)
    assert set(members) == {m2}


async def test_dynamic_group_cannot_have_manual_members(session, seeded):
    actor = _auth(seeded["a"])
    g = await create_group(
        session,
        actor=actor,
        payload=GroupCreate(
            name="Dynamic",
            member_kind="opportunity",
            visibility="private",
            filter_json={"deal_owner": [str(seeded["a"].id)]},
        ),
    )
    await session.commit()
    assert g.filter_json is not None

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await add_members(
            session, actor=actor, group=g, member_ids=(uuid.uuid4(),)
        )
    assert exc.value.status_code == 409


async def test_private_group_hidden_from_other_users(session, seeded):
    owner = _auth(seeded["a"])
    stranger = _auth(seeded["b"])

    g = await create_group(
        session,
        actor=owner,
        payload=GroupCreate(
            name="Private",
            member_kind="client",
            visibility="private",
        ),
    )
    await session.commit()

    # Owner sees it.
    groups = await list_groups(session, actor=owner)
    assert any(row.id == g.id for row in groups)

    # Stranger does not.
    groups = await list_groups(session, actor=stranger)
    assert not any(row.id == g.id for row in groups)

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await load_group(session, actor=stranger, group_id=g.id)
    assert exc.value.status_code == 404


async def test_team_group_visible_to_all_but_editable_only_by_owner(
    session, seeded
):
    owner = _auth(seeded["a"])
    stranger = _auth(seeded["b"])

    g = await create_group(
        session,
        actor=owner,
        payload=GroupCreate(
            name="Team",
            member_kind="opportunity",
            visibility="team",
        ),
    )
    await session.commit()

    # Stranger can list + read.
    groups = await list_groups(session, actor=stranger)
    assert any(row.id == g.id for row in groups)
    fetched = await load_group(session, actor=stranger, group_id=g.id)
    assert fetched.id == g.id

    # But cannot edit.
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await patch_group(
            session,
            actor=stranger,
            group=g,
            patch=GroupPatch(name="Hacked"),
        )
    assert exc.value.status_code == 403


async def test_leader_can_edit_any_group(session, seeded):
    owner = _auth(seeded["a"])
    leader = _auth(seeded["leader"])
    g = await create_group(
        session,
        actor=owner,
        payload=GroupCreate(
            name="Team", member_kind="opportunity", visibility="team"
        ),
    )
    await session.commit()
    g = await patch_group(
        session,
        actor=leader,
        group=g,
        patch=GroupPatch(name="Renamed"),
    )
    await session.commit()
    assert g.name == "Renamed"


async def test_endpoint_create_list(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/tracking-groups",
            json={
                "name": "My favourites",
                "member_kind": "opportunity",
                "visibility": "private",
            },
            headers={"X-Test-User": "alice@smartek21.com"},
        )
        assert r.status_code == 201, r.text
        gid = r.json()["id"]

        r = await c.get(
            "/tracking-groups",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
        assert r.status_code == 200
        assert any(row["id"] == gid for row in r.json()["items"])
