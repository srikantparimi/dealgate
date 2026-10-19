"""S24-AG1 T12 local parity (lane T-C) — the Pipeline and the Agreements page report the same Needs-attention
number, and every Agreements card equals the list it opens. The lead runs the staging half after the deploy.

Both pages are read through their HTTP routes on ONE database (GET /pipeline/workspace and
GET /agreements/workspace), as the browser does:

* metrics.agreement_gap_clients.value equals the Agreements needs_attention card, and the client rows the
  Pipeline card drills into are exactly the clients the Agreements card drills into;
* every Agreements card's drill, applied to the reset view (decided deviation #10), returns exactly the card's
  value as the list total, and every row it returns is one the card counts (and none it counts is missing);
* on the shared PL2 seed (hand-stamped relationships), before any cutover, and before and after a REAL batch
  (dry run, typed confirm, the job run inline) that sets the cutover and stamps every relationship, then again
  after life goes on (a net-new client's first win, a client created after the cutover whose company has an
  earlier win, a client stamped net new at creation) — on SQLite and on a scratch Postgres;
* the residual case of deviation #11, named: an SOW- or engagement-only required client with no HubSpot deal.
  Before the cutover the numbers are equal (an SOW makes a client existing); after it, such a client is on the
  Agreements card and cannot be on the deal-based Pipeline card, so the Agreements number is higher by exactly
  those clients, while a client with only a lost deal and the same late SOW is counted on both.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.agreements import AgreementMark, AgreementsSettings, StandardAgreement
from app.models.client import Agreement, Client
from app.models.engagement import Engagement
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.routers.agreements import get_batch_launcher
from app.routers.agreements import router as agreements_router
from app.routers.agreements_workspace import router as workspace_router
from app.routers.pipeline import router as pipeline_router
from app.services import agreement_batches
from app.services.agreement_hooks import stamp_new_client
from app.services.pipeline_workspace import DRILLS
from tests import test_s23_pl2_workspace as shared
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s23_pl2_workspace import NOW, PIPELINE_ID, STAGES, TODAY, VIEWER, day, seed_population

# The shared PL2 fixtures (foreign keys on; the frozen clock), bound here so pytest finds them.
engine, frozen_clock, seeded = shared.engine, shared.frozen_clock, shared.seeded

ADMIN = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000012a1"), "ada@example.test", "Ada Admin", ("SystemAdmin",))
CARD_ORDER = ["clients", "existing", "net_new", "needs_attention", "standard_attached", "client_copies"]
# What each card counts, in the contract's words, read off a row of the reset view.
CARD_MEANS: dict[str, Callable[[dict], bool]] = {
    "clients": lambda row: True,
    "existing": lambda row: row["relationship"] == "existing",
    "net_new": lambda row: row["relationship"] == "net_new",
    "needs_attention": lambda row: row["needs_attention"],
    "standard_attached": lambda row: "standard" in (row["nda"]["state"], row["msa"]["state"]),
    "client_copies": lambda row: "client" in (row["nda"]["state"], row["msa"]["state"]),
}
LATER = NOW + timedelta(days=6)  # life after the cutover (the batch runs on TODAY)


# --- one database, both pages over HTTP ----------------------------------------------------------------------


@dataclass
class Db:
    factory: async_sessionmaker
    shared_session: AsyncSession | None = None  # SQLite: every request reuses the test's session

    async def requests(self):
        if self.shared_session is not None:
            yield self.shared_session
            return
        async with self.factory() as session:
            yield session


def inline(factory) -> Callable:
    async def launch(batch_id, phase):
        runner = agreement_batches.run_batch if phase == "run" else agreement_batches.run_undo
        await runner(factory, batch_id)
    return launch


@asynccontextmanager
async def api_as(db: Db, user: AuthUser):
    app = FastAPI()
    for router in (pipeline_router, workspace_router, agreements_router):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_session] = db.requests
    app.dependency_overrides[get_batch_launcher] = lambda: inline(db.factory)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t12") as http:
        yield http


def wire(params: dict[str, Any]) -> dict[str, Any]:
    return {k: ("true" if v is True else "false" if v is False else v) for k, v in params.items()}


async def get_json(http, path: str, **params) -> dict:
    response = await http.get(path, params=wire(params))
    assert response.status_code == 200, (path, params, response.text)
    return response.json()


@dataclass
class Parity:
    agreements: int  # the Agreements needs_attention card
    pipeline: int  # metrics.agreement_gap_clients.value
    attention: set[str]  # client ids the Agreements card drills into
    pipeline_ids: set[str]  # client ids the Pipeline card drills into
    rows: dict[str, dict]  # the Agreements reset view, by client id
    cards: dict[str, int]

    def by_name(self, name: str) -> dict:
        return next(row for row in self.rows.values() if row["name"] == name)

    def ids(self, *names: str) -> set[str]:
        return {self.by_name(name)["client_id"] for name in names}


async def read_both(db: Db) -> Parity:
    """Both pages, and every Agreements card against the list its drill opens (on the reset view)."""
    async with api_as(db, VIEWER) as http:
        body = await get_json(http, "/agreements/workspace", page_size=100)
        assert [c["key"] for c in body["cards"]] == CARD_ORDER
        cards = {c["key"]: c for c in body["cards"]}
        rows = {row["client_id"]: row for row in body["items"]}
        assert body["total"] == cards["clients"]["value"] == len(rows) <= 100
        for card in body["cards"]:
            drilled = await get_json(http, "/agreements/workspace", page_size=100, **card["drill"])
            assert drilled["total"] == card["value"] == len(drilled["items"]), card["key"]
            counted = {cid for cid, row in rows.items() if CARD_MEANS[card["key"]](row)}
            assert {row["client_id"] for row in drilled["items"]} == counted, card["key"]
        pipeline = await get_json(http, "/pipeline/workspace")
        gap = pipeline["metrics"]["agreement_gap_clients"]
        assert gap["drill"] == DRILLS["agreement_gap_clients"]
        gap_rows = await get_json(http, "/pipeline/workspace", page_size=100, **gap["drill"])
        assert gap_rows["page"]["total_rows"] == gap["value"] == len(gap_rows["rows"])
    return Parity(agreements=cards["needs_attention"]["value"], pipeline=gap["value"],
                  attention={cid for cid, row in rows.items() if row["needs_attention"]},
                  pipeline_ids={row["id"] for row in gap_rows["rows"]}, rows=rows,
                  cards={k: c["value"] for k, c in cards.items()})


def assert_equal(p: Parity) -> None:
    assert p.pipeline == p.agreements
    assert p.pipeline_ids == p.attention


# --- extra clients (synthetic names) ----------------------------------------------------------------------------


def hubspot_deal(client_id: uuid.UUID, key: str, position: int, *, close: date | None = None,
                 stage_id: str | None = None) -> Opportunity:
    """A live HubSpot deal in the PL2 mirror: position 1-6 open, 7 won, 8 lost, 9 Hold."""
    sid, label, order, _closed = STAGES[position - 1]
    return Opportunity(
        source="hubspot", hubspot_deal_id=f"t12-{key}", name=f"Deal {key}", client_id=client_id,
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=stage_id or sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=position == 7, is_closed_lost=position == 8, amount=Decimal("1000"),
        currency="USD", close_date=close or day(30), governance_status="Intake", created_at=NOW - timedelta(days=20),
        business_unit_value="US", business_unit_mapping_version=1, business_unit_observed_at=NOW)


async def add_client(session, name: str, *, deals=(), relationship: str | None = None,
                     company: bool = True) -> uuid.UUID:
    client = Client(id=uuid.uuid4(), name=name,
                    hubspot_company_id=f"t12-{name.lower().replace(' ', '-')}" if company else None,
                    relationship=relationship, relationship_basis="none" if relationship else None)
    session.add(client)
    await session.flush()
    for index, (position, close, *stage) in enumerate(deals):
        session.add(hubspot_deal(client.id, f"{client.id.hex[:8]}-{index}", position, close=close,
                                 stage_id=stage[0] if stage else None))
    await session.flush()
    return client.id


async def add_extras(session, *, writer: uuid.UUID) -> dict[str, uuid.UUID]:
    """States the PL2 seed lacks. Before any cutover they judge live: an SOW or engagement makes a client
    existing, so the PL2 seed's own clients are existing and these carry the warnings."""
    ids = {
        "Nova Retail": await add_client(session, "Nova Retail", deals=[(3, None)]),
        "Orbit Media": await add_client(session, "Orbit Media", deals=[(1, None)]),
        "Pine Labs": await add_client(session, "Pine Labs", deals=[(9, None)]),
        "Rowan Health": await add_client(session, "Rowan Health", deals=[(3, None, "t12-retired-stage")]),
        "Sable Works": await add_client(session, "Sable Works", deals=[(4, None)]),
        "Arvella Foods": await add_client(session, "Arvella Foods", deals=[(2, None)]),
        "Arvella Foods LLC": await add_client(session, "Arvella Foods LLC", deals=[(2, None)]),
        "S24 e2e 5b1d fixture": await add_client(session, "S24 e2e 5b1d fixture", deals=[(3, None)]),
        "Quill Partners": await add_client(session, "Quill Partners", deals=[(8, day(-40))]),
        "Lumen Studio": await add_client(session, "Lumen Studio", company=False),
        "Opal Systems": await add_client(session, "Opal Systems", company=False),
        "Mesa Works": await add_client(session, "Mesa Works", company=False),
        "Nimbus Tools": await add_client(session, "Nimbus Tools", company=False),
    }
    # Sable holds its own NDA and a HubSpot mark on the MSA. Mesa is engagement-only and Nimbus SOW-only (its SOW
    # sits on a local SOW-upload deal): neither has a HubSpot deal at all.
    nimbus_upload = Opportunity(source="sow_upload", name="Nimbus SOW upload", client_id=ids["Nimbus Tools"],
                                governance_status="Intake", amount=Decimal("1"), currency="USD")
    session.add(nimbus_upload)
    await session.flush()
    session.add_all([
        Sow(opportunity_id=nimbus_upload.id, created_at=NOW - timedelta(days=30)),
        Agreement(client_id=ids["Sable Works"], kind="NDA", file_key="agreements/t12/sable-nda.pdf",
                  filename="sable-nda.pdf", file_size=100, uploaded_by=writer),
        AgreementMark(client_id=ids["Sable Works"], kind="MSA", reason="per_hubspot", source="hubspot",
                      hubspot_value="Signed MSA", marked_on=TODAY - timedelta(days=2), marked_by=writer),
        Engagement(client_id=ids["Mesa Works"], name="Mesa forecast", type="fixed_cost", start=date(2026, 1, 1),
                   end=date(2026, 12, 31), business_unit="ST21", created_at=NOW - timedelta(days=90)),
    ])
    await session.flush()
    return ids


