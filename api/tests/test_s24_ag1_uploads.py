"""S24-AG1 T3 (lane T-A) — the upload rules, through every upload route.

Lanes BE-A and BE-B already send the classic refusals and five awkward names to the client-copy and
standard routes (test_s24_ag1_bea_standard.py, test_s24_ag1_beb_client.py). This file adds what they leave
out, all through the HTTP routes with StubS3 as storage:

* the legacy ``POST /agreements`` and ``POST /agreements/{id}/replace`` under the same file and note rules,
  and three refusals no lane sends (a zip that is not a Word file, "%PDF" without its dash, ``.pdf.exe``);
* review findings #92 (repeated extensions with a gap) and #93 (hidden characters), including raw C0
  controls that a hostile client can put in a hand-built multipart body: the stored key and the display
  name the API returns;
* the browser's content type is never trusted, either way: a real PDF called text/plain is stored as a PDF,
  a .txt or a fake PDF called application/pdf is refused (D3/D14 found a header-only check);
* the exact key shapes and the per-upload nonce on every route;
* a client copy over a standard copy that three clients hold, by the new route and by the legacy replace;
* the compensating delete when the COMMIT itself fails (the earlier tests fail the audit write instead);
* the 25 MiB boundary and the 200-character note boundary.

Small helpers here (seed, client_for, upload_via, counts) are reused by the other lane T-A files.
SQLite with foreign keys on.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.agreements import AgreementBatch, AgreementMark, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers import agreements as legacy_routes
from app.routers import agreements_hubspot, agreements_workspace, client_agreements
from app.services import agreement_audit
from app.services.agreement_files import MAX_BYTES, MSG_EMPTY, MSG_NOT_DOCX, MSG_NOT_PDF, MSG_TOO_LARGE, MSG_TYPE
from app.services.deletion_cleanup import process_deletion_jobs
from app.services.hubspot_owners import HubspotOwner  # noqa: F401 — registers the table for create_all
from app.services.hubspot_properties import HubspotPropertyMapping  # noqa: F401 — same

NOW = datetime(2026, 10, 15, 19, 0, tzinfo=UTC)  # 12:00 in Los Angeles
TODAY = date(2026, 10, 15)
BUCKET = "stub-agreements-lane-ta"
PIPELINE_ID = "ta-pipeline"
STAGES = (  # stage id, label, display order, closed (the staging shape)
    ("ta-s1", "1-Initial Contact/Prospecting", 0, False),
    ("ta-s2", "2-Qualification", 1, False),
    ("ta-s3", "3-Requirement/Fit Gap Analysis", 2, False),
    ("ta-s4", "4-Proposal", 3, False),
    ("ta-s5", "5-Negotiation", 4, False),
    ("ta-s6", "6-Contracting/Drive Commitment", 5, False),
    ("ta-s7", "7-Closed Won", 6, True),
    ("ta-s8", "8-Closed Lost", 7, True),
    ("ta-s9", "Hold", 8, False),
)
ADMIN = AuthUser(uuid.UUID("7a000000-0000-4000-8000-0000000000a1"), "tess.admin@example.test", "Tess Admin",
                 ("SystemAdmin",))
LEGAL = AuthUser(uuid.UUID("7a000000-0000-4000-8000-0000000000b2"), "lena.legal@example.test", "Lena Legal",
                 ("Legal",))
SALES = AuthUser(uuid.UUID("7a000000-0000-4000-8000-0000000000c3"), "sid.sales@example.test", "Sid Sales",
                 ("Sales",))
E2E = AuthUser(uuid.UUID("7a000000-0000-4000-8000-0000000000e2"), "lane-bot@example.test", "Lane Bot",
               ("SystemAdmin", "officeapp-e2e"))
# key -> (name, deal stage positions: 1-6 open, 7 Closed Won, 8 Closed Lost, 9 Hold). Synthetic names.
CLIENTS: dict[str, tuple[str, list[int]]] = {
    "arden": ("Arden Foods", [7]),  # existing (Closed Won)
    "birch": ("Birch Logistics", [7, 4]),  # existing (Closed Won, another deal open)
    "cinder": ("Cinder Systems", [3]),  # net new, past stage 1
    "dorado": ("Dorado Farms", [1]),  # net new, stage 1 only
    "elm": ("Elm Retail", [5]),  # net new, past stage 1
    "garnet": ("Garnet Media", []),  # net new, nothing needed
    "heron": ("Heron Labs", [2, 8]),  # net new, past stage 1
}
PDF = b"%PDF-1.4\n% synthetic lane T-A agreement\n" + b"0" * 64
DOCX = b"PK\x03\x04\x14\x00" + b"\x00" * 62
STAMP_NONCE = r"(?P<stamp>\d{8}T\d{6}Z)-(?P<nonce>[0-9a-f]{8})-(?P<name>[^/\\]+)"
STANDARD_KEY = re.compile(rf"agreements/standard/(?P<kind>NDA|MSA)/{STAMP_NONCE}")
SAFE_STORED = re.compile(r"[A-Za-z0-9._\- ]+")
HIDDEN = frozenset({"Cc", "Cf", "Zl", "Zp"})


def client_key(agreement_id) -> re.Pattern:
    return re.compile(rf"agreements/{agreement_id}/{STAMP_NONCE}")


def fixture_key(run_id, agreement_id) -> re.Pattern:
    return re.compile(rf"agreements/e2e/{run_id}/{agreement_id}/{STAMP_NONCE}")


def body_for(name: str) -> bytes:
    return DOCX if name.lower().endswith(".docx") else PDF


@dataclass
class World:
    storage: StubS3
    clients: dict[str, uuid.UUID] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    standard_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    standard_keys: dict[str, str] = field(default_factory=dict)
    standard_files: dict[str, str] = field(default_factory=dict)


def deal(client_id: uuid.UUID, position: int, n: str, *, region: str | None = None,
         msa_type: str | None = None) -> Opportunity:
    sid, label, order, _closed = STAGES[position - 1]
    return Opportunity(
        source="hubspot", hubspot_deal_id=f"ta-hs-{n}", name=f"Deal {n}", client_id=client_id,
        hubspot_pipeline_id=PIPELINE_ID, hubspot_stage_id=sid, stage_label=label, sales_stage=label,
        stage_order=order, is_closed_won=position == 7, is_closed_lost=position == 8,
        close_date=TODAY - timedelta(days=90) if position in (7, 8) else TODAY + timedelta(days=30),
        governance_status="Intake", amount=Decimal("1000"), currency="USD", hubspot_last_modified_at=NOW,
        business_unit_value=region, business_unit_mapping_version=1 if region else None,
        business_unit_observed_at=NOW if region else None, hubspot_msa_type=msa_type)


async def seed_world(session, storage: StubS3 | None = None, *, users=(ADMIN, LEGAL, SALES),
                     clients: dict[str, tuple[str, list[int]]] | None = None,
                     standards: tuple[str, ...] = ("NDA", "MSA")) -> World:
    """Users (provisioned exactly as their tokens say, so ensure_user writes nothing), the staging stage
    mirror, the clients and their HubSpot deals, and the standard NDA and MSA v1 with their stored objects."""
    world = World(storage=storage or StubS3(bucket=BUCKET))
    for user in users:
        session.add(User(id=user.id, email=user.email, name=user.name, groups=list(user.groups)))
    session.add(HubspotPipeline(id=PIPELINE_ID, label="Lane T-A Pipeline", display_order=0, archived=False))
    await session.flush()
    session.add_all([HubspotStage(id=sid, pipeline_id=PIPELINE_ID, label=label, display_order=order,
                                  is_closed=closed, probability=Decimal("0.10"), archived=False)
                     for sid, label, order, closed in STAGES])
    for key, (name, positions) in (clients if clients is not None else CLIENTS).items():
        client = Client(name=name, hubspot_company_id=f"ta-c-{key}")
        session.add(client)
        await session.flush()
        world.clients[key], world.names[key] = client.id, name
        session.add_all([deal(client.id, position, f"{key}-{i}") for i, position in enumerate(positions)])
    for kind in standards:
        file_name = f"Lane Standard {kind}.pdf"
        file_key = f"agreements/standard/{kind}/20261001T120000Z-5a5a5a5a-Lane Standard {kind}.pdf"
        standard = StandardAgreement(kind=kind, version_no=1, file_key=file_key, filename=file_name,
                                     file_size=len(PDF), sha256="c" * 64, uploaded_by=ADMIN.id,
                                     uploaded_at=NOW - timedelta(days=14))
        session.add(standard)
        await session.flush()
        world.storage.objects[file_key] = PDF
        world.standard_ids[kind], world.standard_keys[kind], world.standard_files[kind] = (
            standard.id, file_key, file_name)
    await session.commit()
    return world


async def _noop_launcher(batch_id, phase):  # noqa: ARG001
    return None


@asynccontextmanager
async def client_for(session, user: AuthUser, storage: StubS3, launcher=None):
    """The four agreement routers in main.py's order, the caller's token, this session and StubS3."""
    app = FastAPI()
    for router in (agreements_workspace.router, agreements_hubspot.router, legacy_routes.router,
                   client_agreements.router):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    app.dependency_overrides[get_evidence_s3] = lambda: storage
    app.dependency_overrides[legacy_routes.get_batch_launcher] = lambda: launcher or _noop_launcher
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://lane-ta") as api:
        yield api


def raw_multipart(name: str, content: bytes, fields: dict[str, str] | None = None) -> dict:
    """A hand-built multipart body. A browser (and httpx) percent-encodes C0 controls in a file name; a
    hostile client does not, so this sends the name's characters as they are."""
    boundary = f"ta-{uuid.uuid4().hex}"
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
             for key, value in (fields or {}).items()]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return {"content": b"".join(parts), "headers": {"Content-Type": f"multipart/form-data; boundary={boundary}"}}


