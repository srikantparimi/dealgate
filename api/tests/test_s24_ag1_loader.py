"""S24-AG1 T1, database part (lane T-C) — load_agreement_population builds the ClientInput the rows say.

The pure rules are table-tested in test_s24_ag1_t1_table.py. This file checks the query layer that feeds them
(agreement_status.load_agreement_population), on SQLite with foreign keys on and on a scratch Postgres, where
timestamptz values come back aware, groups are JSONB and the hint uses row_number():

* relationship stamps: the stored value and basis, who set it (a display name, never an id) and when;
* SOW and engagement dates are America/Los_Angeles calendar dates (la_date), first and last, archived SOWs
  left out: an SOW stored at 05:30 UTC on 2 October is 1 October in Los Angeles (the cutover day, so it is
  not "after the cutover"), and an engagement stored at 07:30 UTC is 2 October (after it);
* deals as the rules see them: Hold, an open deal in a stage the mirror does not have, Closed Won close dates
  (the B8 "company has an earlier win" rule), lost deals; archived deals and local SOW-upload deals left out;
* business units paired with their regions (deals through the region map, engagements through their unit);
  an unmapped region gives its reason and never a unit;
* the test-data flag from the client.created actor (a test identity) or a run tag in the name;
* the forecast flag from an allocation's import_key (basis text "Engagement from the forecast model");
* what each kind holds (agreement row source, standard version, batch label, active mark source) and the
  HubSpot msa_type hint (the value on the most recently modified deal that has one).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.audit import append_audit
from app.auth import AuthUser
from app.models.agreements import AgreementBatch, AgreementMark, AgreementsSettings, StandardAgreement
from app.models.client import Agreement, Client
from app.models.engagement import Allocation, Engagement, Resource
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.services.agreement_status import (
    DocInput,
    Population,
    business_unit_text,
    client_row,
    load_agreement_population,
)
from app.services.hubspot_owners import HubspotOwner  # noqa: F401 — registers the table for create_all
from app.services.hubspot_properties import HubspotPropertyMapping
from tests.s24_pg import POSTGRES, scratch_postgres

NOW = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)  # 12:00 in Los Angeles
CUTOVER = date(2026, 10, 1)
STAMP_AT = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
PIPELINE_ID = "t1-loader"
STAGES = (  # HubSpot stage id, label, display order, closed (as on staging)
    ("t1-s1", "1-Initial Contact/Prospecting", 0, False), ("t1-s2", "2-Qualification", 1, False),
    ("t1-s3", "3-Requirement/Fit Gap Analysis", 2, False), ("t1-s4", "4-Proposal", 3, False),
    ("t1-s5", "5-Negotiation", 4, False), ("t1-s6", "6-Contracting/Drive Commitment", 5, False),
    ("t1-s7", "7-Closed Won", 6, True), ("t1-s8", "8-Closed Lost", 7, True), ("t1-s9", "Hold", 8, False),
)
ADMIN = AuthUser(uuid.UUID("00000000-0000-4000-8000-00000000c1a1"), "ada@example.test", "Ada Admin", ("SystemAdmin",))
LEGAL = AuthUser(uuid.UUID("00000000-0000-4000-8000-00000000c1b2"), "lee@example.test", "Lee Legal", ("Legal",))
BOT = AuthUser(uuid.UUID("00000000-0000-4000-8000-00000000c1e2"), "e2e-runner@example.test", "E2E Runner",
               ("SystemAdmin", "officeapp-e2e"))
VIEWER = AuthUser(uuid.UUID("00000000-0000-4000-8000-00000000c1f3"), "vera@example.test", "Vera Viewer",
                  ("SalesLeader",))


def at_utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_NOW", NOW.isoformat())
    monkeypatch.delenv("DEALGATE_TENANT_ID", raising=False)


# --- the world -----------------------------------------------------------------------------------------


async def seed_reference(session) -> None:
    """Users, the staging stage mirror, the business-unit mapping, the region map and the cutover."""
    session.add_all([User(id=u.id, email=u.email, name=u.name, groups=list(u.groups))
                     for u in (ADMIN, LEGAL, BOT, VIEWER)])
    session.add(HubspotPipeline(id=PIPELINE_ID, label="T1 Pipeline", display_order=0, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    if await session.get(HubspotPropertyMapping, "business_unit") is None:
        session.add(HubspotPropertyMapping(
            key="business_unit", internal_name="region", object_type="deal", label="Region",
            field_type="enumeration", availability_state="configured", mapping_version=1,
            options=[{"value": v, "label": v} for v in ("US", "US - IT Avalon", "South Africa", "Brazil")]))
    if not await session.scalar(select(func.count()).select_from(HubspotRegionMap)):  # 0070 seeds it on Postgres
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    settings = await session.get(AgreementsSettings, 1)  # 0072 inserts it on Postgres
    if settings is None:
        settings = AgreementsSettings(id=1)
        session.add(settings)
    settings.cutover_date, settings.set_by, settings.set_at = CUTOVER, ADMIN.id, STAMP_AT
    await session.flush()


def deal(client_id: uuid.UUID, key: str, position: int, *, region: str | None = None, close: date | None = None,
         msa: str | None = None, modified: datetime | None = None, stage_id: str | None = None,
         archived: bool = False) -> Opportunity:
    sid, label, order, _closed = STAGES[position - 1]
    return Opportunity(
        source="hubspot", hubspot_deal_id=f"t1-{key}", name=f"Deal {key}", client_id=client_id,
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=stage_id or sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=position == 7, is_closed_lost=position == 8, amount=Decimal("1000"),
        currency="USD", close_date=close, governance_status="Intake", business_unit_value=region,
        business_unit_mapping_version=1 if region else None, business_unit_observed_at=NOW if region else None,
        hubspot_msa_type=msa, hubspot_last_modified_at=modified, archived_at=NOW if archived else None)


async def add_client(session, name: str, *, company: bool = True, stored: tuple[str, str] | None = None,
                     set_by: uuid.UUID | None = None, archived: bool = False) -> uuid.UUID:
    client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=f"co-{uuid.uuid4().hex[:8]}" if company else None,
                    relationship=stored[0] if stored else None, relationship_basis=stored[1] if stored else None,
                    relationship_set_by=set_by if stored else None, relationship_set_at=STAMP_AT if stored else None,
                    archived_at=NOW if archived else None)
    session.add(client)
    await session.flush()
    return client.id


async def seed_world(session) -> dict[str, uuid.UUID]:
    await seed_reference(session)
    ids: dict[str, uuid.UUID] = {}
    stamped_new = ("net_new", "none")

    # Arvella: stamped existing; a win, a Hold deal and a lost deal; standard NDA v2 from AG-0001 (plus a removed
    # mark that must not count); the MSA marked from HubSpot. Its hint is the newest deal value.
    a = ids["Arvella Foods"] = await add_client(session, "Arvella Foods", stored=("existing", "closed_won"),
                                                set_by=ADMIN.id)
    session.add_all([
        deal(a, "a-won", 7, region="US", close=date(2026, 8, 1), msa="Signed MSA", modified=at_utc("2026-09-01T12:00")),
        deal(a, "a-hold", 9, region="US - IT Avalon", msa="MSA in progress", modified=at_utc("2026-09-20T12:00")),
        deal(a, "a-lost", 8, close=date(2026, 7, 1), modified=at_utc("2026-10-10T12:00")),
    ])
    nda_v1 = StandardAgreement(kind="NDA", version_no=1, file_key="agreements/standard/NDA/t1-v1.pdf",
                               filename="Standard NDA v1.pdf", file_size=2048, sha256="1" * 64, uploaded_by=ADMIN.id)
    nda_v2 = StandardAgreement(kind="NDA", version_no=2, file_key="agreements/standard/NDA/t1-v2.pdf",
                               filename="Standard NDA v2.pdf", file_size=2048, sha256="2" * 64, uploaded_by=ADMIN.id)
    session.add_all([nda_v1, nda_v2])
    await session.flush()
    batch = AgreementBatch(label="AG-0001", status="done", kinds=["NDA"], target_client_ids=[str(a)],
                           standard_ids={"NDA": str(nda_v2.id)}, target_count=1, done_count=1, attached_count=1,
                           attached_clients=1, idempotency_key="t1-loader-batch", created_by=ADMIN.id)
    session.add(batch)
    await session.flush()
    session.add_all([
        Agreement(client_id=a, kind="NDA", source="standard", standard_agreement_id=nda_v2.id, batch_id=batch.id,
                  file_key=nda_v2.file_key, filename=nda_v2.filename, file_size=nda_v2.file_size, uploaded_by=ADMIN.id),
        AgreementMark(client_id=a, kind="NDA", reason="other", marked_on=date(2026, 9, 2), marked_by=LEGAL.id,
                      removed_at=at_utc("2026-09-03T12:00"), removed_by=LEGAL.id),
        AgreementMark(client_id=a, kind="MSA", reason="per_hubspot", marked_on=date(2026, 10, 2), marked_by=ADMIN.id,
                      source="hubspot", hubspot_value="Signed MSA"),
    ])

    # Brintmoor: stamped net new; open stages 3 and 1 in South Africa; an archived stage 6 deal never counts.
    b = ids["Brintmoor Logistics"] = await add_client(session, "Brintmoor Logistics", stored=stamped_new,
                                                      set_by=ADMIN.id)
    session.add_all([
        deal(b, "b-3", 3, region="South Africa", close=date(2026, 12, 15)),
        deal(b, "b-1", 1, region="South Africa", close=date(2027, 1, 31)),
        deal(b, "b-archived", 6, region="US", close=date(2026, 11, 1), archived=True),
        Agreement(client_id=b, kind="MSA", file_key="agreements/t1/brintmoor-msa.pdf", filename="msa.pdf",
                  file_size=100, uploaded_by=LEGAL.id),
    ])

    # Cassowin: stamped net new, no HubSpot deal; its SOW (on a local SOW-upload deal) was stored at 05:30 UTC on
    # 2 October, which is 22:30 on 1 October in Los Angeles: the cutover day, not after it.
    c = ids["Cassowin Health"] = await add_client(session, "Cassowin Health", stored=stamped_new, set_by=ADMIN.id)
    local = Opportunity(source="sow_upload", name="Cassowin SOW upload", client_id=c, governance_status="Intake",
                        amount=Decimal("1"), currency="USD")
    session.add(local)
    await session.flush()
    session.add(Sow(opportunity_id=local.id, created_at=at_utc("2026-10-02T05:30")))

    # Dellford: stamped net new; an IT Avalon engagement stored at 07:30 UTC on 2 October (00:30 in Los Angeles,
    # after the cutover): it makes the client required.
    d = ids["Dellford Media"] = await add_client(session, "Dellford Media", stored=stamped_new, set_by=ADMIN.id)
    session.add(Engagement(client_id=d, name="Dellford retainer", type="fixed_cost", start=date(2026, 10, 5),
                           end=date(2026, 12, 31), business_unit="IT Avalon", created_at=at_utc("2026-10-02T07:30")))

    # Embertine: set existing by hand (Lee Legal); SOWs on two deals; the first and last count, an archived one never.
    e = ids["Embertine Labs"] = await add_client(session, "Embertine Labs", stored=("existing", "manual"),
                                                 set_by=LEGAL.id)
    e1 = deal(e, "e-2", 2, region="US - IT Avalon", close=date(2026, 12, 1))
    e2 = deal(e, "e-5", 5, region="US", close=date(2026, 11, 20))
    session.add_all([e1, e2])
    await session.flush()
    session.add_all([
        Sow(opportunity_id=e1.id, created_at=at_utc("2026-06-01T20:00")),
        Sow(opportunity_id=e1.id, created_at=at_utc("2026-07-15T20:00")),
        Sow(opportunity_id=e2.id, created_at=at_utc("2026-09-30T20:00")),
        Sow(opportunity_id=e2.id, created_at=at_utc("2026-10-10T20:00"), archived_at=at_utc("2026-10-11T12:00")),
    ])

    # Fenwick: stamped net new; one deal on Hold.
    f = ids["Fenwick Orchard"] = await add_client(session, "Fenwick Orchard", stored=stamped_new, set_by=ADMIN.id)
    session.add(deal(f, "f-hold", 9, region="US", close=date(2026, 12, 31)))

    # Glimmerbay: created after the cutover (not stamped yet); its company won on 15 September; one open deal sits in
    # a stage the mirror no longer has.
    g = ids["Glimmerbay Systems"] = await add_client(session, "Glimmerbay Systems")
    session.add_all([
        deal(g, "g-won", 7, region="US", close=date(2026, 9, 15)),
        deal(g, "g-retired", 3, region="US", close=date(2026, 12, 1), stage_id="t1-retired"),
    ])

    # Hollowmere: stamped existing; a Retro Rabbit engagement from the forecast model (allocation import_key) and an
    # open ST21 deal.
    h = ids["Hollowmere Systems"] = await add_client(session, "Hollowmere Systems", stored=("existing", "sow_engagement"),
                                                     set_by=ADMIN.id)
    session.add(deal(h, "h-4", 4, region="US", close=date(2026, 12, 1)))
    forecast = Engagement(client_id=h, name="Hollowmere forecast", type="time_and_materials", start=date(2026, 1, 1),
                          end=date(2026, 12, 31), business_unit="Retro Rabbit", created_at=at_utc("2026-05-01T12:00"))
    resource = Resource(name="Synthetic consultant", location="US", employment_type="w2_employee")
    session.add_all([forecast, resource])
    await session.flush()
    session.add(Allocation(engagement_id=forecast.id, resource_id=resource.id, role="Consultant", location="US",
                           employment_type="w2_employee", utilization=Decimal("1"), import_key="fm:t1:row7:0"))

    # Istvale: stamped net new; its only deal carries a region the map does not know.
    i = ids["Istvale Analytics"] = await add_client(session, "Istvale Analytics", stored=stamped_new, set_by=ADMIN.id)
    session.add(deal(i, "i-2", 2, region="Brazil", close=date(2026, 12, 1)))

    # Jorvane: created by a test identity (client.created by the e2e runner), not stamped, no company, no deals.
    j = ids["Jorvane Partners"] = await add_client(session, "Jorvane Partners", company=False)
    # Kestrine: created by a real writer; stamped existing; an ST21 engagement whose allocation has no import_key.
    k = ids["Kestrine Group"] = await add_client(session, "Kestrine Group", stored=("existing", "sow_engagement"),
                                                 set_by=ADMIN.id)
    plain = Engagement(client_id=k, name="Kestrine delivery", type="fixed_cost", start=date(2026, 2, 1),
                       end=date(2026, 9, 30), business_unit="ST21", created_at=at_utc("2026-03-01T12:00"))
    session.add(plain)
    await session.flush()
    session.add(Allocation(engagement_id=plain.id, resource_id=resource.id, role="Consultant", location="US",
                           employment_type="w2_employee", utilization=Decimal("1")))
    await session.flush()
    for client_id, actor in ((j, BOT.id), (k, LEGAL.id)):
        await append_audit(session, actor_id=actor, action="client.created", entity="client",
                           entity_id=str(client_id), before=None, after={"origin": "manual"})

    # Never loaded: an archived client.
    ids["Old Mill Co"] = await add_client(session, "Old Mill Co", stored=("existing", "closed_won"), set_by=ADMIN.id,
                                          archived=True)
    await session.commit()
    return ids


# --- what the rows say ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Want:
    stored: tuple[str | None, str | None]
    deals: tuple[tuple, ...]  # (status, ordinal for an open deal, close date), sorted
    status: tuple  # (relationship, basis, requirement, NDA, MSA, needs attention)
    sows: tuple[date, ...] = ()
    engagements: tuple[date, ...] = ()
    units: list[dict[str, str]] = field(default_factory=list)
    unit_note: str | None = None
    hint: str | None = None
    docs: dict[str, DocInput] = field(default_factory=dict)
    test_data: bool = False
    forecast: bool = False
    set_by: str | None = None
    basis_text: str | None = None


WON, LOST_, HOLD_ = "won", "lost", "hold"
NONE_STD = ("not_needed", "not_needed")
WANT: dict[str, Want] = {
    "Arvella Foods": Want(
        stored=("existing", "closed_won"),
        deals=((HOLD_, None, None), (LOST_, None, date(2026, 7, 1)), (WON, None, date(2026, 8, 1))),
        units=[{"name": "ST21", "region": "US"}, {"name": "IT Avalon", "region": "US"}],
        hint="MSA in progress",
        docs={"NDA": DocInput(source="standard", standard_version=2, batch_label="AG-0001", mark_source=None),
              "MSA": DocInput(source=None, standard_version=None, batch_label=None, mark_source="hubspot")},
        set_by="Ada Admin", basis_text="Closed Won deal",
        status=("existing", "closed_won", "none", "standard", "covered", False)),
    "Brintmoor Logistics": Want(
        stored=("net_new", "none"),
        deals=(("open", 1, date(2027, 1, 31)), ("open", 3, date(2026, 12, 15))),
        units=[{"name": "Retro Rabbit", "region": "South Africa"}],
        docs={"MSA": DocInput(source="client")}, set_by="Ada Admin", basis_text="No earlier work found",
        status=("net_new", "none", "required", "missing", "client", True)),
    "Cassowin Health": Want(
        stored=("net_new", "none"), deals=(), sows=(date(2026, 10, 1), date(2026, 10, 1)),
        unit_note="No business unit on its deals or engagements", set_by="Ada Admin",
        status=("net_new", "none", "none", *NONE_STD, False)),
    "Dellford Media": Want(
        stored=("net_new", "none"), deals=(), engagements=(date(2026, 10, 2), date(2026, 10, 2)),
        units=[{"name": "IT Avalon", "region": "US"}], set_by="Ada Admin",
        status=("net_new", "none", "required", "missing", "missing", True)),
    "Embertine Labs": Want(
        stored=("existing", "manual"),
        deals=(("open", 2, date(2026, 12, 1)), ("open", 5, date(2026, 11, 20))),
        sows=(date(2026, 6, 1), date(2026, 9, 30)),
        units=[{"name": "ST21", "region": "US"}, {"name": "IT Avalon", "region": "US"}],
        set_by="Lee Legal", basis_text="Marked existing by Lee Legal",
        status=("existing", "manual", "none", "existing_none", "existing_none", False)),
    "Fenwick Orchard": Want(
        stored=("net_new", "none"), deals=((HOLD_, None, date(2026, 12, 31)),),
        units=[{"name": "ST21", "region": "US"}], set_by="Ada Admin",
        status=("net_new", "none", "required", "missing", "missing", True)),
    "Glimmerbay Systems": Want(
        stored=(None, None), deals=(("open", None, date(2026, 12, 1)), (WON, None, date(2026, 9, 15))),
        units=[{"name": "ST21", "region": "US"}], basis_text="Closed Won deal",
        status=("existing", "closed_won", "none", "existing_none", "existing_none", False)),
    "Hollowmere Systems": Want(
        stored=("existing", "sow_engagement"), deals=(("open", 4, date(2026, 12, 1)),),
        engagements=(date(2026, 5, 1), date(2026, 5, 1)),
        units=[{"name": "ST21", "region": "US"}, {"name": "Retro Rabbit", "region": "South Africa"}],
        forecast=True, set_by="Ada Admin", basis_text="Engagement from the forecast model",
        status=("existing", "sow_engagement", "none", "existing_none", "existing_none", False)),
    "Istvale Analytics": Want(
        stored=("net_new", "none"), deals=(("open", 2, date(2026, 12, 1)),),
        unit_note="Region not mapped to a business unit: Brazil", set_by="Ada Admin",
        status=("net_new", "none", "required", "missing", "missing", True)),
    "Jorvane Partners": Want(
        stored=(None, None), deals=(), test_data=True, unit_note="No deals or engagements yet",
        status=("net_new", "none", "none", *NONE_STD, False)),
    "Kestrine Group": Want(
        stored=("existing", "sow_engagement"), deals=(), engagements=(date(2026, 3, 1), date(2026, 3, 1)),
        units=[{"name": "ST21", "region": "US"}], set_by="Ada Admin", basis_text="SOW or engagement",
        status=("existing", "sow_engagement", "none", "existing_none", "existing_none", False)),
}


def _deals(item) -> tuple[tuple, ...]:
    return tuple(sorted(((d.status, d.ordinal if d.status == "open" else None, d.close_date) for d in item.deals),
                        key=repr))


def check_population(pop: Population, ids: dict[str, uuid.UUID]) -> None:
    by_name = {facts.input.name: facts for facts in pop.clients.values()}
    assert pop.cutover == CUTOVER
    assert set(by_name) == set(WANT), "archived clients are never loaded"
    assert ids["Old Mill Co"] not in pop.clients
    for name, want in WANT.items():
        facts = by_name[name]
        item, status = facts.input, facts.status
        assert item.id == ids[name]
        assert (item.stored_relationship, item.stored_basis) == want.stored, name
        assert _deals(item) == tuple(sorted(want.deals, key=repr)), name
        assert (item.sow_dates, item.engagement_dates) == (want.sows, want.engagements), name
        assert item.hubspot_msa_type == want.hint, name
        assert dict(item.docs) == want.docs, name
        assert item.test_data is want.test_data, name
        assert facts.forecast is want.forecast, name
        assert facts.set_by == want.set_by, name
        stamped_at = facts.set_at.replace(tzinfo=facts.set_at.tzinfo or UTC) if facts.set_at else None
        assert stamped_at == (STAMP_AT if want.stored[0] else None), name  # SQLite returns it naive (UTC)
        assert (status.relationship, status.relationship_basis, status.requirement, status.nda, status.msa,
                status.needs_attention) == want.status, name
        row = client_row(pop, facts)
        assert row["business_units"] == want.units, name  # a unit always comes with its region
        assert row["business_unit_note"] == want.unit_note, name
        if want.basis_text is not None:
            assert row["basis_text"] == want.basis_text, name
        if want.units:
            assert business_unit_text(facts) == "; ".join(f"{u['name']} · {u['region']}" for u in want.units)
    # Three facts the classification hangs on, read back through the rows.
    assert by_name["Fenwick Orchard"].status.on_hold and by_name["Fenwick Orchard"].status.stage_bucket == "past_stage_1"
    assert by_name["Glimmerbay Systems"].status.unknown_stage and not by_name["Glimmerbay Systems"].status.provisional
    assert "test_data" in by_name["Jorvane Partners"].status.flags
    assert "test_data" not in by_name["Kestrine Group"].status.flags


async def test_the_loader_builds_the_input_each_clients_rows_say(session):
    ids = await seed_world(session)
    pop = await load_agreement_population(session, VIEWER)
    check_population(pop, ids)


async def test_sow_and_engagement_dates_are_los_angeles_calendar_dates(session):
    """05:30 UTC on 2 October is still 1 October in Los Angeles; 07:30 UTC is 2 October. With the cutover on 1
    October, only the second is "created after the cutover", so only Dellford becomes required."""
    ids = await seed_world(session)
    pop = await load_agreement_population(session, VIEWER)
    cassowin, dellford = pop.clients[ids["Cassowin Health"]], pop.clients[ids["Dellford Media"]]
    assert cassowin.input.sow_dates == (CUTOVER, CUTOVER)
    assert cassowin.status.requirement == "none" and not cassowin.status.needs_attention
    assert dellford.input.engagement_dates == (date(2026, 10, 2), date(2026, 10, 2))
    assert dellford.status.requirement == "required" and dellford.status.needs_attention
    # The archived SOW stored on 10 October never counts: Embertine's last SOW is 30 September.
    assert pop.clients[ids["Embertine Labs"]].input.sow_dates == (date(2026, 6, 1), date(2026, 9, 30))


async def test_an_engagement_on_the_cutover_day_in_los_angeles_is_not_after_it(session):
    """The engagement half of la_date (T-C verifier gap): 05:30 UTC on 2 October is 22:30 on 1 October in Los
    Angeles, the cutover day, so a stamped net-new client with only that engagement stays 'none'. Read as a UTC
    day it would be 2 October, after the cutover, and the client would wrongly become required."""
    ids = await seed_world(session)
    fenwick = await add_client(session, "Fenwick Arts", stored=("net_new", "none"), set_by=ADMIN.id)
    session.add(Engagement(client_id=fenwick, name="Fenwick retainer", type="fixed_cost", start=date(2026, 10, 5),
                           end=date(2026, 12, 31), business_unit="IT Avalon", created_at=at_utc("2026-10-02T05:30")))
    await session.commit()
    pop = await load_agreement_population(session, VIEWER)
    facts = pop.clients[fenwick]
    assert facts.input.engagement_dates == (CUTOVER, CUTOVER)
    assert (facts.status.requirement, facts.status.needs_attention) == ("none", False)
    assert pop.clients[ids["Dellford Media"]].status.requirement == "required"  # 07:30 UTC is 2 October in LA


async def _one_client(session, name: str, *, creator: AuthUser | None = None) -> uuid.UUID:
    await seed_reference(session)
    client_id = await add_client(session, name, company=False)
    if creator is not None:
        await append_audit(session, actor_id=creator.id, action="client.created", entity="client",
                           entity_id=str(client_id), before=None, after={"origin": "manual"})
    await session.commit()
    return client_id


@pytest.mark.parametrize(("creator", "test_data"), [(BOT, True), (LEGAL, False), (ADMIN, False), (None, False)],
                         ids=["created by a test identity", "created by Legal", "created by SystemAdmin",
                              "no client.created row"])
async def test_test_data_comes_from_the_client_created_actor(session, creator, test_data):
    client_id = await _one_client(session, "Lunavale Studio", creator=creator)
    status = (await load_agreement_population(session, VIEWER)).clients[client_id].status
    assert ("test_data" in status.flags) is test_data
    # A flag only: the test client is classified like any other client (B12).
    assert (status.relationship, status.requirement, status.nda) == ("net_new", "none", "not_needed")


RUN_TAGS = [
    ("S24 e2e 7d2a fixture", True),
    ("S14b e2e 99 client", True),
    ("s19-a1b2 client", True),
    ("smoke 2026-10-15 run", True),
    ("SMOKE run in capitals", True),
    ("Smokehouse Grill", False),
    ("Lunavale e2e Services", False),
    ("S24e2e without a space", False),
    # The gate's two legacy fixture prefixes (bug #106, fixed); the real-looking names stay real.
    ("S17 delete-everywhere 42", True),
    ("Peppermill Casino (smoke fixture)", True),
    ("Peppermill Casino", False),
    ("Peppermill Casino's, LLC", False),
]


@pytest.mark.parametrize(("name", "test_data"), RUN_TAGS)
async def test_a_run_tagged_name_is_test_data(session, name, test_data):
    """Run tags as the leak gate (scripts/check-test-data-clean.sh) knows them: a known prefix at the start."""
    client_id = await _one_client(session, name)
    status = (await load_agreement_population(session, VIEWER)).clients[client_id].status
    assert ("test_data" in status.flags) is test_data


@POSTGRES
async def test_the_loader_builds_the_same_inputs_on_postgres(env):
    """Aware timestamptz values (la_date), JSONB groups (the test-identity check), row_number() (the hint) and
    real foreign keys and partial unique indexes: the same world reads the same on Postgres."""
    async with scratch_postgres() as (_engine, factory):
        async with factory() as session:
            ids = await seed_world(session)
        async with factory() as session:
            check_population(await load_agreement_population(session, VIEWER), ids)
