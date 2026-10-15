"""S23-PL2 B12 — Sales-only users can open the client pages the Pipeline links to.

The Pipeline lists every client to Sales, and a row opens ``/clients/:id``.
The client page used to answer 403 unless the caller owned one of the client's
deals. Sales now reads client pages like Presales; fixture scoping still hides
test clients from everyone else.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.main import app as main_app
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User

SALES = {"X-Test-User": "sales.only@example.test"}


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


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
async def someone_elses_client(session) -> uuid.UUID:
    owner = User(id=uuid.uuid4(), email="owner@example.test", name="Deal Owner", groups=["Sales"])
    client = Client(name="Meridian Partners", hubspot_company_id="c-meridian")
    session.add_all([owner, client])
    await session.flush()
    session.add(Opportunity(source="hubspot", hubspot_deal_id="d-meridian", name="Application support",
                            owner_id=owner.id, client_id=client.id, amount=Decimal("404000.00"),
                            currency="USD", close_date=date(2026, 12, 10)))
    await session.commit()
    return client.id


async def test_sales_only_user_reads_a_client_whose_deals_someone_else_owns(api, someone_elses_client):
    r = await api.get(f"/clients/{someone_elses_client}", headers=SALES)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Meridian Partners"
    assert [o["hubspot_deal_id"] for o in body["opportunities"]] == ["d-meridian"]
    # The Pipeline's own client tab already answered for Sales; it still does.
    r = await api.get("/pipeline/clients", headers=SALES)
    assert r.status_code == 200, r.text


async def test_a_role_without_client_access_is_still_refused(api, someone_elses_client, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
    r = await api.get(f"/clients/{someone_elses_client}", headers=SALES)
    assert r.status_code == 403


async def test_an_unknown_client_is_still_404_for_sales(api, someone_elses_client):
    r = await api.get(f"/clients/{uuid.uuid4()}", headers=SALES)
    assert r.status_code == 404