async def upload_via(api, route: str, target: dict, name: str, content: bytes, note: str | None = None,
                     raw: bool = False, content_type: str = "application/octet-stream"):
    """One upload through ``route``: client_copy, legacy_create, legacy_replace or standard. ``content_type``
    is what the browser claims (never trusted)."""
    fields: dict[str, str] = {}
    if route == "client_copy":
        url = f"/clients/{target['client_id']}/agreements/{target['kind']}/client-copy"
    elif route == "legacy_create":
        url, fields = "/agreements", {"client_id": str(target["client_id"]), "kind": target["kind"]}
    elif route == "legacy_replace":
        url, fields = f"/agreements/{target['agreement_id']}/replace", {"expected_version": str(target["version"])}
    elif route == "standard":
        url = f"/agreements/standard/{target['kind']}"
    else:
        raise AssertionError(route)
    if note is not None:
        fields["note"] = note
    if raw:
        return await api.post(url, **raw_multipart(name, content, fields))
    return await api.post(url, data=fields, files={"file": (name, content, content_type)})


def shown(route: str, body: dict) -> str:
    """The display name in the route's response (AgreementRow.filename on the legacy routes)."""
    return body["filename"] if route.startswith("legacy") else body["file_name"]


async def target_for(api, world: World, route: str) -> dict:
    """Where ``route`` uploads in these tests. The legacy replace first needs a copy to replace."""
    if route == "client_copy":
        return {"client_id": world.clients["cinder"], "kind": "NDA"}
    if route == "legacy_create":
        return {"client_id": world.clients["heron"], "kind": "MSA"}
    if route == "standard":
        return {"kind": "MSA"}
    first = await upload_via(api, "client_copy", {"client_id": world.clients["elm"], "kind": "NDA"},
                             "elm-first.pdf", PDF)
    assert first.status_code == 201, first.text
    return {"agreement_id": first.json()["agreement_id"], "version": 1}


