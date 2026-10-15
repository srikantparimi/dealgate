"""S23-PL2 T3 / B3 — HubSpot region value → business unit, editable in Settings.

Deals carry HubSpot region values. ``hubspot_region_map`` says which business
unit each value is and which region to show beside it; it is read at request
time, so a Settings edit changes every deal row immediately, with no resync.
"""

from __future__ import annotations

import importlib.util
import pathlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_session
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.services.hubspot_properties import HubspotPropertyMapping
from tests.test_s23_pl2_personal import needs_postgres, pg_api  # noqa: F401 — shared Postgres fixture

ADMIN = {"X-Test-User": "admin@example.test"}
SALES = {"X-Test-User": "rep@example.test"}
SEED_VALUES = ["South Africa", "US - IT Avalon (Staffing)", "US - IT Avalon", "US"]


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")


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
async def deals(session) -> dict[str | None, list[uuid.UUID]]:
    """Deals carrying each seeded region, an unmapped one, and none at all.

    The four seeded rows are what migration 0070 writes; create_all does not
    run migrations, so the test seeds the same rows.
    """
    session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    values = [*SEED_VALUES, "US - Other"]
    session.add(HubspotPropertyMapping(
        key="business_unit", internal_name="region", object_type="deal", label="Region",
        field_type="enumeration", options=[{"value": v, "label": v} for v in values],
        availability_state="configured", mapping_version=3))
    session.add(HubspotPipeline(id="p1", label="Global sales pipeline", display_order=0, archived=False))
    await session.flush()
    session.add(HubspotStage(id="s2", pipeline_id="p1", label="2-Qualification", display_order=1,
                             is_closed=False, probability=Decimal("0.20"), archived=False))
    client = Client(name="Keystone Energy", hubspot_company_id="c-1")
    session.add(client)
    await session.flush()
    out: dict[str | None, list[uuid.UUID]] = {}
    plan = [(v, 1) for v in SEED_VALUES] + [("US - Other", 2), (None, 1)]
    for value, count in plan:
        for i in range(count):
            deal = Opportunity(
                source="hubspot", hubspot_deal_id=f"{value}-{i}", name=f"{value or 'No region'} deal {i}",
                client_id=client.id, amount=Decimal("1000.00"), currency="USD", close_date=date(2026, 12, 1),
                hubspot_pipeline_id="p1", hubspot_stage_id="s2", stage_label="2-Qualification", stage_order=1,
                business_unit_value=value, business_unit_mapping_version=3 if value else None,
                business_unit_observed_at=datetime(2026, 10, 1, tzinfo=UTC) if value else None)
            session.add(deal)
            await session.flush()
            out.setdefault(value, []).append(deal.id)
    # An archived deal never counts.
    session.add(Opportunity(source="hubspot", hubspot_deal_id="gone", name="Archived deal", client_id=client.id,
                            business_unit_value="US - Other", business_unit_mapping_version=3,
                            business_unit_observed_at=datetime(2026, 10, 1, tzinfo=UTC),
                            archived_at=datetime(2026, 10, 2, tzinfo=UTC)))
    await session.commit()
    return out


