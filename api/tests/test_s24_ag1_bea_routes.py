"""S24-AG1 lane BE-A — GET /agreements/workspace, /export, /documents and /activity (B3, B11 read side, B15).

A self-contained seed (its own stage mirror, region map, clients and deals; foreign keys enforced, as on
PostgreSQL): two existing clients (Closed Won), four net-new ones, a hostile client name, an archived client,
the standard NDA and MSA v1 attached by batch AG-0001, a covered mark, a server-issued test fixture with its
own document, and audit events from a writer, an admin, the e2e identity and the deletion job.

Clients (real viewer):  NDA                MSA              relationship   attention
  Acme Retail          client copy        client copy      existing       -
  Bolt Logistics       client copy        missing          net new (st 3) yes
  Cobalt Health        standard v1        standard v1      net new (st 4) -
  Echo Media           standard v1        marked covered   net new (st 1) -
  Fjord Energy         not needed         client copy      net new        -
  Garnet Labs          client copy        existing, none   existing       -
  =HYPERLINK(...)      not needed         not needed       net new        -
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.agreements import AgreementBatch, AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers.agreements_workspace import router as workspace_router
from app.services import agreement_audit as aa
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.test_fixtures import ISSUED

NOW = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)  # 12:00 in Los Angeles
TODAY = date(2026, 10, 14)
PIPELINE_ID = "bea-pipeline"
STAGES = (  # HubSpot stage id, label, display order, closed (as on staging)
    ("bea-s1", "1-Initial Contact/Prospecting", 0, False), ("bea-s2", "2-Qualification", 1, False),
    ("bea-s3", "3-Requirement/Fit Gap Analysis", 2, False), ("bea-s4", "4-Proposal", 3, False),
    ("bea-s5", "5-Negotiation", 4, False), ("bea-s6", "6-Contracting/Drive Commitment", 5, False),
    ("bea-s7", "7-Closed Won", 6, True), ("bea-s8", "8-Closed Lost", 7, True), ("bea-s9", "Hold", 8, False),
)
UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
HOSTILE = '=HYPERLINK("http://evil.test","x")'

E2E_ID = uuid.UUID("0e2e0000-0000-4000-8000-0000000000e2")
VIEWER_DB_ID = uuid.UUID("0c9f11af-0000-4000-8000-0000000000f1")
VIEWER = AuthUser(uuid.UUID("9da92a7c-0000-4000-8000-0000000000f2"), "viewer@example.test", "Viewer Vance",
                  ("SalesLeader",))
ADMIN = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000a1"), "admin@example.test", "Ada Admin",
                 ("SystemAdmin",))
LEGAL = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000b2"), "writer@example.test", "Wendy Writer",
                 ("Legal",))
SALES = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000c3"), "sales@example.test", "Sam Sales", ("Sales",))
E2E = AuthUser(E2E_ID, "e2e-runner@example.test", "E2E Runner", ("SystemAdmin", "officeapp-e2e"))
NOBODY = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000d4"), "nobody@example.test", "No Role", ())

# client key → (name, [(deal key, stage ordinal 1-9, region, close date)], {kind: file name of a client copy})
CLIENTS: dict[str, tuple[str, list[tuple[str, int, str | None, date | None]], dict[str, str]]] = {
    "acme": ("Acme Retail", [("a1", 2, "US", None), ("a2", 3, "US - IT Avalon", None),
                             ("a3", 7, "US", date(2026, 8, 1))], {"NDA": "acme-nda.pdf", "MSA": "acme-msa.pdf"}),
    "bolt": ("Bolt Logistics", [("b1", 3, "South Africa", None)], {"NDA": "bolt-nda.pdf"}),
    "cobalt": ("Cobalt Health", [("c1", 4, "US", None)], {}),
    "echo": ("Echo Media", [("e1", 1, "US", None)], {}),
    "fjord": ("Fjord Energy", [], {"MSA": "fjord-msa.pdf"}),
    "garnet": ("Garnet Labs", [("g1", 7, "US", date(2026, 7, 1))], {"NDA": "garnet-nda.pdf"}),
    "hostile": (HOSTILE, [], {}),
}


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", NOW.isoformat())
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "bea-tenant")


@asynccontextmanager
async def client_for(session, user: AuthUser, *routers):
    app = FastAPI()
    for router in routers or (workspace_router,):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://bea") as client:
        yield client


async def _event(session, *, actor, action, entity, entity_id, after=None, before=None, minutes_ago):
    # Inserted with its own time (newest first is then deterministic). The audit table is append-only on
    # Postgres, so the time cannot be changed after an append; the hash chain is irrelevant to these tests.
    row = AuditEvent(id=uuid.uuid4(), ts=NOW - timedelta(minutes=minutes_ago), actor_id=actor, action=action,
                     entity=entity, entity_id=str(entity_id), before=before, after=after,
                     row_hash=uuid.uuid4().hex * 2)
    session.add(row)
    await session.flush()
    return row


async def seed_reference(session) -> None:
    """The stage mirror and the business-unit mapping the Pipeline loader reads."""
    session.add(HubspotPipeline(id=PIPELINE_ID, label="BE-A Pipeline", display_order=1, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    if await session.get(HubspotPropertyMapping, "business_unit") is None:
        session.add(HubspotPropertyMapping(
            key="business_unit", internal_name="region", object_type="deal", label="Region",
            field_type="enumeration", availability_state="configured", mapping_version=1,
            options=[{"value": v, "label": v} for v in ("South Africa", "US - IT Avalon", "US")]))
    if not await session.scalar(select(func.count()).select_from(HubspotRegionMap)):  # 0070 seeds it on Postgres
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    await session.flush()


def _deal(client_id: uuid.UUID, key: str, ordinal: int, region: str | None, close: date | None) -> Opportunity:
    sid, label, order, _closed = STAGES[ordinal - 1]
    return Opportunity(
        source="hubspot", hubspot_deal_id=f"hs-{key}", name=f"Deal {key}", client_id=client_id,
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=ordinal == 7, is_closed_lost=ordinal == 8, amount=Decimal("1000"),
        currency="USD", close_date=close, created_at=NOW - timedelta(days=30), hubspot_created_at=NOW - timedelta(days=30),
        business_unit_value=region, business_unit_mapping_version=1 if region else None,
        business_unit_observed_at=NOW if region else None, governance_status="Intake")


async def seed_world(session) -> dict:
    await seed_reference(session)
    writer = User(id=uuid.uuid4(), email=LEGAL.email, name="Wendy Writer", groups=["Legal"])
    admin = User(id=uuid.uuid4(), email=ADMIN.email, name="Ada Admin", groups=["SystemAdmin"])
    viewer = User(id=VIEWER_DB_ID, email=VIEWER.email, name="Viewer Vance", groups=["SalesLeader"])
    e2e = User(id=E2E_ID, email=E2E.email, name="E2E Runner", groups=["SystemAdmin", "officeapp-e2e"])
    session.add_all([writer, admin, viewer, e2e])
    await session.flush()
    clients: dict[str, uuid.UUID] = {}
    for key, (name, deals, copies) in CLIENTS.items():
        client = Client(name=name, hubspot_company_id=f"c-{key}")
        session.add(client)
        await session.flush()
        clients[key] = client.id
        for deal_key, ordinal, region, close in deals:
            session.add(_deal(client.id, deal_key, ordinal, region, close))
        for kind, file_name in copies.items():
            session.add(Agreement(client_id=client.id, kind=kind, file_key=f"agreements/{key}/{file_name}",
                                  filename=file_name, file_size=1024, uploaded_by=writer.id, note=None))
    old = Client(name="Old Co", hubspot_company_id="c-old", archived_at=NOW - timedelta(days=2))
    session.add(old)
    nda = StandardAgreement(kind="NDA", version_no=1, file_key="agreements/standard/NDA/20261001-std-nda.pdf",
                            filename="Standard NDA.pdf", file_size=2048, sha256="1" * 64, uploaded_by=admin.id)
    msa = StandardAgreement(kind="MSA", version_no=1, file_key="agreements/standard/MSA/20261001-std-msa.pdf",
                            filename="Standard MSA.pdf", file_size=4096, sha256="2" * 64, uploaded_by=admin.id)
    session.add_all([nda, msa])
    await session.flush()
    batch = AgreementBatch(label="AG-0001", status="done", kinds=["NDA", "MSA"],
                           target_client_ids=[str(clients["cobalt"]), str(clients["echo"])],
                           standard_ids={"NDA": str(nda.id), "MSA": str(msa.id)}, target_count=2, done_count=2,
                           attached_count=3, attached_clients=2, idempotency_key="bea-batch-1", created_by=admin.id)
    session.add(batch)
    await session.flush()
    for key, std in (("cobalt", nda), ("cobalt", msa), ("echo", nda)):
        session.add(Agreement(client_id=clients[key], kind=std.kind, source="standard",
                              standard_agreement_id=std.id, batch_id=batch.id, file_key=std.file_key,
                              filename=std.filename, file_size=std.file_size, uploaded_by=admin.id))
    session.add(AgreementMark(client_id=clients["echo"], kind="MSA", reason="signed_outside_dealgate",
                              marked_on=TODAY, marked_by=writer.id, note="Signed MSA is with Legal"))
    fixture = Client(name="S21 e2e run42 fixture")
    session.add(fixture)
    await session.flush()
    fixture_deal = Opportunity(client_id=fixture.id, owner_id=e2e.id, source="sow_upload", name=fixture.name,
                               governance_status="Intake")
    session.add(fixture_deal)
    await session.flush()
    session.add(Agreement(client_id=fixture.id, kind="NDA", source="client", file_key="agreements/fx/nda.pdf",
                          filename="fixture-nda.pdf", file_size=10, uploaded_by=e2e.id))
    await _event(session, actor=e2e.id, action=ISSUED, entity="client", entity_id=fixture.id, minutes_ago=600,
                 after={"run_id": str(uuid.uuid4()), "environment": "local", "tenant_id": "bea-tenant",
                        "owner_id": str(e2e.id), "participant_ids": [str(e2e.id)],
                        "expires_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
                        "opportunity_id": str(fixture_deal.id)})
    detached_id = uuid.uuid4()
    events = [
        (admin.id, aa.STANDARD_UPLOADED, "standard_agreement", nda.id, 120,
         {"kind": "NDA", "version_no": 1, "filename": "Standard NDA.pdf", "standard": True}, None),
        (admin.id, aa.BATCH_RUN, "agreement_batch", batch.id, 110,
         {"label": "AG-0001", "kinds": ["NDA", "MSA"], "attached_clients": 2, "existing": 1, "net_new": 1}, None),
        (admin.id, aa.BATCH_ATTACHED, "agreement_batch", batch.id, 109,
         {"label": "AG-0001", "client_id": str(clients["cobalt"]), "client_name": "Cobalt Health"}, None),
        (writer.id, aa.CLIENT_UPLOADED, "agreement", uuid.uuid4(), 100,
         {"client_id": str(clients["acme"]), "client_name": "Acme Retail", "kind": "NDA",
          "filename": "acme-nda.pdf", "source": "client"}, None),
        (writer.id, aa.MARKED, "agreement_mark", uuid.uuid4(), 90,
         {"client_id": str(clients["echo"]), "client_name": "Echo Media", "kind": "MSA",
          "reason": "signed_outside_dealgate"}, None),
        (writer.id, aa.DETACHED, "agreement", detached_id, 80,
         {"client_id": str(clients["bolt"]), "client_name": "Bolt Logistics", "kind": "MSA", "source": "client",
          "filename": "bolt-msa.pdf"}, None),
        (writer.id, aa.DELETED, "agreement", detached_id, 80, {"job_id": str(uuid.uuid4())},
         {"name": "bolt-msa.pdf", "counts": {"agreements": 1}}),
        (writer.id, aa.DELETED, "agreement", uuid.uuid4(), 70, {"job_id": str(uuid.uuid4())},
         {"name": "legacy.pdf", "counts": {"agreements": 1}}),
        (e2e.id, aa.DOWNLOADED, "standard_agreement", nda.id, 60, {"kind": "NDA", "standard": True}, None),
        (e2e.id, aa.CLIENT_UPLOADED, "agreement", uuid.uuid4(), 50,
         {"client_id": str(fixture.id), "client_name": fixture.name, "kind": "NDA", "filename": "fixture-nda.pdf"},
         None),
        (writer.id, aa.MARK_REMOVED, "agreement_mark", uuid.uuid4(), 45,
         {"client_id": str(fixture.id), "client_name": fixture.name, "kind": "MSA"}, None),
        (writer.id, aa.RELATIONSHIP_CHANGED, "client", old.id, 40,
         {"client_id": str(old.id), "client_name": "Old Co", "relationship": "existing"}, None),
        (writer.id, aa.HUBSPOT_MARKED, "agreement_mark", uuid.uuid4(), 30,
         {"client_id": str(clients["acme"]), "client_name": "Acme Retail", "kind": "MSA"}, None),
    ]
    for actor, action, entity, entity_id, minutes, after, before in events:
        await _event(session, actor=actor, action=action, entity=entity, entity_id=entity_id, after=after,
                     before=before, minutes_ago=minutes)
    await session.commit()
    return {"clients": clients, "fixture": fixture.id, "old": old.id, "nda": nda.id, "msa": msa.id,
            "batch": batch.id, "writer": writer.id, "admin": admin.id}


@pytest_asyncio.fixture
async def world(session, clock):
    return await seed_world(session)


async def get(session, user, path, **params):
    async with client_for(session, user) as api:
        return await api.get(path, params=params)


# --- workspace ---------------------------------------------------------------------------------------------


async def test_workspace_shape_cards_and_drills(session, world):
    response = await get(session, VIEWER, "/agreements/workspace")
    assert response.status_code == 200, response.text
    body = response.json()
    cards = {c["key"]: c for c in body["cards"]}
    assert [c["key"] for c in body["cards"]] == ["clients", "existing", "net_new", "needs_attention",
                                                 "standard_attached", "client_copies"]
    assert {k: c["value"] for k, c in cards.items()} == {
        "clients": 7, "existing": 2, "net_new": 5, "needs_attention": 1, "standard_attached": 2, "client_copies": 4}
    assert cards["standard_attached"]["note"] == "clients · NDA 2 · MSA 1"
    assert cards["client_copies"]["note"] == "clients · NDA 3 · MSA 2 · 1 marked covered"
    for card in body["cards"]:
        drilled = (await get(session, VIEWER, "/agreements/workspace", **card["drill"])).json()
        assert drilled["total"] == card["value"], card["key"]
    names = [row["name"] for row in body["items"]]
    assert names[0] == "Bolt Logistics"  # needs attention sorts first
    assert "S21 e2e run42 fixture" not in names and "Old Co" not in names
    assert body["cutover"]["set"] is False and body["cutover"]["date"] is None
    batch = body["cutover"]["latest_batch"]
    assert (batch["id"], batch["status"], batch["created_by"], batch["undo_would_remove"]) == (
        "AG-0001", "done", "Ada Admin", 3)
    assert body["standard"]["NDA"]["version"] == 1 and body["standard"]["NDA"]["attached_clients"] == 2
    assert body["standard"]["MSA"]["attached_clients"] == 1 and body["standard"]["NDA"]["uploaded_by"] == "Ada Admin"
    assert body["can_write"] is False and body["is_admin"] is False
    rows = {row["name"]: row for row in body["items"]}
    assert rows["Acme Retail"]["business_units"] == [{"name": "ST21", "region": "US"},
                                                    {"name": "IT Avalon", "region": "US"}]
    assert rows["Bolt Logistics"]["business_units"] == [{"name": "Retro Rabbit", "region": "South Africa"}]
    assert rows["Cobalt Health"]["nda"] == {"state": "standard", "source_label": "Standard v1"}
    assert rows["Echo Media"]["msa"] == {"state": "covered", "source_label": "Marked covered"}
    for row in body["items"]:
        if row["business_units"]:
            assert row["business_unit_note"] is None
        else:  # a missing value shows its reason
            assert row["business_unit_note"] == "No deals or engagements yet", row["name"]


@pytest.mark.parametrize(("user", "can_write", "is_admin"), [(LEGAL, True, False), (ADMIN, True, True),
                                                             (SALES, False, False)])
async def test_workspace_rights_come_from_the_callers_groups(session, world, user, can_write, is_admin):
    body = (await get(session, user, "/agreements/workspace")).json()
    assert (body["can_write"], body["is_admin"]) == (can_write, is_admin)


async def test_workspace_writes_nothing_and_stays_within_the_statement_budget(session, world, engine):
    users = await session.scalar(select(func.count()).select_from(User))
    audits = await session.scalar(select(func.count()).select_from(AuditEvent))
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        response = await get(session, SALES, "/agreements/workspace", status="attention", sort="stage")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert response.status_code == 200
    assert [row["name"] for row in response.json()["items"]] == ["Bolt Logistics"]
    assert len(statements) <= 8, len(statements)
    assert await session.scalar(select(func.count()).select_from(User)) == users
    assert await session.scalar(select(func.count()).select_from(AuditEvent)) == audits


@pytest.mark.parametrize("size", [0, 10, 26, 1000])
async def test_page_size_must_be_one_of_the_allowed_sizes(session, world, size):
    for path in ("/agreements/workspace", "/agreements/documents", "/agreements/activity"):
        response = await get(session, VIEWER, path, page_size=size)
        assert response.status_code == 422, path
        assert "25, 50, 100" in response.text


@pytest.mark.parametrize("params", [{"status": "bogus"}, {"relationship": "both"}, {"stage": "2"},
                                    {"bu": "Narnia"}, {"sort": "value"}, {"q": "x" * 121}, {"page": 0}])
async def test_unknown_filter_values_are_rejected(session, world, params):
    assert (await get(session, VIEWER, "/agreements/workspace", **params)).status_code == 422
    if "page" not in params:
        assert (await get(session, VIEWER, "/agreements/export", **params)).status_code == 422


async def test_every_role_reads_and_a_caller_without_a_role_is_refused(session, world):
    for role in ("Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO",
                 "SystemAdmin"):
        user = AuthUser(uuid.uuid4(), f"{role.lower()}@example.test", role, (role,))
        for path in ("/agreements/workspace", "/agreements/documents", "/agreements/activity",
                     "/agreements/standard"):
            assert (await get(session, user, path)).status_code == 200, (role, path)
    for path in ("/agreements/workspace", "/agreements/export", "/agreements/documents", "/agreements/activity",
                 "/agreements/standard", "/agreements/standard/NDA/download"):
        assert (await get(session, NOBODY, path)).status_code == 403, path


async def test_workspace_paging(session, world):
    first = (await get(session, VIEWER, "/agreements/workspace", sort="name")).json()
    assert first["total"] == len(first["items"]) == 7
    assert [row["name"] for row in first["items"]] == sorted((row["name"] for row in first["items"]),
                                                            key=str.casefold)
    page_two = (await get(session, VIEWER, "/agreements/workspace", sort="name", page=2)).json()
    assert page_two["total"] == 7 and page_two["items"] == []


# --- export ------------------------------------------------------------------------------------------------


def _csv(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


async def test_export_is_the_whole_filtered_view_as_csv(session, world):
    response = await get(session, VIEWER, "/agreements/export", sort="name")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="DealGate_Agreements.csv"' in response.headers["content-disposition"]
    assert response.content.startswith("\ufeff".encode())
    assert b"\r\n" in response.content
    rows = _csv(response)
    assert rows[0] == ["Client", "Business unit", "Relationship", "Relationship basis", "Furthest open stage",
                       "NDA", "MSA", "Needs attention", "Possible duplicate"]
    assert len(rows) - 1 == 7
    by_name = {row[0]: row for row in rows[1:]}
    assert by_name["Acme Retail"] == ["Acme Retail", "ST21 · US; IT Avalon · US", "Existing", "Closed Won deal",
                                      "3 · Fit gap analysis", "Client copy", "Client copy", "No", "No"]
    assert by_name["Bolt Logistics"][1:] == ["Retro Rabbit · South Africa", "Net new", "No earlier work found",
                                             "3 · Fit gap analysis", "Client copy", "Missing", "Yes", "No"]
    assert by_name["Cobalt Health"][5:7] == ["Standard copy", "Standard copy"]
    assert by_name["Echo Media"][4:7] == ["1 · Prospecting", "Standard copy", "Marked covered"]
    assert by_name["Garnet Labs"][4:7] == ["No active deal", "Client copy", "Existing, none attached"]
    assert by_name["Fjord Energy"][1] == "No deals or engagements yet"
    assert "'" + HOSTILE in by_name  # neutralised: a spreadsheet shows it as text
    assert not any(UUID_TEXT.search(cell) for row in rows for cell in row)


async def test_export_follows_the_filters_and_is_audited(session, world):
    filtered = _csv(await get(session, VIEWER, "/agreements/export", relationship="net_new"))[1:]
    workspace = (await get(session, VIEWER, "/agreements/workspace", relationship="net_new")).json()
    assert len(filtered) == workspace["total"] == 5
    audit = (await session.scalars(select(AuditEvent).where(AuditEvent.action == aa.EXPORTED))).all()
    assert len(audit) == 1
    assert audit[0].actor_id == VIEWER_DB_ID and audit[0].entity == aa.EXPORT_ENTITY
    assert audit[0].after["rows"] == 5 and audit[0].after["filters"] == {"relationship": "net_new"}
    activity = (await get(session, LEGAL, "/agreements/activity")).json()
    assert activity["items"][0] == {"at": activity["items"][0]["at"], "by": "Viewer Vance", "action": "exported",
                                    "text": "Exported 5 clients to CSV", "client_id": None}


# --- documents ---------------------------------------------------------------------------------------------


async def test_documents_rows_order_and_count(session, world):
    body = (await get(session, VIEWER, "/agreements/documents", page_size=100)).json()
    workspace = (await get(session, VIEWER, "/agreements/workspace")).json()
    assert body["total"] == workspace["document_count"] == len(body["items"]) == 8
    keys = [(row["client_name"].casefold(), row["kind"]) for row in body["items"]]
    assert keys == sorted(keys)
    assert "fixture-nda.pdf" not in {row["file_name"] for row in body["items"]}
    cobalt = [row for row in body["items"] if row["client_name"] == "Cobalt Health"]
    assert [(row["kind"], row["source"], row["standard_version"], row["batch_id"], row["uploaded_by"])
            for row in cobalt] == [("MSA", "standard", 1, "AG-0001", "Ada Admin"),
                                   ("NDA", "standard", 1, "AG-0001", "Ada Admin")]
    acme = [row for row in body["items"] if row["client_name"] == "Acme Retail"]
    assert [(row["file_name"], row["source"], row["standard_version"], row["batch_id"], row["uploaded_by"])
            for row in acme] == [("acme-msa.pdf", "client", None, None, "Wendy Writer"),
                                 ("acme-nda.pdf", "client", None, None, "Wendy Writer")]
    for row in body["items"]:
        assert row["uploaded_at"].endswith("Z") and row["version_no"] == 1
        uuid.UUID(row["agreement_id"]) and uuid.UUID(row["client_id"])  # ids are links only
        for key in ("client_name", "file_name", "uploaded_by", "batch_id"):
            assert not UUID_TEXT.search(str(row[key] or "")), (key, row)


@pytest.mark.parametrize(("params", "expected"), [
    ({"q": "wendy"}, 5),  # uploader: the five client copies
    ({"q": "ada"}, 3),  # uploader: the three standard attachments
    ({"q": "standard msa"}, 1),  # file name
    ({"q": "COBALT"}, 2),  # client name, any case
    ({"q": "msa"}, 3),  # kind or file name
    ({"kind": "NDA"}, 5),
    ({"source": "standard"}, 3),
    ({"source": "client", "kind": "MSA"}, 2),
    ({"q": "no such thing"}, 0),
])
async def test_documents_search_and_filters(session, world, params, expected):
    body = (await get(session, VIEWER, "/agreements/documents", **params)).json()
    assert body["total"] == expected == len(body["items"]), body


async def test_documents_paging_and_bad_filters(session, world):
    page = (await get(session, VIEWER, "/agreements/documents", page=2)).json()
    assert page["total"] == 8 and page["items"] == []
    assert (await get(session, VIEWER, "/agreements/documents", kind="SOW")).status_code == 422
    assert (await get(session, VIEWER, "/agreements/documents", source="signed")).status_code == 422


async def test_documents_for_the_test_identity_are_its_fixtures(session, world):
    body = (await get(session, E2E, "/agreements/documents")).json()
    assert [row["file_name"] for row in body["items"]] == ["fixture-nda.pdf"]


# --- activity ----------------------------------------------------------------------------------------------

REAL_FEED = [
    "Changed Old Co to existing",
    "Removed file (legacy.pdf) from a client",
    "Removed MSA file from Bolt Logistics",
    "Marked MSA covered for Echo Media (Signed outside DealGate)",
    "Uploaded client NDA for Acme Retail (acme-nda.pdf)",
    "Attached standard NDA and MSA to 2 clients (batch AG-0001): 1 existing and 1 net new in the pipeline",
    "Uploaded standard NDA version 1 (Standard NDA.pdf)",
]


async def test_activity_for_a_real_user(session, world):
    body = (await get(session, VIEWER, "/agreements/activity")).json()
    assert [row["text"] for row in body["items"]] == REAL_FEED
    assert [row["action"] for row in body["items"]] == [
        "relationship_changed", "detached", "detached", "marked", "client_uploaded", "batch_run",
        "standard_uploaded"]
    assert [row["by"] for row in body["items"]] == ["Wendy Writer"] * 5 + ["Ada Admin"] * 2
    assert body["items"][0]["client_id"] is None  # an archived client's event: named, not linked
    assert body["items"][3]["client_id"] == str(world["clients"]["echo"])
    assert body["items"][1]["client_id"] is None and body["items"][5]["client_id"] is None
    assert all(row["at"].endswith("Z") for row in body["items"])
    workspace = (await get(session, VIEWER, "/agreements/workspace")).json()
    assert workspace["activity_count"] == body["total"] == 7


async def test_activity_for_the_test_identity_is_its_fixtures_and_shared_events(session, world):
    body = (await get(session, E2E, "/agreements/activity")).json()
    assert [row["text"] for row in body["items"]] == [
        "Removed MSA mark from S21 e2e run42 fixture",
        "Uploaded client NDA for S21 e2e run42 fixture (fixture-nda.pdf)",
        "Downloaded the standard NDA",
        # An older client-level event with no client id ("Removed file (legacy.pdf) from a client") may name a
        # real client's document, so a test identity never sees it (review finding, safety).
        "Attached standard NDA and MSA to 2 clients (batch AG-0001): 1 existing and 1 net new in the pipeline",
        "Uploaded standard NDA version 1 (Standard NDA.pdf)",
    ]
    assert body["items"][0]["client_id"] == str(world["fixture"])
    workspace = (await get(session, E2E, "/agreements/workspace")).json()
    assert workspace["activity_count"] == body["total"] == 5
    assert [row["name"] for row in workspace["items"]] == ["S21 e2e run42 fixture"]
    assert "test_data" in workspace["items"][0]["flags"]


async def test_activity_search_and_paging(session, world):
    by_person = (await get(session, VIEWER, "/agreements/activity", q="ada admin")).json()
    assert by_person["total"] == 2
    by_text = (await get(session, VIEWER, "/agreements/activity", q="ECHO")).json()
    assert [row["action"] for row in by_text["items"]] == ["marked"]
    small = (await get(session, VIEWER, "/agreements/activity", page_size=25, page=1)).json()
    assert small["total"] == 7 and len(small["items"]) == 7
    paged = (await get(session, VIEWER, "/agreements/activity", page=2)).json()
    assert paged["total"] == 7 and paged["items"] == []


# --- T13 evidence: statements per request (a real user; reads never write) --------------------------------


async def test_statements_per_route(session, world, engine, capsys):
    def measure():
        statements: list[str] = []

        def count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
            if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
                statements.append(statement)

        return statements, count

    counts: dict[str, int] = {}
    for label, user, path, params in (
        ("workspace", SALES, "/agreements/workspace", {}),
        ("workspace filtered", SALES, "/agreements/workspace",
         {"relationship": "net_new", "stage": "past_stage_1", "bu": "ST21", "q": "o", "sort": "stage",
          "page_size": 100}),
        ("documents", SALES, "/agreements/documents", {"q": "msa"}),
        ("activity", SALES, "/agreements/activity", {}),
        ("standard", SALES, "/agreements/standard", {}),
        ("export", VIEWER, "/agreements/export", {}),
    ):
        statements, count = measure()
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        try:
            response = await get(session, user, path, **params)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count)
        assert response.status_code == 200, (label, response.text)
        counts[label] = len(statements)
    with capsys.disabled():
        print("\nS24-AG1 BE-A statements per request:", counts)
    assert counts["workspace"] <= 8 and counts["workspace filtered"] <= 8
    assert counts["documents"] == 2 and counts["activity"] == 3 and counts["standard"] == 3


# --- B15: one sentence per event, the prototype's wording, never an id, never an invented zero ------------

ACME = {"client_id": str(uuid.uuid4()), "client_name": "Acme Retail"}


@pytest.mark.parametrize(("action", "after", "before", "text"), [
    (aa.STANDARD_UPLOADED, {"kind": "NDA", "version_no": 2, "filename": "nda.pdf"}, None,
     "Uploaded standard NDA version 2 (nda.pdf)"),
    (aa.CLIENT_UPLOADED, {**ACME, "kind": "MSA", "filename": "msa.pdf"}, None,
     "Uploaded client MSA for Acme Retail (msa.pdf)"),
    (aa.CLIENT_REPLACED, {**ACME, "kind": "MSA", "filename": "msa-v2.pdf"}, {"source": "standard"},
     "Replaced client MSA for Acme Retail (msa-v2.pdf)"),
    (aa.STANDARD_ATTACHED, {**ACME, "kind": "NDA", "standard_version": 1}, None, "Attached standard NDA to Acme Retail"),
    (aa.DETACHED, {**ACME, "kind": "NDA", "source": "standard"}, None, "Removed NDA file from Acme Retail"),
    # The client-copy detach is the deletion job's own row, which now names the client (parent_deletion).
    (aa.DELETED, {**ACME, "kind": "NDA", "filename": "nda.pdf", "job_id": "j"}, {"name": "nda.pdf"},
     "Removed NDA file from Acme Retail"),
    (aa.MARKED, {**ACME, "kind": "MSA", "reason": "covered_by_earlier_work"}, None,
     "Marked MSA covered for Acme Retail (Covered by earlier work)"),
    (aa.MARK_REMOVED, {**ACME, "kind": "MSA"}, None, "Removed MSA mark from Acme Retail"),
    (aa.RELATIONSHIP_CHANGED, {**ACME, "relationship": "net_new"}, None, "Changed Acme Retail to net new"),
    (aa.BATCH_RUN, {"label": "AG-0002", "kinds": ["MSA"], "attached_clients": 1}, None,
     "Attached standard MSA to 1 client (batch AG-0002)"),
    (aa.BATCH_RUN, {"label": "AG-0003", "kinds": ["NDA", "MSA"]}, None, "Attached standard NDA and MSA (batch AG-0003)"),
    (aa.BATCH_UNDONE, {"label": "AG-0001", "removed": 1}, None, "Undid batch AG-0001: removed 1 standard attachment"),
    (aa.BATCH_UNDONE, {"label": "AG-0001"}, None, "Undid batch AG-0001"),
    (aa.HUBSPOT_APPLIED, {"marked": 4, "would_mark": 4}, None,
     "Applied HubSpot msa_type mapping: marked MSA covered for 4 clients"),
    (aa.HUBSPOT_APPLIED, {"would_mark": 4}, None, "Applied HubSpot msa_type mapping"),
    (aa.DOWNLOADED, {"kind": "MSA", "standard": True}, None, "Downloaded the standard MSA"),
    (aa.DOWNLOADED, {**ACME, "kind": "NDA", "source": "standard", "standard_version": 1}, None,
     "Downloaded NDA for Acme Retail"),
    (aa.EXPORTED, {"rows": 1}, None, "Exported 1 client to CSV"),
    (aa.EXPORTED, {}, None, "Exported the client view to CSV"),
])
def test_activity_sentences(action, after, before, text):
    assert aa.activity_text(action, after, before) == text
    assert not UUID_TEXT.search(text)
