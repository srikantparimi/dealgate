"""Granted local fixtures are Pipeline projections, never CRM identities."""
import uuid
import csv
import json
import os
from io import StringIO
from urllib.parse import urlparse
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers.pipeline import router
from app.routers.reports import router as reports_router
from app.routers import reports
from app.services import hubspot_pipeline as pipeline
from app.services.test_fixtures import create_fixture


@pytest.fixture
async def projected(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "fixture-projection")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    people = [User(email=f"{uuid.uuid4()}@example.test", name=name, groups=groups) for name, groups in [
        ("Issuer", ["SystemAdmin", "officeapp-e2e"]), ("Participant", ["Sales", "officeapp-e2e"]),
        ("Other test", ["Sales", "officeapp-e2e"]), ("Business", ["SystemAdmin"])]]
    session.add_all(people)
    await session.flush()
    issued = await create_fixture(session, actor_id=people[0].id, label="Named local projection", reviewer_ids=[people[1].id])
    local = await session.get(Opportunity, issued["opportunity_id"])
    extra = Opportunity(client_id=local.client_id, owner_id=people[0].id,
        source="sow_upload", name="Unissued sibling", governance_status="Intake")
    account = Client(name="Real mirrored company", hubspot_company_id="real-company")
    session.add(account)
    await session.flush()
    crm = Opportunity(client_id=account.id, owner_id=people[3].id, name="Real mirrored deal",
        source="hubspot", hubspot_deal_id="real-deal", governance_status="Intake")
    session.add_all([extra, crm])
    await session.flush()
    return people, issued, local, extra, crm


async def filters(session, user):
    return await pipeline.scope_pipeline_filters(session, user, pipeline.PipelineFilters())


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", [0, 1])
async def test_granted_exact_source_is_present_in_every_query_population(session, projected, participant):
    people, issued, local, extra, crm = projected
    scoped = await filters(session, people[participant])
    page = await pipeline.list_opportunities(session, filters=scoped)
    assert [r.opportunity_id for r in page.items] == [local.id]
    assert page.total == 1 and page.items[0].source_origin == "local_test_fixture"
    clients = await pipeline.list_clients(session, filters=scoped)
    assert clients.total == 1 and clients.items[0].client_id == local.client_id
    assert clients.items[0].matching_deal_count == clients.items[0].total_open_deal_count == 1
    assert (await pipeline.summary(session, filters=scoped)).open_count == 1
    assert (await pipeline.get_pipeline_deal(session, local.id, filters=scoped)).opportunity_id == local.id
    detail = await pipeline.get_opportunity_row(session, opportunity_id=local.id, filters=scoped)
    assert detail.source_origin == "local_test_fixture" and detail.hubspot_deal_id is None
    assert detail.hubspot_pipeline_id is None and detail.stage_id is None and detail.business_unit is None
    assert [r.opportunity_id for r in await pipeline.search_pipeline_deals(session, q="Named local", filters=scoped)] == [local.id]
    facets = await pipeline.list_pipeline_facets(session, filters=scoped)
    assert [r.id for r in facets.owners] == [people[0].id]
    assert not await pipeline.is_hubspot_linked(session, local.id)
    assert local.id not in {r.id for r in await pipeline.list_opportunity_rows(session)}
    assert local.source == "sow_upload" and local.hubspot_deal_id is None
    assert await pipeline.get_opportunity_row(session, opportunity_id=local.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_index, expected_kind", [(2, "none"), (3, "crm")])
async def test_nonparticipants_and_normal_users_never_receive_fixture_counts(session, projected, actor_index, expected_kind):
    people, _, local, _, crm = projected
    scoped = await filters(session, people[actor_index])
    expected = [crm.id] if expected_kind == "crm" else []
    page = await pipeline.list_opportunities(session, filters=scoped)
    assert [r.opportunity_id for r in page.items] == expected
    assert (await pipeline.summary(session, filters=scoped)).open_count == len(expected)
    assert (await pipeline.list_clients(session, filters=scoped)).total == len(expected)
    assert await pipeline.get_pipeline_deal(session, local.id, filters=scoped) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["expired", "tenant", "environment", "issuer", "owner", "external_id", "archived", "forged"])
