"""One text-extraction seam for every document the pipeline reads (S10-04).

Before this module, three call sites each reached for :mod:`pypdf`
independently (``document_type``, ``sow_extract``, ``integrations.textract``),
which meant a Word file — accepted by the upload router and advertised by the
UI — hit a PDF-only parser, yielded zero pages, and was rejected as "not a
SOW". ``docs/backlog/s10-sow-upload.md`` calls for "the PDF or DOCX" and
``docs/sow-first-principles.md`` for "SOW file (PDF/Word)".

Everything that needs the text of an uploaded document goes through
:func:`extract_document_text`.

Why stdlib ``zipfile`` + ``ElementTree`` and not ``python-docx``
---------------------------------------------------------------
A ``.docx`` is a zip whose ``word/document.xml`` holds the body. To read
paragraphs and tables *in document order* you have to walk ``w:body``'s
children yourself — ``python-docx`` exposes ``.paragraphs`` and ``.tables``
as separate sequences, so it does not save that walk. It would, however, pull
``lxml`` (a C extension) into an image that currently carries no C dependency
beyond ``libpq``. ``docx2txt`` flattens tables away entirely, which is
disqualifying: real SOWs carry schedules, milestones and rate grids in tables.

Known limits, deliberately accepted
-----------------------------------
This walks ``w:body`` only, so it does not see headers/footers
(``word/header*.xml``), footnotes, text boxes (``w:txbxContent``) or
``w:altChunk`` embedded content. If a real SOW turns up with commercial terms
in a text box, revisit. Legacy ``.doc`` (OLE2) is not a zip and is rejected
with a clear message rather than silently returning nothing.

Provenance
----------
Blocks are numbered from 1 in document order. For a PDF the block index *is*
the page number. A ``.docx`` has no pages, so the index is the body-child
ordinal and ``ref_unit`` says ``"block"``. We do not synthesise page numbers
by chunking characters: an invented locator is a fabricated number, and the
ordinal is a real, verifiable address into the file.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from io import BytesIO

__all__ = [
    "DocumentText",
    "TextBlock",
    "UnreadableDocument",
    "extract_document_text",
    "is_low_density",
    "numbered_prompt_text",
    "pages_text",
    "text_document_from_string",
    "total_chars",
]

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# WordprocessingML namespace.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Chars per page below which a PDF is assumed image-only and worth OCR.
# Mirrors the threshold `document_type` and `sow_extract` already used.
_PDF_MIN_CHARS_PER_PAGE = 40

# A .docx carries a real text layer or it carries nothing — there is no OCR
# path for Word — so the floor is a whole-document one, not per page.
_DOCX_MIN_TOTAL_CHARS = 200

# Zip-bomb guard: refuse anything whose uncompressed size is absurd for a SOW.
_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


class UnreadableDocument(Exception):
    """The bytes are not a document we can read.

    Raised for a corrupt zip, a password-protected file, a legacy ``.doc``,
    or anything whose magic bytes match neither PDF nor DOCX. The router
    turns this into a 422 with an actionable message — never a 500.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class TextBlock:
    """One addressable unit of text.

    ``index`` is the 1-based provenance locator quoted back as ``page_ref``.
    """

    index: int
    kind: str  # "page" | "paragraph" | "table"
    text: str
    page: int | None = None  # PDF only; None for DOCX


@dataclass(frozen=True)
class DocumentText:
    blocks: tuple[TextBlock, ...]
    kind: str  # "pdf" | "docx"
    ref_unit: str  # "page" | "block"
    page_count: int | None = None