def advance(target: dict, route: str, body: dict) -> None:
    """After a successful replace, the next one names the new version."""
    if route == "legacy_replace":
        target["version"] = body["version_no"]


COUNTED = (Agreement, AgreementFileVersion, AgreementMark, StandardAgreement, AgreementBatch, AuditEvent,
           DeletionJob, User)


async def counts(session) -> dict[str, int]:
    return {model.__tablename__: int(await session.scalar(select(func.count()).select_from(model)))
            for model in COUNTED}


def check_stored_name(name: str) -> None:
    """Letters, digits, dot, dash, underscore and space; at most 80 before exactly one extension."""
    assert SAFE_STORED.fullmatch(name), repr(name)
    base, dot, ext = name.rpartition(".")
    assert dot and ext in ("pdf", "docx"), repr(name)
    assert not re.search(r"\.(pdf|docx)$", base, re.IGNORECASE), repr(name)
    assert 0 < len(base) <= 80 and base == base.strip(" ."), repr(name)


def check_display_name(name: str) -> None:
    assert name and name == name.strip(), repr(name)
    assert not any(unicodedata.category(ch) in HIDDEN for ch in name), repr(name)
    assert "/" not in name and "\\" not in name and len(name) <= 255, repr(name)


def check_stamp(stamp: str) -> None:
    at = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    assert abs(datetime.now(UTC) - at) < timedelta(minutes=10), stamp


def new_key(storage: StubS3, before: set[str]) -> str:
    (key,) = set(storage.objects) - before
    return key


class StubVersions:
    """The deletion-cleanup worker's view of StubS3 (one version per key)."""

    def __init__(self, stub: StubS3):
        self.stub = stub

    def get_paginator(self, name):
        assert name == "list_object_versions"
        return self

    def paginate(self, *, Bucket, Prefix):  # noqa: N803 — boto3's names
        assert Bucket == self.stub.bucket
        return [{"Versions": [{"Key": k, "VersionId": "v1"} for k in self.stub.objects if k.startswith(Prefix)],
                 "DeleteMarkers": []}]

    def delete_objects(self, *, Bucket, Delete):  # noqa: N803
        assert Bucket == self.stub.bucket
        for item in Delete["Objects"]:
            self.stub.objects.pop(item["Key"], None)
        return {}


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
async def world(session, env) -> World:
    return await seed_world(session)


# --- the file rules on every route ------------------------------------------------------------------------

ROUTES = ("client_copy", "legacy_create", "legacy_replace", "standard")
BIG = object()  # 26 MiB behind a %PDF- prefix, built in the test rather than held by the collection
# Refusals no earlier lane sends: a zip that is not a Word document (end-of-archive record, not a local file
# header), a PDF signature missing its dash, an executable named .pdf.exe.
NEW_REFUSALS = (
    ("zip-not-docx", "contract.docx", b"PK\x05\x06" + b"\x00" * 18, 415, MSG_NOT_DOCX),
    ("pdf-without-dash", "contract.pdf", b"%PDF1.7 the dash is missing", 415, MSG_NOT_PDF),
    ("pdf-exe", "contract.pdf.exe", PDF, 415, MSG_TYPE),
)
# The directive's set, sent to the legacy routes (the earlier lanes cover the client-copy and standard routes).
EVERY_REFUSAL = (
    ("text-named-pdf", "contract.pdf", b"just some text, not a PDF", 415, MSG_NOT_PDF),
    ("pdf-named-docx", "contract.docx", b"%PDF-1.4 a PDF named docx", 415, MSG_NOT_DOCX),
    ("txt", "contract.txt", PDF, 415, MSG_TYPE),
    ("no-extension", "contract", PDF, 415, MSG_TYPE),
    ("empty", "contract.pdf", b"", 422, MSG_EMPTY),
    ("26-mib", "big.pdf", BIG, 413, MSG_TOO_LARGE),
)
REFUSAL_CASES = [pytest.param(route, *case[1:], id=f"{route}-{case[0]}")
                 for route in ROUTES for case in NEW_REFUSALS] + [
    pytest.param(route, *case[1:], id=f"{route}-{case[0]}")
    for route in ("legacy_create", "legacy_replace") for case in EVERY_REFUSAL]


