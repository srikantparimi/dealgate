"""S23-PL2 T4 / B4 — a DealGate user is linked to their HubSpot owner.

Automatic link: exact email equality, case-insensitive (HubSpot and Cognito
casing differ), active owners only, never an ambiguous or already-claimed
owner, only while the link is undecided — at login (``ensure_user``) and in
bulk once the owner-mirror sync has committed (its own transaction). Admin override and unlink through
``PUT /users/{id}/hubspot-owner``; an admin decision is never undone by the
automatic link. ``mine=true`` on the workspace filters on the link.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.integrations.hubspot import StubHubSpotClient
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_owners import HubspotOwner, link_all_by_email, sync_owner_mirror
from tests.test_s23_pl2_personal import needs_postgres, pg_api  # noqa: F401 — shared Postgres fixture

REP = "rita.rep@example.test"
ADMIN = "admin@example.test"
AS_REP = {"X-Test-User": REP}
AS_ADMIN = {"X-Test-User": ADMIN}


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


@pytest_asyncio.fixture
async def mirror(session):
    session.add_all([
        # HubSpot's casing differs from the sign-in email on purpose.
        HubspotOwner(id="o-rep", email="Rita.Rep@Example.test", first_name="Rita", last_name="Rep", archived=False),
        HubspotOwner(id="o-other", email="otto.other@example.test", first_name="Otto", last_name="Other",
                     archived=False),
        HubspotOwner(id="o-gone", email="gus.gone@example.test", first_name="Gus", last_name="Gone", archived=True),
        HubspotOwner(id="o-twin-1", email="twin@example.test", first_name="Twin", last_name="One", archived=False),
        HubspotOwner(id="o-twin-2", email="TWIN@example.test", first_name="Twin", last_name="Two", archived=False),
    ])
    await session.commit()


async def _hubspot_created_user(session, email: str, name: str) -> uuid.UUID:
    """The row HubSpot intake writes for a deal owner: fresh uuid4, no groups."""
    user = User(id=uuid.uuid4(), email=email, name=name, groups=[])
    session.add(user)
    await session.commit()
    return user.id


async def _user(session, user_id: uuid.UUID) -> User:
    session.expire_all()
    return await session.get(User, user_id)


async def _audits(session, action: str) -> list[AuditEvent]:
    session.expire_all()
    return list((await session.scalars(select(AuditEvent).where(AuditEvent.action == action))).all())


async def test_login_links_a_hubspot_created_user_by_email(api, session, mirror):
    rep_id = await _hubspot_created_user(session, REP, "Rita Rep")
    assert rep_id != _login_id(REP)

    r = await api.get("/me", headers=AS_REP)
    assert r.status_code == 200, r.text
    assert r.json()["id"] == str(rep_id)

    rep = await _user(session, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == ("o-rep", "email")
    assert rep.hubspot_owner_linked_at is not None
    [event] = await _audits(session, "user.hubspot_owner_linked")
    assert event.entity_id == str(rep_id)
    assert event.after["hubspot_owner_id"] == "o-rep"
    assert event.after["source"] == "email"

    # Signing in again changes nothing and writes nothing.
    assert (await api.get("/me", headers=AS_REP)).status_code == 200
    assert len(await _audits(session, "user.hubspot_owner_linked")) == 1


async def test_a_first_login_links_the_new_row_too(api, session, mirror):
    r = await api.get("/me", headers={"X-Test-User": "otto.other@example.test"})
    assert r.status_code == 200, r.text
    otto = await _user(session, _login_id("otto.other@example.test"))
    assert (otto.hubspot_owner_id, otto.hubspot_owner_link) == ("o-other", "email")


@pytest.mark.parametrize("email", [
    "twin@example.test",        # two active owners share the address
    "gus.gone@example.test",    # the only match is archived
    "nobody@example.test",      # no owner at all
])
async def test_no_automatic_link_without_exactly_one_active_owner(api, session, mirror, email):
    assert (await api.get("/me", headers={"X-Test-User": email})).status_code == 200
    user = await _user(session, _login_id(email))
    assert (user.hubspot_owner_id, user.hubspot_owner_link) == (None, None)
    assert await _audits(session, "user.hubspot_owner_linked") == []


async def test_an_owner_claimed_by_someone_else_is_not_linked_again(api, session, mirror):
    session.add(User(id=uuid.uuid4(), email="someone@example.test", name="Someone Else", groups=["Sales"],
                     hubspot_owner_id="o-other", hubspot_owner_link="admin"))
    await session.commit()
    assert (await api.get("/me", headers={"X-Test-User": "otto.other@example.test"})).status_code == 200
    otto = await _user(session, _login_id("otto.other@example.test"))
    assert (otto.hubspot_owner_id, otto.hubspot_owner_link) == (None, None)


class _OwnersStub(StubHubSpotClient):
    def __init__(self, active: list[dict[str, Any]], archived: list[dict[str, Any]]) -> None:
        super().__init__()
        self._active, self._archived = active, archived

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: SLF001
        assert path == "/crm/v3/owners"
        archived = str((params or {}).get("archived", "false")).lower() == "true"
        return {"results": self._archived if archived else self._active}


async def _owner_sync(session, stub) -> None:
    """What the backfill runs: the mirror commits, then the bulk link in a transaction of its own."""
    await sync_owner_mirror(session, stub)
    await session.commit()
    await link_all_by_email(session)
    await session.commit()


async def test_owner_sync_links_every_undecided_user(session):
    rep_id = await _hubspot_created_user(session, REP, "Rita Rep")
    decided = User(id=uuid.uuid4(), email="otto.other@example.test", name="Otto Other", groups=["Sales"],
                   hubspot_owner_link="admin")  # an admin said "no owner": never auto-linked
    session.add(decided)
    await session.commit()
    decided_id = decided.id
    stub = _OwnersStub(
        active=[{"id": "o-rep", "email": "RITA.REP@example.test", "firstName": "Rita", "lastName": "Rep"},
                {"id": "o-other", "email": "otto.other@example.test", "firstName": "Otto", "lastName": "Other"}],
        archived=[],
    )
    await _owner_sync(session, stub)
    rep = await _user(session, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == ("o-rep", "email")
    otto = await _user(session, decided_id)
    assert (otto.hubspot_owner_id, otto.hubspot_owner_link) == (None, "admin")
    assert [e.entity_id for e in await _audits(session, "user.hubspot_owner_linked")] == [str(rep_id)]

    # A second run is a no-op.
    await _owner_sync(session, stub)
    assert len(await _audits(session, "user.hubspot_owner_linked")) == 1


async def test_admin_override_conflict_and_unlink(api, session, mirror, monkeypatch):
    rep_id = await _hubspot_created_user(session, REP, "Rita Rep")
    otto = User(id=uuid.uuid4(), email="otto.other@example.test", name="Otto Other", groups=["Sales"],
                hubspot_owner_id="o-other", hubspot_owner_link="email")
    session.add(otto)
    await session.commit()
    otto_id = otto.id
    assert (await api.get("/me", headers=AS_REP)).status_code == 200  # auto-linked to o-rep

    url = f"/users/{rep_id}/hubspot-owner"
    # Only a SystemAdmin may override.
    assert (await api.put(url, headers=AS_REP, json={"hubspot_owner_id": "o-gone"})).status_code == 403

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    r = await api.put(url, headers=AS_ADMIN, json={"hubspot_owner_id": "o-gone"})  # a former owner is allowed
    assert r.status_code == 204, r.text
    rep = await _user(session, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == ("o-gone", "admin")
    [event] = await _audits(session, "user.hubspot_owner_overridden")
    assert event.before == {"hubspot_owner_id": "o-rep", "hubspot_owner_link": "email"}
    assert event.after == {"hubspot_owner_id": "o-gone", "hubspot_owner_link": "admin"}
    assert event.actor_id == _login_id(ADMIN)

    taken = await api.put(url, headers=AS_ADMIN, json={"hubspot_owner_id": "o-other"})
    assert taken.status_code == 409
    assert "Otto Other" in taken.json()["detail"]
    assert str(otto_id) not in taken.json()["detail"]

    assert (await api.put(url, headers=AS_ADMIN, json={"hubspot_owner_id": "no-such-owner"})).status_code == 422
    assert (await api.put(f"/users/{uuid.uuid4()}/hubspot-owner", headers=AS_ADMIN,
                          json={"hubspot_owner_id": "o-rep"})).status_code == 404
    assert (await api.put(url, headers=AS_ADMIN, json={})).status_code == 422

    r = await api.put(url, headers=AS_ADMIN, json={"hubspot_owner_id": None})
    assert r.status_code == 204, r.text
    rep = await _user(session, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (None, "admin")
    assert len(await _audits(session, "user.hubspot_owner_overridden")) == 2

    # The automatic link never undoes an admin's decision.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    assert (await api.get("/me", headers=AS_REP)).status_code == 200
    rep = await _user(session, rep_id)
    assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (None, "admin")


async def test_admin_lists_show_the_link_and_the_owner_picker(api, session, mirror, monkeypatch):
    rep_id = await _hubspot_created_user(session, REP, "Rita Rep")
    assert (await api.get("/me", headers=AS_REP)).status_code == 200

    assert (await api.get("/admin/hubspot-owners", headers=AS_REP)).status_code == 403
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    assert (await api.get("/me", headers=AS_ADMIN)).status_code == 200  # the admin's own row
    users = (await api.get("/admin/users", headers=AS_ADMIN)).json()["items"]
    row = next(u for u in users if u["id"] == str(rep_id))
    assert {k: row[k] for k in ("hubspot_owner_id", "hubspot_owner_name", "hubspot_owner_state",
                                "hubspot_owner_link")} == {
        "hubspot_owner_id": "o-rep", "hubspot_owner_name": "Rita Rep",
        "hubspot_owner_state": "active", "hubspot_owner_link": "email"}
    admin_row = next(u for u in users if u["email"] == ADMIN)
    assert (admin_row["hubspot_owner_id"], admin_row["hubspot_owner_state"]) == (None, "none")

    owners = (await api.get("/admin/hubspot-owners", headers=AS_ADMIN)).json()
    by_id = {o["id"]: o for o in owners}
    assert by_id["o-rep"] == {"id": "o-rep", "name": "Rita Rep", "email": "Rita.Rep@Example.test",
                              "archived": False, "linked_user_id": str(rep_id), "linked_user_name": "Rita Rep"}
    assert by_id["o-gone"]["archived"] is True and by_id["o-gone"]["linked_user_id"] is None
    # Active owners first, each group by name.
    assert [o["archived"] for o in owners] == sorted(o["archived"] for o in owners)


# --- mine=true on the workspace (lane L1's endpoint) ---------------------------


async def _deals_for_mine(session) -> dict[str, list[uuid.UUID]]:
    session.add(HubspotPipeline(id="p1", label="Global sales pipeline", display_order=0, archived=False))
    await session.flush()
    session.add(HubspotStage(id="s2", pipeline_id="p1", label="2-Qualification", display_order=1,
                             is_closed=False, probability=Decimal("0.20"), archived=False))
    client = Client(name="Keystone Energy", hubspot_company_id="c-1")
    session.add(client)
    await session.flush()
    out: dict[str, list[uuid.UUID]] = {"o-rep": [], "o-other": []}
    for owner, n in (("o-rep", 2), ("o-other", 1)):
        for i in range(n):
            deal = Opportunity(source="hubspot", hubspot_deal_id=f"{owner}-{i}", name=f"{owner} deal {i}",
                               client_id=client.id, hubspot_owner_id=owner, amount=Decimal("1000.00"),
                               currency="USD", close_date=date(2026, 12, 1), hubspot_pipeline_id="p1",
                               hubspot_stage_id="s2", stage_label="2-Qualification", stage_order=1)
            session.add(deal)
            await session.flush()
            out[owner].append(deal.id)
    await session.commit()
    return out


async def test_workspace_mine_follows_the_link(api, session, mirror):
    deals = await _deals_for_mine(session)
    await _hubspot_created_user(session, REP, "Rita Rep")
    assert (await api.get("/me", headers=AS_REP)).status_code == 200

    r = await api.get("/pipeline/workspace", headers=AS_REP, params={"mine": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {row["id"] for row in body["rows"]} == {str(d) for d in deals["o-rep"]}
    assert body["focus"]["mine_available"] is True
    assert body["focus"]["mine"] == 2


async def test_workspace_mine_without_a_link(api, session, mirror):
    await _deals_for_mine(session)
    headers = {"X-Test-User": "nobody@example.test"}
    assert (await api.get("/me", headers=headers)).status_code == 200
    r = await api.get("/pipeline/workspace", headers=headers, params={"mine": "true"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["focus"]["mine_available"] is False
    assert body["focus"]["mine"] is None


@needs_postgres
async def test_postgres_email_link_ignores_case_and_admin_override(pg_api, monkeypatch):  # noqa: F811
    api, factory = pg_api
    tag = uuid.uuid4().hex[:8]
    email = f"pg.rita.{tag}@example.test"
    async with factory() as s:
        s.add_all([
            HubspotOwner(id=f"pg-o-{tag}", email=f"PG.Rita.{tag}@Example.test", first_name="Pg", last_name="Rita",
                         archived=False),
            HubspotOwner(id=f"pg-x-{tag}", email=f"pg.other.{tag}@example.test", first_name="Pg", last_name="Other",
                         archived=True),
        ])
        rep = User(id=uuid.uuid4(), email=email, name="Pg Rita", groups=[])
        s.add(rep)
        await s.commit()
        rep_id = rep.id
    assert (await api.get("/me", headers={"X-Test-User": email})).status_code == 200
    async with factory() as s:
        rep = await s.get(User, rep_id)
        assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (f"pg-o-{tag}", "email")

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    admin = {"X-Test-User": f"pg.admin.{tag}@example.test"}
    r = await api.put(f"/users/{rep_id}/hubspot-owner", headers=admin, json={"hubspot_owner_id": f"pg-x-{tag}"})
    assert r.status_code == 204, r.text
    async with factory() as s:
        rep = await s.get(User, rep_id)
        await s.refresh(rep)
        assert (rep.hubspot_owner_id, rep.hubspot_owner_link) == (f"pg-x-{tag}", "admin")