async def seed_before_any_batch(db: Db, *, region_map: bool) -> dict[str, uuid.UUID]:
    """The PL2 seed and the extras, as they stand before the first real batch: no cutover, nothing stamped."""
    async with db.factory() as session:
        seed = await seed_population(session, region_map=region_map)
        settings = await session.get(AgreementsSettings, 1)
        settings.cutover_date = settings.set_by = settings.set_at = None
        await session.execute(update(Client).values(relationship=None, relationship_basis=None,
                                                    relationship_set_by=None, relationship_set_at=None))
        session.add(User(id=ADMIN.id, email=ADMIN.email, name="Ada Admin", groups=["SystemAdmin"]))
        session.add(StandardAgreement(kind="MSA", version_no=1, file_key="agreements/standard/MSA/t12-msa.pdf",
                                      filename="Standard MSA.pdf", file_size=4096, sha256="d" * 64,
                                      uploaded_by=seed.writer))
        ids = await add_extras(session, writer=seed.writer)
        await session.commit()
    return {**seed.clients, **ids}


async def run_a_real_batch(db: Db) -> dict:
    """The admin's one-time attach, as the wizard does it: dry run, the typed phrase, the job (run inline)."""
    async with api_as(db, ADMIN) as http:
        dry = await http.post("/agreements/batches", json={"kinds": ["NDA", "MSA"], "include_net_new_past_stage_1": True})
        assert dry.status_code == 200, dry.text
        will_receive = dry.json()["will_receive"]
        started = await http.post("/agreements/batches", json={
            "kinds": ["NDA", "MSA"], "dry_run": False, "include_net_new_past_stage_1": True,
            "idempotency_key": "t12-parity", "confirm": f"ATTACH {will_receive}"})
        assert started.status_code == 202, started.text
        batch = await get_json(http, f"/agreements/batches/{started.json()['id']}")
    assert (batch["status"], batch["target_count"], batch["attached_clients"]) == ("done", will_receive, will_receive)
    return dry.json()