@pytest.mark.parametrize(("route", "name", "content", "status", "message"), REFUSAL_CASES)
async def test_file_rules_refuse_on_every_upload_route(session, world, route, name, content, status, message):
    if content is BIG:
        content = b"%PDF-" + bytes(26 * 1024 * 1024)
    async with client_for(session, LEGAL, world.storage) as api:
        target = await target_for(api, world, route)
        objects, before = set(world.storage.objects), await counts(session)
        response = await upload_via(api, route, target, name, content)
    assert response.status_code == status, response.text
    assert response.json()["detail"] == message
    # Refused before anything is stored: no object, no row, no version, no audit row, no cleanup job.
    assert set(world.storage.objects) == objects
    assert await counts(session) == before


async def test_exactly_25_mib_is_accepted_and_one_byte_more_is_refused(session, world):
    assert MAX_BYTES == 25 * 1024 * 1024  # the directive's cap, pinned to a literal (not only the product constant)
    exact = b"%PDF-" + bytes(25 * 1024 * 1024 - 5)
    target = {"client_id": world.clients["cinder"], "kind": "NDA"}
    async with client_for(session, LEGAL, world.storage) as api:
        objects = set(world.storage.objects)
        over = await upload_via(api, "client_copy", target, "over.pdf", exact + b"x")
        assert over.status_code == 413 and over.json()["detail"] == MSG_TOO_LARGE
        assert set(world.storage.objects) == objects
        accepted = await upload_via(api, "client_copy", target, "exact.pdf", exact)
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["file_size"] == MAX_BYTES == len(world.storage.objects[new_key(world.storage, objects)])


# --- names: review findings #92 and #93, path characters, length, markup ---------------------------------

# (name sent, stored name after the stamp and nonce, display name returned). Every one survives multipart
# transport unchanged (a browser percent-encodes only C0 controls, quotes and backslashes).
GAP_AND_HIDDEN = (
    ("x.pdf .pdf", "x.pdf", "x.pdf .pdf"),
    ("x.docx .pdf", "x.pdf", "x.docx .pdf"),
    ("x.pdf..pdf", "x.pdf", "x.pdf..pdf"),
    ("Arden_MSA.docx .pdf", "Arden_MSA.pdf", "Arden_MSA.docx .pdf"),
    ("x .PDF. .pdf", "x.pdf", "x .PDF. .pdf"),
    ("x.pdf.pdf.pdf", "x.pdf", "x.pdf.pdf.pdf"),
    ("a\u0085b.pdf", "a_b.pdf", "a b.pdf"),  # C1 next line: whitespace, kept apart
    ("a\u0080b.pdf", "ab.pdf", "ab.pdf"),  # C1 control: removed
    ("a\u061cb.pdf", "ab.pdf", "ab.pdf"),  # Arabic letter mark
    ("a\u2028b.pdf", "a b.pdf", "a b.pdf"),  # line separator becomes a space
    ("a\u2029b.pdf", "a b.pdf", "a b.pdf"),  # paragraph separator becomes a space
    ("x\u200b.pdf", "x.pdf", "x.pdf"),  # zero-width space
    ("\ufeffbom.pdf", "bom.pdf", "bom.pdf"),  # byte order mark
    ("\u202eevil\u202c.pdf", "evil.pdf", "evil.pdf"),  # right-to-left override
    ("Arden\u200d\u2066NDA\u2069.pdf", "ArdenNDA.pdf", "ArdenNDA.pdf"),  # joiner and isolates
    ("a\u00a0\u00a0b.pdf", "a_b.pdf", "a b.pdf"),  # no-break spaces
)
# Raw C0 controls and DEL, only possible from a hand-built request.
RAW_CONTROLS = (
    ("tab\tname.pdf", "tab_name.pdf", "tab name.pdf"),
    ("x.pdf\t.pdf", "x.pdf", "x.pdf .pdf"),
    ("a\x1fb.pdf", "a_b.pdf", "a b.pdf"),
    ("a\x00b.pdf", "ab.pdf", "ab.pdf"),
    ("a\x1bb.pdf", "ab.pdf", "ab.pdf"),
    ("a\x7fb.pdf", "ab.pdf", "ab.pdf"),
)
# On the routes the earlier lanes did not send these to (they covered the client-copy route).
PATH_LENGTH_MARKUP = (
    ("../../a\\b.pdf", "b.pdf", "b.pdf"),
    ("..\\..\\Windows\\System32\\nda.pdf", "nda.pdf", "nda.pdf"),
    ("/etc/agreements/passwd.pdf", "passwd.pdf", "passwd.pdf"),
    ("C:\\Users\\me\\NDA final.docx", "NDA final.docx", "NDA final.docx"),
    ("x.pdf.pdf", "x.pdf", "x.pdf.pdf"),
    ("<img src=x onerror=alert(document.cookie)>.pdf", "_img src_x onerror_alert_document.cookie_.pdf",
     "<img src=x onerror=alert(document.cookie)>.pdf"),
    ("a" * 300 + ".pdf", "a" * 80 + ".pdf", "a" * 251 + ".pdf"),
)


