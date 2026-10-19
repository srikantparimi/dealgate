"""S24-AG1 F2/B5/T3 — the browser's "Will be stored as" line must match the server.

web/src/pages/v2/agreements/fileRules.ts mirrors app.services.agreement_files.stored_name. The same
table runs in web/src/__tests__/v2/S24FEBFileRules.test.tsx (STORED_NAME_VECTORS); if either side
changes, one of the two tests fails.
"""

from __future__ import annotations

import pytest

from app.services.agreement_files import (
    MSG_EMPTY,
    MSG_NOT_DOCX,
    MSG_NOT_PDF,
    MSG_TOO_LARGE,
    MSG_TYPE,
    _EXT,
    _last_segment,
    display_name,
    stored_name,
)

# [original name, extension the server derives, stored name] — identical to STORED_NAME_VECTORS.
STORED_NAME_VECTORS: list[tuple[str, str, str]] = [
    ("Contract.pdf", "pdf", "Contract.pdf"),
    ("x.pdf.pdf", "pdf", "x.pdf"),
    ("x.docx.pdf", "pdf", "x.pdf"),
    ("X.PDF", "pdf", "X.pdf"),
    ("x.PDF.Pdf", "pdf", "x.pdf"),
    ("..\\a/b.pdf", "pdf", "b.pdf"),
    ("C:\\Users\\me\\NDA final.docx", "docx", "NDA final.docx"),
    ("<img src=x onerror=alert(1)>.pdf", "pdf", "_img src_x onerror_alert_1_.pdf"),
    ("a" * 90 + ".pdf", "pdf", "a" * 80 + ".pdf"),
    ("a" * 79 + " " + "b" * 10 + ".pdf", "pdf", "a" * 79 + ".pdf"),
    ("...hidden.pdf", "pdf", "hidden.pdf"),
    ("  spaced   name  .pdf", "pdf", "spaced name.pdf"),
    ("Acme\u2019s NDA (v2).pdf", "pdf", "Acme_s NDA _v2_.pdf"),
    ("r\u00e9sum\u00e9.docx", "docx", "r_sum_.docx"),
    (".pdf", "pdf", "file.pdf"),
    ("report.pdf\n", "pdf", "report.pdf"),
    ("\U0001F600 emoji.pdf", "pdf", "_ emoji.pdf"),
    ("a.b.c.pdf", "pdf", "a.b.c.pdf"),
    ("trailing dots....docx", "docx", "trailing dots.docx"),
    ("tab\tname.pdf", "pdf", "tab_name.pdf"),
    ("x.pdf.docx", "docx", "x.docx"),
    # Review finding: a gap between repeated extensions, and invisible characters (C0, C1, U+061C, zero-width,
    # BOM, line separator) in the stored name.
    ("x.pdf .pdf", "pdf", "x.pdf"),
    ("x.docx .pdf", "pdf", "x.pdf"),
    ("x.pdf..pdf", "pdf", "x.pdf"),
    ("Acme_MSA.docx .pdf", "pdf", "Acme_MSA.pdf"),
    ("x.pdf\t.pdf", "pdf", "x.pdf"),
    ("x .PDF. .pdf", "pdf", "x.pdf"),
    ("a\u0085b.pdf", "pdf", "a_b.pdf"),
    ("a\u0080b.pdf", "pdf", "ab.pdf"),
    ("a\u061cb.pdf", "pdf", "ab.pdf"),
    ("a\u2028b.pdf", "pdf", "a b.pdf"),
    ("x\u200b.pdf", "pdf", "x.pdf"),
    ("a\u00a0\u00a0b.pdf", "pdf", "a_b.pdf"),
    ("a\u001fb.pdf", "pdf", "a_b.pdf"),
    ("\ufeffbom.pdf", "pdf", "bom.pdf"),
]


def _ext(name: str) -> str:
    match = _EXT.search(_last_segment(name))
    return match.group(1).lower() if match else ""


@pytest.mark.parametrize(("name", "ext", "expected"), STORED_NAME_VECTORS)
def test_stored_name_matches_the_browser_table(name: str, ext: str, expected: str) -> None:
    assert _ext(name) == ext
    assert stored_name(name, ext) == expected


def test_display_name_matches_the_browser() -> None:
    assert display_name("..\\a/b.pdf") == "b.pdf"
    assert display_name("tab\tname.pdf") == "tab name.pdf"  # whitespace keeps words apart
    assert display_name("a\u0085b.pdf") == "a b.pdf"
    assert display_name("a\u0080b.pdf") == "ab.pdf"
    assert display_name("a\u061cb.pdf") == "ab.pdf"
    assert display_name("a\u2028b.pdf") == "a b.pdf"
    assert display_name("\ufeffbom.pdf") == "bom.pdf"
    assert display_name("x.pdf .pdf") == "x.pdf .pdf"
    assert display_name("report.pdf\n") == "report.pdf"
    assert display_name("\u202eevil\u202c.pdf") == "evil.pdf"
    assert display_name("") == "file"
    long = display_name("n" * 300 + ".pdf")
    assert len(long) == 255 and long.endswith(".pdf")


def test_messages_are_the_ones_the_browser_shows() -> None:
    # fileRules.ts repeats these strings word for word.
    assert MSG_TYPE == "Only PDF and Word (.docx) files can be uploaded."
    assert MSG_TOO_LARGE == "This file is larger than 25 MB."
    assert MSG_EMPTY == "This file is empty."
    assert MSG_NOT_PDF == "This file is named .pdf but its contents are not a PDF."
    assert MSG_NOT_DOCX == "This file is named .docx but its contents are not a Word document."
