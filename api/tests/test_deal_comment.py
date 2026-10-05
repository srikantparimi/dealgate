"""S20 · W6 · pytest — deal comments service + router."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio

from app.auth import AuthUser
from app.db import get_session
from app.main import app as main_app
from app.models.deal_comment import DealComment
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.deal_comment import (
    CommentCreate,
    CommentPatch,
    comment_revision,
    create_comment,
    delete_comment,
    latest_visible_comment,
    list_comments,
    patch_comment,
    upsert_hubspot_note,
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
    sales = User(email="sales@smartek21.com", name="Sales One", groups=["Sales"])
    sales.id = _fake_user_id("sales@smartek21.com")
    other = User(email="rep2@smartek21.com", name="Sales Two", groups=["Sales"])
    other.id = _fake_user_id("rep2@smartek21.com")
    session.add_all([sales, other])
    await session.flush()

    opp = Opportunity(
        hubspot_deal_id="H-902",
        owner_id=sales.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return {"sales": sales, "other": other, "opp": opp}


def _auth(user: User) -> AuthUser:
    return AuthUser(
        id=user.id, email=user.email, name=user.name, groups=tuple(user.groups)
    )


async def test_create_internal_comment(session, seeded):
    actor = _auth(seeded["sales"])
    c = await create_comment(
        session,
        actor=actor,
        payload=CommentCreate(
            opportunity_id=seeded["opp"].id, body="Talked to client"
        ),
    )
    await session.commit()
    assert c.source == "internal"
    assert c.body == "Talked to client"
    assert c.author_id == seeded["sales"].id


async def test_patch_internal_comment_records_edited_at(session, seeded):
    actor = _auth(seeded["sales"])
    c = await create_comment(
        session,
        actor=actor,
        payload=CommentCreate(opportunity_id=seeded["opp"].id, body="Draft"),
    )
    await session.commit()
    assert c.edited_at is None

    c = await patch_comment(
        session, actor=actor, comment=c,
        patch=CommentPatch(body="Final", expected_revision=await comment_revision(session, c))
    )
    await session.commit()
    assert c.body == "Final"
    assert c.edited_at is not None


async def test_pin_toggle(session, seeded):
    actor = _auth(seeded["sales"])
    c = await create_comment(
        session,
        actor=actor,
        payload=CommentCreate(opportunity_id=seeded["opp"].id, body="Note"),
    )
    await session.commit()
    assert c.pinned is False
    c = await patch_comment(
        session, actor=actor, comment=c,
        patch=CommentPatch(pinned=True, expected_revision=await comment_revision(session, c))
    )
    await session.commit()
    assert c.pinned is True


async def test_hubspot_note_is_readonly(session, seeded):
    hn = await upsert_hubspot_note(
        session,
        opportunity_id=seeded["opp"].id,
        hubspot_note_id="hs-note-1",
        body="Note from CRM",
        author_name="Kanna",
        created_at=datetime.now(UTC),
    )
    await session.commit()
    assert hn.source == "hubspot_note"

    actor = _auth(seeded["sales"])
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await patch_comment(
            session, actor=actor, comment=hn,
            patch=CommentPatch(body="Edit", expected_revision=await comment_revision(session, hn))
        )
    assert exc.value.status_code == 409

    with pytest.raises(HTTPException) as exc:
        await delete_comment(session, actor=actor, comment=hn,
                             expected_revision=await comment_revision(session, hn))
    assert exc.value.status_code == 409


async def test_hubspot_note_upsert_is_idempotent(session, seeded):
    ts = datetime.now(UTC)
    a = await upsert_hubspot_note(
        session,
        opportunity_id=seeded["opp"].id,
        hubspot_note_id="hs-dup",
        body="First",
        author_name=None,
        created_at=ts,
    )
    await session.commit()
    b = await upsert_hubspot_note(
        session,
        opportunity_id=seeded["opp"].id,
        hubspot_note_id="hs-dup",
        body="First",
        author_name=None,
        created_at=ts,
    )
    await session.commit()
    assert a.id == b.id


async def test_soft_delete_hides_from_latest(session, seeded):
    actor = _auth(seeded["sales"])
    a = await create_comment(
        session,
        actor=actor,
        payload=CommentCreate(opportunity_id=seeded["opp"].id, body="a"),
    )
    await session.commit()
    b = await create_comment(
        session,
        actor=actor,
        payload=CommentCreate(opportunity_id=seeded["opp"].id, body="b"),
    )
    await session.commit()

    latest = await latest_visible_comment(session, opportunity_id=seeded["opp"].id)
    assert latest is not None
    assert latest.id == b.id

    await delete_comment(session, actor=actor, comment=b,
                         expected_revision=await comment_revision(session, b))
    await session.commit()

    latest = await latest_visible_comment(session, opportunity_id=seeded["opp"].id)
    assert latest is not None
    assert latest.id == a.id


async def test_third_party_cannot_edit_others_comment(session, seeded):
    author = _auth(seeded["sales"])
    third = _auth(seeded["other"])
    c = await create_comment(
        session,
        actor=author,
        payload=CommentCreate(opportunity_id=seeded["opp"].id, body="hi"),
    )
    await session.commit()

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await patch_comment(
            session, actor=third, comment=c,
            patch=CommentPatch(body="bye", expected_revision=await comment_revision(session, c))
        )
    assert exc.value.status_code == 403


async def test_list_endpoint_returns_pinned_then_recent(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/deals/{seeded['opp'].id}/comments",
            json={"body": "first"},
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 201
        first_id = r.json()["id"]

        r = await c.post(
            f"/deals/{seeded['opp'].id}/comments",
            json={"body": "second", "pinned": True},
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 201

        r = await c.get(
            f"/deals/{seeded['opp'].id}/comments",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
        assert r.status_code == 200
        body = r.json()
        # Pinned first.
        assert body["items"][0]["body"] == "second"
        assert body["items"][0]["pinned"] is True
        # Latest = most recent regardless of pin.
        assert body["latest"]["body"] == "second"