async def life_after_the_cutover(db: Db, ids: dict[str, uuid.UUID], monkeypatch) -> dict[str, uuid.UUID]:
    """A week later: Orbit's stage 1 deal closes won (its first win); Juniper arrives from HubSpot (not stamped
    yet) with a win dated before the cutover; Kestrel is created by hand and stamped net new at creation."""
    monkeypatch.setenv("DEALGATE_NOW", LATER.isoformat())
    won_id, won_label, won_order, _ = STAGES[6]
    async with db.factory() as session:
        await session.execute(update(Opportunity).where(Opportunity.client_id == ids["Orbit Media"]).values(
            hubspot_stage_id=won_id, stage_label=won_label, sales_stage=won_label, stage_order=won_order,
            is_closed_won=True, close_date=day(5)))
        juniper = await add_client(session, "Juniper Health", deals=[(7, day(-13)), (3, None)])
        kestrel = Client(id=uuid.uuid4(), name="Kestrel Labs")
        session.add(kestrel)
        await session.flush()
        assert await stamp_new_client(session, kestrel, actor_id=ADMIN.id, origin="manual") == "net_new"
        session.add(hubspot_deal(kestrel.id, "kestrel-2", 2))
        await session.commit()
    return {**ids, "Juniper Health": juniper, "Kestrel Labs": kestrel.id}


