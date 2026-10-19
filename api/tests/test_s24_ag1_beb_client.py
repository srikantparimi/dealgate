"""S24-AG1 lane BE-B — per-client agreement routes, the legacy routes and the deletion fixes.

B5 (file rules on every upload route, compensating delete), B6 (panel, client copy, attach standard, mark,
unmark, detach, download, relationship), B11 (roles on the server, an audit row for every write and download),
T11 server part (a fixture's uploads are keyed under agreements/e2e/{run}/), deletion fixes (a standard key is
never queued; a client with marks can be deleted). SQLite with foreign keys on; StubS3 for storage.
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.audit import verify_chain
from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.agreements import AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.models.user import User
from app.routers.agreements import get_batch_launcher
from app.routers.agreements import router as agreements_router
from app.routers.client_agreements import router as client_router
from app.services import agreement_audit
from app.services.agreement_files import MSG_EMPTY, MSG_NOT_DOCX, MSG_NOT_PDF, MSG_TOO_LARGE, MSG_TYPE
from app.services.deletion_storage import key_is_referenced
from app.services.hubspot_owners import HubspotOwner  # noqa: F401 — registers the table for create_all
from app.services.hubspot_properties import HubspotPropertyMapping  # noqa: F401 — same

NOW = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)  # 12:00 in Los Angeles
TODAY = date(2026, 10, 15)
BUCKET = "stub-agreements"
PIPELINE_ID = "710688094"
STAGES = (  # HubSpot stage id, label, display order, closed — as on staging
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
ADMIN = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000a1"), "ada@example.test", "Ada Admin", ("SystemAdmin",))
LEGAL = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000b2"), "lee@example.test", "Lee Legal", ("Legal",))
SALES = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000c3"), "sam@example.test", "Sam Sales", ("Sales",))
FINANCE = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000d4"), "fin@example.test", "Fay Finance", ("Finance",))
# key → (name, deal stage positions [1-6 open, 7 won, 8 lost, 9 hold], has an SOW)
CLIENTS: dict[str, tuple[str, list[int], bool]] = {
    "atlas": ("Atlas Foods", [7], False),  # existing (Closed Won)
    "beacon": ("Beacon Logistics", [4], True),  # existing (SOW)
    "cobalt": ("Cobalt Systems", [3], False),  # net new, past stage 1: required
    "dune": ("Dune Farms", [1], True),  # existing, deals only in stage 1
    "ember": ("Ember Retail", [1], False),  # net new, due at stage 2
    "falcon": ("Falcon Capital", [9], False),  # net new, on Hold: required
    "granite": ("Granite Media", [], False),  # net new, nothing needed
    "harbor": ("Harbor Labs", [5, 8], False),  # net new, required
    "test": ("S21 e2e 1234 Seeded run", [7], False),  # a run-tagged name: test data
}
PDF = b"%PDF-1.4\n% synthetic agreement\n" + b"x" * 64
DOCX = b"PK\x03\x04" + b"\x00" * 64


@dataclass
class Seed:
    clients: dict[str, uuid.UUID] = field(default_factory=dict)
    standards: dict[str, StandardAgreement] = field(default_factory=dict)


def deal(client_id: uuid.UUID, position: int, n: str) -> Opportunity:
    sid, label, order, _closed = STAGES[position - 1]
    return Opportunity(
        source="hubspot", hubspot_deal_id=f"hs-{n}", name=f"Deal {n}", client_id=client_id,
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=position == 7, is_closed_lost=position == 8,
        close_date=TODAY - timedelta(days=90) if position in (7, 8) else TODAY + timedelta(days=30),
        governance_status="Intake", amount=Decimal("1000"), currency="USD", hubspot_last_modified_at=NOW)


async def seed(session, *, standards: tuple[str, ...] = ("NDA", "MSA"), extra_existing: int = 0) -> Seed:
    """Users, the staging stage mirror, the clients above (plus ``extra_existing`` Closed Won clients)."""
    out = Seed()
    for user in (ADMIN, LEGAL, SALES, FINANCE):
        session.add(User(id=user.id, email=user.email, name=user.name, groups=list(user.groups)))
    session.add(HubspotPipeline(id=PIPELINE_ID, label="SmarTek21 Global Pipeline", display_order=0, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    entries = list(CLIENTS.items()) + [(f"extra{i:03d}", (f"Existing Client {i:03d}", [7], False))
                                       for i in range(extra_existing)]
    for key, (name, positions, sow) in entries:
        client = Client(name=name, hubspot_company_id=f"c-{key}")
        session.add(client)
        await session.flush()
        out.clients[key] = client.id
        deals = [deal(client.id, position, f"{key}-{i}") for i, position in enumerate(positions)]
        session.add_all(deals)
        await session.flush()
        if sow:
            session.add(Sow(opportunity_id=deals[0].id, created_at=NOW - timedelta(days=60)))
    for kind in standards:
        standard = StandardAgreement(kind=kind, version_no=1, file_key=f"agreements/standard/{kind}/std-{kind}.pdf",
                                     filename=f"SmarTek21_Standard_{kind}.pdf", file_size=2048, sha256="c" * 64,
                                     uploaded_by=ADMIN.id, uploaded_at=NOW - timedelta(days=1))
        session.add(standard)
        out.standards[kind] = standard
    await session.commit()
    return out


async def _noop_launcher(batch_id, phase):  # noqa: ARG001
    return None


@asynccontextmanager
async def client_for(session, user: AuthUser, storage: StubS3 | None = None, launcher=None):
    app = FastAPI()
    app.include_router(agreements_router)
    app.include_router(client_router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    app.dependency_overrides[get_evidence_s3] = lambda: storage or StubS3(bucket=BUCKET)
    app.dependency_overrides[get_batch_launcher] = lambda: launcher or _noop_launcher
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://ag1") as client:
        yield client


class StubVersions:
    """The cleanup worker's view of StubS3 (one version per key)."""

    def __init__(self, stub: StubS3):
        self.stub = stub

    def get_paginator(self, name):
        assert name == "list_object_versions"
        return self

    def paginate(self, *, Bucket, Prefix):  # noqa: N803 — boto3 names
        return [{"Versions": [{"Key": k, "VersionId": "v1"} for k in self.stub.objects if k.startswith(Prefix)],
                 "DeleteMarkers": []}]

    def delete_objects(self, *, Bucket, Delete):  # noqa: N803
        for item in Delete["Objects"]:
            self.stub.objects.pop(item["Key"], None)
        return {}