async def test_invalid_grant_cannot_enable_local_projection(session, projected, monkeypatch, damage):
    people, issued, local, _, _ = projected
    if damage == "expired":
        grant = await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(local.client_id), AuditEvent.action == "test.fixture_created"))
        grant.after = {**grant.after, "expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
    elif damage == "tenant":
        monkeypatch.setenv("DEALGATE_TENANT_ID", "other")
    elif damage == "environment":
        monkeypatch.setenv("DEALGATE_ENV", "staging")
    elif damage == "issuer":
        people[0].groups = ["officeapp-e2e"]
    elif damage == "owner":
        local.owner_id = people[1].id
    elif damage == "external_id":
        local.hubspot_deal_id = "not-a-fixture"
    elif damage == "archived":
        local.archived_at = datetime.now(UTC)
    else:
        account = Client(name="S21 e2e forged fixture")
        session.add(account)
        await session.flush()
        local.client_id = account.id
    await session.flush()
    scoped = await filters(session, people[1])
    assert [r.opportunity_id for r in (await pipeline.list_opportunities(session, filters=scoped)).items] == []
    assert (await pipeline.summary(session, filters=scoped)).open_count == 0


@pytest.mark.asyncio
async def test_http_detail_provenance_filters_and_export_share_authority(session, projected):
    people, _, local, _, crm = projected
    app = FastAPI()
    app.include_router(router)
    app.include_router(reports_router)
    actor = people[0]
    app.dependency_overrides[current_user] = lambda: actor
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
        detail = await http.get(f"/pipeline/opportunities/{local.id}")
        assert detail.status_code == 200 and detail.json()["source_origin"] == "local_test_fixture"
        search = await http.get("/pipeline/deals/search", params={"q": "Named local"})
        assert search.status_code == 200 and [r["opportunity_id"] for r in search.json()] == [str(local.id)]
        assert (await http.get("/pipeline/opportunities", params={"pipeline": "fake-pipeline"})).json()["total"] == 0
        exported = await http.get("/reports/pipeline/export.csv")
        assert exported.status_code == 200 and local.name in exported.text and crm.name not in exported.text
        assert list(csv.DictReader(StringIO(exported.text)))[1]["source_origin"] == "local_test_fixture"
        actor = people[3]
        denied = await http.get(f"/pipeline/opportunities/{local.id}", params={"authorized_fixture_opportunity_ids": str(local.id)})
        assert denied.status_code == 404
        exported = await http.get("/reports/pipeline/export.csv")
        assert local.name not in exported.text and crm.name in exported.text
        actor = people[2]
        exported = await http.get("/reports/pipeline/export.csv")
        assert local.name not in exported.text and crm.name not in exported.text
        assert exported.headers["X-Totals-Count"] == "0"


@pytest.mark.asyncio
async def test_export_keeps_all_1002_authorized_business_rows_and_excludes_fixture(session, projected):
    people, _, local, _, crm = projected
    names = {f"Bulk authorized {index:04}" for index in range(1001)} | {crm.name}
    session.add_all([Opportunity(client_id=crm.client_id, owner_id=people[3].id,
        source="hubspot", name=name, governance_status="Intake") for name in names - {crm.name}])
    await session.flush()
    app = FastAPI()
    app.include_router(reports_router)
    app.dependency_overrides[current_user] = lambda: people[3]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://fixture") as http:
        response = await http.get("/reports/pipeline/export.csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(StringIO(response.text)))
    assert response.headers["X-Totals-Count"] == "1002"
    assert len(rows) == 1003 and {row["deal"] for row in rows[1:]} == names
    assert local.name not in response.text


async def prove_postgres_export_snapshot(monkeypatch):
    """Lead supplies a dedicated disposable migrated DB; real two-session commit."""
    url = os.environ["S21_PROJECTION_TEST_PG_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"}
    assert parsed.path.startswith("/s21_pipeline_export_")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    run = uuid.uuid4().hex
    actor = User(id=uuid.uuid4(), email=f"{run}@example.test", name="Snapshot reader", groups=["SystemAdmin"])
    account = Client(id=uuid.uuid4(), name=f"Snapshot company {run}")
    deals = [Opportunity(id=uuid.uuid4(), source="hubspot", owner_id=actor.id, client_id=account.id,
        name=f"{run}-deal-{index:04}", governance_status="Intake", amount=1001 if index == 1000 else 1, currency="USD",
        close_date=datetime(2020, 1, 1).date() + timedelta(days=index)) for index in range(1002)]
    original_names = {deal.name for deal in deals}
    try:
        async with factory() as setup:
            setup.add_all([actor, account])
            await setup.flush()
            setup.add_all(deals)
            await setup.commit()
        original_list = reports.list_opportunities
        original_scope = pipeline.scope_pipeline_filters
        calls, isolation = [], []
        async def check_scope_snapshot(session, user, filters):
            isolation.append((await session.scalar(text("SHOW transaction_isolation")),
                              await session.scalar(text("SHOW transaction_read_only"))))
            return await original_scope(session, user, filters)
        monkeypatch.setattr(pipeline, "scope_pipeline_filters", check_scope_snapshot)
        async def after_first_page(session, **kwargs):
            result = await original_list(session, **kwargs)
            calls.append(kwargs["page"])
            if kwargs["page"] == 1:
                identity = result.items[0].opportunity_id
                reader_pid = await session.scalar(text("SELECT pg_backend_pid()"))
                async with factory() as writer:
                    writer_pid = await writer.scalar(text("SELECT pg_backend_pid()"))
                    moved = await writer.get(Opportunity, identity)
                    moved.close_date = datetime(2030, 1, 1).date()
                    moved.amount = 99999
                    moved.name = "Changed after first exported page"
                    company = await writer.get(Client, account.id)
                    company.name = "Changed company after summary"
                    await writer.commit()
                print(json.dumps({"reader_pid": reader_pid, "writer_pid": writer_pid,
                    "writer_committed_after_page": 1, "moved_id": str(identity)}), flush=True)
            return result
        monkeypatch.setattr(reports, "list_opportunities", after_first_page)
        app = FastAPI()
        app.include_router(reports_router)
        app.dependency_overrides[current_user] = lambda: actor
        async def database():
            async with factory() as session:
                yield session
        app.dependency_overrides[get_session] = database
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://snapshot") as http:
            response = await http.get("/reports/pipeline/export.csv")
        assert response.status_code == 200
        exported = list(csv.DictReader(StringIO(response.text)))
        assert calls == [1, 2]
        assert len(exported) == 1003 and response.headers["X-Totals-Count"] == "1002"
        assert {row["deal"] for row in exported[1:]} == original_names
        assert all(row["client"] == account.name for row in exported[1:])
        assert {row["deal"]: Decimal(row["amount"]) for row in exported[1:]} == {
            deal.name: Decimal("1001") if index == 1000 else Decimal("1") for index, deal in enumerate(deals)}
        assert sum(Decimal(row["amount"]) for row in exported[1:]) == Decimal("2002")
        assert "2002.00 USD" in exported[0]["deal"]
        assert isolation == [("repeatable read", "on")]
        async with factory() as verify:
            assert (await verify.get(Client, account.id)).name == "Changed company after summary"
        async def already_active():
            async with factory() as session:
                await session.execute(text("SELECT 1"))
                yield session
        app.dependency_overrides[get_session] = already_active
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://snapshot") as http:
            refused = await http.get("/reports/pipeline/export.csv")
        assert refused.status_code == 409 and "fresh snapshot" in refused.json()["detail"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [{"pipeline": "absent"}, {"search": "no matching source"},
    {"stage": "absent"}, {"owner": str(uuid.UUID(int=0))}, {"client": str(uuid.UUID(int=0))},
    {"missing": "amount"}])
async def test_export_matches_pipeline_business_filters(session, projected, query):
    people, _, local, _, _ = projected
    app = FastAPI()
    app.include_router(router)
    app.include_router(reports_router)
    app.dependency_overrides[current_user] = lambda: people[0]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://filters") as http:
        listing = await http.get("/pipeline/opportunities", params=query)
        exported = await http.get("/reports/pipeline/export.csv", params=query)
    assert listing.status_code == exported.status_code == 200
    items = listing.json()["items"]
    rows = list(csv.DictReader(StringIO(exported.text)))[1:]
    assert len(rows) == listing.json()["total"]
    assert {row["deal"] for row in rows} == {row["name"] for row in items}


@pytest.mark.asyncio
async def test_export_rejects_unknown_query_instead_of_exporting_broader_scope(session, projected):
    app = FastAPI()
    app.include_router(reports_router)
    app.dependency_overrides[current_user] = lambda: projected[0][0]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://filters") as http:
        result = await http.get("/reports/pipeline/export.csv?pipeline_typo=absent")
    assert result.status_code == 400 and "Unsupported" in result.json()["detail"]


@pytest.mark.asyncio
async def test_export_nontrivial_intersection_matches_exact_rows_and_summary(session, projected):
    people, _, _, _, crm = projected
    crm.name, crm.hubspot_stage_id, crm.amount, crm.currency = "Selected target", "qualified", 120, "USD"
    session.add_all([
        Opportunity(source="hubspot", client_id=crm.client_id, owner_id=people[3].id,
            name="Selected wrong stage", hubspot_stage_id="other", amount=900, currency="USD", governance_status="Intake"),
        Opportunity(source="hubspot", client_id=crm.client_id, owner_id=people[1].id,
            name="Selected wrong owner", hubspot_stage_id="qualified", amount=700, currency="USD", governance_status="Intake"),
    ])
    await session.flush()
    app = FastAPI()
    app.include_router(router)
    app.include_router(reports_router)
    app.dependency_overrides[current_user] = lambda: people[3]
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    query = {"stage": "qualified", "owner": str(people[3].id), "search": "Selected"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://filters") as http:
        listing = await http.get("/pipeline/opportunities", params=query)
        summary = await http.get("/pipeline/summary", params=query)
        exported = await http.get("/reports/pipeline/export.csv", params=query)
    assert listing.status_code == summary.status_code == exported.status_code == 200
    assert [r["opportunity_id"] for r in listing.json()["items"]] == [str(crm.id)]
    rows = list(csv.DictReader(StringIO(exported.text)))
    assert len(rows) == 2 and rows[1]["deal"] == "Selected target"
    assert Decimal(rows[1]["amount"]) == Decimal("120")
    assert summary.json()["open_count"] == int(exported.headers["X-Totals-Count"]) == 1
    assert Decimal(summary.json()["open_value_by_currency"]["USD"]) == Decimal("120")