# --- format sniffing ------------------------------------------------------


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def _looks_like_zip(data: bytes) -> bool:
    # Normal archive, empty archive, spanned archive.
    return data[:4] in (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _looks_like_ole2(data: bytes) -> bool:
    """Legacy .doc / .xls compound-file magic."""
    return data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


# --- PDF ------------------------------------------------------------------


def _pdf_blocks(data: bytes) -> tuple[TextBlock, ...]:
    try:
        from pypdf import PdfReader  # local import — keep boot cheap

        reader = PdfReader(BytesIO(data))
        blocks: list[TextBlock] = []
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — one bad page must not kill the run
                text = ""
            blocks.append(
                TextBlock(index=page_no, kind="page", text=text, page=page_no)
            )
        return tuple(blocks)
    except UnreadableDocument:
        raise
    except Exception as exc:
        raise UnreadableDocument(f"could not parse PDF: {exc}") from exc


# --- DOCX -----------------------------------------------------------------


def _para_text(node: ET.Element) -> str:
    """Flatten one ``w:p`` into a string, honouring tabs and line breaks."""

    parts: list[str] = []
    for child in node.iter():
        tag = child.tag
        if tag == f"{_W}t":
            parts.append(child.text or "")
        elif tag == f"{_W}tab":
            parts.append("\t")
        elif tag in (f"{_W}br", f"{_W}cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _table_text(node: ET.Element) -> str:
    """Render one ``w:tbl`` as pipe-delimited rows.

    Keeping the grid is the whole point: a milestone table flattened to prose
    loses the row/column pairing that makes dates and amounts extractable.
    """

    rows: list[str] = []
    for tr in node.findall(f"{_W}tr"):
        cells: list[str] = []
        for tc in tr.findall(f"{_W}tc"):
            cell = " ".join(
                t for t in (_para_text(p) for p in tc.findall(f"{_W}p")) if t
            )
            cells.append(cell.strip())
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _docx_blocks(data: bytes) -> tuple[TextBlock, ...]:
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except Exception as exc:
        raise UnreadableDocument(f"not a readable .docx container: {exc}") from exc

    with zf:
        total = sum(i.file_size for i in zf.infolist())
        if total > _MAX_UNCOMPRESSED_BYTES:
            raise UnreadableDocument("document is implausibly large; refusing to read")

        try:
            xml_bytes = zf.read("word/document.xml")
        except KeyError as exc:
            raise UnreadableDocument(
                "zip archive has no word/document.xml — not a Word document"
            ) from exc
        except Exception as exc:
            raise UnreadableDocument(f"could not read .docx body: {exc}") from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise UnreadableDocument(f"malformed WordprocessingML: {exc}") from exc

    body = root.find(f"{_W}body")
    if body is None:
        raise UnreadableDocument("Word document has no body")

    blocks: list[TextBlock] = []
    index = 0
    for child in body:
        if child.tag == f"{_W}p":
            text = _para_text(child)
            kind = "paragraph"
        elif child.tag == f"{_W}tbl":
            text = _table_text(child)
            kind = "table"
        else:
            continue  # sectPr and friends carry no body text
        if not text:
            continue  # empty spacer paragraphs are not addressable units
        index += 1
        blocks.append(TextBlock(index=index, kind=kind, text=text, page=None))

    return tuple(blocks)


# --- public API -----------------------------------------------------------


def extract_document_text(
    file_bytes: bytes, content_type: str | None = None
) -> DocumentText:
    """Return the document's text as ordered, numbered blocks.

    The format is decided by magic bytes, not by ``content_type`` — the
    browser-supplied MIME type is caller-controlled and routinely wrong
    (``application/octet-stream`` for a perfectly good PDF). ``content_type``
    is accepted for logging and for a tie-break only.

    Raises :class:`UnreadableDocument` when the bytes are not a PDF or DOCX
    we can parse.
    """

    if not file_bytes:
        raise UnreadableDocument("uploaded file is empty")

    if _looks_like_pdf(file_bytes):
        blocks = _pdf_blocks(file_bytes)
        return DocumentText(
            blocks=blocks, kind="pdf", ref_unit="page", page_count=len(blocks)
        )

    if _looks_like_zip(file_bytes):
        blocks = _docx_blocks(file_bytes)
        return DocumentText(
            blocks=blocks, kind="docx", ref_unit="block", page_count=None
        )

    if _looks_like_ole2(file_bytes):
        raise UnreadableDocument(
            "this looks like a legacy .doc file; re-save it as .docx or PDF"
        )

    raise UnreadableDocument(
        f"unrecognised file format (content_type={content_type!r})"
    )


def pages_text(doc: DocumentText) -> list[str]:
    """Back-compat shim for callers that want a plain list of page strings."""

    return [b.text for b in doc.blocks]


def total_chars(doc: DocumentText) -> int:
    return sum(len(b.text) for b in doc.blocks)


def is_low_density(doc: DocumentText) -> bool:
    """True when the text layer is too thin to classify from — i.e. OCR territory.

    Only meaningful for PDFs. A ``.docx`` either has a text layer or is empty;
    there is no OCR fallback for Word, so the check is whole-document.
    """

    if not doc.blocks:
        return True
    if doc.kind == "pdf":
        return (total_chars(doc) / len(doc.blocks)) < _PDF_MIN_CHARS_PER_PAGE
    return total_chars(doc) < _DOCX_MIN_TOTAL_CHARS


def numbered_prompt_text(doc: DocumentText, *, max_chars: int = 240_000) -> str:
    """Render the document for the extractor, each block tagged ``[[n]]``.

    The model is told to quote that number back as ``page_ref``, which is how
    every extracted field gets a verifiable address in the source document
    (CLAUDE.md rule 6). Truncation is explicit and visible rather than silent.
    """

    out: list[str] = []
    used = 0
    for block in doc.blocks:
        piece = f"[[{block.index}]] {block.text}"
        if used + len(piece) > max_chars:
            out.append(
                f"\n[[truncated after block {block.index - 1} of {len(doc.blocks)}]]"
            )
            break
        out.append(piece)
        used += len(piece)
    return "\n\n".join(out)


def text_document_from_string(text: str, *, kind: str = "ocr") -> DocumentText:
    """Wrap already-extracted plain text (e.g. Textract OCR output) as blocks.

    Lets the OCR path and the native-parse path hand the extractor the same
    shape, so there is one prompt format and one provenance scheme rather
    than two. Blocks split on blank lines, which is what OCR emits between
    paragraphs.
    """

    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    blocks = tuple(
        TextBlock(index=i, kind="paragraph", text=c, page=None)
        for i, c in enumerate(chunks, start=1)
    )
    return DocumentText(blocks=blocks, kind=kind, ref_unit="block", page_count=None)


def normalise_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()
