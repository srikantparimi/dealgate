"""S2-E3 acceptance tests — client page, opportunity->client link,
HubSpot intake now upserts a client + entity, deals list surfaces real
coverage_state instead of "No client linked".
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.integrations.hubspot import HubSpotClient, StubHubSpotClient, get_hubspot_client
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.clients import (
    ClientListFilters,
    coverage_state,
    get_client_detail,
    list_clients,
    upsert_client_from_hubspot,
    upsert_unknown_client_for_deal,
)
from app.services.hubspot_intake import handle_event


HUBSPOT_SECRET = "unit-test-secret"
WEBHOOK_URL = "https://dealgate.example.com/integrations/hubspot/webhook"
LEADER_EMAIL = "sales-leader@smartek21.com"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("HUBSPOT_APP_SECRET", HUBSPOT_SECRET)
    monkeypatch.setenv("HUBSPOT_WEBHOOK_URL", WEBHOOK_URL)
    monkeypatch.setenv("SALES_LEADER_EMAIL", LEADER_EMAIL)
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _fake_user_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


# --- pure coverage_state tests --------------------------------------------


def _ag(kind: str, effective: date | None, expiry: date | None) -> Agreement:
    # Build a lightweight stand-in — coverage_state only reads three fields.
    return SimpleNamespace(kind=kind, effective_date=effective, expiry_date=expiry)


def test_coverage_state_complete_when_both_kinds_executed():
    today = date(2026, 6, 1)
    ags = [
        _ag("NDA", date(2025, 1, 1), date(2027, 1, 1)),
        _ag("MSA", date(2025, 6, 1), date(2028, 6, 1)),
    ]
    assert coverage_state(ags, today=today) == "Complete"


def test_coverage_state_returns_nda_missing_when_only_msa_present():
    today = date(2026, 6, 1)
    ags = [_ag("MSA", date(2025, 6, 1), date(2028, 6, 1))]
    assert coverage_state(ags, today=today) == "NDA missing"


def test_coverage_state_returns_msa_missing_when_only_nda_present():
    today = date(2026, 6, 1)
    ags = [_ag("NDA", date(2025, 6, 1), date(2028, 6, 1))]
    assert coverage_state(ags, today=today) == "MSA missing"


def test_coverage_state_returns_combined_missing_when_none_present():
    today = date(2026, 6, 1)
    assert coverage_state([], today=today) == "NDA + MSA missing"


def test_coverage_state_returns_nda_expired_when_nda_expiry_past():
    today = date(2026, 6, 1)
    ags = [
        _ag("NDA", date(2024, 1, 1), date(2025, 12, 31)),
        _ag("MSA", date(2025, 6, 1), date(2028, 6, 1)),
    ]
    assert coverage_state(ags, today=today) == "NDA expired"


def test_coverage_state_returns_msa_expired_when_msa_expiry_past():
    today = date(2026, 6, 1)
    ags = [
        _ag("NDA", date(2025, 6, 1), date(2028, 6, 1)),
        _ag("MSA", date(2024, 1, 1), date(2025, 12, 31)),
    ]
    assert coverage_state(ags, today=today) == "MSA expired"


def test_coverage_state_returns_awaiting_signature_when_not_yet_effective():
    today = date(2026, 6, 1)
    ags = [
        _ag("NDA", None, date(2027, 1, 1)),
        _ag("MSA", date(2025, 6, 1), date(2028, 6, 1)),
    ]
    assert coverage_state(ags, today=today) == "Awaiting signature"


def test_coverage_state_prefers_freshest_agreement_of_each_kind():
    today = date(2026, 6, 1)
    ags = [
        _ag("NDA", date(2020, 1, 1), date(2021, 1, 1)),  # old & expired
        _ag("NDA", date(2025, 1, 1), date(2028, 1, 1)),  # freshest -> current
        _ag("MSA", date(2025, 6, 1), date(2028, 6, 1)),
    ]
    assert coverage_state(ags, today=today) == "Complete"


# --- upsert_client_from_hubspot -------------------------------------------


async def test_upsert_client_from_hubspot_creates_client_and_default_entity(session):
    payload = {
        "id": "COMP-1",
        "properties": {"name": "Acme Corp", "timezone": "America/Los_Angeles"},
    }
    client = await upsert_client_from_hubspot(session, company_payload=payload)
    await session.commit()

    assert client.name == "Acme Corp"
    assert client.hubspot_company_id == "COMP-1"
    assert client.timezone == "America/Los_Angeles"

    entities = (
        await session.execute(select(LegalEntity).where(LegalEntity.client_id == client.id))
    ).scalars().all()
    assert len(entities) == 1
    assert entities[0].name.endswith("(default)")

    audits = (
        await session.execute(select(AuditEvent))
    ).scalars().all()
    actions = {a.action for a in audits}
    assert "client.created" in actions
    assert "legal_entity.created" in actions


async def test_upsert_client_is_idempotent_on_replay(session):
    payload = {"id": "COMP-2", "properties": {"name": "Beta LLC"}}
    a = await upsert_client_from_hubspot(session, company_payload=payload)
    await session.commit()
    b = await upsert_client_from_hubspot(session, company_payload=payload)
    await session.commit()

    assert a.id == b.id
    clients = (await session.execute(select(Client))).scalars().all()
    entities = (await session.execute(select(LegalEntity))).scalars().all()
    assert len(clients) == 1
    assert len(entities) == 1


async def test_upsert_unknown_client_for_deal(session):
    client = await upsert_unknown_client_for_deal(session, deal_id="555")
    await session.commit()
    assert client.name == "Unknown company (deal 555)"
    assert client.hubspot_company_id == "unknown:deal:555"


# --- HubSpot intake flow now creates client + entity ----------------------


def _sign(body: bytes, timestamp: str) -> str:
    import base64
    import hashlib
    import hmac

    base = f"POST{WEBHOOK_URL}{body.decode('utf-8')}{timestamp}"
    return base64.b64encode(
        hmac.new(HUBSPOT_SECRET.encode(), base.encode(), hashlib.sha256).digest()
    ).decode()


def _headers(body: bytes) -> dict[str, str]:
    import time

    ts = str(int(time.time() * 1000))
    return {
        "X-HubSpot-Signature-v3": _sign(body, ts),
        "X-HubSpot-Request-Timestamp": ts,
        "Content-Type": "application/json",
    }


@pytest_asyncio.fixture
async def wired_intake_app(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as s:
            yield s

    deal_payload_with_company = {
        "id": "555",
        "properties": {
            "dealname": "Acme Governance Rollout",
            "dealstage": "qualifiedtobuy",
            "pipeline": "default",
            "hubspot_owner_id": "42",
            "engagement_type": "TM",
        },
        "associations": {
            "companies": {"results": [{"id": "COMP-777"}]},
        },
    }
    stub = StubHubSpotClient(
        deals={"555": deal_payload_with_company},
        owners={"42": {"id": "42", "email": "rep@smartek21.com", "firstName": "Rep", "lastName": "One"}},
        companies={
            "COMP-777": {
                "id": "COMP-777",
                "properties": {"name": "Acme Corp", "timezone": "America/New_York"},
            }
        },
    )

    def _override_client() -> HubSpotClient:
        return stub

    main_app.dependency_overrides[get_session] = _override_session
    main_app.dependency_overrides[get_hubspot_client] = _override_client
    try:
        yield main_app, factory, stub
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_hubspot_client, None)


async def test_hubspot_intake_upserts_client_entity_and_sets_client_id(wired_intake_app):
    app, factory, stub = wired_intake_app
    event = {
        "eventId": 1001,
        "subscriptionType": "deal.creation",
        "objectId": 555,
    }
    body = json.dumps([event]).encode()
    async with _client(app) as c:
        r = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
        assert r.status_code == 200

    async with factory() as s:
        from app.models.integration import IntegrationEvent

        event_row = (
            await s.execute(
                select(IntegrationEvent).where(IntegrationEvent.source_event_id == "1001")
            )
        ).scalar_one()
        await handle_event(s, event_row.payload, stub)

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
        clients = (await s.execute(select(Client))).scalars().all()
        entities = (await s.execute(select(LegalEntity))).scalars().all()
    assert opp.client_id is not None
    assert len(clients) == 1
    assert clients[0].name == "Acme Corp"
    assert clients[0].hubspot_company_id == "COMP-777"
    assert opp.client_id == clients[0].id
    assert len(entities) == 1
    assert entities[0].client_id == clients[0].id


async def test_hubspot_intake_falls_back_to_unknown_client_when_no_company(wired_intake_app):
    app, factory, stub = wired_intake_app
    # Strip company association so intake takes the "Unknown company" path.
    stub.deals["555"] = {
        "id": "555",
        "properties": {
            "dealname": "Solo Deal",
            "dealstage": "appointmentscheduled",
            "pipeline": "default",
            "hubspot_owner_id": "42",
            "engagement_type": None,
        },
    }
    event = {"eventId": 2002, "subscriptionType": "deal.creation", "objectId": 555}
    body = json.dumps([event]).encode()
    async with _client(app) as c:
        r = await c.post("/integrations/hubspot/webhook", content=body, headers=_headers(body))
        assert r.status_code == 200

    async with factory() as s:
        from app.models.integration import IntegrationEvent

        event_row = (
            await s.execute(
                select(IntegrationEvent).where(IntegrationEvent.source_event_id == "2002")
            )
        ).scalar_one()
        await handle_event(s, event_row.payload, stub)

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
        clients = (await s.execute(select(Client))).scalars().all()
    assert opp.client_id is not None
    assert len(clients) == 1
    assert clients[0].name == "Unknown company (deal 555)"


# --- GET /clients + /clients/{id} endpoint tests --------------------------


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
async def seeded_clients(session):
    """Two clients, one Sales user owns the first, another owns the second."""

    sales = User(email="sales@smartek21.com", name="Sales One", groups=["Sales"])
    sales.id = _fake_user_id("sales@smartek21.com")
    other = User(email="rep2@smartek21.com", name="Sales Two", groups=["Sales"])
    other.id = _fake_user_id("rep2@smartek21.com")
    ceo = User(email="ceo@smartek21.com", name="CEO", groups=["CEO"])
    ceo.id = _fake_user_id("ceo@smartek21.com")
    session.add_all([sales, other, ceo])
    await session.flush()

    acme = Client(id=uuid.uuid4(), name="Acme Corp", hubspot_company_id="COMP-1")
    beta = Client(id=uuid.uuid4(), name="Beta LLC", hubspot_company_id="COMP-2")
    session.add_all([acme, beta])
    await session.flush()

    acme_le = LegalEntity(
        id=uuid.uuid4(), client_id=acme.id, name="Acme Inc.", country="US"
    )
    beta_le = LegalEntity(
        id=uuid.uuid4(), client_id=beta.id, name="Beta Ltd.", country="GB"
    )
    session.add_all([acme_le, beta_le])
    await session.flush()

    # Acme has an executed NDA but no MSA -> "MSA missing".
    session.add(
        Agreement(
            id=uuid.uuid4(),
            legal_entity_id=acme_le.id,
            kind="NDA",
            effective_date=date(2025, 1, 1),
            expiry_date=date(2027, 1, 1),
        )
    )
    session.add_all(
        [
            Opportunity(
                id=uuid.uuid4(),
                hubspot_deal_id="H-1",
                owner_id=sales.id,
                client_id=acme.id,
                governance_status="Intake",
            ),
            Opportunity(
                id=uuid.uuid4(),
                hubspot_deal_id="H-2",
                owner_id=other.id,
                client_id=beta.id,
                governance_status="Intake",
            ),
        ]
    )
    await session.commit()
    return {"acme": acme, "beta": beta, "sales": sales, "other": other, "ceo": ceo}


async def test_get_client_detail_returns_msa_missing_for_acme(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/clients/{seeded_clients['acme'].id}",
            headers={"X-Test-User": "ceo@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Acme Corp"
    assert body["coverage_state"] == "MSA missing"
    assert len(body["legal_entities"]) == 1
    assert len(body["agreements"]) == 1
    assert len(body["opportunities"]) == 1
    assert body["opportunities"][0]["hubspot_deal_id"] == "H-1"


async def test_get_client_detail_requires_auth(app_with_session, seeded_clients):
    async with _client(app_with_session) as c:
        r = await c.get(f"/clients/{seeded_clients['acme'].id}")
    assert r.status_code == 401


async def test_get_client_detail_sales_owner_can_read(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/clients/{seeded_clients['acme'].id}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 200


async def test_get_client_detail_sales_non_owner_gets_403(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/clients/{seeded_clients['beta'].id}",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


async def test_get_unknown_client_returns_404(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    missing = uuid.uuid4()
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/clients/{missing}", headers={"X-Test-User": "ceo@smartek21.com"}
        )
    assert r.status_code == 404


async def test_list_clients_as_sales_returns_only_own(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/clients", headers={"X-Test-User": "sales@smartek21.com"}
        )
    assert r.status_code == 200
    names = {row["name"] for row in r.json()["items"]}
    assert names == {"Acme Corp"}


async def test_list_clients_as_ceo_returns_all(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/clients", headers={"X-Test-User": "ceo@smartek21.com"}
        )
    assert r.status_code == 200
    names = {row["name"] for row in r.json()["items"]}
    assert names == {"Acme Corp", "Beta LLC"}


async def test_list_clients_search_filter_narrows(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/clients?search=beta", headers={"X-Test-User": "ceo@smartek21.com"}
        )
    assert r.status_code == 200
    names = {row["name"] for row in r.json()["items"]}
    assert names == {"Beta LLC"}


async def test_list_clients_reports_coverage_state_per_row(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/clients", headers={"X-Test-User": "ceo@smartek21.com"}
        )
    assert r.status_code == 200
    by_name = {row["name"]: row for row in r.json()["items"]}
    # Acme has NDA-only -> MSA missing; Beta has no agreements at all.
    assert by_name["Acme Corp"]["coverage_state"] == "MSA missing"
    assert by_name["Beta LLC"]["coverage_state"] == "NDA + MSA missing"


# --- Deal list now shows real coverage (not "No client linked") -----------


async def test_deal_list_shows_real_coverage_from_client_agreements(
    app_with_session, seeded_clients, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get("/deals", headers={"X-Test-User": "ceo@smartek21.com"})
    assert r.status_code == 200
    by_hsid = {row["hubspot_deal_id"]: row for row in r.json()["items"]}
    # H-1 is on Acme (NDA present, MSA missing) -> "MSA missing".
    assert by_hsid["H-1"]["coverage_state"] == "MSA missing"
    assert by_hsid["H-1"]["client_name"] == "Acme Corp"
    # H-2 is on Beta (no agreements) -> "NDA + MSA missing".
    assert by_hsid["H-2"]["coverage_state"] == "NDA + MSA missing"
    assert by_hsid["H-2"]["client_name"] == "Beta LLC"


async def test_client_detail_recent_activity_includes_opportunity_audit(
    app_with_session, seeded_clients, session, monkeypatch
):
    # Emit an audit row for the opportunity so it shows up in recent activity.
    from app.audit import append_audit

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.client_id == seeded_clients["acme"].id)
        )
    ).scalar_one()
    await append_audit(
        session,
        actor_id=None,
        action="opportunity.updated",
        entity="opportunity",
        entity_id=str(opp.id),
        before={"engagement_type": None},
        after={"engagement_type": "TM"},
    )
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/clients/{seeded_clients['acme'].id}",
            headers={"X-Test-User": "ceo@smartek21.com"},
        )
    assert r.status_code == 200
    activity = r.json()["recent_activity"]
    actions = {row["action"] for row in activity}
    assert "opportunity.updated" in actions


async def test_get_client_detail_service_pure_function(session, seeded_clients):
    detail = await get_client_detail(session, seeded_clients["acme"].id)
    assert detail is not None
    assert detail.coverage_state == "MSA missing"
    assert len(detail.opportunities) == 1


async def test_list_clients_service_filters_by_accessible_ids(session, seeded_clients):
    filters = ClientListFilters()
    rows, total = await list_clients(
        session,
        filters=filters,
        accessible_client_ids={seeded_clients["acme"].id},
    )
    assert total == 1
    assert rows[0].name == "Acme Corp"
