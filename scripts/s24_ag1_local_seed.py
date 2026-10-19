"""S24-AG1 local seed for the Agreements Playwright run (T9, T14). Loopback databases only.

Seeds a realistic population on a freshly migrated local Postgres: the staging pipeline's nine stages,
the default region map, and about thirty clients covering every classification the page shows
(existing through a Closed Won deal, an SOW or a forecast-model engagement; net new at stages 1 to 6,
on Hold, Closed Lost only, no deals; an "Unknown company" placeholder; a duplicate-name pair; a client
created by a test identity; and a hostile name for the escaping check). No agreements: the run starts
in the prototype's "Staging tonight" state and uploads its own synthetic files.

T-D additions (the Playwright run): an existing client whose only open deal is in stage 1 (the attach wizard's
"Deals only in stage 1" exclusion), which also takes the population past one page of 25, and raw HubSpot msa_type
values on three deals so the HubSpot hints dialog and the panel's hint have something to show.

Usage: POSTGRES_URL=postgresql+asyncpg://…@localhost:55432/dealgate_ag1_e2e python scripts/s24_ag1_local_seed.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

PIPELINE_ID = "710688094"
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
E2E_USER_ID = uuid.UUID("00000000-0000-4000-8000-0000000000e2")
TODAY = date.today()
HOSTILE = '<img src=x onerror="window.__agXss=1">Hostile & Co'

# name → (company?, deals [(position 1-9, region)], sow?, engagement BU?, forecast?)
# position: 1-6 open stages, 7 won, 8 lost, 9 hold
CLIENTS: list[tuple[str, bool, list[tuple[int, str]], bool, str | None, bool]] = [
    ("Atlas Foods", True, [(7, "US"), (4, "US")], False, None, False),
    ("Beacon Logistics", True, [(7, "US - IT Avalon")], False, None, False),
    ("Cobalt Systems", True, [(3, "South Africa")], True, None, False),
    ("Delta Health", False, [], False, "Retro Rabbit", True),
    ("Ember Retail", True, [(2, "US")], False, None, False),
    ("Falcon Capital", True, [(5, "US - IT Avalon")], False, None, False),
    ("Granite Media", True, [(6, "South Africa")], False, None, False),
    ("Harbor Labs", True, [(1, "US")], False, None, False),
    ("Indigo Partners", True, [(1, "US"), (8, "US")], False, None, False),
    ("Juniper Group", True, [(8, "South Africa")], False, None, False),
    ("Keystone Brands", True, [], False, None, False),
    ("Lantern Energy", True, [(9, "US - IT Avalon (Staffing)")], False, None, False),
    ("Unknown company (deal 4417)", False, [(2, "US")], False, None, False),
    ("Meridian Retail", True, [(7, "US")], False, None, False),
    ("Meridian Retail, LLC", True, [(3, "US")], False, None, False),
    (HOSTILE, True, [(3, "US")], False, None, False),
    ("Northgate Dental", False, [], False, "ST21", True),
    ("Orchard Health", True, [(7, "South Africa"), (2, "South Africa")], True, None, False),
    ("Pinnacle Motors", True, [(4, "US")], False, None, False),
    ("Quarry Telecom", True, [(7, "US - IT Avalon"), (8, "US")], False, None, False),
    ("Redwood Pharma", True, [(6, "US")], False, None, False),
    ("Summit Gaming", True, [(2, "South Africa"), (8, "South Africa")], False, None, False),
    ("Timber Freight", True, [(7, "US")], False, "IT Avalon", False),
    ("Union Textiles", True, [(1, "South Africa")], False, None, False),
    ("Vantage Realty", True, [(5, "US")], False, None, False),
    ("Willow Farms", True, [(8, "US")], False, None, False),
    ("Zephyr Brands", True, [(7, "US"), (5, "US")], False, None, False),
    ("Alder Holdings", True, [(3, "US - IT Avalon")], False, None, False),
    ("Birch Analytics", True, [(1, "US")], True, None, False),
]

# Raw HubSpot msa_type on the client's first deal (B9 hints; synthetic values).
MSA_TYPE = {"Redwood Pharma": "Signed", "Juniper Group": "Signed", "Willow Farms": "Not signed"}


def _guard(url: str) -> None:
    host = make_url(url).host or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        sys.exit(f"refusing to seed a non-loopback database host: {host!r}")


async def main() -> None:
    url = os.environ["POSTGRES_URL"]
    _guard(url)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
    from app.audit import append_audit
    from app.models.client import Client
    from app.models.engagement import Allocation, Engagement, Resource
    from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
    from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow
    from app.models.user import User
    from app.services.hubspot_properties import HubspotPropertyMapping

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        if (await s.execute(text("select count(*) from client"))).scalar():
            sys.exit("the database already has clients; seed a fresh one")
        e2e = User(id=E2E_USER_ID, email="e2e-local@example.test", name="E2E Local Bot",
                   groups=["SystemAdmin", "officeapp-e2e"])
        s.add(e2e)
        s.add(HubspotPipeline(id=PIPELINE_ID, label="SmarTek21 Global Pipeline", display_order=0, archived=False))
        await s.flush()
        s.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order, is_closed=closed,
                                probability=Decimal("0.10"), archived=False) for sid, label, order, closed in STAGES])
        if not (await s.execute(text("select count(*) from hubspot_region_map"))).scalar():
            s.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])  # migration 0070 seeds it on Postgres
        if not (await s.execute(text("select count(*) from hubspot_property_mapping"))).scalar():
            # the deal BU property as configured on staging; regions resolve only when it is configured
            s.add(HubspotPropertyMapping(
                key="business_unit", internal_name="region", object_type="deal", label="Region",
                field_type="enumeration", availability_state="configured", mapping_version=1,
                options=[{"value": v, "label": v} for v in
                         ("South Africa", "US - IT Avalon (Staffing)", "US - IT Avalon", "US")]))
        resource = Resource(name="TBC", location="US", employment_type="employee")
        s.add(resource)
        await s.flush()
        n = 0
        for name, company, deals, sow, eng_bu, forecast in CLIENTS:
            n += 1
            client = Client(name=name, hubspot_company_id=f"c-{n:03d}" if company else None)
            s.add(client)
            await s.flush()
            for i, (position, region) in enumerate(deals):
                sid, label, order, _closed = STAGES[position - 1]
                close = TODAY - timedelta(days=200) if position in (7, 8) else TODAY + timedelta(days=30)
                s.add(Opportunity(
                    source="hubspot", hubspot_deal_id=f"hs-{n:03d}-{i}", name=f"{name.split('<')[0] or 'Deal'} deal {i + 1}",
                    client_id=client.id, hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label,
                    sales_stage=label, stage_order=order, is_closed_won=position == 7, is_closed_lost=position == 8,
                    amount=Decimal("50000"), currency="USD", close_date=close, governance_status="Intake",
                    business_unit_value=region, business_unit_mapping_version=1,
                    business_unit_observed_at=datetime.now(UTC), hubspot_last_modified_at=datetime.now(UTC),
                    hubspot_msa_type=MSA_TYPE.get(name) if i == 0 else None))
            await s.flush()
            if sow:
                deal = (await s.execute(text("select id from opportunity where client_id = :c limit 1"),
                                        {"c": client.id})).scalar()
                s.add(Sow(opportunity_id=deal))
            if eng_bu:
                eng = Engagement(client_id=client.id, name=f"{name} engagement", type="staff_augmentation",
                                 start=TODAY - timedelta(days=300), end=TODAY + timedelta(days=60),
                                 business_unit=eng_bu)
                s.add(eng)
                await s.flush()
                if forecast:
                    s.add(Allocation(engagement_id=eng.id, resource_id=resource.id, role="Engineer", location="US",
                                     employment_type="employee", utilization=Decimal("1"), import_key=f"seed:{n}"))
            if name == "Orchard Health":
                # created by a test identity: the test-data flag comes from this audit row
                await append_audit(s, actor_id=E2E_USER_ID, action="client.created", entity="client",
                                   entity_id=str(client.id), before=None, after={"name": name, "source": "sow_upload"})
        await s.commit()
        print(f"seeded {n} clients")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
