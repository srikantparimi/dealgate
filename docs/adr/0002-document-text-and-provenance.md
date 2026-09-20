# ADR 0002 — One text seam for PDF and Word; provenance refs are block ordinals

Date: 2026-09-20
Status: Accepted (S10-04)

## Context

`docs/backlog/s10-sow-upload.md` specifies the upload takes "the PDF or DOCX",
`docs/directives/sow-first.md` §1 says "SOW file (PDF/Word)", the router
allowlists the DOCX MIME type and the UI advertises `accept=".docx"`. But
nothing in the codebase could read a Word file: text extraction was `pypdf`
in three independent places (`document_type`, `sow_extract`,
`integrations/textract`).

A real Word SOW uploaded to the deployed app was handed to a PDF parser,
yielded zero pages, fell through the density check to a null classifier, and
came back to the user as **"This file does not look like a SOW."** There was no
test covering `.docx` in either direction.

Separately, CLAUDE.md rule 6 requires every extracted field to carry a page
reference. A `.docx` has no pages.

## Decision

**One seam.** `api/app/services/document_text.py` is the only place that turns
bytes into text. It dispatches on magic bytes (not the caller-supplied MIME
type, which is routinely wrong) and returns ordered, numbered `TextBlock`s.
`document_type`, `sow_extract` and the upload pipeline all route through it.

**Stdlib, not python-docx.** A `.docx` is a zip; reading paragraphs and tables
*in document order* means walking `w:body`'s children, which `python-docx` does
not save you from — it exposes `.paragraphs` and `.tables` as separate
sequences. It would add `lxml`, a C extension, to an image with no C dependency
beyond `libpq`. `docx2txt` discards tables entirely, which is disqualifying:
SOWs carry schedules, milestones and rate grids in tables. Tables render as
pipe-delimited rows so the grid survives into the model prompt.

Accepted limits: the walk sees `w:body` only, so headers/footers, footnotes,
text boxes (`w:txbxContent`) and `w:altChunk` are not read. Revisit if a real
SOW turns up with commercial terms in a text box. Legacy `.doc` (OLE2) is
rejected with a message telling the user to re-save.

**`page_ref` keeps its name and its `int >= 1` contract; its meaning becomes
"block ordinal", and the unit travels beside it.**

- PDF: block index *is* the page number. Nothing changes; existing fixtures,
  stubs and schema validation are untouched.
- DOCX: block index is the body-child ordinal. `ref_unit` is `"block"`.
- The unit is recorded once per version at
  `extracted_fields.metadata.ref_unit`, beside the existing `extract_source`.

## Alternatives rejected

**Synthesise page numbers** by chunking characters at ~3000 and calling the
result "page N". Rejected: that is a fabricated number presented as a citation.
The whole point of rule 6 is that a human can verify a field against the source
document, and a made-up page number cannot be verified. A block ordinal is a
real, checkable address.

**A separate `block_ref` field** alongside `page_ref`. Rejected: it means a
schema migration, a change to `_validate_field`, and updating six PDF fixtures
and every stub, to express something the existing integer already carries.

## Consequences

- The confirm screen must read `ref_unit` to label a citation — `p.12` for a
  PDF, `¶12` for a Word file. Labelling a Word ref "p.12" is misleading
  provenance. **Not yet done in the UI** (`provenance.tsx` still hardcodes
  `p.`); the data is correct and stored, the label is not.
- Textract is now gated to PDFs. It never accepted Word files; previously a
  `.docx` looked like a 0-page PDF and was routed to OCR, which could only fail.