async def audit_rows(session, action: str) -> list[AuditEvent]:
    return list((await session.scalars(select(AuditEvent).where(AuditEvent.action == action)
                                       .order_by(AuditEvent.ts))).all())


def upload(name: str, content: bytes, note: str | None = None):
    data = {"note": note} if note is not None else {}
    return {"files": {"file": (name, content, "application/octet-stream")}, "data": data}


@pytest_asyncio.fixture
async def engine(fk_engine):
    return fk_engine


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_NOW", NOW.isoformat())
    monkeypatch.setenv("AGREEMENTS_BUCKET", BUCKET)
    monkeypatch.delenv("DEALGATE_TENANT_ID", raising=False)


@pytest_asyncio.fixture
async def seeded(session, env) -> Seed:
    return await seed(session)


# --- B6: the panel ----------------------------------------------------------------------------


async def test_panel_is_readable_by_every_role_and_never_writes(session, seeded):
    cobalt = seeded.clients["cobalt"]
    before = await session.scalar(select(func.count()).select_from(AuditEvent))
    for user, can_write in ((SALES, False), (FINANCE, False), (LEGAL, True), (ADMIN, True)):
        async with client_for(session, user) as api:
            response = await api.get(f"/clients/{cobalt}/agreements")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["can_write"] is can_write
        assert body["name"] == "Cobalt Systems"
        assert (body["relationship"], body["requirement"], body["needs_attention"]) == ("net_new", "required", True)
        assert body["provisional"] is True  # no cutover yet: judged live
        assert (body["nda"]["state"], body["msa"]["state"]) == ("missing", "missing")
        assert body["missing_kinds"] == ["NDA", "MSA"]
        assert body["deals"]["furthest_open_stage"] == 3 and body["deals"]["open"] == 1
        assert body["nda"]["history"] == [] and body["msa"]["hubspot_hint"] is None
    assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before
    async with client_for(session, SALES) as api:
        assert (await api.get(f"/clients/{uuid.uuid4()}/agreements")).status_code == 404
        hold = (await api.get(f"/clients/{seeded.clients['falcon']}/agreements")).json()
    assert (hold["requirement"], hold["deals"]["on_hold"], hold["deals"]["stage_text"]) == ("required", True, "On hold")


