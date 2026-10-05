"""S20 W3 T11/T37 · SOW upload binds to client + deal end to end.

The upload router accepts `client_id` and `opportunity_id` together (or
neither). When both are supplied and valid, the pipeline skips the
picker step and creates the SOW under the named opportunity directly.
Extraction failure preserves the file *and* the binding.

Coverage:
  - both fields together → SOW binds to that opportunity, no picker.
  - one field without the other → 422.
  - mismatched client / opportunity → 422 (the opportunity's actual
    client wins; the caller's assertion is refused, not silently
    overwritten).
  - unknown opportunity → 404.
"""

from __future__ import annotations

import uuid
from io import BytesIO
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from pypdf import PdfWriter
from sqlalchemy import select

from app.db import get_session
from app.integrations.bedrock_sow_extract import StubBedrock, get_bedrock_sow
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.integrations.textract import StubTextract, get_textract_client
from app.main import app as main_app
from app.models.client import Client, LegalEntity
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "sample_sows"


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _scanned_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


OWNER_EMAIL = "bind-owner@smartek21.com"


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


@pytest_asyncio.fixture
async def app_with_deps(session):
    async def _override():
        yield session

    stub_s3 = StubS3()
    stub_textract = StubTextract(
        text="Statement of Work\nScope: scanned assessment\nDeliverables: report"
    )
    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_sow_s3] = lambda: stub_s3
    main_app.dependency_overrides[get_bedrock_sow] = lambda: StubBedrock()
    main_app.dependency_overrides[get_textract_client] = lambda: stub_textract
    main_app.state.stub_s3 = stub_s3
    main_app.state.stub_textract = stub_textract
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_sow_s3, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)
        main_app.dependency_overrides.pop(get_textract_client, None)


async def _seed_deal(
    session, client_name: str = "Bound Client"
) -> tuple[Client, Opportunity]:
    client = Client(id=uuid.uuid4(), name=client_name)
    session.add(client)
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name=client_name))
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=None,
        source="hubspot",
        owner_id=_uid(OWNER_EMAIL),
        client_id=client.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    return client, opp


async def test_upload_with_both_bound_creates_sow_under_deal(app_with_deps, session):
    """Happy path: both fields present, pipeline skips picker, SOW
    binds to the named opportunity."""

    client, opp = await _seed_deal(session)
    pdf = (FIXTURE_DIR / "05_tm_capped.pdf").read_bytes()
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
            data={
                "client_id": str(client.id),
                "opportunity_id": str(opp.id),
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opportunity_id"] == str(opp.id)
    assert body["sow_version_id"]
    # No picker: resolution should not be needs_pick.
    assert body["needs_pick"] is None

    # SowVersion was created for the bound Sow, not a new one.
    sow_rows = list(
        (
            await session.execute(select(Sow).where(Sow.opportunity_id == opp.id))
        ).scalars()
    )
    assert len(sow_rows) == 1
    versions = list(
        (
            await session.execute(
                select(SowVersion).where(SowVersion.sow_id == sow_rows[0].id)
            )
        ).scalars()
    )
    assert len(versions) == 1


async def test_bound_scanned_sow_uses_ocr_and_preserves_source_evidence(
    app_with_deps, session
):
    client, opp = await _seed_deal(session, client_name="Scanned SOW Client")
    scan = _scanned_pdf()
    async with _client(app_with_deps) as c:
        response = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("scanned-sow.pdf", scan, "application/pdf")},
            data={"client_id": str(client.id), "opportunity_id": str(opp.id)},
        )

    assert response.status_code == 200, response.text
    version = await session.get(
        SowVersion, uuid.UUID(response.json()["sow_version_id"])
    )
    assert version is not None and version.extract_status == "complete"
    assert version.extracted_fields["metadata"]["extract_source"] == "textract"
    assert main_app.state.stub_textract.calls == [len(scan)]
    assert version.file_hash
    assert main_app.state.stub_s3.put_calls == [
        (version.file_s3_key, len(scan), "application/pdf")
    ]


async def test_bound_scanned_sow_preserves_file_when_ocr_requires_manual_review(
    app_with_deps, session
):
    client, opp = await _seed_deal(session, client_name="Unreadable Scan Client")
    scan = _scanned_pdf()
    main_app.state.stub_textract.fail_with = "Textract rate limited"

    async with _client(app_with_deps) as c:
        response = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("unreadable-scan.pdf", scan, "application/pdf")},
            data={"client_id": str(client.id), "opportunity_id": str(opp.id)},
        )

    assert response.status_code == 200, response.text
    version = await session.get(
        SowVersion, uuid.UUID(response.json()["sow_version_id"])
    )
    assert version is not None and version.extract_status == "manual_required"
    assert "OCR unavailable" in (version.extract_error or "")
    assert version.extracted_fields["metadata"]["extract_source"] == "textract"
    assert main_app.state.stub_textract.calls == [len(scan)]
    assert main_app.state.stub_s3.put_calls == [
        (version.file_s3_key, len(scan), "application/pdf")
    ]


async def test_unbound_scanned_sow_caches_ocr_evidence_for_client_picker(app_with_deps):
    scan = _scanned_pdf()
    async with _client(app_with_deps) as c:
        response = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("unbound-scan.pdf", scan, "application/pdf")},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "needs_pick"
    assert body["sow_version_id"] is None
    assert body["needs_pick"]["extract"]["extract_source"] == "textract"
    assert main_app.state.stub_textract.calls == [len(scan)]
    assert main_app.state.stub_s3.put_calls[0][1:] == (len(scan), "application/pdf")


async def test_upload_missing_one_of_two_bindings_returns_422(app_with_deps, session):
    """One without the other is a caller bug — server refuses."""

    client, opp = await _seed_deal(session, client_name="Half Bound Co")
    pdf = (FIXTURE_DIR / "05_tm_capped.pdf").read_bytes()
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
            data={"client_id": str(client.id)},
        )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "together" in detail.lower()


async def test_upload_mismatched_client_and_opportunity_returns_422(
    app_with_deps, session
):
    """The server checks the opportunity's actual client — a mismatched
    assertion is refused, not silently accepted."""

    _client_a, opp_a = await _seed_deal(session, client_name="Client A")
    other_client = Client(id=uuid.uuid4(), name="Other Co")
    session.add(other_client)
    session.add(
        LegalEntity(id=uuid.uuid4(), client_id=other_client.id, name="Other Co")
    )
    await session.commit()
    pdf = (FIXTURE_DIR / "05_tm_capped.pdf").read_bytes()
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
            data={
                "client_id": str(other_client.id),
                "opportunity_id": str(opp_a.id),
            },
        )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert "bound to client" in detail


async def test_upload_unknown_opportunity_returns_404(app_with_deps, session):
    """An opportunity that doesn't exist → 404, no rows created."""

    client, _opp = await _seed_deal(session, client_name="Nonexistent")
    pdf = (FIXTURE_DIR / "05_tm_capped.pdf").read_bytes()
    fake_opp = uuid.uuid4()
    async with _client(app_with_deps) as c:
        r = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": ("sow.pdf", pdf, "application/pdf")},
            data={
                "client_id": str(client.id),
                "opportunity_id": str(fake_opp),
            },
        )
    assert r.status_code == 404, r.text
