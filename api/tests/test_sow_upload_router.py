"""S10-01 — acceptance tests for the SOW-upload router.

Every branch the story lists (happy, résumé reject, duplicate,
needs_pick + resume, role gate) is exercised end-to-end through the
FastAPI test client against the in-memory SQLite fixture.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.integrations.bedrock_sow_extract import (
    EXTRACTED_FIELDS,
    ExtractedFields,
    StubBedrock,
    get_bedrock_sow,
)
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.client import Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.opportunity import Opportunity
from app.models.sow_upload_job import SowUploadJob


OWNER_EMAIL = "sow-owner@smartek21.com"
OTHER_EMAIL = "other-sales@smartek21.com"
ADMIN_EMAIL = "sysadmin@smartek21.com"


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "sample_sows"


def _load_pdf(name: str) -> bytes:
    return (FIXTURE_DIR / name).read_bytes()


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


class _StubBedrockWithClient(StubBedrock):
    """Extract stub that reports a specific client legal name.

    Sets both the first-class ``client_legal_name`` field (which
    ``_client_signals`` now prefers) and the signatories block (its
    fallback), so this fixture exercises the real precedence order.
    """

    def __init__(self, client_legal_name: str) -> None:
        super().__init__()
        self.client_legal_name = client_legal_name

    def extract(self, doc) -> ExtractedFields:
        result = super().extract(doc)
        assert isinstance(result, ExtractedFields)
        fields = dict(result.fields)
        domain = f"{self.client_legal_name.lower().replace(' ', '')}.example"
        fields["client_legal_name"] = {
            "value": self.client_legal_name,
            "page_ref": 1,
            "status": "unconfirmed",
        }
        fields["client_domain"] = {
            "value": domain,
            "page_ref": 1,
            "status": "unconfirmed",
        }
        fields["signatories"] = {
            "value": [
                {
                    "client_legal_name": self.client_legal_name,
                    "name": "J. Doe",
                    "role": "Client sponsor",
                    "email": f"j.doe@{domain}",
                },
                {"name": "A. Roe", "role": "Delivery lead"},
            ],
            "page_ref": 8,
            "status": "unconfirmed",
        }
        return ExtractedFields(
            fields=fields,
            model=result.model,
            prompt_version=result.prompt_version,
        )


@pytest_asyncio.fixture
async def app_with_deps(session):
    async def _override():
        yield session

    stub_s3 = StubS3()
    # The bedrock override is opted-in per test via `app_with_bedrock`.
    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_sow_s3] = lambda: stub_s3
    main_app.state.stub_s3 = stub_s3
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_sow_s3, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)


def _override_bedrock(client_name: str) -> None:
    main_app.dependency_overrides[get_bedrock_sow] = lambda: _StubBedrockWithClient(
        client_name
    )


async def _seed_client(session, name: str, alias: str | None = None) -> Client:
    client = Client(id=uuid.uuid4(), name=name)
    session.add(client)
    await session.flush()
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name=name))
    if alias:
        session.add(
            ClientAlias(
                id=uuid.uuid4(),
                client_id=client.id,
                alias=alias,
                source="test",
            )
        )
    await session.commit()
    return client


# --- happy path -----------------------------------------------------------


async def test_upload_happy_path_creates_opportunity_sow_and_gm(
    app_with_deps, session
):
    """PDF → job runs to done; opportunity + sow + gm exist; audits chain."""

    client_name = "Northstar Analytics"
    await _seed_client(session, client_name)
    _override_bedrock(client_name)

    pdf = _load_pdf("05_tm_capped.pdf")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duplicate"] is False
    assert body["status"] == "done"
    assert body["opportunity_id"]
    assert body["sow_version_id"]

    opp_id = uuid.UUID(body["opportunity_id"])
    opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opp_id))
    ).scalar_one()
    assert opp.source == "sow_upload"
    assert opp.hubspot_deal_id is None

    # Audit chain: at least queued + extracting + matching_client + deriving_gm + done.
    job_id = uuid.UUID(body["job_id"])
    audits = (
        await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity == "sow_upload_job")
            .where(AuditEvent.entity_id == str(job_id))
            .order_by(AuditEvent.ts.asc(), AuditEvent.id.asc())
        )
    ).scalars().all()
    actions = [a.action for a in audits]
    for expected in (
        "sow_upload_job.queued",
        "sow_upload_job.extracting",
        "sow_upload_job.matching_client",
        "sow_upload_job.deriving_gm",
        "sow_upload_job.done",
    ):
        assert expected in actions, f"missing {expected}; got {actions}"


# --- doc-type reject ------------------------------------------------------


async def test_upload_resume_pdf_returns_422_and_creates_no_rows(
    app_with_deps, session
):
    _override_bedrock("Unused")
    pdf = _load_pdf("99_resume.pdf")

    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("resume.pdf", pdf, "application/pdf")},
        )
    assert r.status_code == 422, r.text
    body = r.json()
    detail = body["detail"]
    assert detail["detected_type"] == "resume"
    assert "not look like a SOW" in detail["message"]

    # No rows created.
    job_count = (
        await session.execute(select(SowUploadJob))
    ).scalars().all()
    assert job_count == []
    opp_count = (
        await session.execute(select(Opportunity))
    ).scalars().all()
    assert opp_count == []


# --- duplicate ------------------------------------------------------------


async def test_upload_same_bytes_twice_returns_duplicate(
    app_with_deps, session
):
    client_name = "Duplicate Client"
    await _seed_client(session, client_name)
    _override_bedrock(client_name)

    pdf = _load_pdf("05_tm_capped.pdf")

    async with _client(app_with_deps) as c:
        first = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
        assert first.status_code == 200, first.text
        first_body = first.json()

        second = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["duplicate"] is True
    assert second_body["job_id"] == first_body["job_id"]

    # Only one job row.
    jobs = (await session.execute(select(SowUploadJob))).scalars().all()
    assert len(jobs) == 1


# --- needs_pick + resume via create_new ----------------------------------


async def test_upload_unknown_client_lands_needs_pick_and_resume_creates_client(
    app_with_deps, session
):
    """No matching client → needs_pick with candidates; picker with
    create_new creates the client + opportunity and finishes the pipeline."""

    _override_bedrock("Brand New Client Inc")

    pdf = _load_pdf("05_tm_capped.pdf")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "needs_pick"
    assert body["needs_pick"] is not None
    signals = body["needs_pick"]["signals"]
    assert signals["legal_name"] == "Brand New Client Inc"
    create_new = body["needs_pick"]["create_new"]
    assert create_new["legal_name"] == "Brand New Client Inc"

    job_id = body["job_id"]

    async with _client(app_with_deps) as c:
        pick = await c.post(
            f"/sows/jobs/{job_id}/pick",
            headers={"X-Test-User": OWNER_EMAIL},
            json={
                "create_new": {
                    "legal_name": "Brand New Client Inc",
                    "domain": "brandnew.example",
                }
            },
        )
    assert pick.status_code == 200, pick.text
    picked = pick.json()
    assert picked["status"] == "done"
    assert picked["resolution"] == "created"
    assert picked["opportunity_id"]

    # Verify the client was actually created + aliased.
    clients = (await session.execute(select(Client))).scalars().all()
    assert any(c.name == "Brand New Client Inc" for c in clients)
    aliases = (await session.execute(select(ClientAlias))).scalars().all()
    assert any(
        a.alias == "brandnew.example" for a in aliases
    ), f"expected domain alias; got {[a.alias for a in aliases]}"


# --- role gate ------------------------------------------------------------


async def test_non_uploader_cannot_view_others_job(
    app_with_deps, session, monkeypatch
):
    client_name = "Guarded Client"
    await _seed_client(session, client_name)
    _override_bedrock(client_name)

    pdf = _load_pdf("05_tm_capped.pdf")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]

    # Other Sales user (not a leader) — role passes require_role, but
    # `_ensure_read_access` rejects because they are not the uploader.
    async with _client(app_with_deps) as c:
        forbidden = await c.get(
            f"/sows/jobs/{job_id}",
            headers={"X-Test-User": OTHER_EMAIL},
        )
    assert forbidden.status_code == 403, forbidden.text

    # SystemAdmin can see anything.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_deps) as c:
        admin = await c.get(
            f"/sows/jobs/{job_id}",
            headers={"X-Test-User": ADMIN_EMAIL},
        )
    assert admin.status_code == 200, admin.text


# --- empty file & bad content-type ---------------------------------------


async def test_upload_empty_file_returns_422(app_with_deps):
    _override_bedrock("Whatever")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", b"", "application/pdf")},
        )
    assert r.status_code == 422, r.text
    assert "empty" in r.json()["detail"].lower()


async def test_upload_wrong_content_type_returns_422(app_with_deps):
    _override_bedrock("Whatever")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.txt", b"junk", "text/plain")},
        )
    assert r.status_code == 422, r.text


# --- pick body validation ------------------------------------------------


async def test_pick_requires_client_id_or_create_new(
    app_with_deps, session
):
    _override_bedrock("Some Nowhere Client")
    pdf = _load_pdf("05_tm_capped.pdf")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
        )
    job_id = r.json()["job_id"]

    async with _client(app_with_deps) as c:
        empty = await c.post(
            f"/sows/jobs/{job_id}/pick",
            headers={"X-Test-User": OWNER_EMAIL},
            json={},
        )
    assert empty.status_code == 422, empty.text


# --- Word documents -------------------------------------------------------
#
# The story (docs/backlog/s10-sow-upload.md:21) specifies "the PDF or DOCX",
# the router allowlists the DOCX MIME type and the UI advertises
# accept=".docx" — but nothing could read a Word file, and there was no test
# in either direction. A real Word SOW uploaded to the deployed app came back
# as "This file does not look like a SOW."

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


async def test_upload_docx_runs_the_full_pipeline(app_with_deps, session):
    """DOCX → job runs to done, exactly like a PDF."""

    client_name = "Contoso Data Services, LLC"
    await _seed_client(session, client_name)
    _override_bedrock(client_name)

    docx = _load_pdf("08_assessment_fixed_fee.docx")
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.docx", docx, DOCX_CONTENT_TYPE)},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done", body
    assert body["opportunity_id"]
    assert body["sow_version_id"]

    opp = (
        await session.execute(
            select(Opportunity).where(
                Opportunity.id == uuid.UUID(body["opportunity_id"])
            )
        )
    ).scalar_one()
    assert opp.source == "sow_upload"


async def test_docx_is_classified_as_a_sow_by_the_rules(app_with_deps, session):
    """The keyword rules read the Word body, so no model call is needed to
    decide the document type."""

    from app.services.document_type import classify_document

    result = classify_document(
        _load_pdf("08_assessment_fixed_fee.docx"), content_type=DOCX_CONTENT_TYPE
    )
    assert result.type == "sow"
    assert result.source == "rules"
    assert result.confidence >= 0.9


async def test_unreadable_file_says_so_rather_than_blaming_the_content(
    app_with_deps, session
):
    """An allowlisted MIME type with unreadable bytes is a 422 that names the
    real problem — not "this does not look like a SOW", which sends the user
    hunting for the wrong thing, and not a 500."""

    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.docx", b"PK\x03\x04 corrupt", DOCX_CONTENT_TYPE)},
        )

    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["detected_type"] == "unreadable"
    assert "could not read" in detail["message"].lower()


async def test_failed_job_does_not_poison_the_file_hash(app_with_deps, session):
    """`file_hash` is UNIQUE, so a job left in `failed` used to make those
    exact bytes permanently un-uploadable: every retry returned the dead job
    with duplicate=true. A retry must be able to succeed."""

    from app.models.sow_upload_job import SowUploadJob
    from app.services.sow_upload_job_service import find_by_hash, sha256_hex

    client_name = "Contoso Data Services, LLC"
    await _seed_client(session, client_name)
    _override_bedrock(client_name)
    docx = _load_pdf("08_assessment_fixed_fee.docx")

    async with _client(app_with_deps) as c:
        first = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.docx", docx, DOCX_CONTENT_TYPE)},
        )
    assert first.status_code == 200

    # Force the job into the terminal failure state, as a transient S3 or
    # Bedrock outage would.
    job = await find_by_hash(session, sha256_hex(docx))
    assert job is not None
    job.status = "failed"
    job.error = "simulated transient failure"
    await session.commit()

    async with _client(app_with_deps) as c:
        retry = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.docx", docx, DOCX_CONTENT_TYPE)},
        )

    assert retry.status_code == 200, retry.text
    assert retry.json()["duplicate"] is False
    assert retry.json()["status"] == "done"

    # The row was reused, not duplicated — the unique constraint holds.
    rows = (
        await session.execute(
            select(SowUploadJob).where(SowUploadJob.file_hash == sha256_hex(docx))
        )
    ).scalars().all()
    assert len(rows) == 1