async def stamped_everything(db: Db) -> None:
    async with db.factory() as session:
        settings = await session.get(AgreementsSettings, 1)
        unstamped = await session.scalar(select(func.count()).select_from(Client).where(
            Client.archived_at.is_(None), Client.relationship.is_(None)))
    assert settings.cutover_date == TODAY  # the Los Angeles date of the first real batch
    assert unstamped == 0


async def parity_through_a_real_batch(db: Db, monkeypatch, *, region_map: bool) -> tuple[dict, Parity]:
    ids = await seed_before_any_batch(db, region_map=region_map)
    before = await read_both(db)
    assert_equal(before)
    # Live and provisional: Nova (stage 3), Pine (Hold), Rowan (unknown stage), both Arvellas (stage 2) and the
    # run-tagged test client (a flag only) need attention; Mesa (engagement only, no deal) is existing.
    assert before.attention == before.ids("Nova Retail", "Pine Labs", "Rowan Health", "Arvella Foods",
                                          "Arvella Foods LLC", "S24 e2e 5b1d fixture")
    # Residual case #11, before the cutover: an SOW or engagement makes a client existing, so the SOW-only and the
    # engagement-only client (no HubSpot deal) are on neither card and the two numbers are equal by construction.
    for name in ("Mesa Works", "Nimbus Tools"):
        row = before.by_name(name)
        assert (row["relationship"], row["needs_attention"], row["deal_count"]) == ("existing", False, 0), name
    assert before.by_name("Lumen Studio")["relationship"] == before.by_name("Opal Systems")["relationship"] == "net_new"

    preview = await run_a_real_batch(db)
    excluded = {t["name"]: t["reason"] for t in preview["targets"] if not t["included"]}
    # Echo is existing with deals only in stage 1 (an open stage 1 deal and a lost one): held back, as directed.
    assert excluded == {"S24 e2e 5b1d fixture": "test_data", "Echo Media": "stage_1_only"}
    await stamped_everything(db)
    after = await read_both(db)
    assert_equal(after)
    # The pipeline clients past stage 1 got the standard copies and stay net new; the test client is still flagged.
    assert after.attention == after.ids("S24 e2e 5b1d fixture")
    for name in ("Nova Retail", "Pine Labs", "Rowan Health", "Arvella Foods"):
        row = after.by_name(name)
        assert (row["relationship"], row["nda"]["state"], row["msa"]["state"]) == ("net_new", "standard", "standard")
    assert after.cards["standard_attached"] > 0 and after.cards["existing"] > 0

    ids = await life_after_the_cutover(db, ids, monkeypatch)
    later = await read_both(db)
    assert_equal(later)
    assert later.attention == later.ids("S24 e2e 5b1d fixture", "Orbit Media", "Kestrel Labs")
    assert later.by_name("Orbit Media")["relationship"] == "net_new"  # a first win never makes it existing
    assert (later.by_name("Juniper Health")["relationship"], later.by_name("Juniper Health")["needs_attention"]) == (
        "existing", False)
    return ids, later