# --- B5 + B6: client copies -------------------------------------------------------------------


async def test_client_copy_over_a_standard_replaces_it_for_that_client_only(session, seeded):
    storage = StubS3(bucket=BUCKET)
    atlas, beacon = seeded.clients["atlas"], seeded.clients["beacon"]
    async with client_for(session, LEGAL, storage) as api:
        for client_id in (atlas, beacon):
            response = await api.post(f"/clients/{client_id}/agreements/NDA/attach-standard")
            assert response.status_code == 201, response.text
            card = response.json()
            assert (card["state"], card["source"], card["standard_version"], card["version_no"]) == (
                "standard", "standard", 1, 1)
            assert card["uploaded_by"] == "Lee Legal" and card["source_label"] == "Standard v1"
        assert storage.objects == {}  # attaching copies nothing: every row points at the one standard object
        response = await api.post(f"/clients/{atlas}/agreements/NDA/client-copy",
                                  **upload("Atlas NDA (signed).pdf", PDF, note="Updated payment terms"))
        assert response.status_code == 201, response.text
        card = response.json()
    assert (card["state"], card["source"], card["version_no"], card["note"]) == ("client", "client", 2, "Updated payment terms")
    assert card["file_name"] == "Atlas NDA (signed).pdf" and card["standard_version"] is None
    assert [h["what"] for h in card["history"]] == [
        "Standard copy replaced with a client copy: Atlas NDA (signed).pdf. Note: Updated payment terms",
        "Standard NDA v1 attached"]
    rows = {r.client_id: r for r in (await session.scalars(select(Agreement))).all()}
    assert rows[beacon].file_key == seeded.standards["NDA"].file_key and rows[beacon].source == "standard"
    assert rows[atlas].source == "client" and rows[atlas].standard_agreement_id is None
    (key,) = storage.objects
    assert re.fullmatch(rf"agreements/{rows[atlas].id}/\d{{8}}T\d{{6}}Z-[0-9a-f]{{8}}-Atlas NDA _signed_\.pdf", key)
    replaced = (await audit_rows(session, agreement_audit.CLIENT_REPLACED))[-1]
    assert replaced.before["source"] == "standard" and replaced.before["standard_version"] == 1
    assert replaced.after["client_name"] == "Atlas Foods" and replaced.after["kind"] == "NDA"
    assert replaced.actor_id == LEGAL.id
    assert len(await audit_rows(session, agreement_audit.STANDARD_ATTACHED)) == 2
    assert await verify_chain(session)


async def test_new_versions_keep_history_and_a_long_note_is_refused(session, seeded):
    storage = StubS3(bucket=BUCKET)
    cobalt = seeded.clients["cobalt"]
    async with client_for(session, ADMIN, storage) as api:
        too_long = await api.post(f"/clients/{cobalt}/agreements/MSA/client-copy", **upload("m.pdf", PDF, "n" * 201))
        assert too_long.status_code == 422, too_long.text
        assert storage.objects == {}
        first = await api.post(f"/clients/{cobalt}/agreements/MSA/client-copy", **upload("msa-v1.pdf", PDF))
        second = await api.post(f"/clients/{cobalt}/agreements/MSA/client-copy",
                                **upload("msa-v2.docx", DOCX, "Mutual MSA requested by the client"))
        assert (first.status_code, second.status_code) == (201, 201), second.text
        panel = (await api.get(f"/clients/{cobalt}/agreements")).json()
    assert first.json()["version_no"] == 1 and second.json()["version_no"] == 2
    assert panel["msa"]["state"] == "client" and panel["nda"]["state"] == "missing"
    assert panel["needs_attention"] is True  # the NDA is still missing: a warning only
    assert [h["what"] for h in panel["msa"]["history"]] == [
        "Client copy version 2 uploaded: msa-v2.docx. Note: Mutual MSA requested by the client",
        "Client copy uploaded: msa-v1.pdf"]
    assert (await session.scalar(select(func.count()).select_from(Agreement))) == 1  # one row per client and kind
    assert len(storage.objects) == 2
    uploaded = await audit_rows(session, agreement_audit.CLIENT_UPLOADED)
    assert [(a.after["client_name"], a.after["kind"], a.after["filename"]) for a in uploaded] == [
        ("Cobalt Systems", "MSA", "msa-v1.pdf")]


