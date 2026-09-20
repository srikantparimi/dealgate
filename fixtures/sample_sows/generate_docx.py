"""Deterministic .docx fixture builder (S10-04).

Sibling of ``generate.py`` (which builds the PDF fixtures with reportlab).
Word files are built here from literal WordprocessingML inside a zip, for the
same reasons ``app/services/document_text`` parses them that way: no new
dependency, and byte-for-byte reproducible output when every ``ZipInfo``
carries a fixed timestamp.

The fixture deliberately mirrors the *shape* of a real assessment SOW — a
"STATEMENT OF WORK" heading, a parties clause naming the client, a fixed fee
written in prose rather than a rate table, a schedule table, and a bracketed
``[End Date]`` placeholder — so it exercises table extraction, prose-money
extraction and the disputed-placeholder path in one file.

The client is fictional. CLAUDE.md rule 8: no real client data in fixtures.
"""

from __future__ import annotations

import pathlib
import zipfile

# Fixed timestamp so the archive is reproducible.
_ZIP_DATE = (2026, 1, 1, 0, 0, 0)

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _para(text: str) -> str:
    return f'<w:p><w:r><w:t xml:space="preserve">{_esc(text)}</w:t></w:r></w:p>'


def _row(cells: list[str]) -> str:
    tcs = "".join(
        f'<w:tc><w:tcPr/><w:p><w:r><w:t xml:space="preserve">{_esc(c)}</w:t></w:r></w:p></w:tc>'
        for c in cells
    )
    return f"<w:tr>{tcs}</w:tr>"


def _table(rows: list[list[str]]) -> str:
    return f'<w:tbl><w:tblPr/>{"".join(_row(r) for r in rows)}</w:tbl>'


# --- the fixture body -----------------------------------------------------

_BODY_PARTS: list[str] = [
    _para("STATEMENT OF WORK"),
    _para(
        'This Statement of Work ("SOW") is made pursuant to and governed by the '
        "Master Services Agreement entered by and between Contoso Data Services, "
        'LLC ("Contoso" or "Client"), and SmarTek21 ("Supplier") dated '
        "[Agreement Date]."
    ),
    _para("Project Background"),
    _para(
        "Client has engaged Supplier to conduct a Phase 1 Discovery and "
        "High-Level Assessment of its order-management estate."
    ),
    _para("Scope of Work"),
    _para(
        "Supplier will run a three-day onsite discovery, a use-case inventory "
        "workshop, and a findings playback."
    ),
    _para("Schedule"),
    _table(
        [
            ["Day", "Date", "Focus"],
            ["Day 1", "Mon, Mar 2, 2026", "Kickoff and executive interviews"],
            ["Day 2", "Tue, Mar 3, 2026", "Technical review and process mapping"],
            ["Day 3", "Wed, Mar 4, 2026", "Feasibility and roadmap session"],
        ]
    ),
    _para("Deliverables"),
    _para("1. Current-state assessment report."),
    _para("2. Prioritised use-case inventory."),
    _para("3. High-level roadmap and indicative costs."),
    _para("Fees"),
    _para(
        "Client shall pay Supplier a fixed fee of $75,000.00 for this "
        "engagement. Invoices are payable Net 30 from the invoice date."
    ),
    _para("Term"),
    _para(
        "This SOW commences on Mar 2, 2026 and continues until [End Date] "
        "unless terminated earlier in accordance with the Agreement."
    ),
    _para("Assumptions"),
    _para("Client makes stakeholders available for scheduled sessions."),
    _para("Exclusions"),
    _para("Implementation, licence procurement and managed services are excluded."),
]

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<w:document xmlns:w="{_W_NS}"><w:body>'
    + "".join(_BODY_PARTS)
    + "<w:sectPr/></w:body></w:document>"
)

FIXTURE_NAME = "08_assessment_fixed_fee.docx"


def build(out_dir: pathlib.Path | None = None) -> pathlib.Path:
    """Write the fixture and return its path."""

    out_dir = out_dir or pathlib.Path(__file__).parent
    target = out_dir / FIXTURE_NAME
    parts = {
        "[Content_Types].xml": _CONTENT_TYPES,
        "_rels/.rels": _RELS,
        "word/document.xml": _DOCUMENT_XML,
    }
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return target


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
