"""S24-AG1 T7 (lane T-A) — every write, download and export is one audit row; Activity; the CSV export.

Earlier lanes checked single rows (BE-B: a download, a detach, a relationship change) and a hand-inserted
feed (BE-A). This file drives the real routes end to end:

* one script of every per-client write, every download route and the export, each followed by a check that
  exactly ONE audit row landed, with the right action, entity, actor, client, kind and file name; failed and
  refused calls in between write nothing; the HubSpot apply and the batch run and undo add exactly one feed
  event each (their per-client rows stay out of the feed);
* the Activity tab then lists every one of those events newest first, worded as the prototype's log lines,
  with the actor's name and never an id, and its count equals the workspace's Activity count;
* events on a server-issued test fixture, and events a test identity caused, never reach a real user; the
  test identity sees its own fixture's events and the events about no client;
* the export: the contract's columns in order, UTF-8 with a BOM, a business unit with its region ("IT Avalon
  · US"), the duplicate and attention columns, and every formula start (= + - @ tab CR) neutralised.

SQLite with foreign keys on; StubS3; the batch job runs inline.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime

import pytest_asyncio
from sqlalchemy import func, select

from app.audit import verify_chain
from app.models.agreements import AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.hubspot_region_map import DEFAULT_REGION_MAP, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.services import agreement_audit as aa
from app.services.hubspot_properties import HubspotPropertyMapping
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_permissions import inline
from tests.test_s24_ag1_uploads import (  # noqa: F401  (engine and env are fixtures)
    ADMIN,
    DOCX,
    E2E,
    LEGAL,
    PDF,
    SALES,
    World,
    client_for,
    deal,
    engine,
    env,
    seed_world,
)

UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)
NAMES = {ADMIN.id: "Tess Admin", LEGAL.id: "Lena Legal", SALES.id: "Sid Sales", E2E.id: "Lane Bot"}


def _file(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


def _file_of(row: AuditEvent) -> str | None:
    after = row.after or {}
    return after.get("file_name") or after.get("filename")


class Ledger:
    """Runs one call and checks the audit rows it wrote; collects the feed lines the script expects."""

    def __init__(self, session, world: World) -> None:
        self.session = session
        self.world = world
        self.feed: list[dict] = []  # oldest first

    async def _ids(self) -> set[uuid.UUID]:
        return set((await self.session.scalars(select(AuditEvent.id))).all())

    async def _new(self, before: set[uuid.UUID]) -> list[AuditEvent]:
        rows = (await self.session.scalars(select(AuditEvent).order_by(AuditEvent.ts, AuditEvent.id))).all()
        return [row for row in rows if row.id not in before]

    async def _rows(self) -> dict[str, int]:
        return {model.__tablename__: int(await self.session.scalar(select(func.count()).select_from(model)))
                for model in (Agreement, AgreementFileVersion, AgreementMark, StandardAgreement, DeletionJob)}

    async def nothing(self, call, status: int):
        """A failed, refused or read-only call: its status, no audit row, no stored object, no row."""
        before, objects, rows = await self._ids(), set(self.world.storage.objects), await self._rows()
        response = await call
        assert response.status_code == status, response.text
        assert await self._new(before) == [], response.text
        assert set(self.world.storage.objects) == objects and await self._rows() == rows, response.text
        return response

    async def one(self, call, *, status: int, by, action: str, entity: str, client: str | None = None,
                  kind: str | None = None, file: str | None = None, feed: tuple[str, str] | None = None):
        """Exactly one audit row: action, entity, actor, client (id and name), kind and file name."""
        before = await self._ids()
        response = await call
        assert response.status_code == status, response.text
        rows = await self._new(before)
        assert [r.action for r in rows] == [action], [(r.action, r.after) for r in rows]
        (row,) = rows
        after = row.after or {}
        assert (row.entity, row.actor_id) == (entity, by.id), (row.entity, row.actor_id)
        if client is None:
            assert after.get("client_id") is None, after
        else:
            assert after["client_id"] == str(self.world.clients[client]), after
            assert after["client_name"] == self.world.names[client], after
        assert after.get("kind") == kind, after
        assert _file_of(row) == file, after
        if feed is not None:
            self.feed.append({"action": feed[0], "text": feed[1], "by": NAMES[by.id],
                              "client_id": str(self.world.clients[client]) if client else None})
        return response, row

    async def many(self, call, *, status: int, by, feed: tuple[str, str], counts: dict[str, int]):
        """A global action (an apply, a batch, an undo): its rows by action, exactly one of them in the feed."""
        before = await self._ids()
        response = await call
        assert response.status_code == status, response.text
        rows = await self._new(before)
        seen: dict[str, int] = {}
        for row in rows:
            seen[row.action] = seen.get(row.action, 0) + 1
        assert seen == counts, seen
        assert sum(1 for r in rows if r.action in aa.ACTIVITY_ACTIONS) == 1, seen
        self.feed.append({"action": feed[0], "text": feed[1], "by": NAMES[by.id], "client_id": None})
        return response, rows


async def seed_script_world(session) -> World:
    world = await seed_world(session)
    # Dorado's HubSpot deal says the MSA is in place: the mapping apply has one client to mark.
    dorado = (await session.scalars(select(Opportunity).where(
        Opportunity.client_id == world.clients["dorado"]))).one()
    dorado.hubspot_msa_type = "Signed MSA"
    await session.commit()
    return world


@pytest_asyncio.fixture
async def world(session, env) -> World:  # noqa: F811 — env is imported
    return await seed_script_world(session)


async def _row_id(session, client_id: uuid.UUID, kind: str) -> uuid.UUID:
    return await session.scalar(select(Agreement.id).where(Agreement.client_id == client_id, Agreement.kind == kind))


async def run_script(session, world: World) -> Ledger:
    """Every per-client write, every download route and the export, in the order a Legal user, a salesperson
    and an admin would use them, with the failures that must write nothing in between."""
    c = world.clients
    led = Ledger(session, world)
    launcher = inline(session)
    async with client_for(session, LEGAL, world.storage, launcher=launcher) as legal, \
            client_for(session, SALES, world.storage, launcher=launcher) as sales, \
            client_for(session, ADMIN, world.storage, launcher=launcher) as admin:
        # Client copies: a first copy, a new version with a note.
        await led.one(legal.post(f"/clients/{c['cinder']}/agreements/NDA/client-copy", files=_file("Cinder NDA.pdf", PDF)),
                      status=201, by=LEGAL, action=aa.CLIENT_UPLOADED, entity="agreement", client="cinder",
                      kind="NDA", file="Cinder NDA.pdf",
                      feed=("client_uploaded", "Uploaded client NDA for Cinder Systems (Cinder NDA.pdf)"))
        await led.one(legal.post(f"/clients/{c['cinder']}/agreements/NDA/client-copy",
                                 data={"note": "Payment terms 45 days"}, files=_file("Cinder NDA v2.pdf", PDF)),
                      status=201, by=LEGAL, action=aa.CLIENT_REPLACED, entity="agreement", client="cinder",
                      kind="NDA", file="Cinder NDA v2.pdf",
                      feed=("client_replaced", "Replaced client NDA for Cinder Systems (Cinder NDA v2.pdf)"))
        await led.nothing(legal.post(f"/clients/{c['cinder']}/agreements/MSA/client-copy",
                                     files=_file("empty.pdf", b"")), 422)
        # A standard copy attached, then replaced by the client's own copy (history keeps the standard).
        await led.one(legal.post(f"/clients/{c['arden']}/agreements/NDA/attach-standard"),
                      status=201, by=LEGAL, action=aa.STANDARD_ATTACHED, entity="agreement", client="arden",
                      kind="NDA", file="Lane Standard NDA.pdf",
                      feed=("standard_attached", "Attached standard NDA to Arden Foods"))
        await led.nothing(legal.post(f"/clients/{c['arden']}/agreements/NDA/attach-standard"), 409)
        _, replaced = await led.one(
            legal.post(f"/clients/{c['arden']}/agreements/NDA/client-copy", files=_file("Arden NDA.pdf", PDF)),
            status=201, by=LEGAL, action=aa.CLIENT_REPLACED, entity="agreement", client="arden", kind="NDA",
            file="Arden NDA.pdf", feed=("client_replaced", "Replaced client NDA for Arden Foods (Arden NDA.pdf)"))
        assert (replaced.before["source"], replaced.before["filename"]) == ("standard", "Lane Standard NDA.pdf")
        # Marks: set, replaced by another mark, removed; a future date and a missing mark write nothing.
        await led.one(legal.put(f"/clients/{c['elm']}/agreements/MSA/mark",
                                json={"reason": "signed_outside_dealgate", "marked_on": "2026-10-01"}),
                      status=200, by=LEGAL, action=aa.MARKED, entity="agreement_mark", client="elm", kind="MSA",
                      feed=("marked", "Marked MSA covered for Elm Retail (Signed outside DealGate)"))
        _, remarked = await led.one(
            legal.put(f"/clients/{c['elm']}/agreements/MSA/mark",
                      json={"reason": "confirmed_with_client", "marked_on": "2026-10-02", "note": "Per call"}),
            status=200, by=LEGAL, action=aa.MARKED, entity="agreement_mark", client="elm", kind="MSA",
            feed=("marked", "Marked MSA covered for Elm Retail (Confirmed with the client)"))
        assert remarked.before["reason"] == "signed_outside_dealgate"
        await led.nothing(legal.put(f"/clients/{c['elm']}/agreements/NDA/mark",
                                    json={"reason": "other", "marked_on": "2026-10-16"}), 422)
        await led.one(legal.delete(f"/clients/{c['elm']}/agreements/MSA/mark"),
                      status=200, by=LEGAL, action=aa.MARK_REMOVED, entity="agreement_mark", client="elm",
                      kind="MSA", feed=("mark_removed", "Removed MSA mark from Elm Retail"))
        await led.nothing(legal.delete(f"/clients/{c['elm']}/agreements/MSA/mark"), 404)
        # A client copy over a mark: one row, the mark described in ``before`` (and soft-removed).
        await led.one(legal.put(f"/clients/{c['heron']}/agreements/MSA/mark",
                                json={"reason": "other", "marked_on": "2026-10-03"}),
                      status=200, by=LEGAL, action=aa.MARKED, entity="agreement_mark", client="heron", kind="MSA",
                      feed=("marked", "Marked MSA covered for Heron Labs (Other)"))
        _, over_mark = await led.one(
            legal.post(f"/clients/{c['heron']}/agreements/MSA/client-copy", files=_file("Heron MSA.pdf", PDF)),
            status=201, by=LEGAL, action=aa.CLIENT_UPLOADED, entity="agreement", client="heron", kind="MSA",
            file="Heron MSA.pdf", feed=("client_uploaded", "Uploaded client MSA for Heron Labs (Heron MSA.pdf)"))
        assert over_mark.before["mark"]["reason"] == "other"
        # The legacy routes: create, replace, then remove (a client copy: the deletion job's row).
        await led.one(legal.post("/agreements", data={"client_id": str(c["dorado"]), "kind": "NDA"},
                                 files=_file("Dorado NDA.docx", DOCX)),
                      status=201, by=LEGAL, action=aa.CLIENT_UPLOADED, entity="agreement", client="dorado",
                      kind="NDA", file="Dorado NDA.docx",
                      feed=("client_uploaded", "Uploaded client NDA for Dorado Farms (Dorado NDA.docx)"))
        dorado_nda = await _row_id(session, c["dorado"], "NDA")
        await led.nothing(legal.post(f"/agreements/{dorado_nda}/replace", data={"expected_version": "7"},
                                     files=_file("stale.pdf", PDF)), 409)
        await led.one(legal.post(f"/agreements/{dorado_nda}/replace", data={"expected_version": "1"},
                                 files=_file("Dorado NDA v2.pdf", PDF)),
                      status=200, by=LEGAL, action=aa.CLIENT_REPLACED, entity="agreement", client="dorado",
                      kind="NDA", file="Dorado NDA v2.pdf",
                      feed=("client_replaced", "Replaced client NDA for Dorado Farms (Dorado NDA v2.pdf)"))
        # Detach: a standard attachment (200, the shared object stays), a client copy (202, a deletion job).
        await led.one(legal.post(f"/clients/{c['birch']}/agreements/MSA/attach-standard"),
                      status=201, by=LEGAL, action=aa.STANDARD_ATTACHED, entity="agreement", client="birch",
                      kind="MSA", file="Lane Standard MSA.pdf",
                      feed=("standard_attached", "Attached standard MSA to Birch Logistics"))
        await led.one(legal.delete(f"/clients/{c['birch']}/agreements/MSA"),
                      status=200, by=LEGAL, action=aa.DETACHED, entity="agreement", client="birch", kind="MSA",
                      file="Lane Standard MSA.pdf", feed=("detached", "Removed MSA file from Birch Logistics"))
        await led.one(legal.delete(f"/clients/{c['cinder']}/agreements/NDA"),
                      status=202, by=LEGAL, action=aa.DELETED, entity="agreement", client="cinder", kind="NDA",
                      file="Cinder NDA v2.pdf", feed=("detached", "Removed NDA file from Cinder Systems"))
        await led.one(legal.delete(f"/agreements/{dorado_nda}"),
                      status=202, by=LEGAL, action=aa.DELETED, entity="agreement", client="dorado", kind="NDA",
                      file="Dorado NDA v2.pdf", feed=("detached", "Removed NDA file from Dorado Farms"))
        await led.nothing(legal.delete(f"/clients/{c['birch']}/agreements/MSA"), 404)
        # The legacy DELETE on a standard attachment removes only the row (200), audited as a detach.
        await led.one(legal.post(f"/clients/{c['heron']}/agreements/NDA/attach-standard"),
                      status=201, by=LEGAL, action=aa.STANDARD_ATTACHED, entity="agreement", client="heron",
                      kind="NDA", file="Lane Standard NDA.pdf",
                      feed=("standard_attached", "Attached standard NDA to Heron Labs"))
        heron_nda = await _row_id(session, c["heron"], "NDA")
        await led.one(legal.delete(f"/agreements/{heron_nda}"),
                      status=200, by=LEGAL, action=aa.DETACHED, entity="agreement", client="heron", kind="NDA",
                      file="Lane Standard NDA.pdf", feed=("detached", "Removed NDA file from Heron Labs"))
        # Relationship by hand.
        _, changed = await led.one(
            legal.put(f"/clients/{c['garnet']}/relationship",
                      json={"relationship": "existing", "note": "Worked with them in 2024"}),
            status=200, by=LEGAL, action=aa.RELATIONSHIP_CHANGED, entity="client", client="garnet",
            feed=("relationship_changed", "Changed Garnet Media to existing"))
        assert changed.entity_id == str(c["garnet"]) and changed.after["note"] == "Worked with them in 2024"
        # A new standard version (an event about no client).
        await led.one(legal.post("/agreements/standard/NDA", files=_file("Lane NDA v2.pdf", PDF)),
                      status=201, by=LEGAL, action=aa.STANDARD_UPLOADED, entity="standard_agreement", kind="NDA",
                      file="Lane NDA v2.pdf",
                      feed=("standard_uploaded", "Uploaded standard NDA version 2 (Lane NDA v2.pdf)"))
        # Every download route, by a salesperson (all audited); a kind with no file writes nothing.
        await led.one(sales.get("/agreements/standard/NDA/download"),
                      status=200, by=SALES, action=aa.DOWNLOADED, entity="standard_agreement", kind="NDA",
                      file="Lane NDA v2.pdf", feed=("downloaded", "Downloaded the standard NDA"))
        await led.one(sales.get(f"/clients/{c['arden']}/agreements/NDA/download"),
                      status=200, by=SALES, action=aa.DOWNLOADED, entity="agreement", client="arden", kind="NDA",
                      file="Arden NDA.pdf", feed=("downloaded", "Downloaded NDA for Arden Foods"))
        arden_nda = await _row_id(session, c["arden"], "NDA")
        await led.one(sales.get(f"/agreements/{arden_nda}/download"),
                      status=200, by=SALES, action=aa.DOWNLOADED, entity="agreement", client="arden", kind="NDA",
                      file="Arden NDA.pdf", feed=("downloaded", "Downloaded NDA for Arden Foods"))
        _, first_version = await led.one(
            sales.get(f"/agreements/{arden_nda}/versions/1/download"),
            status=200, by=SALES, action=aa.DOWNLOADED, entity="agreement", client="arden", kind="NDA",
            file="Lane Standard NDA.pdf", feed=("downloaded", "Downloaded NDA for Arden Foods"))
        assert (first_version.after["version_no"], first_version.after["source"]) == (1, "standard")
        await led.nothing(sales.get(f"/clients/{c['garnet']}/agreements/NDA/download"), 404)
        # The export: one row, about no client, with the file name and the row count.
        _, exported = await led.one(sales.get("/agreements/export"),
                                    status=200, by=SALES, action=aa.EXPORTED, entity=aa.EXPORT_ENTITY,
                                    file="DealGate_Agreements.csv",
                                    feed=("exported", "Exported 7 clients to CSV"))
        assert exported.after["rows"] == 7 and exported.after["filters"] == {}
        # Refused writes (403 from the server) write nothing.
        await led.nothing(sales.post(f"/clients/{c['garnet']}/agreements/NDA/attach-standard"), 403)
        await led.nothing(legal.put("/agreements/hubspot-mapping",
                                    json={"items": [{"value": "Signed MSA", "action": "covered"}]}), 403)
        # The HubSpot mapping (save: one row, outside the feed) and its apply (one mark + one summary).
        await led.one(admin.put("/agreements/hubspot-mapping",
                                json={"items": [{"value": "Signed MSA", "action": "covered"}]}),
                      status=200, by=ADMIN, action=aa.HUBSPOT_MAPPING_SAVED, entity="agreement_hubspot_map")
        await led.many(admin.post("/agreements/hubspot-mapping/apply", params={"dry_run": "false"}),
                       status=200, by=ADMIN, counts={aa.HUBSPOT_MARKED: 1, aa.HUBSPOT_APPLIED: 1},
                       feed=("hubspot_applied", "Applied HubSpot msa_type mapping: marked MSA covered for 1 client"))
        # The batch (its dry run writes nothing) and its undo: one feed event each.
        preview = await led.nothing(admin.post("/agreements/batches", json={"kinds": ["NDA"]}), 200)
        targets = preview.json()["will_receive"]
        assert targets == 2  # Birch (Closed Won) and Garnet (existing by hand) hold no NDA
        _, run_rows = await led.many(
            admin.post("/agreements/batches", json={"kinds": ["NDA"], "dry_run": False, "confirm": f"ATTACH {targets}",
                                                    "idempotency_key": "ta-audit-batch"}),
            status=202, by=ADMIN, feed=("batch_run", "Attached standard NDA to 2 clients (batch AG-0001)"),
            counts={aa.BATCH_STARTED: 1, aa.CUTOVER_SET: 1, aa.RELATIONSHIP_STAMPED: 6, aa.BATCH_ATTACHED: 2,
                    aa.BATCH_RUN: 1})
        attached = {r.after["client_name"] for r in run_rows if r.action == aa.BATCH_ATTACHED}
        assert attached == {"Birch Logistics", "Garnet Media"}
        await led.many(admin.post("/agreements/batches/AG-0001/undo"),
                       status=202, by=ADMIN, counts={aa.BATCH_UNDO_STARTED: 1, aa.BATCH_DETACHED: 2,
                                                     aa.BATCH_UNDONE: 1},
                       feed=("batch_undone", "Undid batch AG-0001: removed 2 standard attachments"))
    return led


async def test_every_write_download_and_export_writes_exactly_one_audit_row(session, world):
    led = await run_script(session, world)
    assert len(led.feed) == 27
    # The detaches above: the standard object stayed (no job); the two client copies each queued one job.
    jobs = (await session.scalars(select(DeletionJob))).all()
    assert sorted(job.subject_type for job in jobs) == ["agreement", "agreement"]
    assert world.standard_keys["MSA"] in world.storage.objects
    # A client copy over a mark soft-removed the mark (history keeps it).
    heron_mark = (await session.scalars(select(AgreementMark).where(
        AgreementMark.client_id == world.clients["heron"]))).one()
    assert heron_mark.removed_at is not None and heron_mark.removed_by == LEGAL.id
    # The chain still verifies after every writer (routes, the batch job, the apply) appended to it.
    assert await verify_chain(session)


async def check_activity(session, world: World, led: Ledger) -> None:
    async with client_for(session, SALES, world.storage) as sales:
        feed = (await sales.get("/agreements/activity", params={"page_size": 100})).json()
        workspace = (await sales.get("/agreements/workspace")).json()
        page_two = (await sales.get("/agreements/activity", params={"page_size": 25, "page": 2})).json()
        page_three = (await sales.get("/agreements/activity", params={"page_size": 25, "page": 3})).json()
    items = feed["items"]
    assert feed["total"] == workspace["activity_count"] == len(led.feed) == len(items)
    assert [{k: item[k] for k in ("action", "text", "by", "client_id")} for item in items] == led.feed[::-1]
    assert all(item["at"].endswith("Z") for item in items)
    stamps = [datetime.fromisoformat(item["at"].replace("Z", "+00:00")) for item in items]
    assert stamps == sorted(stamps, reverse=True)
    for item in items:
        assert not UUID_TEXT.search(item["text"]) and not UUID_TEXT.search(item["by"]), item
        assert "agreements/" not in item["text"], item  # no storage key either
        assert set(item) == {"at", "by", "action", "text", "client_id"}
    assert page_two["total"] == page_three["total"] == len(items)
    assert page_two["items"] == items[25:] and len(page_two["items"]) == len(items) - 25 > 0
    assert page_three["items"] == []


async def test_activity_lists_every_event_newest_first_in_words_without_ids(session, world):
    led = await run_script(session, world)
    await check_activity(session, world, led)


@POSTGRES
async def test_the_whole_script_on_postgres(env):  # noqa: F811 — env is imported
    """The same writes, rows and feed on a fresh migrated Postgres database: the real audit lock and its
    append-only trigger, real foreign keys and partial unique indexes, JSONB, the settings row from 0072."""
    async with scratch_postgres() as (_engine, factory):
        async with factory() as session:
            world = await seed_script_world(session)
            led = await run_script(session, world)
            await check_activity(session, world, led)
            assert await verify_chain(session)
            jobs = (await session.scalars(select(DeletionJob))).all()
            assert sorted(job.subject_type for job in jobs) == ["agreement", "agreement"]


@pytest_asyncio.fixture
async def fixture_world(session, env, monkeypatch) -> tuple[World, dict]:  # noqa: F811 — env is imported
    from app.services.test_fixtures import create_fixture

    monkeypatch.setenv("DEALGATE_TENANT_ID", "lane-ta-tenant")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    world = await seed_world(session, users=(ADMIN, LEGAL, SALES, E2E))
    fixture = await create_fixture(session, actor_id=E2E.id, label="Agreements", reviewer_ids=[])
    await session.commit()
    return world, fixture


async def test_real_users_never_see_fixture_events_and_the_test_identity_sees_its_own(session, fixture_world):
    world, fixture = fixture_world
    fx = fixture["client_id"]
    fx_name = (await session.get(Client, fx)).name
    async with client_for(session, E2E, world.storage) as bot:
        assert (await bot.post(f"/clients/{fx}/agreements/NDA/client-copy",
                               files=_file("fixture-nda.pdf", PDF))).status_code == 201
        assert (await bot.put(f"/clients/{fx}/agreements/MSA/mark",
                              json={"reason": "other", "marked_on": "2026-10-05"})).status_code == 200
        assert (await bot.get(f"/clients/{fx}/agreements/NDA/download")).status_code == 200
        assert (await bot.get("/agreements/standard/NDA/download")).status_code == 200
        assert (await bot.get("/agreements/export")).status_code == 200
        assert (await bot.get(f"/clients/{world.clients['cinder']}/agreements")).status_code == 404
    async with client_for(session, LEGAL, world.storage) as legal:
        assert (await legal.post(f"/clients/{world.clients['cinder']}/agreements/NDA/client-copy",
                                 files=_file("Cinder NDA.pdf", PDF))).status_code == 201
        assert (await legal.post("/agreements/standard/MSA", files=_file("Lane MSA v2.pdf", PDF))).status_code == 201
        assert (await legal.get(f"/clients/{fx}/agreements")).status_code == 404
    real_lines = [
        ("standard_uploaded", "Uploaded standard MSA version 2 (Lane MSA v2.pdf)", "Lena Legal", None),
        ("client_uploaded", "Uploaded client NDA for Cinder Systems (Cinder NDA.pdf)", "Lena Legal",
         str(world.clients["cinder"])),
    ]
    for user in (SALES, LEGAL, ADMIN):  # every real user, whatever the role
        async with client_for(session, user, world.storage) as api:
            feed = (await api.get("/agreements/activity")).json()
            workspace = (await api.get("/agreements/workspace")).json()
            searched = (await api.get("/agreements/activity", params={"q": "fixture"})).json()
        assert [(i["action"], i["text"], i["by"], i["client_id"]) for i in feed["items"]] == real_lines, user.name
        assert feed["total"] == workspace["activity_count"] == 2
        assert searched == {"total": 0, "items": []}
    async with client_for(session, E2E, world.storage) as bot:
        feed = (await bot.get("/agreements/activity")).json()
        workspace = (await bot.get("/agreements/workspace")).json()
    assert [(i["action"], i["text"], i["by"], i["client_id"]) for i in feed["items"]] == [
        ("standard_uploaded", "Uploaded standard MSA version 2 (Lane MSA v2.pdf)", "Lena Legal", None),
        ("exported", "Exported 1 client to CSV", "Lane Bot", None),
        ("downloaded", "Downloaded the standard NDA", "Lane Bot", None),
        ("downloaded", f"Downloaded NDA for {fx_name}", "Lane Bot", str(fx)),
        ("marked", f"Marked MSA covered for {fx_name} (Other)", "Lane Bot", str(fx)),
        ("client_uploaded", f"Uploaded client NDA for {fx_name} (fixture-nda.pdf)", "Lane Bot", str(fx)),
    ]
    assert feed["total"] == workspace["activity_count"] == 6
    # Every one of those events is in the audit log; visibility, not omission, keeps them apart.
    fixture_rows = (await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == E2E.id,
                                                                    AuditEvent.action.in_(list(aa.ACTIVITY_ACTIONS))))).all()
    assert len(fixture_rows) == 5


# --- the CSV export -------------------------------------------------------------------------------------------

HEADER = ["Client", "Business unit", "Relationship", "Relationship basis", "Furthest open stage", "NDA", "MSA",
          "Needs attention", "Possible duplicate"]


async def seed_regions(session) -> None:
    """The business-unit mapping the Pipeline loader reads (migration 0070 seeds the region map)."""
    if await session.get(HubspotPropertyMapping, "business_unit") is None:
        session.add(HubspotPropertyMapping(
            key="business_unit", internal_name="region", object_type="deal", label="Region",
            field_type="enumeration", availability_state="configured", mapping_version=1,
            options=[{"value": row["hubspot_value"], "label": row["hubspot_value"]} for row in DEFAULT_REGION_MAP]))
    if not await session.scalar(select(func.count()).select_from(HubspotRegionMap)):
        session.add_all([HubspotRegionMap(**row) for row in DEFAULT_REGION_MAP])
    await session.flush()


async def add_client(session, name: str, deals: list[tuple[int, str | None]]) -> uuid.UUID:
    client = Client(name=name, hubspot_company_id=f"ta-x-{uuid.uuid4().hex[:10]}")
    session.add(client)
    await session.flush()
    for i, (position, region) in enumerate(deals):
        session.add(deal(client.id, position, f"x-{client.id.hex[:8]}-{i}", region=region))
    await session.flush()
    return client.id


def read_csv(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))


async def export(session, world: World, user=SALES, **params):
    async with client_for(session, user, world.storage) as api:
        return await api.get("/agreements/export", params=params)


@pytest_asyncio.fixture
async def export_world(session, env) -> World:  # noqa: F811 — env is imported
    world = await seed_world(session, clients={})
    await seed_regions(session)
    await session.commit()
    return world


async def test_export_columns_bom_regions_and_flags(session, export_world):
    await add_client(session, "Avalon Staffing Partners", [(7, "US - IT Avalon")])  # existing, one unit
    await add_client(session, "Kloof Analytics", [(3, "South Africa")])  # net new, past stage 1
    await add_client(session, "Twin Peaks LLC", [(4, "US")])  # possible duplicates of each other
    await add_client(session, "Twin Peaks, Inc.", [(1, "US - IT Avalon (Staffing)")])
    await add_client(session, "Quiet Harbor", [])
    await session.commit()
    response = await export(session, export_world, sort="name")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content[:3] == b"\xef\xbb\xbf" and response.content.count(b"\xef\xbb\xbf") == 1  # one BOM
    assert response.content.decode("utf-8").splitlines()[0] == "﻿" + ",".join(HEADER)
    rows = read_csv(response)
    assert rows[0] == HEADER  # the contract's columns, in order
    by_name = {row[0]: dict(zip(HEADER, row, strict=True)) for row in rows[1:]}
    assert [row[0] for row in rows[1:]] == sorted(by_name, key=str.casefold)
    assert by_name["Avalon Staffing Partners"]["Business unit"] == "IT Avalon · US"
    assert by_name["Kloof Analytics"]["Business unit"] == "Retro Rabbit · South Africa"
    assert by_name["Twin Peaks LLC"]["Business unit"] == "ST21 · US"
    assert by_name["Twin Peaks, Inc."]["Business unit"] == "IT Avalon · US"  # the staffing value, same unit
    assert by_name["Quiet Harbor"]["Business unit"] == "No deals or engagements yet"  # a reason, never blank
    assert {k: by_name["Avalon Staffing Partners"][k] for k in ("Relationship", "NDA", "MSA", "Needs attention")} == {
        "Relationship": "Existing", "NDA": "Existing, none attached", "MSA": "Existing, none attached",
        "Needs attention": "No"}
    assert {k: by_name["Kloof Analytics"][k] for k in ("Relationship", "NDA", "MSA", "Needs attention")} == {
        "Relationship": "Net new", "NDA": "Missing", "MSA": "Missing", "Needs attention": "Yes"}
    assert (by_name["Twin Peaks LLC"]["Possible duplicate"], by_name["Twin Peaks, Inc."]["Possible duplicate"],
            by_name["Kloof Analytics"]["Possible duplicate"]) == ("Yes", "Yes", "No")
    assert by_name["Twin Peaks, Inc."]["NDA"] == "Due at stage 2"
    assert not any(UUID_TEXT.search(cell) for row in rows for cell in row)


FORMULA_NAMES = ["=1+1", "+1+1 Holdings", "-1+1 Partners", "@SUM(A1:A9)", "\tTabbed Trading", "\rReturned Goods",
                 '=HYPERLINK("http://evil.test","open")', "=cmd|' /C calc'!A0"]
SAFE_NAMES = ["Plain Name Co", "Mid=Formula Ltd", "Comma, Quote \"and\" Co", "Line\nBreak Labs"]


async def test_export_neutralises_every_formula_start(session, export_world):
    for name in FORMULA_NAMES + SAFE_NAMES:
        await add_client(session, name, [(3, "US")])
    await session.commit()
    rows = read_csv(await export(session, export_world))
    cells = {row[0] for row in rows[1:]}
    # A cell that starts with = + - @ tab or CR gets exactly one leading apostrophe, so a spreadsheet shows it
    # as text; every other cell (including a "=" later in the name, commas, quotes, newlines) is unchanged.
    assert cells == {"'" + name for name in FORMULA_NAMES} | set(SAFE_NAMES)
    assert len(rows) - 1 == len(FORMULA_NAMES) + len(SAFE_NAMES)
    for row in rows[1:]:
        for cell in row[1:]:
            assert not cell.startswith(("=", "+", "-", "@", "\t", "\r")), row
    # A plain number cannot run as a formula; csv_safety (the rule every DealGate export uses, directive F10)
    # leaves it as it is, which is narrower than the contract's "any cell" wording (reported as a deviation).
    await add_client(session, "-42", [(3, "US")])
    await session.commit()
    names = {row[0] for row in read_csv(await export(session, export_world))[1:]}
    assert "-42" in names and "'-42" not in names


async def test_export_follows_the_filters_and_its_audit_row_counts_the_rows(session, export_world):
    await add_client(session, "Avalon Staffing Partners", [(7, "US - IT Avalon")])
    await add_client(session, "Kloof Analytics", [(3, "South Africa")])
    await add_client(session, "Orchid Media", [(2, "US")])
    await session.commit()
    attention = read_csv(await export(session, export_world, status="attention", bu="Retro Rabbit"))
    assert [row[0] for row in attention[1:]] == ["Kloof Analytics"]
    everyone = read_csv(await export(session, export_world, user=ADMIN))
    assert len(everyone) - 1 == 3
    rows = (await session.scalars(select(AuditEvent).where(AuditEvent.action == aa.EXPORTED)
                                  .order_by(AuditEvent.ts))).all()
    assert [(r.actor_id, r.after["rows"], r.after["filters"], r.after["file_name"]) for r in rows] == [
        (SALES.id, 1, {"status": "attention", "bu": ["Retro Rabbit"]}, "DealGate_Agreements.csv"),
        (ADMIN.id, 3, {}, "DealGate_Agreements.csv"),
    ]
    assert all(r.entity == aa.EXPORT_ENTITY and r.after.get("client_id") is None for r in rows)