@pytest.mark.parametrize(("name", "content", "status", "message"), [
    ("contract.pdf", b"just some text, not a PDF", 415, MSG_NOT_PDF),
    ("contract.docx", b"%PDF-1.4 a PDF named docx", 415, MSG_NOT_DOCX),
    ("contract.txt", PDF, 415, MSG_TYPE),
    ("contract", PDF, 415, MSG_TYPE),
    ("contract.pdf", b"", 422, MSG_EMPTY),
    ("big.pdf", b"%PDF-" + bytes(26 * 1024 * 1024), 413, MSG_TOO_LARGE),
])
async def test_file_rules_are_enforced_on_the_server(session, seeded, name, content, status, message):
    storage = StubS3(bucket=BUCKET)
    async with client_for(session, LEGAL, storage) as api:
        response = await api.post(f"/clients/{seeded.clients['cobalt']}/agreements/NDA/client-copy",
                                  **upload(name, content))
    assert response.status_code == status, response.text
    assert response.json()["detail"] == message
    assert storage.objects == {}
    assert await session.scalar(select(func.count()).select_from(Agreement)) == 0


@pytest.mark.parametrize(("name", "stored", "shown"), [
    ("x.pdf.pdf", "x.pdf", "x.pdf.pdf"),
    ("Report.PDF.pdf", "Report.pdf", "Report.PDF.pdf"),
    ("<img src=x onerror='alert(1)'>.pdf", "_img src_x onerror_alert_1_.pdf", "<img src=x onerror='alert(1)'>.pdf"),
    ("../../secret\\board.pdf", "board.pdf", "board.pdf"),
    ("a" * 300 + ".pdf", "a" * 80 + ".pdf", "a" * 251 + ".pdf"),
])
async def test_stored_names_are_sanitised_and_the_original_is_kept_for_display(session, seeded, name, stored, shown):
    storage = StubS3(bucket=BUCKET)
    async with client_for(session, LEGAL, storage) as api:
        response = await api.post(f"/clients/{seeded.clients['cobalt']}/agreements/NDA/client-copy",
                                  **upload(name, PDF))
    assert response.status_code == 201, response.text
    (key,) = storage.objects
    assert key.split("/", 2)[2].split("-", 2)[2] == stored
    assert key.count("/") == 2 and "\\" not in key
    assert response.json()["file_name"] == shown


async def test_upload_object_is_queued_for_deletion_when_the_row_cannot_be_committed(session, seeded, monkeypatch):
    from app.services.deletion_cleanup import process_deletion_jobs

    storage = StubS3(bucket=BUCKET)

    async def broken(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(agreement_audit, "record", broken)
    async with client_for(session, LEGAL, storage) as api:
        response = await api.post(f"/clients/{seeded.clients['cobalt']}/agreements/NDA/client-copy",
                                  **upload("nda.pdf", PDF))
    assert response.status_code == 500
    monkeypatch.undo()
    (key,) = storage.objects  # written first …
    assert await session.scalar(select(func.count()).select_from(Agreement)) == 0
    job = (await session.scalars(select(DeletionJob))).one()  # … and queued for the cleanup worker
    assert (job.subject_type, job.status, job.objects) == ("agreement_upload", "pending",
                                                            [{"bucket": BUCKET, "key": key}])
    assert await process_deletion_jobs(session, s3=StubVersions(storage)) == 1
    assert storage.objects == {}


async def test_fixture_uploads_are_keyed_under_their_run(session, seeded, monkeypatch):
    from app.services.test_fixtures import create_fixture

    monkeypatch.setenv("DEALGATE_TENANT_ID", "ag1-run-tags")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    bot = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000e2"), "bot@example.test", "E2E Bot",
                   ("SystemAdmin", "officeapp-e2e"))
    session.add(User(id=bot.id, email=bot.email, name=bot.name, groups=list(bot.groups)))
    await session.flush()
    fixture = await create_fixture(session, actor_id=bot.id, label="Agreements", reviewer_ids=[])
    await session.commit()
    storage = StubS3(bucket=BUCKET)
    async with client_for(session, bot, storage) as api:
        mine = await api.post(f"/clients/{fixture['client_id']}/agreements/NDA/client-copy", **upload("n.pdf", PDF))
        theirs = await api.get(f"/clients/{seeded.clients['cobalt']}/agreements")
    async with client_for(session, LEGAL, storage) as api:
        real = await api.post(f"/clients/{seeded.clients['cobalt']}/agreements/NDA/client-copy",
                              **upload("n.pdf", PDF))
        hidden = await api.get(f"/clients/{fixture['client_id']}/agreements")
    assert (mine.status_code, real.status_code, theirs.status_code, hidden.status_code) == (201, 201, 404, 404)
    fixture_key = next(k for k in storage.objects if k.startswith("agreements/e2e/"))
    assert fixture_key.startswith(f"agreements/e2e/{fixture['run_id']}/{mine.json()['agreement_id']}/")
    real_key = next(k for k in storage.objects if not k.startswith("agreements/e2e/"))
    assert real_key.startswith(f"agreements/{real.json()['agreement_id']}/")