def test_seed_is_the_directive_mapping_and_matches_the_migration():
    assert [(r["hubspot_value"], r["business_unit"], r["region"], r["note"]) for r in DEFAULT_REGION_MAP] == [
        ("South Africa", "Retro Rabbit", "South Africa", None),
        ("US - IT Avalon (Staffing)", "IT Avalon", "US", "Staffing"),
        ("US - IT Avalon", "IT Avalon", "US", None),
        ("US", "ST21", "US", None),
    ]
    path = pathlib.Path(__file__).resolve().parents[1] / "alembic/versions/20261014_0070_pl2_workspace.py"
    spec = importlib.util.spec_from_file_location("migration_0070", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert list(module.REGION_SEED) == list(DEFAULT_REGION_MAP)


async def test_settings_lists_the_map_and_unmapped_values_with_deal_counts(api, deals):
    r = await api.get("/settings/business-units", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == [
        {"hubspot_value": "South Africa", "business_unit": "Retro Rabbit", "region": "South Africa", "note": None},
        {"hubspot_value": "US", "business_unit": "ST21", "region": "US", "note": None},
        {"hubspot_value": "US - IT Avalon", "business_unit": "IT Avalon", "region": "US", "note": None},
        {"hubspot_value": "US - IT Avalon (Staffing)", "business_unit": "IT Avalon", "region": "US",
         "note": "Staffing"},
    ]
    # Only the value with no map row, counted over live deals; the deal with
    # no region at all is reported separately.
    assert body["unmapped_on_deals"] == [{"hubspot_value": "US - Other", "deals": 2}]
    assert body["deals_without_region"] == 1
    assert body["business_units"] == ["ST21", "IT Avalon", "Retro Rabbit"]


async def test_replace_maps_a_new_value_and_audits(api, session, deals):
    current = (await api.get("/settings/business-units", headers=ADMIN)).json()["rows"]
    new_rows = [*current, {"hubspot_value": "US - Other", "business_unit": "ST21", "region": "US",
                           "note": "  Other  "}]
    r = await api.put("/settings/business-units", headers=ADMIN, json={"rows": new_rows})
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"hubspot_value": "US - Other", "business_unit": "ST21", "region": "US", "note": "Other"} in body["rows"]
    assert body["unmapped_on_deals"] == []

    session.expire_all()
    [event] = (await session.scalars(
        select(AuditEvent).where(AuditEvent.action == "business_unit_map.replaced"))).all()
    assert len(event.before["rows"]) == 4 and len(event.after["rows"]) == 5
    stored = (await session.scalars(select(HubspotRegionMap).where(HubspotRegionMap.hubspot_value == "US - Other"))).one()
    assert stored.updated_by is not None

    # Saving the same map again changes nothing and writes no audit row.
    assert (await api.put("/settings/business-units", headers=ADMIN, json={"rows": body["rows"]})).status_code == 200
    session.expire_all()
    assert len((await session.scalars(
        select(AuditEvent).where(AuditEvent.action == "business_unit_map.replaced"))).all()) == 1


@pytest.mark.parametrize("rows,needle", [
    ([{"hubspot_value": "US", "business_unit": "ST21", "region": "US"},
      {"hubspot_value": "US", "business_unit": "IT Avalon", "region": "US"}], "“US” is mapped twice"),
    ([{"hubspot_value": "US", "business_unit": "Avalon", "region": "US"}], "ST21, IT Avalon or Retro Rabbit"),
    ([{"hubspot_value": "US", "business_unit": "ST21", "region": "  "}], "region"),
    ([{"hubspot_value": "  ", "business_unit": "ST21", "region": "US"}], "HubSpot value"),
])
async def test_replace_rejects_an_invalid_map(api, session, deals, rows, needle):
    r = await api.put("/settings/business-units", headers=ADMIN, json={"rows": rows})
    assert r.status_code == 422
    assert needle in r.json()["detail"]
    session.expire_all()
    assert len((await session.scalars(select(HubspotRegionMap))).all()) == 4


async def test_only_a_system_admin_reads_or_writes_the_map(api, deals, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales,SalesLeader,Finance")
    assert (await api.get("/settings/business-units", headers=SALES)).status_code == 403
    assert (await api.put("/settings/business-units", headers=SALES,
                          json={"rows": list(DEFAULT_REGION_MAP)})).status_code == 403


# --- deal rows on the workspace (lane L1's endpoint) ---------------------------


async def test_workspace_rows_carry_bu_region_note_and_unmapped(api, deals, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    r = await api.get("/pipeline/workspace", headers=SALES, params={"status": "all", "page_size": 25})
    assert r.status_code == 200, r.text
    rows = {row["id"]: row for row in r.json()["rows"]}

    def shown(value):
        row = rows[str(deals[value][0])]
        return (row["business_unit"], row["region"], row["region_note"], row["hubspot_region"], row["bu_unmapped"])

    assert shown("South Africa") == ("Retro Rabbit", "South Africa", None, "South Africa", False)
    assert shown("US - IT Avalon (Staffing)") == ("IT Avalon", "US", "Staffing", "US - IT Avalon (Staffing)", False)
    assert shown("US - IT Avalon") == ("IT Avalon", "US", None, "US - IT Avalon", False)
    assert shown("US") == ("ST21", "US", None, "US", False)
    assert shown("US - Other") == (None, None, None, "US - Other", True)
    assert shown(None) == (None, None, None, None, True)
    assert r.json()["unmapped_regions"] == 3


async def test_a_settings_edit_changes_workspace_rows_immediately(api, deals, monkeypatch):
    current = (await api.get("/settings/business-units", headers=ADMIN)).json()["rows"]
    edited = [{**row, "business_unit": "IT Avalon"} if row["hubspot_value"] == "US" else row for row in current]
    assert (await api.put("/settings/business-units", headers=ADMIN, json={"rows": edited})).status_code == 200

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    r = await api.get("/pipeline/workspace", headers=SALES, params={"status": "all", "bu": "IT Avalon"})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["rows"]}
    assert str(deals["US"][0]) in ids
    row = next(row for row in r.json()["rows"] if row["id"] == str(deals["US"][0]))
    assert (row["business_unit"], row["region"]) == ("IT Avalon", "US")


@needs_postgres
async def test_postgres_unmapped_counts_and_replace(pg_api):  # noqa: F811 — the imported fixture
    api, factory = pg_api
    tag = uuid.uuid4().hex[:8]
    value = f"PL2 region {tag}"
    async with factory() as s:
        mapping = await s.get(HubspotPropertyMapping, "business_unit")
        if mapping is None:
            mapping = HubspotPropertyMapping(key="business_unit", mapping_version=1)
            s.add(mapping)
        mapping.internal_name, mapping.object_type, mapping.label = "region", "deal", "Region"
        mapping.field_type, mapping.availability_state = "enumeration", "configured"
        mapping.options = [*(mapping.options or []), {"value": value, "label": value}]
        await s.flush()
        client = Client(name=f"PG BU client {tag}", hubspot_company_id=f"pg-bu-{tag}")
        s.add(client)
        await s.flush()
        for i in range(2):
            s.add(Opportunity(source="hubspot", hubspot_deal_id=f"pg-bu-{tag}-{i}", name=f"PG BU deal {i}",
                              client_id=client.id, business_unit_value=value,
                              business_unit_mapping_version=mapping.mapping_version,
                              business_unit_observed_at=datetime(2026, 10, 1, tzinfo=UTC)))
        await s.commit()

    body = (await api.get("/settings/business-units", headers=ADMIN)).json()
    assert {"hubspot_value": value, "deals": 2} in body["unmapped_on_deals"]
    seeded = {r["hubspot_value"] for r in body["rows"]}
    assert set(SEED_VALUES) <= seeded

    rows = [*body["rows"], {"hubspot_value": value, "business_unit": "Retro Rabbit", "region": "South Africa",
                            "note": None}]
    r = await api.put("/settings/business-units", headers=ADMIN, json={"rows": rows})
    assert r.status_code == 200, r.text
    after = r.json()
    assert value not in {u["hubspot_value"] for u in after["unmapped_on_deals"]}
    assert {"hubspot_value": value, "business_unit": "Retro Rabbit", "region": "South Africa", "note": None} in (
        after["rows"])
    async with factory() as s:
        stored = await s.get(HubspotRegionMap, value)
        assert stored is not None and stored.updated_by is not None