def key_pattern(route: str, target: dict, body: dict) -> re.Pattern:
    if route == "standard":
        return STANDARD_KEY
    agreement_id = body["agreement_id"] if route == "client_copy" else body["id"]
    if route == "legacy_replace":
        assert agreement_id == target["agreement_id"]
    return client_key(agreement_id)


async def send_names(session, world: World, route: str, vectors, *, raw: bool = False) -> list[str]:
    """Upload every vector through ``route``; check the stored key and the returned display name."""
    shown_names: list[str] = []
    async with client_for(session, LEGAL, world.storage) as api:
        target = await target_for(api, world, route)
        for name, stored, display in vectors:
            objects = set(world.storage.objects)
            response = await upload_via(api, route, target, name, body_for(stored), raw=raw)
            assert response.status_code in (200, 201), (repr(name), response.text)
            body = response.json()
            key = new_key(world.storage, objects)
            match = key_pattern(route, target, body).fullmatch(key)
            assert match, (repr(name), key)
            assert match["name"] == stored, (repr(name), key)
            check_stored_name(match["name"])
            check_stamp(match["stamp"])
            assert shown(route, body) == display, repr(name)  # the original, verbatim (escaped on screen)
            check_display_name(shown(route, body))
            shown_names.append(display)
            advance(target, route, body)
    return shown_names


@pytest.mark.parametrize("route", ["client_copy", "legacy_create", "legacy_replace", "standard"])
async def test_repeated_extensions_and_hidden_characters_through_the_route(session, world, route):
    displays = await send_names(session, world, route, GAP_AND_HIDDEN)
    async with client_for(session, SALES, world.storage) as api:
        if route == "standard":
            listed = (await api.get("/agreements/standard")).json()["MSA"]
            link = (await api.get("/agreements/standard/MSA/download")).json()
            assert listed["file_name"] == link["file_name"] == displays[-1]
            assert listed["version"] == len(GAP_AND_HIDDEN) + 1
            return
        key = "heron" if route == "legacy_create" else "elm" if route == "legacy_replace" else "cinder"
        kind = "MSA" if route == "legacy_create" else "NDA"
        client_id = world.clients[key]
        panel = (await api.get(f"/clients/{client_id}/agreements")).json()[kind.lower()]
        documents = (await api.get("/agreements/documents", params={"q": world.names[key]})).json()["items"]
        link = (await api.get(f"/clients/{client_id}/agreements/{kind}/download")).json()
        versions = (await api.get(f"/agreements/{panel['agreement_id']}/versions")).json()["items"]
    # The Documents tab, the panel, the download link and every version keep the display name.
    assert panel["file_name"] == link["file_name"] == displays[-1]
    assert [d["file_name"] for d in documents if d["kind"] == kind] == [displays[-1]]
    assert [v["filename"] for v in versions][: len(displays)] == displays[::-1]


@pytest.mark.parametrize("route", ["client_copy", "legacy_replace", "standard"])
async def test_raw_control_characters_from_a_hand_built_request(session, world, route):
    await send_names(session, world, route, RAW_CONTROLS, raw=True)


@pytest.mark.parametrize("route", ["legacy_create", "legacy_replace", "standard"])
async def test_path_characters_long_names_and_markup_on_the_other_routes(session, world, route):
    await send_names(session, world, route, PATH_LENGTH_MARKUP)
    # Nothing after the fixed prefix adds a folder: every key has exactly its prefix's slashes, no backslash.
    for key in world.storage.objects:
        assert key.count("/") == (3 if key.startswith("agreements/standard/") else 2), key
        assert "\\" not in key and ".." not in key.split("/"), key


# --- the browser's content type is never trusted -------------------------------------------------------------

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class RecordingS3(StubS3):
    """StubS3 that also records the content type each object was stored with."""

    def __init__(self, bucket: str) -> None:
        super().__init__(bucket=bucket)
        self.content_types: dict[str, str] = {}

    def put_object_at(self, key: str, content_type: str, body: bytes) -> str:
        stored = super().put_object_at(key, content_type, body)
        self.content_types[key] = content_type
        return stored