# --- B6: attach, mark, detach, download, relationship -----------------------------------------


async def test_attach_standard_needs_a_standard_and_an_empty_kind(session, env):
    await seed(session, standards=("NDA",))
    cobalt = (await session.scalar(select(Client.id).where(Client.name == "Cobalt Systems")))
    async with client_for(session, ADMIN) as api:
        assert (await api.post(f"/clients/{cobalt}/agreements/MSA/attach-standard")).status_code == 404
        assert (await api.post(f"/clients/{cobalt}/agreements/NDA/attach-standard")).status_code == 201
        again = await api.post(f"/clients/{cobalt}/agreements/NDA/attach-standard")
        assert again.status_code == 409 and again.json()["detail"] == "This client already has an NDA."
        marked = await api.put(f"/clients/{cobalt}/agreements/MSA/mark",
                               json={"reason": "signed_outside_dealgate", "marked_on": TODAY.isoformat()})
        assert marked.status_code == 200
        session.add(StandardAgreement(kind="MSA", version_no=1, file_key="agreements/standard/MSA/m.pdf",
                                      filename="m.pdf", file_size=1, sha256="d" * 64, uploaded_by=ADMIN.id))
        await session.commit()
        assert (await api.post(f"/clients/{cobalt}/agreements/MSA/attach-standard")).status_code == 409


async def test_marks_are_validated_replaced_and_removed_softly(session, seeded):
    cobalt = seeded.clients["cobalt"]
    async with client_for(session, LEGAL) as api:
        future = await api.put(f"/clients/{cobalt}/agreements/NDA/mark",
                               json={"reason": "other", "marked_on": (TODAY + timedelta(days=1)).isoformat()})
        assert future.status_code == 422 and future.json()["detail"] == "The date cannot be in the future."
        bad = await api.put(f"/clients/{cobalt}/agreements/NDA/mark",
                            json={"reason": "per_hubspot", "marked_on": TODAY.isoformat()})
        assert bad.status_code == 422
        first = await api.put(f"/clients/{cobalt}/agreements/NDA/mark",
                              json={"reason": "signed_outside_dealgate", "marked_on": "2026-10-01",
                                    "note": "Signed NDA is with Legal"})
        assert first.status_code == 200, first.text
        card = first.json()
        assert card["state"] == "covered" and card["source_label"] == "Marked covered"
        assert card["mark"] == {"reason": "signed_outside_dealgate", "note": "Signed NDA is with Legal",
                                "marked_on": "2026-10-01", "marked_by": "Lee Legal", "source": "dealgate",
                                "hubspot_value": None, "reason_label": "Signed outside DealGate"}
        second = await api.put(f"/clients/{cobalt}/agreements/NDA/mark",
                               json={"reason": "confirmed_with_client", "marked_on": TODAY.isoformat()})
        assert second.status_code == 200 and second.json()["mark"]["reason"] == "confirmed_with_client"
        removed = await api.delete(f"/clients/{cobalt}/agreements/NDA/mark")
        assert removed.status_code == 200 and removed.json()["state"] == "missing"
        assert (await api.delete(f"/clients/{cobalt}/agreements/NDA/mark")).status_code == 404
        assert (await api.post(f"/clients/{cobalt}/agreements/NDA/client-copy", **upload("n.pdf", PDF))).status_code == 201
        held = await api.put(f"/clients/{cobalt}/agreements/NDA/mark",
                             json={"reason": "other", "marked_on": TODAY.isoformat()})
        assert held.status_code == 409
    marks = (await session.scalars(select(AgreementMark).where(AgreementMark.client_id == cobalt))).all()
    assert len(marks) == 2 and all(m.removed_at is not None for m in marks)  # kept in history
    assert [a.after["reason"] for a in await audit_rows(session, agreement_audit.MARKED)] == [
        "signed_outside_dealgate", "confirmed_with_client"]
    assert len(await audit_rows(session, agreement_audit.MARK_REMOVED)) == 1