async def test_on_the_shared_pl2_seed_the_cards_agree_and_every_drill_is_its_card(seeded, session):
    p = await read_both(Db(factory=async_sessionmaker(session.bind, class_=AsyncSession), shared_session=session))
    assert_equal(p)
    assert p.attention == {str(seeded.clients[key]) for key in shared.NEEDS_ATTENTION}
    states = shared.AGREEMENT_STATES  # the seed's documented states; Fjord (unstamped, no deals) is net new
    existing = sum(1 for key in states if shared.RELATIONSHIPS.get(key, ("net_new",))[0] == "existing")
    assert p.cards == {"clients": len(states), "existing": existing, "net_new": len(states) - existing,
                       "needs_attention": len(shared.NEEDS_ATTENTION),
                       "standard_attached": sum(1 for pair in states.values() if "standard" in pair),
                       "client_copies": sum(1 for pair in states.values() if "client" in pair)}


async def test_before_any_cutover_the_cards_agree_and_every_drill_is_its_card(session, frozen_clock):
    db = Db(factory=async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession),
            shared_session=session)
    await seed_before_any_batch(db, region_map=True)
    p = await read_both(db)
    assert_equal(p)
    assert all(row["provisional"] for row in p.rows.values())  # judged live until the first real batch


async def test_the_cards_agree_before_and_after_a_real_batch_and_after_the_cutover(session, frozen_clock, monkeypatch):
    db = Db(factory=async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession),
            shared_session=session)
    await parity_through_a_real_batch(db, monkeypatch, region_map=True)


@POSTGRES
async def test_the_cards_agree_before_and_after_a_real_batch_on_a_scratch_postgres(frozen_clock, monkeypatch):
    async with scratch_postgres() as (_engine, factory):
        await parity_through_a_real_batch(Db(factory=factory), monkeypatch, region_map=False)


# --- engagements on clients with live deals (T-C verifier gap) -------------------------------------------------


def _engagement(client_id: uuid.UUID, name: str, created_at: datetime) -> Engagement:
    return Engagement(client_id=client_id, name=name, type="fixed_cost", start=date(2026, 1, 1),
                      end=date(2026, 12, 31), business_unit="ST21", created_at=created_at)


async def engagement_parity(db: Db, monkeypatch, *, region_map: bool) -> None:
    """The Pipeline computes its own per-client facts. These clients have live deals and an engagement decides
    their status, so a Pipeline that ignored engagement dates, or read them as UTC days, would disagree.

    Tamsin: a stage 3 deal and an engagement, so existing before the cutover (no warning on either page).
    Ulric and Vesper: a stage 1 deal only, stamped net new by the batch. Then Ulric gets an engagement on the day
    after the cutover in Los Angeles (required: flagged), and Vesper one at 06:30 UTC the next day, which is still
    the cutover day in Los Angeles (not after it: stage 1 only, no warning)."""
    ids = await seed_before_any_batch(db, region_map=region_map)
    async with db.factory() as session:
        tamsin = await add_client(session, "Tamsin Logistics", deals=[(3, None)])
        ulric = await add_client(session, "Ulric Media", deals=[(1, None)])
        vesper = await add_client(session, "Vesper Arts", deals=[(1, None)])
        session.add(_engagement(tamsin, "Tamsin forecast", NOW - timedelta(days=90)))
        await session.commit()
    before = await read_both(db)
    assert_equal(before)
    row = before.by_name("Tamsin Logistics")
    assert (row["relationship"], row["needs_attention"], row["deal_count"]) == ("existing", False, 1)

    await run_a_real_batch(db)
    await stamped_everything(db)
    for name in ("Ulric Media", "Vesper Arts"):
        row = (await read_both(db)).by_name(name)
        assert (row["relationship"], row["requirement"], row["needs_attention"]) == ("net_new", "later", False), name

    next_day_in_la = datetime.combine(TODAY + timedelta(days=1), time(19, 0), tzinfo=UTC)
    cutover_day_in_la = datetime.combine(TODAY + timedelta(days=1), time(6, 30), tzinfo=UTC)  # still TODAY in LA
    monkeypatch.setenv("DEALGATE_NOW", LATER.isoformat())
    async with db.factory() as session:
        session.add_all([_engagement(ulric, "Ulric retainer", next_day_in_la),
                         _engagement(vesper, "Vesper retainer", cutover_day_in_la)])
        await session.commit()
    later = await read_both(db)
    assert_equal(later)
    ulric_row, vesper_row = later.by_name("Ulric Media"), later.by_name("Vesper Arts")
    assert (ulric_row["requirement"], ulric_row["needs_attention"]) == ("required", True)
    assert (vesper_row["requirement"], vesper_row["needs_attention"]) == ("later", False)
    assert str(ids["Nova Retail"]) not in later.attention  # attached by the batch; unchanged


