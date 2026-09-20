"""Unit tests for the shared PDF/DOCX text seam (S10-04).

The bug this module exists to prevent: a Word file was accepted by the upload
router, handed to a pypdf-only reader, yielded zero pages, and was reported to
the user as "This file does not look like a SOW."
"""

from __future__ import annotations

import pathlib
import zipfile

import pytest

from app.services.document_text import (
    UnreadableDocument,
    extract_document_text,
    is_low_density,
    numbered_prompt_text,
    pages_text,
    text_document_from_string,
    total_chars,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "sample_sows"
DOCX_FIXTURE = FIXTURES / "08_assessment_fixed_fee.docx"
PDF_FIXTURE = FIXTURES / "01_staff_aug_us.pdf"

DOCX_CT = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)


def test_pdf_blocks_are_pages() -> None:
    doc = extract_document_text(PDF_FIXTURE.read_bytes(), "application/pdf")
    assert doc.kind == "pdf"
    assert doc.ref_unit == "page"
    assert doc.page_count == len(doc.blocks)
    assert all(b.kind == "page" for b in doc.blocks)
    # Page refs are 1-based and contiguous — they are quoted back as page_ref.
    assert [b.index for b in doc.blocks] == list(range(1, len(doc.blocks) + 1))
    assert [b.page for b in doc.blocks] == [b.index for b in doc.blocks]


def test_docx_is_read_at_all() -> None:
    """The regression that started this: a .docx used to yield zero blocks."""

    doc = extract_document_text(DOCX_FIXTURE.read_bytes(), DOCX_CT)
    assert doc.kind == "docx"
    assert doc.ref_unit == "block"
    assert doc.page_count is None
    assert len(doc.blocks) > 10
    assert total_chars(doc) > 500
    assert not is_low_density(doc)
    assert doc.blocks[0].text == "STATEMENT OF WORK"


def test_docx_tables_keep_their_grid() -> None:
    """Flattening a table to prose loses the row/column pairing that makes
    dates and amounts extractable — so the renderer must preserve it."""

    doc = extract_document_text(DOCX_FIXTURE.read_bytes(), DOCX_CT)
    tables = [b for b in doc.blocks if b.kind == "table"]
    assert len(tables) == 1
    rows = tables[0].text.splitlines()
    assert rows[0] == "Day | Date | Focus"
    assert rows[1].startswith("Day 1 | Mon, Mar 2, 2026 |")
    assert len(rows) == 4


def test_format_is_sniffed_not_trusted() -> None:
    """The browser-supplied content type is caller-controlled and often wrong,
    so the magic bytes decide."""

    docx = DOCX_FIXTURE.read_bytes()
    # Claim it is a PDF; it should still be read as the .docx it actually is.
    doc = extract_document_text(docx, "application/pdf")
    assert doc.kind == "docx"

    pdf = PDF_FIXTURE.read_bytes()
    doc2 = extract_document_text(pdf, DOCX_CT)
    assert doc2.kind == "pdf"


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        (b"", "empty"),
        (b"just some text", "unrecognised"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1padding", ".doc"),
    ],
)
def test_unreadable_inputs_raise_with_a_reason(payload: bytes, fragment: str) -> None:
    with pytest.raises(UnreadableDocument) as excinfo:
        extract_document_text(payload)
    assert fragment in excinfo.value.reason


def test_zip_without_a_word_body_is_rejected() -> None:
    """A .xlsx or a plain archive is a zip too — it is not a Word document."""

    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    with pytest.raises(UnreadableDocument) as excinfo:
        extract_document_text(buf.getvalue())
    assert "word/document.xml" in excinfo.value.reason


def test_corrupt_docx_is_rejected_not_silently_empty() -> None:
    corrupt = b"PK\x03\x04" + b"\x00" * 64
    with pytest.raises(UnreadableDocument):
        extract_document_text(corrupt)


def test_numbered_prompt_text_tags_every_block() -> None:
    """`page_ref` provenance depends on the model seeing these numbers."""

    doc = extract_document_text(DOCX_FIXTURE.read_bytes(), DOCX_CT)
    rendered = numbered_prompt_text(doc)
    assert rendered.startswith("[[1]] STATEMENT OF WORK")
    for block in doc.blocks:
        assert f"[[{block.index}]]" in rendered


def test_numbered_prompt_text_truncation_is_visible() -> None:
    """Silent truncation would mean fields cited against blocks never sent."""

    doc = extract_document_text(DOCX_FIXTURE.read_bytes(), DOCX_CT)
    rendered = numbered_prompt_text(doc, max_chars=200)
    assert "truncated after block" in rendered


def test_plain_text_wraps_as_blocks() -> None:
    doc = text_document_from_string("One.\n\nTwo.\n\n\nThree.")
    assert [b.text for b in doc.blocks] == ["One.", "Two.", "Three."]
    assert doc.ref_unit == "block"
    assert pages_text(doc) == ["One.", "Two.", "Three."]