async def test_a_client_copy_takes_the_place_of_a_mark(session, seeded):
    cobalt = seeded.clients["cobalt"]
    async with client_for(session, LEGAL) as api:
        await api.put(f"/clients/{cobalt}/agreements/MSA/mark", json={"reason": "other", "marked_on": "2026-10-02"})
        card = (await api.post(f"/clients/{cobalt}/agreements/MSA/client-copy", **upload("msa.pdf", PDF))).json()
    assert card["state"] == "client" and card["mark"] is None
    assert [h["what"] for h in card["history"]][:1] in (["Client copy uploaded: msa.pdf"], ["Mark removed"])
    assert {h["what"] for h in card["history"]} == {"Client copy uploaded: msa.pdf", "Mark removed",
                                                   "Marked covered: Other"}
    uploaded = (await audit_rows(session, agreement_audit.CLIENT_UPLOADED))[-1]
    assert uploaded.before["mark"]["reason"] == "other"


async def test_detaching_a_standard_keeps_the_shared_object_and_a_client_copy_starts_a_job(session, seeded):
    storage = StubS3(bucket=BUCKET)
    atlas, beacon = seeded.clients["atlas"], seeded.clients["beacon"]
    standard_key = seeded.standards["NDA"].file_key
    async with client_for(session, ADMIN, storage) as api:
        for client_id in (atlas, beacon):
            await api.post(f"/clients/{client_id}/agreements/NDA/attach-standard")
        detached = await api.delete(f"/clients/{beacon}/agreements/NDA")
        assert detached.status_code == 200, detached.text
        assert detached.json()["state"] == "existing_none"
        assert await session.scalar(select(func.count()).select_from(DeletionJob)) == 0
        # Atlas's client copy keeps the standard version in its history; detaching it must not queue that key.
        await api.post(f"/clients/{atlas}/agreements/NDA/client-copy", **upload("own.pdf", PDF))
        job = await api.delete(f"/clients/{atlas}/agreements/NDA")
        assert job.status_code == 202, job.text
        assert job.json()["source_deleted"] is True and "job_id" in job.json()
        assert (await api.delete(f"/clients/{atlas}/agreements/NDA")).status_code == 404
    queued = (await session.scalars(select(DeletionJob))).one()
    assert [item["key"] for item in queued.objects] == [k for k in storage.objects]  # only the client copy
    assert standard_key not in {item["key"] for item in queued.objects}
    assert await key_is_referenced(session, BUCKET, standard_key)  # the last holder is gone; the standard stays
    detached_rows = await audit_rows(session, agreement_audit.DETACHED)
    deleted_rows = await audit_rows(session, agreement_audit.DELETED)
    assert detached_rows[0].after == {"client_id": str(beacon), "client_name": "Beacon Logistics", "kind": "NDA",
                                      "filename": "SmarTek21_Standard_NDA.pdf", "version_no": 1,
                                      "source": "standard", "standard_version": 1, "batch": None}
    assert deleted_rows[0].after["client_name"] == "Atlas Foods" and deleted_rows[0].after["kind"] == "NDA"
    assert agreement_audit.activity_text(deleted_rows[0].action, deleted_rows[0].after,
                                         deleted_rows[0].before) == "Removed NDA file from Atlas Foods"


async def test_downloads_are_audited_and_marks_have_no_file(session, seeded):
    storage = StubS3(bucket=BUCKET)
    cobalt = seeded.clients["cobalt"]
    async with client_for(session, LEGAL, storage) as api:
        await api.post(f"/clients/{cobalt}/agreements/NDA/client-copy", **upload("nda.pdf", PDF))
        await api.put(f"/clients/{cobalt}/agreements/MSA/mark", json={"reason": "other", "marked_on": "2026-10-03"})
    async with client_for(session, SALES, storage) as api:
        link = await api.get(f"/clients/{cobalt}/agreements/NDA/download")
        none = await api.get(f"/clients/{cobalt}/agreements/MSA/download")
    assert link.status_code == 200, link.text
    assert link.json()["expires_in_seconds"] == 300 and link.json()["file_name"] == "nda.pdf"
    assert link.json()["url"].startswith(f"https://{BUCKET}.local/get/agreements/")
    assert none.status_code == 404
    (row,) = await audit_rows(session, agreement_audit.DOWNLOADED)
    assert row.actor_id == SALES.id
    assert row.after == {"client_id": str(cobalt), "client_name": "Cobalt Systems", "kind": "NDA",
                         "filename": "nda.pdf", "version_no": 1, "source": "client", "standard_version": None,
                         "batch": None}