# (name, bytes, the content type the browser claims, status, detail or the content type stored)
CLAIMS = (
    ("signed.pdf", PDF, "text/plain", 201, "application/pdf"),  # a real PDF the browser calls text
    ("signed.docx", DOCX, "application/pdf", 201, DOCX_TYPE),  # a real Word file the browser calls a PDF
    ("notes.txt", PDF, "application/pdf", 415, MSG_TYPE),  # PDF bytes and a PDF claim do not make .txt a PDF
    ("notes.pdf", b"plain text pretending", "application/pdf", 415, MSG_NOT_PDF),
    ("macro.docx", b"MZ\x90\x00 an executable", DOCX_TYPE, 415, MSG_NOT_DOCX),
)


@pytest.mark.parametrize("route", ROUTES)
async def test_the_browser_content_type_is_never_trusted(session, env, route):
    world = await seed_world(session, RecordingS3(BUCKET))
    storage = world.storage
    async with client_for(session, LEGAL, storage) as api:
        target = await target_for(api, world, route)
        for name, content, claimed, status, expected in CLAIMS:
            objects, before = set(storage.objects), await counts(session)
            response = await upload_via(api, route, target, name, content, content_type=claimed)
            assert response.status_code in ((200, 201) if status == 201 else (status,)), (name, response.text)
            if status != 201:
                assert response.json()["detail"] == expected, name
                assert set(storage.objects) == objects and await counts(session) == before, name
                continue
            key = new_key(storage, objects)
            # The extension and the first bytes decide the type; the stored object says so, whatever was claimed.
            assert storage.content_types[key] == expected and storage.objects[key] == content, name
            assert key.endswith("-" + name), key
            advance(target, route, response.json())


# --- key shapes -------------------------------------------------------------------------------------------


async def test_key_shapes_and_the_per_upload_nonce_on_every_route(session, world):
    storage = world.storage
    keys: list[str] = []
    async with client_for(session, LEGAL, storage) as api:
        cinder = {"client_id": world.clients["cinder"], "kind": "NDA"}
        first = await upload_via(api, "client_copy", cinder, "same name.pdf", PDF)
        second = await upload_via(api, "client_copy", cinder, "same name.pdf", PDF)  # same second, same name
        assert (first.status_code, second.status_code) == (201, 201), second.text
        agreement_id = first.json()["agreement_id"]
        assert second.json()["agreement_id"] == agreement_id
        created = await upload_via(api, "legacy_create", {"client_id": world.clients["heron"], "kind": "MSA"},
                                   "heron.docx", DOCX)
        assert created.status_code == 201, created.text
        replaced = await upload_via(api, "legacy_replace", {"agreement_id": created.json()["id"], "version": 1},
                                    "heron v2.pdf", PDF)
        assert replaced.status_code == 200, replaced.text
        nda = await upload_via(api, "standard", {"kind": "NDA"}, "Standard NDA.pdf", PDF)
        msa = await upload_via(api, "standard", {"kind": "MSA"}, "Standard MSA.docx", DOCX)
        assert (nda.status_code, msa.status_code) == (201, 201), msa.text
    rows = {(r.client_id, r.kind): r for r in (await session.scalars(select(Agreement))).all()}
    cinder_row = rows[(world.clients["cinder"], "NDA")]
    heron_row = rows[(world.clients["heron"], "MSA")]
    v1 = await session.get(AgreementFileVersion, (cinder_row.id, 1))
    assert str(cinder_row.id) == agreement_id and cinder_row.version_no == 2
    # Two uploads of one name in the same second never share a key: the 8-hex nonce keeps them apart.
    assert v1.file_key != cinder_row.file_key and {v1.file_key, cinder_row.file_key} <= set(storage.objects)
    for key in (v1.file_key, cinder_row.file_key):
        match = client_key(cinder_row.id).fullmatch(key)
        assert match and match["name"] == "same name.pdf", key
        keys.append(key)
    heron_v1 = await session.get(AgreementFileVersion, (heron_row.id, 1))
    for key, name in ((heron_v1.file_key, "heron.docx"), (heron_row.file_key, "heron v2.pdf")):
        match = client_key(heron_row.id).fullmatch(key)
        assert match and match["name"] == name, key
        keys.append(key)
    standards = {(s.kind, s.version_no): s for s in (await session.scalars(select(StandardAgreement))).all()}
    for kind, name in (("NDA", "Standard NDA.pdf"), ("MSA", "Standard MSA.docx")):
        key = standards[(kind, 2)].file_key
        match = STANDARD_KEY.fullmatch(key)
        assert match and (match["kind"], match["name"]) == (kind, name), key
        assert storage.objects[key] == body_for(name)
        keys.append(key)
    assert len(set(keys)) == len(keys) == 6
    for key in keys:
        match = re.search(STAMP_NONCE + "$", key)
        check_stamp(match["stamp"])
        check_stored_name(match["name"])
        assert "/e2e/" not in key and "\\" not in key and "//" not in key  # real clients: no run segment
    assert {a.after["file_key"] for a in (await session.scalars(select(AuditEvent))).all()
            if a.after and "file_key" in a.after} == set(keys)  # the audit trail names the same keys


