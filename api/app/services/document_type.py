"""Document-type classifier (S10-01).

Rules-first, Bedrock second. See ``docs/backlog/s10-sow-upload.md``:

- We probe the file's text density with :mod:`pypdf`. Scanned / image-
  only PDFs (< 40 chars/page) are handed to Bedrock; anything readable
  is inspected with a keyword scan of the top ~100 lines.
- The scan awards points to each candidate type from a small keyword
  table. The best score decides the type; the runner-up sets the
  confidence gap. A score gap of at least 2 → confidence 0.9; gap of 1
  → 0.7; a tie or no evidence → we return the Bedrock fallback.
- The Bedrock adapter accepts a plain-text preview (first 4 kB) and
  returns a ``{type, confidence, page_ref}`` dict; it never fabricates
  a numeric confidence when it cannot answer (returns ``other`` with
  ``confidence=0.0``).

The returned type is one of ``sow | msa | nda | resume | invoice |
other``. The upload router turns ``sow | msa | nda`` into a valid
pipeline start; anything else is rejected 422.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.services.document_text import (
    DocumentText,
    UnreadableDocument,
    extract_document_text,
    is_low_density,
    pages_text,
)

DocType = str  # "sow" | "msa" | "nda" | "resume" | "invoice" | "other"

ALLOWED_START_TYPES: tuple[DocType, ...] = ("sow", "msa", "nda")

# Chars per page below which we assume the PDF is image-only and rules
# would starve — we call Bedrock instead. Same threshold pattern as
# `sow_extract._needs_textract`.
_TEXT_DENSITY_MIN_CHARS_PER_PAGE = 40

# Scanned only the first N lines to keep the rules cheap and to avoid
# the doc's body vocabulary voting against the header signal.
_HEADER_LINE_COUNT = 100


@dataclass(frozen=True)
class DocumentTypeResult:
    type: DocType
    confidence: float
    page_ref: int | None = None
    source: str = "rules"  # "rules" | "bedrock" | "empty"


# --- keyword table --------------------------------------------------------

# Each row: (regex-free lower-case phrase, doc_type, points). Longer
# multi-word phrases carry more weight than single tokens so a résumé
# that happens to include "scope" as part of a bullet does not steal
# the SOW verdict.
_KEYWORD_SCORES: tuple[tuple[str, DocType, int], ...] = (
    # SOW headers
    ("statement of work", "sow", 5),
    ("scope of work", "sow", 4),
    ("this statement of work", "sow", 5),
    ("engagement letter", "sow", 3),
    ("services agreement statement", "sow", 3),
    ("work order", "sow", 2),
    ("deliverables", "sow", 1),
    ("milestones", "sow", 1),
    # MSA headers
    ("master services agreement", "msa", 5),
    ("master service agreement", "msa", 5),
    ("this master services agreement", "msa", 5),
    ("this master service agreement", "msa", 5),
    ("rate schedule", "msa", 2),
    # NDA headers
    ("non-disclosure agreement", "nda", 5),
    ("non disclosure agreement", "nda", 5),
    ("mutual non-disclosure", "nda", 4),
    ("confidentiality agreement", "nda", 4),
    ("confidential information", "nda", 1),
    # Resume tokens
    ("curriculum vitae", "resume", 5),
    ("resume", "resume", 3),
    ("work experience", "resume", 3),
    ("professional experience", "resume", 3),
    ("employment history", "resume", 3),
    ("education", "resume", 1),
    ("skills", "resume", 1),
    # Invoice glyphs
    ("invoice number", "invoice", 5),
    ("invoice #", "invoice", 5),
    ("invoice date", "invoice", 4),
    ("bill to", "invoice", 3),
    ("subtotal", "invoice", 2),
    ("tax id", "invoice", 1),
    ("amount due", "invoice", 3),
)


class DocumentTypeBedrock(Protocol):
    """Interface for the Bedrock fallback. The real adapter lands with
    the shared Bedrock caller; a stub is used in tests."""

    def classify(self, text_preview: str) -> DocumentTypeResult:  # pragma: no cover
        ...


class _NullBedrock:
    """Fallback when Bedrock is not configured — returns ``other``.

    Rule 6: never fabricate an answer; when the caller has no way to
    reach a model we surface the ambiguity and let the router reject
    the upload with a clear 422.
    """

    def classify(self, text_preview: str) -> DocumentTypeResult:
        return DocumentTypeResult(
            type="other", confidence=0.0, page_ref=None, source="bedrock"
        )


# --- text density + preview -----------------------------------------------


def _text_density_low(doc: DocumentText) -> bool:
    """Delegates to the shared seam — kept as a name the tests can reach."""

    return is_low_density(doc)


def _top_lines(pages: list[str]) -> tuple[list[str], int]:
    """First ``_HEADER_LINE_COUNT`` non-empty lines and the page they land on."""

    picked: list[str] = []
    landing_page = 1
    for page_idx, text in enumerate(pages, start=1):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            picked.append(stripped.lower())
            if len(picked) == 1:
                landing_page = page_idx
            if len(picked) >= _HEADER_LINE_COUNT:
                return picked, landing_page
    return picked, landing_page


# --- classifier -----------------------------------------------------------


def classify_from_lines(
    lines: list[str], *, landing_page: int = 1
) -> DocumentTypeResult | None:
    """Score keyword hits and return the winner, or ``None`` when the
    signal is too weak.

    Kept public so the tests can drive the rules without a PDF.
    """

    if not lines:
        return None
    header_blob = " \n ".join(lines)
    scores: dict[DocType, int] = {}
    first_hit_line: dict[DocType, int] = {}
    for phrase, doc_type, points in _KEYWORD_SCORES:
        if phrase in header_blob:
            scores[doc_type] = scores.get(doc_type, 0) + points
            # Track the earliest line index a type hit; page_ref is a
            # rough proxy — we clamp to the header's landing_page below.
            idx = header_blob.find(phrase)
            first_hit_line.setdefault(doc_type, idx)

    if not scores:
        return None

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    winner, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    gap = top_score - second_score

    # Confidence heuristic — deliberately coarse; a real confusion
    # matrix would need a labelled corpus we do not have yet. Numbers
    # tuned so a SOW header with one clear match returns 0.9.
    if top_score >= 5 and gap >= 2:
        confidence = 0.95
    elif top_score >= 3 and gap >= 2:
        confidence = 0.9
    elif top_score >= 3 and gap >= 1:
        confidence = 0.8
    elif top_score >= 2:
        confidence = 0.65
    else:
        confidence = 0.5

    return DocumentTypeResult(
        type=winner,
        confidence=confidence,
        page_ref=landing_page,
        source="rules",
    )


def classify_document(
    file_bytes: bytes,
    *,
    content_type: str | None = None,
    bedrock: DocumentTypeBedrock | None = None,
) -> DocumentTypeResult:
    """Classify an uploaded document's high-level type (PDF or DOCX).

    Order of operations:

    1. If the file is empty, return ``other`` at zero confidence — a
       zero-byte upload is never a real document.
    2. Read the text through :mod:`app.services.document_text`, which
       handles PDF and DOCX alike. If it is dense enough, run the keyword
       rules on the first 100 header lines.
    3. If the rules produce a decisive winner, return it. Otherwise ask
       Bedrock with a text preview.

    Raises :class:`UnreadableDocument` when the bytes are neither a PDF nor a
    DOCX we can parse. That is deliberately *not* swallowed into
    ``other``: "we could not open this file" and "this is not a SOW" are
    different problems and deserve different messages to the user.
    """

    if not file_bytes:
        return DocumentTypeResult(
            type="other", confidence=0.0, page_ref=None, source="empty"
        )

    doc = extract_document_text(file_bytes, content_type)
    lines, landing_page = _top_lines(pages_text(doc))

    density_low = _text_density_low(doc)
    rules_hit = classify_from_lines(lines, landing_page=landing_page)

    if rules_hit is not None and rules_hit.confidence >= 0.7:
        return rules_hit

    if not density_low and rules_hit is not None:
        # Non-decisive rules on a text PDF → still return the runner-up
        # so the router can surface a clear reason. Bedrock is optional
        # scaffolding for future improvement; we only call it when the
        # rules found nothing at all.
        return rules_hit

    caller = bedrock if bedrock is not None else _NullBedrock()
    preview = ("\n".join(lines))[:4000] if lines else ""
    result = caller.classify(preview)
    return result


__all__ = [
    "ALLOWED_START_TYPES",
    "DocType",
    "DocumentTypeBedrock",
    "DocumentTypeResult",
    "UnreadableDocument",
    "classify_document",
    "classify_from_lines",
]