async def test_relationship_is_changed_by_hand_and_saving_the_same_value_writes_nothing(session, seeded):
    cobalt = seeded.clients["cobalt"]
    async with client_for(session, LEGAL) as api:
        # Before the cutover the shown value is live (provisional): saving the same word stores it by hand.
        confirmed = await api.put(f"/clients/{cobalt}/relationship", json={"relationship": "net_new"})
        assert confirmed.status_code == 200, confirmed.text
        assert (confirmed.json()["relationship"], confirmed.json()["relationship_basis"]) == ("net_new", "manual")
        assert len(await audit_rows(session, agreement_audit.RELATIONSHIP_CHANGED)) == 1
        # Saving the stored manual value again changes nothing and writes nothing.
        same = await api.put(f"/clients/{cobalt}/relationship", json={"relationship": "net_new"})
        assert same.status_code == 200 and same.json()["relationship"] == "net_new"
        assert len(await audit_rows(session, agreement_audit.RELATIONSHIP_CHANGED)) == 1
        changed = await api.put(f"/clients/{cobalt}/relationship",
                                json={"relationship": "existing", "note": "Duplicate of Atlas"})
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert (body["relationship"], body["relationship_basis"], body["relationship_set_by"]) == (
        "existing", "manual", "Lee Legal")
    assert body["basis_text"] == "Marked existing by Lee Legal"
    assert (body["requirement"], body["needs_attention"], body["nda"]["state"]) == ("none", False, "existing_none")
    first, row = await audit_rows(session, agreement_audit.RELATIONSHIP_CHANGED)
    assert (first.before["relationship"], first.after["relationship"]) == (None, "net_new")
    assert (row.entity, row.entity_id, row.before["relationship"]) == ("client", str(cobalt), "net_new")
    assert row.after["note"] == "Duplicate of Atlas"
    assert agreement_audit.activity_text(row.action, row.after, row.before) == "Changed Cobalt Systems to existing"


# --- B11: roles on the server -----------------------------------------------------------------


async def test_writes_are_refused_on_the_server_for_read_only_roles(session, seeded):
    storage = StubS3(bucket=BUCKET)
    cobalt = seeded.clients["cobalt"]
    before = await session.scalar(select(func.count()).select_from(AuditEvent))
    async with client_for(session, SALES, storage) as api:
        calls = [
            api.post(f"/clients/{cobalt}/agreements/NDA/client-copy", **upload("n.pdf", PDF)),
            api.post(f"/clients/{cobalt}/agreements/NDA/attach-standard"),
            api.put(f"/clients/{cobalt}/agreements/NDA/mark", json={"reason": "other", "marked_on": "2026-10-01"}),
            api.delete(f"/clients/{cobalt}/agreements/NDA/mark"),
            api.delete(f"/clients/{cobalt}/agreements/NDA"),
            api.put(f"/clients/{cobalt}/relationship", json={"relationship": "existing"}),
            api.post("/agreements", data={"client_id": str(cobalt), "kind": "NDA"},
                     files={"file": ("n.pdf", PDF, "application/pdf")}),
            api.post("/agreements/batches", json={"kinds": ["NDA"]}),
            api.post("/agreements/batches/AG-0001/undo"),
        ]
        statuses = [(await call).status_code for call in calls]
    assert statuses == [403] * len(statuses)
    async with client_for(session, LEGAL, storage) as api:
        assert (await api.post("/agreements/batches", json={"kinds": ["NDA"]})).status_code == 403
        assert (await api.post("/agreements/batches/AG-0001/undo")).status_code == 403
        assert (await api.get("/agreements/batches")).status_code == 200
    assert storage.objects == {}
    assert await session.scalar(select(func.count()).select_from(AuditEvent)) == before


# --- legacy routes ----------------------------------------------------------------------------