def test_two_keys_stamped_in_the_same_second_differ_by_their_nonce():
    """The clock frozen: the same name in the same second still gets two keys (the 8-hex nonce)."""
    from app.services.agreement_files import object_key

    fixed = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
    keys = [object_key("agreements/x", "same name.pdf", now=fixed) for _ in range(50)]
    assert len(set(keys)) == 50
    matches = [re.search(STAMP_NONCE + "$", key) for key in keys]
    assert {m["stamp"] for m in matches} == {"20261015T120000Z"}
    assert {m["name"] for m in matches} == {"same name.pdf"} and len({m["nonce"] for m in matches}) == 50


# --- notes ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["legacy_create", "legacy_replace"])
async def test_a_note_over_200_characters_is_refused_before_anything_is_stored(session, world, route):
    async with client_for(session, LEGAL, world.storage) as api:
        target = await target_for(api, world, route)
        objects, before = set(world.storage.objects), await counts(session)
        response = await upload_via(api, route, target, "with-note.pdf", PDF, note="n" * 201)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "A note can be at most 200 characters."
    assert set(world.storage.objects) == objects and await counts(session) == before


@pytest.mark.parametrize("route", ["client_copy", "legacy_create", "legacy_replace"])
async def test_a_200_character_note_is_kept_and_a_blank_note_is_none(session, world, route):
    note = "Payment terms changed to 45 days; " + "n" * 166
    assert len(note) == 200
    async with client_for(session, LEGAL, world.storage) as api:
        target = await target_for(api, world, route)
        kept = await upload_via(api, route, target, "noted.pdf", PDF, note=f"  {note}  ")
        assert kept.status_code in (200, 201), kept.text
        advance(target, route, kept.json())
        blank = await upload_via(api, route, target, "blank.pdf", PDF, note="   ")
        assert blank.status_code in (200, 201), blank.text
    assert kept.json()["note"] == note  # trimmed, then at most 200
    assert blank.json()["note"] is None
    versions = (await session.scalars(select(AgreementFileVersion).where(
        AgreementFileVersion.note.is_not(None)))).all()
    assert [v.note for v in versions] == [note]


async def test_mark_and_relationship_notes_over_200_characters_are_refused(session, world):
    cinder = world.clients["cinder"]
    async with client_for(session, LEGAL, world.storage) as api:
        before = await counts(session)
        mark = await api.put(f"/clients/{cinder}/agreements/NDA/mark",
                             json={"reason": "other", "marked_on": "2026-10-01", "note": "m" * 201})
        relationship = await api.put(f"/clients/{cinder}/relationship",
                                     json={"relationship": "existing", "note": "r" * 201})
        assert (mark.status_code, relationship.status_code) == (422, 422)
        assert await counts(session) == before
        ok = await api.put(f"/clients/{cinder}/agreements/NDA/mark",
                           json={"reason": "other", "marked_on": "2026-10-01", "note": "m" * 200})
    assert ok.status_code == 200 and ok.json()["mark"]["note"] == "m" * 200


# --- a client copy over a standard copy that three clients hold ------------------------------------------