async def test_engagements_on_clients_with_live_deals_agree_on_both_pages(session, frozen_clock, monkeypatch):
    db = Db(factory=async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession),
            shared_session=session)
    await engagement_parity(db, monkeypatch, region_map=True)


@POSTGRES
async def test_engagements_on_clients_with_live_deals_agree_on_a_scratch_postgres(frozen_clock, monkeypatch):
    async with scratch_postgres() as (_engine, factory):
        await engagement_parity(Db(factory=factory), monkeypatch, region_map=False)


# --- the residual case of deviation #11 ------------------------------------------------------------------------


async def residual_case_11(db: Db, monkeypatch, *, region_map: bool) -> None:
    ids, later = await parity_through_a_real_batch(db, monkeypatch, region_map=region_map)
    # Before the cutover the numbers were equal (checked above): an SOW or engagement made a client existing,
    # so an SOW-only client could never be flagged. After it, Lumen (stamped net new, nothing then) gets an SOW
    # on a local SOW-upload deal and Opal an engagement; Quill (net new, only a lost HubSpot deal) gets an SOW too.
    async with db.factory() as session:
        local = Opportunity(source="sow_upload", name="Lumen SOW upload", client_id=ids["Lumen Studio"],
                            governance_status="Intake", amount=Decimal("1"), currency="USD")
        session.add(local)
        await session.flush()
        quill_deal = await session.scalar(select(Opportunity.id).where(Opportunity.client_id == ids["Quill Partners"]))
        session.add_all([
            Sow(opportunity_id=local.id, created_at=LATER - timedelta(days=1)),
            Sow(opportunity_id=quill_deal, created_at=LATER - timedelta(days=1)),
            Engagement(client_id=ids["Opal Systems"], name="Opal delivery", type="fixed_cost", start=day(10),
                       end=day(100), business_unit="IT Avalon", created_at=LATER - timedelta(days=1)),
        ])
        await session.commit()
    residual = await read_both(db)
    lumen_opal = residual.ids("Lumen Studio", "Opal Systems")
    # The Agreements card counts them; the deal-based Pipeline card cannot: higher by exactly those two clients.
    assert residual.agreements == residual.pipeline + 2
    assert residual.attention - residual.pipeline_ids == lumen_opal
    assert residual.pipeline_ids == residual.attention - lumen_opal
    # A client with only a lost deal and the same late SOW is on both cards: the residual needs "no deal at all".
    assert residual.ids("Quill Partners") <= residual.pipeline_ids
    for name in ("Lumen Studio", "Opal Systems", "Quill Partners"):
        row = residual.by_name(name)
        assert (row["relationship"], row["requirement"], row["nda"]["state"], row["deal_count"] > 0) == (
            "net_new", "required", "missing", name == "Quill Partners")
    # The Agreements cards still equal their own lists (read_both checked every drill).
    assert residual.cards["needs_attention"] == later.cards["needs_attention"] + 3


async def test_residual_case_11_an_sow_only_required_client_with_no_deal(session, frozen_clock, monkeypatch):
    db = Db(factory=async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession),
            shared_session=session)
    await residual_case_11(db, monkeypatch, region_map=True)


@POSTGRES
async def test_residual_case_11_on_a_scratch_postgres(frozen_clock, monkeypatch):
    async with scratch_postgres() as (_engine, factory):
        await residual_case_11(Db(factory=factory), monkeypatch, region_map=False)