async def test_legacy_upload_of_a_held_kind_adds_a_version_and_detach_follows_the_source(session, seeded):
    storage = StubS3(bucket=BUCKET)
    atlas, cobalt = seeded.clients["atlas"], seeded.clients["cobalt"]
    async with client_for(session, LEGAL, storage) as api:
        first = await api.post("/agreements", data={"client_id": str(cobalt), "kind": "NDA"},
                               files={"file": ("one.pdf", PDF, "application/pdf")})
        second = await api.post("/agreements", data={"client_id": str(cobalt), "kind": "nda"},
                                files={"file": ("two.pdf", PDF, "application/pdf")})
        assert (first.status_code, second.status_code) == (201, 201), second.text
        assert second.json()["id"] == first.json()["id"] and second.json()["version_no"] == 2
        attached = (await api.post(f"/clients/{atlas}/agreements/MSA/attach-standard")).json()
        listed = (await api.get(f"/agreements?client_id={atlas}")).json()["items"]
        assert [(r["source"], r["standard_version"], r["batch_id"]) for r in listed] == [("standard", 1, None)]
        versions = (await api.get(f"/agreements/{first.json()['id']}/versions")).json()["items"]
        assert [(v["version_no"], v["source"]) for v in versions] == [(2, "client"), (1, "client")]
        legacy_link = await api.get(f"/agreements/{first.json()['id']}/versions/1/download")
        assert legacy_link.status_code == 200 and legacy_link.json()["filename"] == "one.pdf"
        removed = await api.delete(f"/agreements/{attached['agreement_id']}")
        assert removed.status_code == 200 and removed.json()["state"] == "existing_none"
        started = await api.delete(f"/agreements/{first.json()['id']}")
        assert started.status_code == 202 and started.json()["status"] == "pending"
    assert len(await audit_rows(session, agreement_audit.DOWNLOADED)) == 1
    assert {k for item in (await session.scalars(select(DeletionJob))).one().objects for k in [item["key"]]} == set(
        storage.objects)


# --- deletion fixes ---------------------------------------------------------------------------


async def test_a_client_with_marks_and_a_standard_copy_can_be_deleted(session, seeded):
    from app.services.parent_deletion import request_client_deletion

    storage = StubS3(bucket=BUCKET)
    client = Client(name="Local only client")  # no HubSpot company: deletable
    session.add(client)
    await session.commit()
    async with client_for(session, ADMIN, storage) as api:
        await api.post(f"/clients/{client.id}/agreements/NDA/attach-standard")
        await api.put(f"/clients/{client.id}/agreements/MSA/mark", json={"reason": "other", "marked_on": "2026-10-01"})
        await api.delete(f"/clients/{client.id}/agreements/MSA/mark")
        await api.put(f"/clients/{client.id}/agreements/MSA/mark", json={"reason": "other", "marked_on": "2026-10-02"})
    job = await request_client_deletion(session, actor_id=ADMIN.id, client_id=client.id)
    await session.commit()
    assert job.summary["counts"]["agreement_marks"] == 2 and job.summary["counts"]["agreements"] == 1
    assert job.objects == []  # the standard key is shared: never queued
    assert await session.get(Client, client.id) is None
    assert await key_is_referenced(session, BUCKET, seeded.standards["NDA"].file_key)
    assert await session.scalar(select(func.count()).select_from(AgreementFileVersion).join(
        Agreement, Agreement.id == AgreementFileVersion.agreement_id).where(Agreement.client_id == client.id)) == 0


# --- T13 (my routes): statements per call ---------------------------------------------------------


async def test_statements_per_call_for_the_panel_the_dry_run_and_a_write(session, seeded, engine):  # noqa: F811
    from sqlalchemy import event

    seen: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
            seen.append(statement)

    async def measure(call) -> int:
        seen.clear()
        event.listen(engine.sync_engine, "before_cursor_execute", count)
        try:
            response = await call
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", count)
        assert response.status_code < 300, response.text
        return len(seen)

    cobalt = seeded.clients["cobalt"]
    async with client_for(session, ADMIN) as api:
        panel = await measure(api.get(f"/clients/{cobalt}/agreements"))
        dry_run = await measure(api.post("/agreements/batches", json={"kinds": ["NDA", "MSA"],
                                                                      "include_net_new_past_stage_1": True}))
        attach = await measure(api.post(f"/clients/{cobalt}/agreements/NDA/attach-standard"))
    print(f"T13 statements: panel={panel} dry_run={dry_run} attach_standard={attach}")
    # reader (1) + the shared population (7) + history (2); the dry run has no history.
    assert panel <= 10 and dry_run <= 8
    assert attach <= 30
