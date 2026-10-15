"""S23-PL2 T5 / B11 — the personal workspace on the canonical DealGate user id.

HubSpot intake creates a deal owner's DealGate row with a fresh uuid4 and no
groups. When that person signs in, the login id (Cognito ``sub``; locally the
``X-Test-User`` uuid5) is not that row's id. Saved views, groups, watches,
preferences and next actions carry foreign keys to ``user.id``, so every write
keyed on the login id failed on Postgres. This module runs on the
FK-enforcing engine, so the same writes fail here when they are keyed wrongly.

Also covers the root cause of the second saved view (B11): custom views shared
one ``key`` under a unique (owner, key, is_builtin) constraint.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_session
from app.main import app as main_app
from app.services import saved_view as saved_view_service
from app.services import tracking_group as tracking_group_service
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.saved_view import SavedView
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.watchlist import WatchedItem

REP = "rep.from.hubspot@example.test"
OTHER = "other.rep@example.test"
AS_REP = {"X-Test-User": REP}
AS_OTHER = {"X-Test-User": OTHER}


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


def _login_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def world(session):
    # Created the way HubSpot intake creates owners: a fresh uuid4, no groups.
    rep = User(id=uuid.uuid4(), email=REP, name="Rep From HubSpot", groups=[])
    other = User(id=_login_id(OTHER), email=OTHER, name="Other Rep", groups=["Sales"])
    client = Client(name="Keystone Energy", hubspot_company_id="c-1")
    session.add_all([rep, other, client])
    await session.flush()
    deals = [
        Opportunity(source="hubspot", hubspot_deal_id=f"d-{i}", name=f"Deal {i}", owner_id=rep.id,
                    client_id=client.id, amount=Decimal("1000.00"), currency="USD",
                    close_date=date(2026, 11, 1))
        for i in range(3)
    ]
    session.add_all(deals)
    await session.commit()
    assert rep.id != _login_id(REP)
    return {"rep": rep.id, "other": other.id, "deals": [d.id for d in deals]}


@pytest_asyncio.fixture
async def api(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _session():
        async with factory() as s:
            yield s

    main_app.dependency_overrides[get_session] = _session
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_app, raise_app_exceptions=False),
            base_url="http://t",
        ) as c:
            yield c
    finally:
        main_app.dependency_overrides.pop(get_session, None)


async def _actions(session, entity: str) -> list[str]:
    session.expire_all()
    return list((await session.scalars(
        select(AuditEvent.action).where(AuditEvent.entity == entity).order_by(AuditEvent.ts)
    )).all())


# --- the old routes still used by other pages ---------------------------------


async def test_old_personal_routes_key_on_the_dealgate_user_id(api, session, world):
    deal = str(world["deals"][0])
    rep = str(world["rep"])

    r = await api.get("/saved-views", headers=AS_REP)
    assert r.status_code == 200, r.text
    r = await api.post("/saved-views", headers=AS_REP, json={"name": "Mine", "filter_json": {}})
    assert r.status_code == 201, r.text
    assert r.json()["owner_id"] == rep

    r = await api.post("/watchlist", headers=AS_REP, json={"kind": "opportunity", "item_id": deal})
    assert r.status_code == 201, r.text
    again = await api.post("/watchlist", headers=AS_REP, json={"kind": "opportunity", "item_id": deal})
    assert again.status_code == 201, again.text
    assert again.json()["id"] == r.json()["id"]
    listed = await api.get("/watchlist", headers=AS_REP)
    assert [i["item_id"] for i in listed.json()["items"]] == [deal]

    r = await api.post("/tracking-groups", headers=AS_REP, json={"name": "G", "member_kind": "opportunity"})
    assert r.status_code == 201, r.text
    assert r.json()["owner_id"] == rep
    group = r.json()["id"]
    r = await api.post(f"/tracking-groups/{group}/members", headers=AS_REP, json={"member_ids": [deal]})
    assert r.status_code == 200, r.text
    assert r.json()["member_ids"] == [deal]

    r = await api.put("/user-preferences/pipeline.last_view", headers=AS_REP, json={"value": {"id": "v1"}})
    assert r.status_code == 200, r.text
    r = await api.get("/user-preferences/pipeline.last_view", headers=AS_REP)
    assert r.status_code == 200 and r.json()["value"] == {"id": "v1"}

    # The assignee is the person's DealGate id; their DB groups were [] until now.
    r = await api.post("/next-actions", headers=AS_REP, json={
        "opportunity_id": deal, "title": "Call the sponsor", "assignee_user_id": rep})
    assert r.status_code == 201, r.text
    action = r.json()
    assert action["can_edit"] is True
    r = await api.get("/next-actions", headers=AS_REP, params={"opportunity_id": deal})
    assert r.status_code == 200, r.text
    assert [(i["id"], i["can_edit"]) for i in r.json()["items"]] == [(action["id"], True)]
    r = await api.patch(f"/next-actions/{action['id']}", headers=AS_REP, json={
        "title": "Call the sponsor again", "expected_revision": action["revision"]})
    assert r.status_code == 200, r.text

    session.expire_all()
    login = _login_id(REP)
    assert (await session.scalar(select(User).where(User.id == login))) is None
    owners = {
        "saved_view": set((await session.scalars(select(SavedView.owner_id))).all()),
        "tracking_group": set((await session.scalars(select(TrackingGroup.owner_id))).all()),
        "watched_item": set((await session.scalars(select(WatchedItem.user_id))).all()),
        "user_preference": set((await session.scalars(select(UserPreference.user_id))).all()),
        "next_action": set((await session.scalars(select(NextAction.created_by))).all()),
    }
    assert owners == {k: {world["rep"]} for k in owners}


async def test_second_and_third_custom_view_save_on_the_old_route(api, world):
    for name in ("First", "Second", "Third"):
        r = await api.post("/saved-views", headers=AS_REP, json={"name": name, "filter_json": {"q": name}})
        assert r.status_code == 201, r.text
    dup = await api.post("/saved-views", headers=AS_REP, json={"name": "sECOND", "filter_json": {}})
    assert dup.status_code == 409
    assert dup.json()["detail"] == "You already have a view with this name."


async def test_watch_endpoint_rejects_a_duplicate_without_a_500(api, world):
    # The old handler swallowed the IntegrityError and then crashed on scalar_one().
    deal = str(world["deals"][1])
    for _ in range(3):
        r = await api.post("/watchlist", headers=AS_REP, json={"kind": "opportunity", "item_id": deal})
        assert r.status_code == 201, r.text
    r = await api.delete("/watchlist", headers=AS_REP, params={"kind": "opportunity", "item_id": deal})
    assert r.status_code == 204
    listed = await api.get("/watchlist", headers=AS_REP)
    assert listed.json()["items"] == []


# --- the Pipeline's own routes (contract) -------------------------------------


async def test_saved_views_second_third_duplicate_and_delete(api, session, world):
    assert (await api.get("/pipeline/views", headers=AS_REP)).json() == []

    bodies = [
        {"name": "Closing soon", "tab": "deals", "layout": "list",
         "filters": {"status": "open", "date_field": "close", "date_preset": "next30"}},
        {"name": "  Big deals  ", "tab": "deals", "layout": "board", "filters": {"sort": "value"}},
        {"name": "Clients missing an MSA", "tab": "clients", "layout": "list", "filters": {"missing": ["msa"]}},
    ]
    created = []
    for body in bodies:
        r = await api.post("/pipeline/views", headers=AS_REP, json=body)
        assert r.status_code == 201, r.text
        created.append(r.json())
    assert created[1]["name"] == "Big deals"
    assert created[0]["filters"] == bodies[0]["filters"]
    assert {c["tab"] for c in created} == {"deals", "clients"}

    dup = await api.post("/pipeline/views", headers=AS_REP, json={**bodies[0], "name": "CLOSING SOON"})
    assert dup.status_code == 409
    assert dup.json() == {"detail": "You already have a view with this name."}

    listed = (await api.get("/pipeline/views", headers=AS_REP)).json()
    assert [v["name"] for v in listed] == ["Closing soon", "Big deals", "Clients missing an MSA"]
    assert listed[2] == {"id": created[2]["id"], "name": "Clients missing an MSA", "tab": "clients",
                         "layout": "list", "filters": {"missing": ["msa"]}}

    # Someone else cannot see or delete them.
    assert (await api.get("/pipeline/views", headers=AS_OTHER)).json() == []
    assert (await api.delete(f"/pipeline/views/{created[0]['id']}", headers=AS_OTHER)).status_code == 404
    # Another user may use the same name.
    assert (await api.post("/pipeline/views", headers=AS_OTHER, json=bodies[0])).status_code == 201

    assert (await api.delete(f"/pipeline/views/{created[0]['id']}", headers=AS_REP)).status_code == 204
    assert (await api.delete(f"/pipeline/views/{created[0]['id']}", headers=AS_REP)).status_code == 404
    assert [v["name"] for v in (await api.get("/pipeline/views", headers=AS_REP)).json()] == [
        "Big deals", "Clients missing an MSA"]
    # The deleted name is free again.
    assert (await api.post("/pipeline/views", headers=AS_REP, json=bodies[0])).status_code == 201

    session.expire_all()
    rows = (await session.execute(
        select(SavedView.owner_id, SavedView.key).where(SavedView.is_builtin.is_(False))
    )).all()
    assert {(o, k) for o, k in rows} == {(world["rep"], "pipeline"), (world["other"], "pipeline")}
    assert (await _actions(session, "saved_view")).count("saved_view.created") == 5
    assert "saved_view.archived" in await _actions(session, "saved_view")


async def test_saved_view_name_is_required_and_bounded(api, world):
    for name in ("", "   "):
        r = await api.post("/pipeline/views", headers=AS_REP,
                           json={"name": name, "tab": "deals", "layout": "list", "filters": {}})
        assert r.status_code == 422
        assert r.json()["detail"] == "Enter a name for this view."
    r = await api.post("/pipeline/views", headers=AS_REP,
                       json={"name": "x" * 61, "tab": "deals", "layout": "list", "filters": {}})
    assert r.status_code == 422
    r = await api.post("/pipeline/views", headers=AS_REP,
                       json={"name": "Bad tab", "tab": "people", "layout": "list", "filters": {}})
    assert r.status_code == 422


async def test_groups_create_add_remove_and_duplicate(api, session, world):
    d0, d1, d2 = (str(d) for d in world["deals"])
    r = await api.post("/pipeline/groups", headers=AS_REP, json={"name": "Key accounts", "deal_ids": [d0]})
    assert r.status_code == 201, r.text
    group = r.json()
    assert group["name"] == "Key accounts" and group["deal_ids"] == [d0]

    dup = await api.post("/pipeline/groups", headers=AS_REP, json={"name": "key ACCOUNTS"})
    assert dup.status_code == 409
    assert dup.json() == {"detail": "A group with this name already exists."}
    blank = await api.post("/pipeline/groups", headers=AS_REP, json={"name": "  "})
    assert blank.status_code == 422 and blank.json()["detail"] == "Enter a group name."

    r = await api.put(f"/pipeline/groups/{group['id']}/deals", headers=AS_REP, json={"deal_ids": [d1, d2, d0]})
    assert r.status_code == 204, r.text
    listed = (await api.get("/pipeline/groups", headers=AS_REP)).json()
    assert [(g["name"], sorted(g["deal_ids"])) for g in listed] == [("Key accounts", sorted([d0, d1, d2]))]

    # Removal by query string (a proxy may drop a DELETE body) and by body.
    r = await api.delete(f"/pipeline/groups/{group['id']}/deals", headers=AS_REP, params={"deal_ids": [d1]})
    assert r.status_code == 204, r.text
    r = await api.request("DELETE", f"/pipeline/groups/{group['id']}/deals", headers=AS_REP,
                          json={"deal_ids": [d2]})
    assert r.status_code == 204, r.text
    listed = (await api.get("/pipeline/groups", headers=AS_REP)).json()
    assert listed[0]["deal_ids"] == [d0]

    # Not someone else's group, not an unknown deal.
    assert (await api.put(f"/pipeline/groups/{group['id']}/deals", headers=AS_OTHER,
                          json={"deal_ids": [d1]})).status_code == 404
    assert (await api.put(f"/pipeline/groups/{group['id']}/deals", headers=AS_REP,
                          json={"deal_ids": [str(uuid.uuid4())]})).status_code == 404
    assert (await api.get("/pipeline/groups", headers=AS_OTHER)).json() == []
    # The same name is fine for another user.
    assert (await api.post("/pipeline/groups", headers=AS_OTHER, json={"name": "Key accounts"})).status_code == 201

    session.expire_all()
    owner = await session.scalar(select(TrackingGroup.owner_id).where(TrackingGroup.id == uuid.UUID(group["id"])))
    assert owner == world["rep"]
    added_by = set((await session.scalars(select(TrackingGroupMember.added_by))).all())
    assert added_by == {world["rep"]}
    actions = await _actions(session, "tracking_group")
    assert {"tracking_group.created", "tracking_group.members_added", "tracking_group.members_removed"} <= set(actions)


async def test_group_lists_only_deals_the_caller_can_see(api, session, world):
    d0, d1, _ = (str(d) for d in world["deals"])
    r = await api.post("/pipeline/groups", headers=AS_REP, json={"name": "Watch list", "deal_ids": [d0, d1]})
    assert r.status_code == 201
    deal = await session.get(Opportunity, world["deals"][1])
    from datetime import UTC, datetime
    deal.archived_at = datetime.now(UTC)
    await session.commit()
    listed = (await api.get("/pipeline/groups", headers=AS_REP)).json()
    assert listed[0]["deal_ids"] == [d0]


async def test_watching_is_idempotent_and_keyed_on_the_deal(api, session, world):
    deal = str(world["deals"][2])
    for _ in range(2):
        assert (await api.put(f"/pipeline/watching/{deal}", headers=AS_REP)).status_code == 204
    session.expire_all()
    rows = (await session.execute(select(WatchedItem.user_id, WatchedItem.kind, WatchedItem.item_id))).all()
    assert rows == [(world["rep"], "opportunity", world["deals"][2])]
    for _ in range(2):
        assert (await api.delete(f"/pipeline/watching/{deal}", headers=AS_REP)).status_code == 204
    session.expire_all()
    assert (await session.execute(select(WatchedItem.id))).all() == []
    assert (await api.put(f"/pipeline/watching/{uuid.uuid4()}", headers=AS_REP)).status_code == 404
    assert (await api.delete(f"/pipeline/watching/{uuid.uuid4()}", headers=AS_REP)).status_code == 404
    assert await _actions(session, "watched_item") == ["watch.added", "watch.removed"]


async def test_a_signed_in_user_without_a_row_has_an_empty_workspace(api, world, monkeypatch):
    headers = {"X-Test-User": "first.visit@example.test"}
    assert (await api.get("/pipeline/views", headers=headers)).json() == []
    assert (await api.get("/pipeline/groups", headers=headers)).json() == []


@pytest.mark.parametrize("method,path,body", [
    ("GET", "/pipeline/views", None),
    ("POST", "/pipeline/views", {"name": "V", "tab": "deals", "layout": "list", "filters": {}}),
    ("DELETE", "/pipeline/views/{view}", None),
    ("GET", "/pipeline/groups", None),
    ("POST", "/pipeline/groups", {"name": "G"}),
    ("PUT", "/pipeline/groups/{group}/deals", {"deal_ids": ["{deal}"]}),
    ("DELETE", "/pipeline/groups/{group}/deals", {"deal_ids": ["{deal}"]}),
    ("PUT", "/pipeline/watching/{deal}", None),
    ("DELETE", "/pipeline/watching/{deal}", None),
])
async def test_personal_routes_require_a_pipeline_role(api, world, monkeypatch, method, path, body):
    view = (await api.post("/pipeline/views", headers=AS_REP,
                           json={"name": "V0", "tab": "deals", "layout": "list", "filters": {}})).json()["id"]
    group = (await api.post("/pipeline/groups", headers=AS_REP, json={"name": "G0"})).json()["id"]
    deal = str(world["deals"][0])
    url = path.format(view=view, group=group, deal=deal)
    payload = None if body is None else {
        k: ([deal] if isinstance(v, list) else v) for k, v in body.items()}
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    r = await api.request(method, url, headers=AS_REP, json=payload)
    assert r.status_code == 403, r.text


async def test_a_concurrent_duplicate_name_is_the_same_409(api, world, monkeypatch):
    """The pre-check can lose a race; the case-insensitive unique index then decides."""
    body = {"name": "Closing soon", "tab": "deals", "layout": "list", "filters": {}}
    assert (await api.post("/pipeline/views", headers=AS_REP, json=body)).status_code == 201
    assert (await api.post("/pipeline/groups", headers=AS_REP, json={"name": "Key accounts"})).status_code == 201
    monkeypatch.setattr(saved_view_service, "_name_taken", AsyncMock(return_value=False))
    monkeypatch.setattr(tracking_group_service, "_name_taken", AsyncMock(return_value=False))
    r = await api.post("/pipeline/views", headers=AS_REP, json={**body, "name": "CLOSING soon"})
    assert (r.status_code, r.json()) == (409, {"detail": "You already have a view with this name."})
    r = await api.post("/pipeline/groups", headers=AS_REP, json={"name": "key accounts"})
    assert (r.status_code, r.json()) == (409, {"detail": "A group with this name already exists."})


# --- the same on PostgreSQL ------------------------------------------------------
# lower() unique indexes, savepoints and the IntegrityError text are
# dialect-sensitive. Runs only with DEALGATE_POSTGRES_URL (a migrated database);
# everything happens inside one outer transaction that is rolled back.

_PG_URL = os.environ.get("DEALGATE_POSTGRES_URL")
needs_postgres = pytest.mark.skipif(not _PG_URL, reason="requires postgres; set DEALGATE_POSTGRES_URL to run")


def _pg_async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest_asyncio.fixture
async def pg_api():
    """The app on Postgres; each app commit is a savepoint inside one rolled-back transaction."""
    if not _PG_URL:
        pytest.skip("requires postgres; set DEALGATE_POSTGRES_URL to run")
    engine = create_async_engine(_pg_async_url(_PG_URL))
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            factory = async_sessionmaker(bind=conn, expire_on_commit=False, class_=AsyncSession,
                                         join_transaction_mode="create_savepoint")

            async def _session():
                async with factory() as s:
                    yield s

            main_app.dependency_overrides[get_session] = _session
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=main_app, raise_app_exceptions=False),
                    base_url="http://t",
                ) as client:
                    yield client, factory
            finally:
                main_app.dependency_overrides.pop(get_session, None)
                await outer.rollback()
    finally:
        await engine.dispose()


@needs_postgres
async def test_postgres_personal_workspace_for_a_hubspot_created_user(pg_api, monkeypatch):
    api, factory = pg_api
    tag = uuid.uuid4().hex[:8]
    email = f"pg.rep.{tag}@example.test"
    async with factory() as s:
        rep = User(id=uuid.uuid4(), email=email, name="PG Rep", groups=[])
        client = Client(name=f"PG client {tag}", hubspot_company_id=f"pg-c-{tag}")
        s.add_all([rep, client])
        await s.flush()
        deal = Opportunity(source="hubspot", hubspot_deal_id=f"pg-d-{tag}", name="PG deal", owner_id=rep.id,
                           client_id=client.id, amount=Decimal("1000.00"), currency="USD",
                           close_date=date(2026, 11, 1))
        s.add(deal)
        await s.commit()
        rep_id, deal_id = rep.id, str(deal.id)
    headers = {"X-Test-User": email}

    # The old routes (built-in seeding, repeated star) on the DealGate id.
    assert (await api.get("/saved-views", headers=headers)).status_code == 200
    for _ in range(2):
        r = await api.post("/watchlist", headers=headers, json={"kind": "opportunity", "item_id": deal_id})
        assert r.status_code == 201, r.text

    body = {"tab": "deals", "layout": "list", "filters": {"status": "open"}}
    for name in ("Closing soon", "Big deals", "Third view"):
        r = await api.post("/pipeline/views", headers=headers, json={**body, "name": name})
        assert r.status_code == 201, r.text
    dup = await api.post("/pipeline/views", headers=headers, json={**body, "name": "closing SOON"})
    assert (dup.status_code, dup.json()) == (409, {"detail": "You already have a view with this name."})
    r = await api.post("/pipeline/groups", headers=headers, json={"name": "Key accounts", "deal_ids": [deal_id]})
    assert r.status_code == 201, r.text
    dup = await api.post("/pipeline/groups", headers=headers, json={"name": "KEY accounts"})
    assert (dup.status_code, dup.json()) == (409, {"detail": "A group with this name already exists."})
    with monkeypatch.context() as m:
        m.setattr(saved_view_service, "_name_taken", AsyncMock(return_value=False))
        m.setattr(tracking_group_service, "_name_taken", AsyncMock(return_value=False))
        race = await api.post("/pipeline/views", headers=headers, json={**body, "name": "BIG deals"})
        assert (race.status_code, race.json()) == (409, {"detail": "You already have a view with this name."})
        race = await api.post("/pipeline/groups", headers=headers, json={"name": "key ACCOUNTS"})
        assert (race.status_code, race.json()) == (409, {"detail": "A group with this name already exists."})
    for _ in range(2):
        assert (await api.put(f"/pipeline/watching/{deal_id}", headers=headers)).status_code == 204
    assert [v["name"] for v in (await api.get("/pipeline/views", headers=headers)).json()] == [
        "Closing soon", "Big deals", "Third view"]
    assert (await api.get("/pipeline/groups", headers=headers)).json()[0]["deal_ids"] == [deal_id]

    async with factory() as s:
        owners = set((await s.scalars(select(SavedView.owner_id).where(SavedView.owner_id.in_(
            [rep_id, _login_id(email)])))).all())
        watchers = set((await s.scalars(select(WatchedItem.user_id).where(
            WatchedItem.item_id == uuid.UUID(deal_id)))).all())
    assert owners == {rep_id} and watchers == {rep_id}