async def test_a_client_copy_over_a_standard_copy_changes_only_that_client(session, world):
    storage, std_id, std_key = world.storage, world.standard_ids["NDA"], world.standard_keys["NDA"]
    holders = ("arden", "birch", "cinder")
    async with client_for(session, LEGAL, storage) as api:
        for key in holders:
            attached = await api.post(f"/clients/{world.clients[key]}/agreements/NDA/attach-standard")
            assert attached.status_code == 201, attached.text
        assert set(storage.objects) == set(world.standard_keys.values())  # attaching copies nothing
        birch = await upload_via(api, "client_copy", {"client_id": world.clients["birch"], "kind": "NDA"},
                                 "Birch NDA (signed).pdf", PDF, note="Mutual NDA agreed for Birch")
        assert birch.status_code == 201, birch.text
        cinder_row_id = await session.scalar(select(Agreement.id).where(
            Agreement.client_id == world.clients["cinder"], Agreement.kind == "NDA"))
        cinder = await upload_via(api, "legacy_replace", {"agreement_id": cinder_row_id, "version": 1},
                                  "Cinder NDA.docx", DOCX)
        assert cinder.status_code == 200, cinder.text
        standard = (await api.get("/agreements/standard")).json()["NDA"]
        panels = {k: (await api.get(f"/clients/{world.clients[k]}/agreements")).json()["nda"] for k in holders}
        documents = (await api.get("/agreements/documents", params={"kind": "NDA", "page_size": 100})).json()
        links = {k: (await api.get(f"/clients/{world.clients[k]}/agreements/NDA/download")).json()
                 for k in holders}
    assert (cinder.json()["source"], cinder.json()["standard_version"], cinder.json()["version_no"]) == (
        "client", None, 2)
    rows = {r.client_id: r for r in (await session.scalars(select(Agreement).where(Agreement.kind == "NDA"))).all()}
    arden = rows[world.clients["arden"]]
    # The other holder keeps the shared object, its standard version and its single history entry.
    assert (arden.source, arden.file_key, arden.standard_agreement_id, arden.version_no) == (
        "standard", std_key, std_id, 1)
    assert [h["what"] for h in panels["arden"]["history"]] == ["Standard NDA v1 attached"]
    assert (panels["arden"]["state"], panels["arden"]["source_label"]) == ("standard", "Standard v1")
    for key, file_name, latest in (
        ("birch", "Birch NDA (signed).pdf",
         "Standard copy replaced with a client copy: Birch NDA (signed).pdf. Note: Mutual NDA agreed for Birch"),
        ("cinder", "Cinder NDA.docx", "Standard copy replaced with a client copy: Cinder NDA.docx"),
    ):
        row = rows[world.clients[key]]
        assert (row.source, row.standard_agreement_id, row.batch_id, row.version_no, row.filename) == (
            "client", None, None, 2, file_name)
        assert client_key(row.id).fullmatch(row.file_key) and row.file_key in storage.objects
        earlier = await session.get(AgreementFileVersion, (row.id, 1))
        # History keeps the standard entry (the shared key, the standard version), not a copy of it.
        assert (earlier.source, earlier.file_key, earlier.standard_agreement_id) == ("standard", std_key, std_id)
        assert [h["what"] for h in panels[key]["history"]] == [latest, "Standard NDA v1 attached"]
        assert (panels[key]["state"], panels[key]["file_name"]) == ("client", file_name)
        assert links[key]["file_name"] == file_name and row.file_key in links[key]["url"]
    assert std_key in links["arden"]["url"] and links["arden"]["file_name"] == world.standard_files["NDA"]
    assert storage.objects[std_key] == PDF  # the shared object itself is untouched
    std_row = await session.get(StandardAgreement, std_id)
    assert (std_row.file_key, std_row.version_no) == (std_key, 1)
    assert standard["version"] == 1 and standard["attached_clients"] == 1  # only Arden still holds it
    by_client = {d["client_name"]: d for d in documents["items"]}
    assert (by_client["Arden Foods"]["source"], by_client["Arden Foods"]["standard_version"]) == ("standard", 1)
    assert (by_client["Birch Logistics"]["source"], by_client["Birch Logistics"]["file_name"]) == (
        "client", "Birch NDA (signed).pdf")
    assert (by_client["Cinder Systems"]["source"], by_client["Cinder Systems"]["standard_version"]) == (
        "client", None)


# --- no orphan object when the row cannot be committed --------------------------------------------------


class CommitFailure:
    """Fails the first COMMIT after an agreement audit row is appended, the way a dropped connection would."""

    def __init__(self) -> None:
        self.armed = False
        self.fired = 0

    def before_commit(self, _session) -> None:
        if self.armed:
            self.armed = False
            self.fired += 1
            raise OperationalError("COMMIT", {}, Exception("the database dropped the connection at commit"))


@pytest.mark.parametrize("route", ["client_copy_first", "client_copy_version", "legacy_create", "legacy_replace",
                                   "standard"])
async def test_no_orphan_object_when_the_commit_fails(session, world, monkeypatch, route):
    storage = world.storage
    async with client_for(session, LEGAL, storage) as api:
        if route == "client_copy_version":
            target = {"client_id": world.clients["cinder"], "kind": "NDA"}
            assert (await upload_via(api, "client_copy", target, "v1.pdf", PDF)).status_code == 201
            sent_as = "client_copy"
        else:
            sent_as = route.replace("_first", "")
            target = await target_for(api, world, sent_as)
        objects, before = set(storage.objects), await counts(session)
        rows_before = {(r.id, r.version_no, r.file_key) for r in (await session.scalars(select(Agreement))).all()}

        failure = CommitFailure()
        original = agreement_audit.record

        async def record_then_arm(*args, **kwargs):
            row = await original(*args, **kwargs)
            failure.armed = True  # the audit row is the last write before the commit
            return row

        monkeypatch.setattr(agreement_audit, "record", record_then_arm)
        event.listen(session.sync_session, "before_commit", failure.before_commit)
        try:
            response = await upload_via(api, sent_as, target, "will-not-commit.pdf", PDF)
        finally:
            event.remove(session.sync_session, "before_commit", failure.before_commit)
            monkeypatch.setattr(agreement_audit, "record", original)
    assert response.status_code == 500 and failure.fired == 1
    key = new_key(storage, objects)  # the object was written first ...
    after = await counts(session)
    # ... and nothing else landed: no row, no version, no standard version, no audit row; one cleanup job.
    assert after == {**before, "deletion_job": before["deletion_job"] + 1}
    assert {(r.id, r.version_no, r.file_key) for r in (await session.scalars(select(Agreement))).all()} == rows_before
    job = (await session.scalars(select(DeletionJob))).one()
    assert (job.subject_type, job.status, job.objects) == ("agreement_upload", "pending",
                                                            [{"bucket": BUCKET, "key": key}])
    assert job.summary["reason"] == "upload not committed" and job.actor_id == LEGAL.id
    assert await process_deletion_jobs(session, s3=StubVersions(storage)) == 1
    assert key not in storage.objects and objects <= set(storage.objects)  # earlier objects are untouched
    assert (await session.get(DeletionJob, job.id, populate_existing=True)).status == "done"
