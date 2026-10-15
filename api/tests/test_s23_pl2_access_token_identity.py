"""S23-PL2 · pre-merge review R1 · a HubSpot-created or invited user signed in with a Cognito
ACCESS token (the web app's token, which carries no email) keeps their views, groups, watches,
"My opportunities" and next-action rights.

In production ``_user_from_claims`` maps an access token to AuthUser(id=sub, email=sub). Writes
resolve the user's DealGate row by asking Cognito for the email (``ensure_user``) and adopt the
row created by intake or invite, whose id is not the sub. Reads must find the same row: before
this fix they matched ``User.id == sub OR User.email == sub`` and found nothing, so a saved view
vanished on reload. The fix stores the sub on the adopted row and resolves reads by it, with the
same Cognito lookup as ensure_user (cached) before the first write.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import current_user
from app.auth.deps import _user_from_claims
from app.db import get_session
from app.main import app as main_app
from app.models.client import Client
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import canonical_user, user_provisioning
from app.services.hubspot_owners import HubspotOwner

REP = "rep.from.hubspot@example.test"
SUB = uuid.UUID("5b0c3f6e-1111-4c2a-9d11-0000000000aa")


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture
def cognito(monkeypatch):
    """Cognito's AdminGetUser as ensure_user sees it on staging: the sub's real email."""

    calls: list[str] = []

    def fake_hydrate(sub: str):
        calls.append(sub)
        return (REP, "Rep From HubSpot") if sub == str(SUB) else (None, None)

    monkeypatch.setattr(user_provisioning, "hydrate_from_cognito", fake_hydrate)
    monkeypatch.setenv("DEALGATE_ENV", "local")
    getattr(canonical_user, "_EMAIL_BY_SUB", {}).clear()
    yield calls
    getattr(canonical_user, "_EMAIL_BY_SUB", {}).clear()


@pytest_asyncio.fixture
async def world(session):
    # Created the way HubSpot intake creates deal owners: a fresh uuid4, the owner's email, no groups.
    rep = User(id=uuid.uuid4(), email=REP, name="Rep From HubSpot", groups=[])
    client = Client(name="Keystone Energy", hubspot_company_id="c-1")
    session.add_all([rep, client, HubspotOwner(id="777", email=REP, first_name="Rep", last_name="One", archived=False)])
    await session.flush()
    deals = [
        Opportunity(source="hubspot", hubspot_deal_id=f"d-{i}", name=f"Deal {i}", owner_id=rep.id,
                    hubspot_owner_id="777", client_id=client.id, amount=Decimal("1000.00"), currency="USD",
                    close_date=date(2026, 11, 1), is_closed_won=False, is_closed_lost=False)
        for i in range(3)
    ]
    session.add_all(deals)
    await session.flush()
    action = NextAction(opportunity_id=deals[0].id, title="Call the buyer", description="Call the buyer", owner_user_id=rep.id,
                        assignee_user_id=rep.id, created_by=rep.id, status="open")
    session.add(action)
    await session.commit()
    assert rep.id != SUB
    return {"rep": rep.id, "deals": [d.id for d in deals], "action": action.id}


@pytest_asyncio.fixture
async def api(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _session():
        async with factory() as s:
            yield s

    # Exactly what the API builds from the web app's Cognito access token.
    actor = _user_from_claims({"sub": str(SUB), "username": str(SUB), "token_use": "access",
                               "cognito:groups": ["Sales"]})
    assert actor.id == SUB and actor.email == str(SUB)
    main_app.dependency_overrides[get_session] = _session
    main_app.dependency_overrides[current_user] = lambda: actor
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_app, raise_app_exceptions=False), base_url="http://t",
        ) as c:
            yield c
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(current_user, None)


async def test_reads_find_the_adopted_row_before_and_after_the_first_write(api, session, world, cognito):
    deal = str(world["deals"][0])

    # Before any write: the read path finds the HubSpot-created row the way ensure_user would.
    ws = (await api.get("/pipeline/workspace")).json()
    assert ws["focus"]["mine_available"] is True and ws["focus"]["mine"] == 3
    actions = (await api.get("/next-actions", params={"opportunity_id": deal})).json()["items"]
    assert [(a["title"], a["can_edit"]) for a in actions] == [("Call the buyer", True)]
    assert cognito, "the first read asked Cognito for the login's email"

    # Writes adopt the same row; every one reads back.
    r = await api.post("/pipeline/views", json={"name": "Mine", "tab": "deals", "layout": "list", "filters": {}})
    assert r.status_code == 201, r.text
    assert [v["name"] for v in (await api.get("/pipeline/views")).json()] == ["Mine"]
    assert (await api.put(f"/pipeline/watching/{deal}")).status_code == 204
    ws = (await api.get("/pipeline/workspace")).json()
    assert ws["focus"]["watching"] == 1
    assert {row["id"]: row["watching"] for row in ws["rows"]}[deal] is True
    r = await api.post("/pipeline/groups", json={"name": "Key deals", "deal_ids": [deal]})
    assert r.status_code == 201, r.text
    assert [g["name"] for g in (await api.get("/pipeline/groups")).json()] == ["Key deals"]
    r = await api.put("/user-preferences/s23.check", json={"value": {"on": True}})
    assert r.status_code == 200, r.text
    assert (await api.get("/user-preferences/s23.check")).status_code == 200

    # The adopted row now remembers the login, so reads no longer need Cognito.
    session.expire_all()
    rep = await session.get(User, world["rep"])
    assert rep.cognito_sub == str(SUB)
    assert (await session.scalar(select(User).where(User.id == SUB))) is None, "no second row for the login"
    cognito.clear()
    getattr(canonical_user, "_EMAIL_BY_SUB", {}).clear()
    assert [v["name"] for v in (await api.get("/pipeline/views")).json()] == ["Mine"]
    assert (await api.get("/pipeline/workspace")).json()["focus"]["watching"] == 1
    assert cognito == [], "resolved by the stored login, without Cognito"


async def test_an_unknown_login_reads_as_nobody_and_writes_create_its_own_row(api, session, world, cognito, monkeypatch):
    monkeypatch.setattr(user_provisioning, "hydrate_from_cognito", lambda sub: (None, None))
    getattr(canonical_user, "_EMAIL_BY_SUB", {}).clear()
    ws = (await api.get("/pipeline/workspace")).json()
    assert ws["focus"]["mine_available"] is False and ws["focus"]["watching"] == 0
    assert (await api.get("/pipeline/views")).json() == []
