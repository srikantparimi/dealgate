"""S23-PL2 B1 / B5 / B6 / B9 / B13 / B15 — ``GET /pipeline/workspace``.

One request returns freshness, metrics, stage counts, focus counts, options and
the rows of the active tab, all from one authorized population and one filter
function. The seed below is shared by the other S23-PL2 API tests (drill, dates,
export, cost, Command Center): it holds every status (Hold, won, lost), active,
archived, unknown and missing owners, every business unit plus an unmapped and
a missing region, a deal with no amount and one in EUR, overdue, dated and
undated next actions, NDA / MSA on some clients, all nine SOW states and a deal
with two SOWs.

The caller is a HubSpot-created user: the login id differs from the DealGate
user id, and watches, groups and the HubSpot owner link are keyed on the
DealGate id (foreign keys enforced, as on PostgreSQL).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.approval import ApprovalPackage
from app.models.client import Agreement, Client
from app.models.gm_model import GmModel
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.next_action import NextAction
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.tracking_group import TrackingGroup, TrackingGroupMember
from app.models.user import User
from app.models.watchlist import WatchedItem
from app.routers.pipeline import router as pipeline_router
from app.services.hubspot_owners import HubspotOwner
from app.services.hubspot_properties import HubspotPropertyMapping

LA = ZoneInfo("America/Los_Angeles")
NOW = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)  # 12:00 PDT
TODAY = date(2026, 10, 14)
PIPELINE_ID = "710688094"
PIPELINE_LABEL = "SmarTek21 Global Pipeline"
# HubSpot stage id, HubSpot label, display order, closed — as on staging.
STAGES = (
    ("1038193692", "1-Initial Contact/Prospecting", 0, False),
    ("1038193693", "2-Qualification", 1, False),
    ("1038193694", "3-Requirement/Fit Gap Analysis", 2, False),
    ("1038193695", "4-Proposal", 3, False),
    ("1038193696", "5-Negotiation", 4, False),
    ("1038193697", "6-Contracting/Drive Commitment", 5, False),
    ("1038553758", "7-Closed Won", 6, True),
    ("1038553759", "8-Closed Lost", 7, True),
    ("1182672128", "Hold", 8, False),
)
SHORT_LABELS = ["Prospecting", "Qualification", "Fit gap analysis", "Proposal", "Negotiation",
                "Contracting", "Closed won", "Closed lost", "On hold"]
FULL_LABELS = ["1 · Initial Contact / Prospecting", "2 · Qualification", "3 · Requirement / Fit Gap Analysis",
               "4 · Proposal", "5 · Negotiation", "6 · Contracting / Drive Commitment", "7 · Closed Won",
               "8 · Closed Lost", "Hold (open, paused)"]

VIEWER_DB_ID = uuid.UUID("0c9f11af-0000-4000-8000-000000000001")
VIEWER = AuthUser(uuid.UUID("9da92a7c-0000-4000-8000-000000000002"), "viewer@example.test",
                  "Viewer Vance", ("SalesLeader",))

# id → (first, last, email, archived); "999" is an owner id missing from the mirror.
OWNERS = {
    "101": ("Ava", "Archer", "ava@example.test", False),
    "102": ("Ben", "Brook", "ben@example.test", False),
    "103": ("Cara", "Cole", "cara@example.test", True),
    "104": ("Viewer", "Vance", "viewer@example.test", False),
}
# key → (name, account owner, NDA, MSA)
CLIENTS = {
    "acme": ("Acme Retail", "101", True, True),
    "bolt": ("Bolt Logistics", "103", True, False),
    "cobalt": ("Cobalt Health", None, False, False),
    "delta": ("Delta Foods", "102", False, True),
    "echo": ("Echo Media", "999", False, False),
    "fjord": ("Fjord Energy", "101", False, True),  # no deals at all
    "garnet": ("Garnet Labs", "102", True, True),  # closed-won deals only
}


def day(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def la_noon(offset: int) -> datetime:
    # A UTC instant, as intake stores timestamps (SQLite would drop a non-UTC offset).
    return datetime.combine(day(offset), time(12), LA).astimezone(UTC)


@dataclass(frozen=True)
class DealSpec:
    title: str
    client: str | None
    ordinal: int
    owner: str | None
    amount: str | None
    currency: str
    close: int | None  # days from today
    activity: int | None  # days ago
    created: int  # days ago
    region: str | None


DEALS: dict[str, DealSpec] = {
    "d01": DealSpec("Acme rollout", "acme", 1, "101", "100000", "USD", 5, 2, 40, "US"),
    "d02": DealSpec("Acme data platform", "acme", 2, "101", "250000", "USD", -10, 20, 60, "US - IT Avalon"),
    "d03": DealSpec("Bolt fleet tracking", "bolt", 3, "103", "50000", "USD", 40, None, 10, "South Africa"),
    "d04": DealSpec("Bolt warehouse scanners", "bolt", 4, None, None, "USD", None, 1, 5,
                    "US - IT Avalon (Staffing)"),
    "d05": DealSpec("Cobalt clinic portal", "cobalt", 5, "102", "75000", "EUR", 60, 30, 90, "Brazil"),
    "d06": DealSpec("Cobalt records audit", "cobalt", 9, "104", "30000", "USD", 15, 14, 20, "US"),
    "d07": DealSpec("Delta supply chain", "delta", 6, "104", "400000", "USD", 1, 0, 3, None),
    "d08": DealSpec("Delta pricing engine", "delta", 7, "101", "90000", "USD", -30, 40, 120, "US"),
    "d09": DealSpec("Echo ad exchange", "echo", 8, "999", "20000", "USD", -60, None, 200, "South Africa"),
    "d10": DealSpec("Echo studio tools", "echo", 1, "999", "60000", "USD", 3, 3, 15, "US"),
    "d11": DealSpec("Garnet lab system", "garnet", 7, "102", "10000", "USD", -5, 10, 30, "US"),
    "d12": DealSpec("Standalone advisory", None, 2, "101", "5000", "USD", 30, 5, 8, "US"),
    "d13": DealSpec("Acme loyalty app", "acme", 3, "102", "120000", "USD", 20, 15, 25, "US"),
    "d15": DealSpec("Bolt route optimiser", "bolt", 2, "102", "45000", "USD", 89, 89, 100, "US - IT Avalon"),
    "d16": DealSpec("Delta cold storage", "delta", 9, "103", "15000", "USD", -2, None, 12, "Brazil"),
}
OPEN_KEYS = ["d01", "d02", "d03", "d04", "d05", "d06", "d07", "d10", "d12", "d13", "d15", "d16"]


@dataclass
class Seed:
    deals: dict[str, uuid.UUID] = field(default_factory=dict)
    clients: dict[str, uuid.UUID] = field(default_factory=dict)
    actions: dict[str, uuid.UUID] = field(default_factory=dict)
    group: uuid.UUID | None = None
    other_group: uuid.UUID | None = None
    writer: uuid.UUID | None = None
    hidden: dict[str, uuid.UUID] = field(default_factory=dict)

    def key_of(self, deal_id: str) -> str:
        return next(key for key, value in self.deals.items() if str(value) == deal_id)

    def keys(self, rows: list[dict]) -> list[str]:
        return [self.key_of(row["id"]) for row in rows]


async def _package(session, seed: Seed, deal_id: uuid.UUID, version: SowVersion, status: str,
                   submitted: datetime, *, released: datetime | None = None,
                   voided: datetime | None = None) -> ApprovalPackage:
    model = GmModel(opportunity_id=deal_id, sow_id=version.sow_id, sow_version_id=version.id,
                    engagement_type="fixed_assignment")
    session.add(model)
    await session.flush()
    package = ApprovalPackage(opportunity_id=deal_id, sow_version_id=version.id, gm_model_id=model.id,
                              package_hash=uuid.uuid4().hex * 2, routing_policy_version=2, status=status,
                              submitted_by=seed.writer, submitted_at=submitted, released_at=released,
                              voided_at=voided)
    session.add(package)
    await session.flush()
    return package


async def _sow(session, seed: Seed, key: str, *, created: datetime, uploaded: datetime) -> SowVersion:
    sow = Sow(opportunity_id=seed.deals[key], created_at=created)
    session.add(sow)
    await session.flush()
    version = SowVersion(sow_id=sow.id, uploaded_by=seed.writer, uploaded_at=uploaded,
                         file_s3_key=f"sows/{uuid.uuid4()}.pdf", file_hash="a" * 64)
    session.add(version)
    await session.flush()
    return version


async def seed_population(session, *, region_map: bool = True) -> Seed:
    """The shared population. ``region_map=False`` on a migrated Postgres (0070 seeds it)."""
    seed = Seed()
    writer = User(email="writer@example.test", name="Wendy Writer", groups=["Legal"])
    viewer = User(id=VIEWER_DB_ID, email=VIEWER.email, name="Viewer Vance", groups=["SalesLeader"],
                  hubspot_owner_id="104", hubspot_owner_link="email")
    session.add_all([writer, viewer])
    session.add(HubspotPipeline(id=PIPELINE_ID, label=PIPELINE_LABEL, display_order=2, archived=False))
    await session.flush()
    seed.writer = writer.id
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    session.add_all([HubspotOwner(id=oid, first_name=first, last_name=last, email=email, archived=archived)
                     for oid, (first, last, email, archived) in OWNERS.items()])
    session.add(HubspotPropertyMapping(
        key="business_unit", internal_name="region", object_type="deal", label="Region",
        field_type="enumeration", availability_state="configured", mapping_version=1,
        options=[{"value": v, "label": v} for v in
                 ("South Africa", "US - IT Avalon (Staffing)", "US - IT Avalon", "US", "Brazil")]))
    if region_map:
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    for key, (name, owner, nda, msa) in CLIENTS.items():
        client = Client(name=name, hubspot_company_id=f"c-{key}", hubspot_owner_id=owner)
        session.add(client)
        await session.flush()
        seed.clients[key] = client.id
        for kind, on_file in (("NDA", nda), ("MSA", msa)):
            if on_file:
                session.add(Agreement(client_id=client.id, kind=kind, file_key=f"agreements/{key}/{kind}.pdf",
                                      filename=f"{kind}.pdf", file_size=1024, uploaded_by=writer.id))
    archived_client = Client(name="Old Co", hubspot_company_id="c-old", archived_at=NOW)
    session.add(archived_client)
    await session.flush()

    def opportunity(spec: DealSpec, key: str, **extra) -> Opportunity:
        sid, label, order, _ = STAGES[spec.ordinal - 1]
        return Opportunity(
            source="hubspot", hubspot_deal_id=f"hs-{key}", name=spec.title,
            client_id=seed.clients[spec.client] if spec.client else None,
            hubspot_owner_id=spec.owner, hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid,
            stage_label=label, sales_stage=label, stage_order=order,
            is_closed_won=spec.ordinal == 7, is_closed_lost=spec.ordinal == 8,
            amount=Decimal(spec.amount) if spec.amount else None, currency=spec.currency,
            close_date=day(spec.close) if spec.close is not None else None,
            hubspot_last_activity_at=la_noon(-spec.activity) if spec.activity is not None else None,
            hubspot_created_at=la_noon(-spec.created) if key != "d10" else None,
            created_at=la_noon(-spec.created),
            business_unit_value=spec.region, business_unit_mapping_version=1 if spec.region else None,
            business_unit_observed_at=NOW if spec.region else None,
            governance_status="Intake", **extra)

    for key, spec in DEALS.items():
        deal = opportunity(spec, key)
        session.add(deal)
        await session.flush()
        seed.deals[key] = deal.id
    # Never visible: an archived deal, a deal of an archived client, a local SOW-upload deal.
    for key, deal in (
        ("archived", opportunity(DEALS["d01"], "x1", archived_at=NOW)),
        ("archived_client", opportunity(DEALS["d01"], "x2")),
        ("local", Opportunity(source="sow_upload", name="Local upload deal", client_id=seed.clients["acme"],
                              governance_status="Intake", amount=Decimal("7"), currency="USD")),
    ):
        if key == "archived_client":
            deal.client_id = archived_client.id
        session.add(deal)
        await session.flush()
        seed.hidden[key] = deal.id

    def action(key: str, title: str | None, due: int | None, *, status: str = "open",
               description: str | None = None) -> NextAction:
        row = NextAction(opportunity_id=seed.deals[key], title=title, description=description or title or "",
                         owner_user_id=writer.id, assignee_user_id=writer.id, created_by=writer.id,
                         due_date=day(due) if due is not None else None, status=status)
        session.add(row)
        return row

    actions = {
        "d01": action("d01", "Send revised proposal", -3),
        "d01_done": action("d01", "Old kickoff", -10, status="complete"),
        "d02": action("d02", "Book scoping call", 3),
        "d04": action("d04", "Confirm budget owner", None),
        "d05": action("d05", None, -1, description="Chase CEO sign-off"),
        "d07": action("d07", "Countersign order form", 0),
        "d08": action("d08", "Archive the folder", -5),  # overdue on a closed deal: never a flag
        "d13_dated": action("d13", "Demo loyalty flow", 10, status="in_progress"),
        "d13_undated": action("d13", "Collect references", None),
    }
    await session.flush()
    seed.actions = {key: row.id for key, row in actions.items()}

    # SOW states. d06 has two SOWs: the older one was updated last, so it decides.
    v = await _sow(session, seed, "d02", created=la_noon(-12), uploaded=la_noon(-12))
    await _package(session, seed, seed.deals["d02"], v, "pending_delivery_hr", la_noon(-4))
    v = await _sow(session, seed, "d03", created=la_noon(-9), uploaded=la_noon(-9))
    await _package(session, seed, seed.deals["d03"], v, "voided", la_noon(-8), voided=la_noon(-7))
    v = await _sow(session, seed, "d05", created=la_noon(-20), uploaded=la_noon(-20))
    await _package(session, seed, seed.deals["d05"], v, "pending_ceo_exception", la_noon(-6))
    await _sow(session, seed, "d06", created=la_noon(-30), uploaded=la_noon(-1))  # draft, updated yesterday
    v = await _sow(session, seed, "d06", created=la_noon(-10), uploaded=la_noon(-10))
    await _package(session, seed, seed.deals["d06"], v, "ready_to_sign", la_noon(-5))  # approved, older
    v = await _sow(session, seed, "d07", created=la_noon(-40), uploaded=la_noon(-40))
    await _package(session, seed, seed.deals["d07"], v, "released", la_noon(-30), released=la_noon(-25))
    v = await _sow(session, seed, "d10", created=la_noon(-7), uploaded=la_noon(-7))
    await _package(session, seed, seed.deals["d10"], v, "pending_finance_legal", la_noon(-2))
    v = await _sow(session, seed, "d11", created=la_noon(-15), uploaded=la_noon(-15))
    await _package(session, seed, seed.deals["d11"], v, "ready_to_sign", la_noon(-14))
    v = await _sow(session, seed, "d13", created=la_noon(-18), uploaded=la_noon(-18))
    package = await _package(session, seed, seed.deals["d13"], v, "ready_to_sign", la_noon(-16))
    session.add(SignedSowUpload(package_id=package.id, file_s3_key="signed/d13.pdf", file_hash="b" * 64,
                                uploaded_by=writer.id))
    v = await _sow(session, seed, "d15", created=la_noon(-50), uploaded=la_noon(-50))
    await _package(session, seed, seed.deals["d15"], v, "rejected", la_noon(-45))

    session.add_all([WatchedItem(user_id=VIEWER_DB_ID, kind="opportunity", item_id=seed.deals[key])
                     for key in ("d01", "d06", "d08")])
    session.add(WatchedItem(user_id=VIEWER_DB_ID, kind="client", item_id=seed.clients["echo"]))
    group = TrackingGroup(owner_id=VIEWER_DB_ID, name="Key deals", member_kind="opportunity")
    other = TrackingGroup(owner_id=writer.id, name="Theirs", member_kind="opportunity")
    session.add_all([group, other])
    await session.flush()
    session.add_all([TrackingGroupMember(group_id=group.id, member_id=seed.deals[key]) for key in ("d04", "d07")])
    session.add(TrackingGroupMember(group_id=other.id, member_id=seed.deals["d01"]))
    seed.group, seed.other_group = group.id, other.id
    session.add(HubspotSyncRun(id=uuid.uuid4(), kind="nightly", status="ok", started_at=NOW - timedelta(hours=3),
                               finished_at=NOW - timedelta(hours=2), deals_seen=15, deals_written=15,
                               error_count=0, errors=[]))
    await session.commit()
    return seed


# --- fixtures shared by the S23-PL2 API tests --------------------------------


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", NOW.isoformat())
    monkeypatch.setenv("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def seeded(session, frozen_clock):
    return await seed_population(session)


@asynccontextmanager
async def client_for(session, user: AuthUser, *routers):
    app = FastAPI()
    for router in routers or (pipeline_router,):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://pl2") as client:
        yield client


@pytest_asyncio.fixture
async def api(session, seeded):
    async with client_for(session, VIEWER) as client:
        yield client


async def workspace(api, **params) -> dict:
    response = await api.get("/pipeline/workspace", params=params)
    assert response.status_code == 200, response.text
    return response.json()


# --- B1: one response, exact shape --------------------------------------------


async def test_default_response_has_the_contract_shape(api, seeded):
    body = await workspace(api)
    assert set(body) == {"freshness", "metrics", "stages", "focus", "unmapped_regions", "rows", "rows_by_stage",
                         "page", "tab_counts", "options", "today"}
    assert body["today"] == "2026-10-14"
    assert body["rows_by_stage"] is None
    assert set(body["metrics"]) == {"open_deals", "open_value_usd", "closing_this_month", "overdue_next_actions",
                                    "pending_approvals", "agreement_gap_clients"}
    assert body["metrics"]["open_deals"] == {"value": 12, "accounts": 5, "drill": {"tab": "deals", "status": "open"}}
    assert body["metrics"]["open_value_usd"] == {"value": "1075000.00", "includes_on_hold": 2, "deals": 12,
                                                 "drill": {"tab": "deals", "status": "open"}}
    assert body["metrics"]["closing_this_month"] == {
        "value": 6, "value_usd": "855000.00",
        "drill": {"tab": "deals", "status": "open", "date_field": "close", "date_preset": "month"}}
    assert body["metrics"]["overdue_next_actions"] == {"value": 2, "with_next_action": 6,
                                                       "drill": {"tab": "deals", "attention": "overdue"}}
    assert body["metrics"]["pending_approvals"] == {"value": 3, "drill": {"tab": "deals", "sow": "pending"}}
    assert body["metrics"]["agreement_gap_clients"] == {
        "value": 4, "clients_total": 5, "any_agreement_files": True,
        "drill": {"tab": "clients", "missing": "agreements", "include_unmatched_clients": False}}
    assert body["focus"] == {"all_open": 12, "closing_this_month": 6, "mine": 2, "mine_available": True,
                             "needs_attention": 8, "watching": 2}
    assert body["unmapped_regions"] == 3
    assert body["page"] == {"number": 1, "size": 25, "total_rows": 12, "total_value_usd": "1075000.00"}
    assert body["tab_counts"] == {"deals": 12, "clients": 5}
    assert seeded.keys(body["rows"]) == ["d07", "d02", "d13", "d01", "d05", "d10", "d03", "d15", "d06",
                                         "d16", "d12", "d04"]


async def test_freshness_is_the_sync_health_record(api, seeded, session):
    from app.services.hubspot_sync_runs import compute_sync_health

    body = await workspace(api)
    assert body["freshness"] == await compute_sync_health(session, now=NOW)
    assert body["freshness"]["state"] == "fresh" and body["freshness"]["last_status"] == "ok"


async def test_stages_are_nine_all_status_counts(api, seeded):
    body = await workspace(api, status="won", bu="ST21")
    stages = body["stages"]
    assert [s["stage_id"] for s in stages] == list(range(1, 10))
    assert [s["label"] for s in stages] == SHORT_LABELS
    assert [s["full_label"] for s in stages] == FULL_LABELS
    # Status is ignored; BU is respected: ST21 = region "US".
    assert [s["deals"] for s in stages] == [2, 1, 1, 0, 0, 0, 2, 0, 1]
    everything = (await workspace(api, stage=[4], status="all"))["stages"]
    # The stage filter is ignored too: the navigator is an overview of the population.
    assert [s["deals"] for s in everything] == [2, 3, 2, 1, 1, 1, 2, 1, 2]
    assert [s["known_value_usd"] for s in everything] == [
        "160000.00", "300000.00", "170000.00", "0.00", "0.00", "400000.00", "100000.00", "20000.00", "45000.00"]
    # d04 has no amount; d05's EUR amount is known but not USD.
    assert [s["deals_without_amount"] for s in everything] == [0, 0, 0, 1, 0, 0, 0, 0, 0]


async def test_deal_row_fields(api, seeded):
    rows = {row["id"]: row for row in (await workspace(api, status="all", page_size=50))["rows"]}
    d01 = rows[str(seeded.deals["d01"])]
    assert d01 == {
        "id": str(seeded.deals["d01"]), "title": "Acme rollout",
        "client": {"id": str(seeded.clients["acme"]), "name": "Acme Retail"},
        "stage_id": 1, "stage_label": "Prospecting", "status": "open", "amount": "100000.00", "currency": "USD",
        "business_unit": "ST21", "region": "US", "region_note": None, "hubspot_region": "US",
        "bu_unmapped": False,
        "deal_owner": {"name": "Ava Archer", "state": "active"},
        "account_owner": {"name": "Ava Archer", "state": "active"},
        "close_date": "2026-10-19", "created_date": "2026-09-04", "last_activity_date": "2026-10-12",
        "days_since_activity": 2, "sow_state": "none", "sow_state_label": "No SOW", "sow_count": 0,
        "agreements": {"nda_on_file": True, "msa_on_file": True},
        "next_action": {"id": str(seeded.actions["d01"]), "text": "Send revised proposal", "due_on": "2026-10-11"},
        "flags": ["action_overdue"], "watching": True, "hubspot_deal_id": "hs-d01",
        "pipeline_label": PIPELINE_LABEL,
    }
    d04 = rows[str(seeded.deals["d04"])]
    assert (d04["amount"], d04["close_date"], d04["deal_owner"]) == (None, None, {"name": None, "state": "none"})
    assert (d04["business_unit"], d04["region"], d04["region_note"]) == ("IT Avalon", "US", "Staffing")
    assert d04["next_action"]["text"] == "Confirm budget owner" and d04["next_action"]["due_on"] is None
    assert d04["flags"] == ["no_owner"]
    d05 = rows[str(seeded.deals["d05"])]
    assert (d05["amount"], d05["currency"], d05["bu_unmapped"], d05["hubspot_region"]) == (
        "75000.00", "EUR", True, "Brazil")
    assert d05["next_action"]["text"] == "Chase CEO sign-off"  # no title: the description
    assert d05["flags"] == ["action_overdue", "inactive_14d"]
    d07 = rows[str(seeded.deals["d07"])]
    assert (d07["hubspot_region"], d07["bu_unmapped"], d07["business_unit"]) == (None, True, None)
    assert d07["flags"] == [] and d07["next_action"]["due_on"] == "2026-10-14"  # due today is not overdue
    d10 = rows[str(seeded.deals["d10"])]
    assert d10["created_date"] == "2026-09-29"  # no HubSpot created date: the record's own
    assert d10["deal_owner"] == {"name": None, "state": "archived"}  # owner id missing from the mirror
    d13 = rows[str(seeded.deals["d13"])]
    # The earliest due date first; an in-progress action is still open.
    assert d13["next_action"]["text"] == "Demo loyalty flow" and d13["next_action"]["due_on"] == "2026-10-24"
    d12 = rows[str(seeded.deals["d12"])]
    assert d12["client"] == {"id": None, "name": None} and d12["account_owner"] == {"name": None, "state": "none"}


async def test_closed_deals_never_carry_flags(api, seeded):
    rows = {row["id"]: row for row in (await workspace(api, status="all", page_size=50))["rows"]}
    d08 = rows[str(seeded.deals["d08"])]  # overdue action, closed won
    d09 = rows[str(seeded.deals["d09"])]  # closed lost, owner missing from the mirror
    assert d08["flags"] == [] and d08["next_action"]["text"] == "Archive the folder"
    assert d09["flags"] == []
    # The row says its status, so the page never infers it from a stage name.
    assert (d08["status"], d09["status"]) == ("won", "lost")
    assert {rows[str(seeded.deals[k])]["status"] for k in ("d06", "d16")} == {"hold"}
    assert rows[str(seeded.deals["d06"])]["flags"] == ["inactive_14d"]  # exactly 14 days counts
    assert rows[str(seeded.deals["d16"])]["flags"] == ["close_passed"]


# --- B13: owners ----------------------------------------------------------------


async def test_owner_states_and_filters(api, seeded):
    rows = {row["id"]: row for row in (await workspace(api, status="all", page_size=50))["rows"]}
    assert rows[str(seeded.deals["d03"])]["deal_owner"] == {"name": None, "state": "archived"}
    assert rows[str(seeded.deals["d03"])]["account_owner"] == {"name": None, "state": "archived"}
    assert rows[str(seeded.deals["d05"])]["account_owner"] == {"name": None, "state": "none"}
    assert rows[str(seeded.deals["d10"])]["account_owner"] == {"name": None, "state": "archived"}
    assert seeded.keys((await workspace(api, owner="none"))["rows"]) == ["d04"]
    assert sorted(seeded.keys((await workspace(api, owner="former", status="all"))["rows"])) == [
        "d03", "d09", "d10", "d16"]
    assert sorted(seeded.keys((await workspace(api, owner=["101", "none"]))["rows"])) == [
        "d01", "d02", "d04", "d12"]
    options = (await workspace(api))["options"]
    assert options["deal_owners"] == [{"id": "101", "name": "Ava Archer"}, {"id": "102", "name": "Ben Brook"},
                                      {"id": "104", "name": "Viewer Vance"}]
    assert options["account_owners"] == [{"id": "101", "name": "Ava Archer"}, {"id": "102", "name": "Ben Brook"}]


async def test_no_owner_is_an_open_deal_warning_only(api, seeded, session):
    deal = await session.get(Opportunity, seeded.deals["d09"])  # closed lost
    deal.hubspot_owner_id = None
    await session.commit()
    rows = {row["id"]: row for row in (await workspace(api, status="all", page_size=50))["rows"]}
    assert rows[str(seeded.deals["d09"])]["deal_owner"]["state"] == "none"
    assert rows[str(seeded.deals["d09"])]["flags"] == []
    assert seeded.keys((await workspace(api, attention="no_owner", status="all"))["rows"]) == ["d04"]


# --- B5: status -----------------------------------------------------------------


@pytest.mark.parametrize(("status", "keys"), [
    ("open", OPEN_KEYS),
    ("hold", ["d06", "d16"]),
    ("won", ["d08", "d11"]),
    ("lost", ["d09"]),
    ("all", sorted(DEALS)),
])
async def test_status(api, seeded, status, keys):
    body = await workspace(api, status=status, page_size=50)
    assert sorted(seeded.keys(body["rows"])) == sorted(keys)


# --- B6: SOW state, sorts, search ------------------------------------------------


async def test_sow_state_is_the_most_recently_updated_sow(api, seeded):
    rows = {seeded.key_of(row["id"]): row for row in (await workspace(api, status="all", page_size=50))["rows"]}
    states = {key: (row["sow_state"], row["sow_state_label"], row["sow_count"]) for key, row in rows.items()}
    assert states["d02"] == ("in_review_delivery_hr", "In review · delivery/hr", 1)
    assert states["d03"] == ("draft", "Draft", 1)  # its only package was voided
    assert states["d05"] == ("ceo_exception", "CEO exception", 1)
    assert states["d06"] == ("draft", "Draft", 2)  # not the approved one: the draft was updated later
    assert states["d07"] == ("signed", "Signed", 1)
    assert states["d10"] == ("in_review_finance_legal", "In review · finance/legal", 1)
    assert states["d11"] == ("approved", "Approved", 1)
    assert states["d13"] == ("awaiting_signature", "Awaiting signature", 1)
    assert states["d15"] == ("changes_requested", "Changes requested", 1)
    assert states["d01"] == ("none", "No SOW", 0)
    assert sorted(seeded.keys((await workspace(api, sow="pending", status="all"))["rows"])) == ["d02", "d05", "d10"]
    assert seeded.keys((await workspace(api, sow="draft"))["rows"]) == ["d03", "d06"]
    options = (await workspace(api))["options"]["sow_states"]
    assert [o["value"] for o in options] == ["none", "draft", "in_review_delivery_hr", "in_review_finance_legal",
                                             "changes_requested", "ceo_exception", "approved",
                                             "awaiting_signature", "signed"]
    assert options[2]["label"] == "In review · delivery/hr"


@pytest.mark.parametrize(("sort", "keys"), [
    # amount desc, raw (EUR 75000 sorts as 75000), no amount last
    ("value", ["d07", "d02", "d13", "d01", "d05", "d10", "d03", "d15", "d06", "d16", "d12", "d04"]),
    ("close", ["d02", "d16", "d07", "d10", "d01", "d06", "d13", "d12", "d03", "d05", "d15", "d04"]),
    # oldest activity first, no activity last (then by name)
    ("activity", ["d15", "d05", "d02", "d13", "d06", "d12", "d10", "d01", "d04", "d07", "d03", "d16"]),
    ("name", ["d02", "d13", "d01", "d03", "d15", "d04", "d05", "d06", "d16", "d07", "d10", "d12"]),
])
async def test_deal_sorts(api, seeded, sort, keys):
    assert seeded.keys((await workspace(api, sort=sort))["rows"]) == keys


@pytest.mark.parametrize(("q", "keys"), [
    ("acme", ["d01", "d02", "d13"]),  # client name (and titles)
    ("ROUTE", ["d15"]),  # title, case-insensitive
    ("ben brook", ["d05", "d13", "d15"]),  # deal owner name
    ("countersign", ["d07"]),  # next-action text
    ("ceo sign-off", ["d05"]),  # next-action text from the description
    ("cara", []),  # a former owner's name is not shown, so it is not searched
    ("hs-d01", []),  # ids are not searched
])
async def test_search(api, seeded, q, keys):
    assert sorted(seeded.keys((await workspace(api, q=q))["rows"])) == keys


# --- clients tab ------------------------------------------------------------------


async def test_client_rows(api, seeded):
    body = await workspace(api, tab="clients")
    rows = {row["id"]: row for row in body["rows"]}
    assert body["page"]["total_rows"] == 5 and body["page"]["total_value_usd"] is None
    assert body["tab_counts"] == {"deals": 12, "clients": 5}
    acme = rows[str(seeded.clients["acme"])]
    assert acme == {
        "id": str(seeded.clients["acme"]), "name": "Acme Retail",
        "account_owner": {"name": "Ava Archer", "state": "active"},
        "matching_deals": 3, "open_deals": 3, "matching_value_usd": "470000.00",
        "earliest_close_date": "2026-10-04", "last_activity_date": "2026-10-12", "days_since_activity": 2,
        "agreements": {"nda_on_file": True, "msa_on_file": True},
        "flags": ["action_overdue", "close_passed"], "hubspot_company_id": "c-acme",
    }
    cobalt = rows[str(seeded.clients["cobalt"])]
    assert cobalt["matching_value_usd"] == "30000.00" and cobalt["flags"] == ["action_overdue"]
    bolt = rows[str(seeded.clients["bolt"])]
    assert bolt["account_owner"] == {"name": None, "state": "archived"} and bolt["flags"] == ["no_owner"]
    # Filters narrow the matching deals; open_deals ignores them.
    narrowed = {row["id"]: row for row in (await workspace(api, tab="clients", q="loyalty"))["rows"]}
    assert narrowed[str(seeded.clients["acme"])]["matching_deals"] == 1
    assert narrowed[str(seeded.clients["acme"])]["open_deals"] == 3


async def test_a_client_without_open_deals_is_never_flagged(api, seeded):
    rows = {row["id"]: row for row in (await workspace(api, tab="clients", status="won"))["rows"]}
    garnet = rows[str(seeded.clients["garnet"])]
    assert (garnet["open_deals"], garnet["matching_deals"], garnet["flags"]) == (0, 1, [])
    delta = rows[str(seeded.clients["delta"])]  # its won deal has an overdue action
    assert delta["flags"] == []


async def test_account_owner_applies_to_clients_only(api, seeded):
    body = await workspace(api, tab="clients", account_owner="101")
    assert [row["name"] for row in body["rows"]] == ["Acme Retail"]
    assert body["tab_counts"] == {"deals": 12, "clients": 1}
    assert [row["name"] for row in (await workspace(api, tab="clients", account_owner="none"))["rows"]] == [
        "Cobalt Health"]
    deals = await workspace(api, account_owner="101")
    assert deals["page"]["total_rows"] == 12  # never applied to deal rows


async def test_include_unmatched_clients(api, seeded):
    body = await workspace(api, tab="clients", include_unmatched_clients="true", sort="name")
    assert [row["name"] for row in body["rows"]] == [
        "Acme Retail", "Bolt Logistics", "Cobalt Health", "Delta Foods", "Echo Media", "Fjord Energy",
        "Garnet Labs"]
    fjord = body["rows"][5]
    assert (fjord["matching_deals"], fjord["open_deals"], fjord["matching_value_usd"], fjord["flags"]) == (
        0, 0, None, [])
    assert fjord["agreements"] == {"nda_on_file": False, "msa_on_file": True}
    assert body["tab_counts"]["clients"] == 7
    # A search keeps every matched client and adds unmatched ones by name only.
    searched = await workspace(api, tab="clients", include_unmatched_clients="true", q="energy")
    assert [row["name"] for row in searched["rows"]] == ["Fjord Energy"]
    owned = await workspace(api, tab="clients", include_unmatched_clients="true", account_owner="101", sort="name")
    assert [row["name"] for row in owned["rows"]] == ["Acme Retail", "Fjord Energy"]


@pytest.mark.parametrize(("sort", "names"), [
    ("value", ["Acme Retail", "Delta Foods", "Bolt Logistics", "Echo Media", "Cobalt Health"]),
    ("close", ["Acme Retail", "Delta Foods", "Echo Media", "Cobalt Health", "Bolt Logistics"]),
    # latest matching activity, oldest first: Cobalt Sep 30, Echo Oct 11, Acme Oct 12, Bolt Oct 13, Delta Oct 14
    ("activity", ["Cobalt Health", "Echo Media", "Acme Retail", "Bolt Logistics", "Delta Foods"]),
    ("name", ["Acme Retail", "Bolt Logistics", "Cobalt Health", "Delta Foods", "Echo Media"]),
])
async def test_client_sorts(api, seeded, sort, names):
    assert [row["name"] for row in (await workspace(api, tab="clients", sort=sort))["rows"]] == names


# --- filters ----------------------------------------------------------------------


@pytest.mark.parametrize(("params", "keys"), [
    ({"attention": "overdue"}, ["d01", "d05"]),
    ({"attention": "past_close"}, ["d02", "d16"]),
    ({"attention": "no_owner"}, ["d04"]),
    ({"attention": "inactive"}, ["d02", "d05", "d06", "d13", "d15"]),
    ({"attention": "pending_approval"}, ["d02", "d05", "d10"]),
    ({"attention": "any"}, ["d01", "d02", "d04", "d05", "d06", "d13", "d15", "d16"]),
    ({"attention": "overdue", "status": "all"}, ["d01", "d05"]),  # d08 is closed
    ({"missing": "owner"}, ["d04"]),
    ({"missing": "close"}, ["d04"]),
    ({"missing": "activity"}, ["d03", "d16"]),
    ({"missing": "next_action"}, ["d03", "d06", "d10", "d12", "d15", "d16"]),
    ({"missing": "nda"}, ["d05", "d06", "d07", "d10", "d12", "d16"]),
    ({"missing": "msa"}, ["d03", "d04", "d05", "d06", "d10", "d12", "d15"]),
    ({"missing": "agreements"}, ["d03", "d04", "d05", "d06", "d07", "d10", "d12", "d15", "d16"]),
    ({"bu": "ST21"}, ["d01", "d06", "d10", "d12", "d13"]),
    ({"bu": "IT Avalon"}, ["d02", "d04", "d15"]),
    ({"bu": "Retro Rabbit"}, ["d03"]),
    ({"bu": "unmapped"}, ["d05", "d07", "d16"]),
    ({"bu": ["Retro Rabbit", "unmapped"]}, ["d03", "d05", "d07", "d16"]),
    ({"stage": [1, 9], "status": "all"}, ["d01", "d06", "d10", "d16"]),
    ({"watching": "true"}, ["d01", "d06"]),
    ({"watching": "true", "status": "all"}, ["d01", "d06", "d08"]),
    ({"mine": "true"}, ["d06", "d07"]),
    ({"date_field": "close", "date_preset": "passed"}, ["d02", "d16"]),
    ({"date_field": "activity", "date_preset": "last7"}, ["d01", "d04", "d07", "d10", "d12"]),
    ({"date_field": "created", "date_preset": "last7"}, ["d04", "d07"]),
    ({"date_field": "close", "date_preset": "custom", "date_from": "2026-10-15", "date_to": "2026-10-19"},
     ["d01", "d07", "d10"]),
])
async def test_filters(api, seeded, params, keys):
    assert sorted(seeded.keys((await workspace(api, page_size=50, **params))["rows"])) == keys


async def test_groups_are_the_viewers_own(api, seeded):
    assert sorted(seeded.keys((await workspace(api, group=str(seeded.group)))["rows"])) == ["d04", "d07"]
    assert (await workspace(api, group=str(seeded.other_group)))["rows"] == []
    assert (await workspace(api, group=str(uuid.uuid4())))["rows"] == []


async def test_client_parameter_restricts_to_one_clients_deals(api, seeded):
    body = await workspace(api, client=str(seeded.clients["bolt"]), status="all")
    assert sorted(seeded.keys(body["rows"])) == ["d03", "d04", "d15"]
    assert body["metrics"]["open_deals"]["value"] == 3


async def test_focus_ignores_the_current_filters(api, seeded):
    narrowed = await workspace(api, bu="Retro Rabbit", status="won", q="zzz")
    assert narrowed["focus"] == (await workspace(api))["focus"]


async def test_mine_without_a_link(session, seeded):
    stranger = AuthUser(uuid.uuid4(), "stranger@example.test", "Stranger", ("Sales",))
    async with client_for(session, stranger) as client:
        body = await workspace(client, mine="true")
    assert body["rows"] == [] and body["focus"]["mine"] is None and body["focus"]["mine_available"] is False
    assert body["focus"]["watching"] == 0  # no DealGate row yet: nothing watched


async def test_hidden_rows_never_appear(api, seeded):
    body = await workspace(api, status="all", page_size=100, tab="clients", include_unmatched_clients="true")
    assert "Old Co" not in [row["name"] for row in body["rows"]]
    deals = await workspace(api, status="all", page_size=100)
    assert not {str(v) for v in seeded.hidden.values()} & {row["id"] for row in deals["rows"]}


# --- B9: paging and board ------------------------------------------------------------


@pytest.mark.parametrize("size", [0, 6, 10, 12, 26, 1000])
async def test_page_size_must_be_25_50_or_100(api, seeded, size):
    response = await api.get("/pipeline/workspace", params={"page_size": size})
    assert response.status_code == 422
    assert response.json()["detail"] == "page_size must be one of 25, 50, 100"


@pytest.mark.parametrize(("params", "name"), [
    ({"status": "closed"}, "status"), ({"tab": "accounts"}, "tab"), ({"bu": "Avalon"}, "bu"),
    ({"sort": "attention"}, "sort"), ({"attention": "stalled"}, "attention"), ({"missing": "stage"}, "missing"),
    ({"stage": 10}, "stage"), ({"stage": 0}, "stage"), ({"sow": "scope_gm"}, "sow"), ({"layout": "grid"}, "layout"),
    ({"date_preset": "this_month"}, "date_preset"), ({"date_field": "action_due"}, "date_field"),
    ({"group": "not-a-uuid"}, "group"), ({"page": 0}, "page"), ({"q": "x" * 121}, "q"),
    ({"date_preset": "custom", "date_from": "2026-10-20", "date_to": "2026-10-10"}, "date_from"),
])
async def test_unknown_values_are_rejected(api, seeded, params, name):
    response = await api.get("/pipeline/workspace", params=params)
    assert response.status_code == 422, response.text
    assert name in response.text


async def test_paging(api, seeded):
    first = await workspace(api, status="all", page_size=25, page=1, sort="name")
    assert len(first["rows"]) == 15 and first["page"]["total_rows"] == 15
    beyond = await workspace(api, status="all", page_size=25, page=2)
    assert beyond["rows"] == [] and beyond["page"] == {"number": 2, "size": 25, "total_rows": 15,
                                                       "total_value_usd": "1195000.00"}
    for size in (50, 100):
        assert (await workspace(api, page_size=size))["page"]["size"] == size


async def test_board(api, seeded):
    body = await workspace(api, layout="board", status="all")
    assert body["rows"] == []
    assert body["page"]["total_rows"] == 15
    lanes = body["rows_by_stage"]
    assert list(lanes) == ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
    assert lanes["2"]["total"] == 3 and lanes["2"]["value_usd"] == "300000.00"
    assert seeded.keys(lanes["2"]["deals"]) == ["d02", "d15", "d12"]
    assert lanes["4"] == {"total": 1, "value_usd": "0.00", "deals": lanes["4"]["deals"]}
    # Only stages with a filtered deal get a lane.
    open_board = await workspace(api, layout="board")
    assert list(open_board["rows_by_stage"]) == ["1", "2", "3", "4", "5", "6", "9"]


async def test_board_lanes_hold_at_most_six_deals(api, seeded, session):
    stage_id, label, order, _ = STAGES[0]
    for index in range(8):
        session.add(Opportunity(source="hubspot", hubspot_deal_id=f"hs-bulk-{index}", name=f"Bulk {index}",
                                client_id=seeded.clients["acme"], hubspot_pipeline_id=PIPELINE_ID,
                                hubspot_stage_id=stage_id, stage_label=label, stage_order=order,
                                amount=Decimal(1000 + index), currency="USD", governance_status="Intake"))
    await session.commit()
    lane = (await workspace(api, layout="board"))["rows_by_stage"]["1"]
    assert lane["total"] == 10 and len(lane["deals"]) == 6
    assert [row["title"] for row in lane["deals"]][:2] == ["Acme rollout", "Echo studio tools"]


async def test_clients_board_is_the_paged_client_rows(api, seeded):
    body = await workspace(api, tab="clients", layout="board")
    assert body["rows_by_stage"] is None and len(body["rows"]) == 5


# --- gate and old endpoints ------------------------------------------------------------


async def test_role_gate(session, seeded):
    outsider = AuthUser(uuid.uuid4(), "outsider@example.test", "Outsider", ("Marketing",))
    async with client_for(session, outsider) as client:
        assert (await client.get("/pipeline/workspace")).status_code == 403
    for role in ("Sales", "Presales", "Finance", "SalesLeader"):
        reader = AuthUser(uuid.uuid4(), f"{role.lower()}@example.test", role, (role,))
        async with client_for(session, reader) as client:
            assert (await client.get("/pipeline/workspace")).status_code == 200


async def test_the_old_endpoints_still_answer(api, seeded, session):
    # The old list code subtracts SQLite's naive activity timestamps from an aware "now"
    # (hubspot_pipeline.py _derive_attention / list_clients; pre-existing, never on Postgres),
    # so this smoke test clears them. /pipeline/clients is left out for the same reason.
    from sqlalchemy import update

    await session.execute(update(Opportunity).values(hubspot_last_activity_at=None))
    await session.commit()
    for path in ("/pipeline/opportunities", "/pipeline/summary", "/pipeline/facets",
                 "/pipeline/opportunities?watching=true"):
        response = await api.get(path)
        assert response.status_code == 200, (path, response.text)
    watched = (await api.get("/pipeline/opportunities", params={"watching": "true"})).json()
    # Canonical viewer: the watches are keyed on the DealGate id, not the login id. The old
    # endpoint also expands the watched client (Echo Media) into its open deal d10.
    assert {row["opportunity_id"] for row in watched["items"]} == {
        str(seeded.deals[key]) for key in ("d01", "d06", "d10")}
