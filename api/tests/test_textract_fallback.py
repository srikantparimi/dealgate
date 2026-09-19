"""Acceptance tests for S7 story A — Textract fallback for scanned SOWs.

Given/When/Then:

- Given a *text-based* PDF (chars/page ≥ threshold), when ``run_extract``
  runs, then the stub Bedrock is called directly and Textract is not
  touched. ``extract_source == "pdf_text"``.
- Given an *image-only* PDF (zero chars/page), when ``run_extract`` runs,
  then Textract is called, the recovered text is passed to Bedrock, and
  ``extract_source == "textract"``.
- Given Textract raises, when ``run_extract`` runs, then the version
  lands as ``extract_status="manual_required"`` with reason
  ``"OCR unavailable"`` — no fabricated fields (CLAUDE.md rule 6).
- Metadata is persisted on the version and surfaced back through the
  service snapshot.
"""

from __future__ import annotations

import uuid
from io import BytesIO

import pytest
import pytest_asyncio
from pypdf import PdfWriter

from app.audit import verify_chain
from app.integrations.bedrock_sow_extract import StubBedrock
from app.integrations.textract import StubTextract, TextractError
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.sow_extract import (
    TEXT_DENSITY_MIN_CHARS_PER_PAGE,
    run_extract,
)

# --- fixtures ------------------------------------------------------------


def _blank_image_pdf() -> bytes:
    """A one-page PDF with no text layer — pypdf reports 0 chars/page."""

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _text_pdf() -> bytes:
    """A one-page handcrafted PDF whose text stream extracts to > threshold chars.

    We keep this inline rather than a fixture file so the test is
    self-contained and CI has no binary artefact to ship. The stream
    contains a full sentence about the SOW so ``extract_text`` returns
    comfortably more than ``TEXT_DENSITY_MIN_CHARS_PER_PAGE`` chars.
    """

    body = (
        b"BT /F1 12 Tf 50 750 Td "
        b"(Statement of Work: modernise the loan origination platform onto AWS.) Tj "
        b"0 -20 Td (Fixed price 250000 USD, term 2026-10-01 through 2027-03-31.) Tj "
        b"0 -20 Td (Deliverables: discovery report, cutover plan, runbook, UAT sign off.) Tj "
        b"ET"
    )
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(len(body)).encode() + b" >>\nstream\n"
        + body
        + b"\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000055 00000 n\n"
        b"0000000102 00000 n\n"
        b"0000000209 00000 n\n"
        b"0000000459 00000 n\n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n524\n%%EOF"
    )


@pytest_asyncio.fixture
async def seeded_version(session):
    """Anchor a Sow + SowVersion so ``run_extract`` has a real row to mutate."""

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-TEXTRACT-1",
        owner_id=uuid.uuid4(),
        governance_status="SOWDraft",
    )
    session.add(opp)
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=opp.owner_id,
        file_s3_key="sow/x/y.pdf",
        file_hash="sha256:abc",
        extract_status="pending",
    )
    session.add(version)
    await session.commit()
    return {"opp": opp, "sow": sow, "version": version}


# --- tests --------------------------------------------------------------


async def test_text_pdf_skips_textract_and_calls_bedrock_directly(
    session, seeded_version
):
    bedrock = StubBedrock()
    textract = StubTextract(text="SHOULD NOT BE CALLED")

    state = await run_extract(
        session,
        sow_version_id=seeded_version["version"].id,
        bedrock=bedrock,
        file_bytes=_text_pdf(),
        textract=textract,
    )
    await session.commit()

    assert state.extract_status == "complete"
    # Bedrock got the raw PDF bytes; Textract was never invoked.
    assert bedrock.calls, "Bedrock stub was not called"
    assert textract.calls == []
    metadata = state.extracted_fields.get("metadata")
    assert metadata is not None
    assert metadata["extract_source"] == "pdf_text"
    assert await verify_chain(session) is True


async def test_image_only_pdf_routes_through_textract_then_bedrock(
    session, seeded_version
):
    bedrock = StubBedrock()
    recovered = "SOW recovered by OCR. " * 10
    textract = StubTextract(text=recovered)

    state = await run_extract(
        session,
        sow_version_id=seeded_version["version"].id,
        bedrock=bedrock,
        file_bytes=_blank_image_pdf(),
        textract=textract,
    )
    await session.commit()

    assert state.extract_status == "complete"
    # Textract was called once with the raw PDF bytes.
    assert len(textract.calls) == 1
    # Bedrock received the *recovered* text (as utf-8 bytes), not the raw PDF.
    assert bedrock.calls == [len(recovered.encode("utf-8"))]
    metadata = state.extracted_fields.get("metadata")
    assert metadata is not None
    assert metadata["extract_source"] == "textract"
    assert await verify_chain(session) is True


async def test_textract_failure_marks_manual_required_with_ocr_reason(
    session, seeded_version
):
    bedrock = StubBedrock()
    textract = StubTextract(fail_with="Textract rate limited")

    state = await run_extract(
        session,
        sow_version_id=seeded_version["version"].id,
        bedrock=bedrock,
        file_bytes=_blank_image_pdf(),
        textract=textract,
    )
    await session.commit()

    assert state.extract_status == "manual_required"
    # Bedrock must not have been called — we never fabricate content.
    assert bedrock.calls == []
    # Every real field is blank/disputed.
    for name, entry in state.extracted_fields.items():
        if name == "metadata":
            continue
        assert entry["value"] is None
        assert entry["status"] == "disputed"
    # The OCR path was still recorded in metadata so the audit reader can
    # see why the version failed.
    assert state.extracted_fields["metadata"]["extract_source"] == "textract"
    assert await verify_chain(session) is True


async def test_density_threshold_is_the_documented_constant(
    session, seeded_version
):
    """Guard: if someone bumps the threshold, they must also update the
    story. A quick sanity check that the constant is a small positive int.
    """

    assert isinstance(TEXT_DENSITY_MIN_CHARS_PER_PAGE, int)
    assert 0 < TEXT_DENSITY_MIN_CHARS_PER_PAGE < 1000


async def test_empty_bytes_skips_textract_for_test_shortcut(
    session, seeded_version
):
    """Existing S3-E5 tests pass ``file_bytes=b""`` — do not OCR nothing."""

    bedrock = StubBedrock()
    textract = StubTextract(text="unused", fail_with="must not be called")

    state = await run_extract(
        session,
        sow_version_id=seeded_version["version"].id,
        bedrock=bedrock,
        file_bytes=b"",
        textract=textract,
    )
    await session.commit()

    assert state.extract_status == "complete"
    assert textract.calls == []
    assert state.extracted_fields["metadata"]["extract_source"] == "pdf_text"


def test_textract_error_is_raised_by_stub():
    """Sanity check the stub itself — belt-and-braces so the failure test
    doesn't quietly pass by never raising."""

    stub = StubTextract(fail_with="boom")
    with pytest.raises(TextractError):
        stub.extract_text(b"whatever")
