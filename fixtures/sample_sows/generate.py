"""Deterministic PDF generator for the six sample SOW fixtures (S9 wave 2).

The script writes six PDFs into this directory. Byte-for-byte
reproducibility matters — the E2E suite hashes them to prove the
fixtures did not drift between runs. Every reportlab knob that would
otherwise leak wall-clock or random state is pinned:

- Page metadata (``author``, ``title``, ``creator``, ``subject``,
  ``keywords``) is set explicitly, no defaults.
- ``invariant=1`` is passed to :class:`~reportlab.pdfgen.canvas.Canvas`
  so reportlab bakes a fixed doc id + timestamp into the trailer.
- The ``SOURCE_DATE_EPOCH`` env var is set for the process; reportlab's
  ``invariant`` mode reads it as the creation-date seed.

Usage::

    python fixtures/sample_sows/generate.py            # rebuild PDFs
    python fixtures/sample_sows/generate.py --validate # + validate stubs
    python fixtures/sample_sows/generate.py --hash     # + print sha256

The layout of each PDF is driven by :mod:`extraction_stubs` so text on
each page lines up with the ``page_ref`` field in the canned extract.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

# Pin the epoch *before* importing reportlab so its invariant metadata
# reads the same value on every run.
_FIXED_EPOCH = "1735689600"  # 2025-01-01T00:00:00Z, chosen and pinned.
os.environ.setdefault("SOURCE_DATE_EPOCH", _FIXED_EPOCH)

# Make `extraction_stubs` importable regardless of cwd.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from extraction_stubs import FIXTURES, export_json  # noqa: E402

from reportlab.lib.pagesizes import LETTER  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402


PDF_TITLES: dict[str, str] = {
    "01_staff_aug_us.pdf": "Statement of Work — Data Platform Staff Augmentation (US)",
    "02_managed_service_india.pdf": "Statement of Work — 24x7 Managed Service (India)",
    "03_fixed_price_mixed.pdf": "Statement of Work — Fixed Price Modernisation (US + India)",
    "04_assessment_4week.pdf": "Statement of Work — 4-Week Data Platform Assessment",
    "05_tm_capped.pdf": "Statement of Work — Time and Materials with Cap",
    "06_below_floor.pdf": "Statement of Work — Strategic Seed Engagement",
}


# -------------------------------------------------------------------------
# Page composers.
#
# Each fixture writes one page per `page_ref` in the extraction stub
# (`page_ref`s are 1..7). Text is deliberately dense enough for pypdf to
# recover cleanly, but the E2E specs seed the stub map directly rather
# than depend on OCR — the PDFs prove the fields *exist* in a real
# document, the stubs prove what the pipeline should think they say.
# -------------------------------------------------------------------------


def _header(c: canvas.Canvas, title: str, page_n: int) -> None:
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1 * inch, 10.25 * inch, title)
    c.setFont("Helvetica", 9)
    c.drawRightString(7.5 * inch, 10.25 * inch, f"Page {page_n}")
    c.line(1 * inch, 10.15 * inch, 7.5 * inch, 10.15 * inch)


def _paragraph(c: canvas.Canvas, y: float, text: str, *, size: int = 10) -> float:
    """Draw a paragraph, wrapping at ~90 chars. Returns the new y."""

    c.setFont("Helvetica", size)
    max_chars = 92
    for raw_line in text.splitlines() or [text]:
        words = raw_line.split()
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > max_chars and line:
                c.drawString(1 * inch, y, line)
                y -= 14
                line = word
            else:
                line = candidate
        if line:
            c.drawString(1 * inch, y, line)
            y -= 14
        y -= 4
    return y


def _kv(c: canvas.Canvas, y: float, key: str, value: str) -> float:
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, f"{key}:")
    c.setFont("Helvetica", 10)
    c.drawString(2.2 * inch, y, value)
    return y - 16


def _bulleted(c: canvas.Canvas, y: float, items: list[str]) -> float:
    c.setFont("Helvetica", 10)
    for item in items:
        c.drawString(1.15 * inch, y, "• " + item)
        y -= 14
    return y - 4


def _write_page_1_scope(c: canvas.Canvas, title: str, fields: dict[str, Any]) -> None:
    _header(c, title, 1)
    y = 9.6 * inch
    y = _paragraph(c, y, "1. Scope")
    y = _paragraph(c, y, fields["scope_summary"]["value"])


def _write_page_2_commercial(c: canvas.Canvas, title: str, fields: dict[str, Any]) -> None:
    _header(c, title, 2)
    y = 9.6 * inch
    y = _paragraph(c, y, "2. Commercial terms")
    y = _kv(c, y, "Price", f"{fields['currency']['value']} {fields['price']['value']}")
    y = _kv(c, y, "Currency", fields["currency"]["value"])
    y = _kv(c, y, "Billing basis", str(fields["billing_basis"]["value"]))
    y = _kv(
        c,
        y,
        "Engagement type (suggested)",
        str(fields["engagement_type_suggested"]["value"]),
    )


def _write_page_3_term(c: canvas.Canvas, title: str, fields: dict[str, Any]) -> None:
    _header(c, title, 3)
    y = 9.6 * inch
    y = _paragraph(c, y, "3. Term and notice")
    y = _kv(c, y, "Term start", str(fields["term_start"]["value"]))
    y = _kv(c, y, "Term end", str(fields["term_end"]["value"]))
    y = _kv(c, y, "Notice date", str(fields["notice_date"]["value"]))


def _write_page_4_deliverables(
    c: canvas.Canvas, title: str, fields: dict[str, Any], aux: dict[str, Any]
) -> None:
    _header(c, title, 4)
    y = 9.6 * inch
    y = _paragraph(c, y, "4. Deliverables")
    delivs = fields["deliverables"]["value"]
    if isinstance(delivs, list) and delivs:
        y = _bulleted(c, y, [str(d) for d in delivs])
    else:
        y = _paragraph(c, y, "None specified in this SOW.")

    # Optional resource table on the same page for staff_aug / T&M.
    resource_table = aux.get("resource_table") if aux else None
    if resource_table:
        y -= 4
        y = _paragraph(c, y, "4a. Resource table")
        c.setFont("Helvetica-Bold", 9)
        c.drawString(1.15 * inch, y, "Role")
        c.drawString(3.0 * inch, y, "Seniority")
        c.drawString(4.1 * inch, y, "Location")
        c.drawString(5.1 * inch, y, "Hours")
        c.drawString(6.0 * inch, y, "Rate ($/h)")
        y -= 12
        c.setFont("Helvetica", 9)
        for row in resource_table:
            c.drawString(1.15 * inch, y, str(row.get("role", "")))
            c.drawString(3.0 * inch, y, str(row.get("seniority", "")))
            c.drawString(4.1 * inch, y, str(row.get("location", "")))
            c.drawString(5.1 * inch, y, str(row.get("hours", "")))
            c.drawString(6.0 * inch, y, str(row.get("hourly_rate", "")))
            y -= 12

    # Managed-service coverage details on the same page.
    if aux and "coverage_hours" in aux:
        y -= 8
        y = _paragraph(c, y, "4b. Coverage")
        y = _kv(c, y, "Coverage hours per week", str(aux["coverage_hours"]))
        y = _kv(c, y, "Monthly fee (USD)", str(aux.get("monthly_fee", "")))
        y = _kv(c, y, "Delivery location", str(aux.get("primary_location", "")))


def _write_page_5_milestones(
    c: canvas.Canvas, title: str, fields: dict[str, Any]
) -> None:
    _header(c, title, 5)
    y = 9.6 * inch
    y = _paragraph(c, y, "5. Milestones")
    ms = fields["milestones"]["value"]
    if isinstance(ms, list) and ms:
        y = _bulleted(
            c,
            y,
            [f"{m['name']} — {m['date']}" for m in ms if isinstance(m, dict)],
        )
    else:
        y = _paragraph(c, y, "No milestones specified — engagement is time-based.")

    # Acceptance / assumptions / exclusions land on page 5 or 6 depending
    # on whether we already emitted them above; keep it simple — the
    # fixture stubs' page_refs are the source of truth.


def _write_page_generic(
    c: canvas.Canvas,
    title: str,
    page_n: int,
    heading: str,
    fields: dict[str, Any],
    key_names: list[tuple[str, str]],
) -> None:
    _header(c, title, page_n)
    y = 9.6 * inch
    y = _paragraph(c, y, heading)
    for label, field_name in key_names:
        val = fields[field_name]["value"]
        if isinstance(val, list):
            if val and isinstance(val[0], dict):
                y = _paragraph(c, y, f"{label}:")
                y = _bulleted(
                    c,
                    y,
                    [
                        f"{item.get('name', '')} — {item.get('role', item.get('date', ''))}"
                        for item in val
                    ],
                )
            else:
                y = _paragraph(c, y, f"{label}:")
                y = _bulleted(c, y, [str(v) for v in val])
        else:
            y = _paragraph(c, y, f"{label}: {val}")


def _compose(name: str, fixture: dict[str, Any], out_path: Path) -> None:
    fields = fixture["fields"]
    aux = fixture.get("aux", {})
    title = PDF_TITLES[name]

    c = canvas.Canvas(
        str(out_path),
        pagesize=LETTER,
        invariant=1,
    )
    c.setAuthor("DealGate fixture generator")
    c.setTitle(title)
    c.setCreator("DealGate fixture generator")
    c.setSubject("Deterministic sample SOW for E2E fixtures")
    c.setKeywords("dealgate sow fixture deterministic")

    # Page 1 — scope.
    _write_page_1_scope(c, title, fields)
    c.showPage()

    # Page 2 — commercial terms.
    _write_page_2_commercial(c, title, fields)
    c.showPage()

    # Page 3 — term + notice.
    _write_page_3_term(c, title, fields)
    c.showPage()

    # Page 4 — deliverables (+ resource table / coverage if present).
    _write_page_4_deliverables(c, title, fields, aux)
    c.showPage()

    # Page 5 — milestones.
    _write_page_5_milestones(c, title, fields)
    c.showPage()

    # Page 6 — acceptance / assumptions / exclusions.
    _write_page_generic(
        c,
        title,
        6,
        "6. Acceptance and assumptions",
        fields,
        [
            ("Acceptance criteria", "acceptance_criteria"),
            ("Assumptions", "assumptions"),
            ("Exclusions", "exclusions"),
        ],
    )
    c.showPage()

    # Page 7 — signatories.
    _write_page_generic(
        c,
        title,
        7,
        "7. Signatories",
        fields,
        [("Signatories", "signatories")],
    )
    c.showPage()

    c.save()


def _validate_all() -> None:
    """Self-check: every fixture must pass ``validate_extract``."""

    # Import here so `generate.py` still runs even if the api package is
    # not installed — validation is opt-in.
    from app.integrations.bedrock_sow_extract import validate_extract  # type: ignore

    for name, fixture in FIXTURES.items():
        payload = {
            "fields": fixture["fields"],
            "model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "prompt_version": "sow-v1",
        }
        try:
            validate_extract(payload)
        except Exception as exc:  # noqa: BLE001 — surface any schema drift
            raise SystemExit(f"stub {name} failed validate_extract: {exc}") from exc
    print(f"validated {len(FIXTURES)} extraction stubs against validate_extract")


def _hash_all(out_dir: Path) -> None:
    for name in sorted(FIXTURES):
        path = out_dir / name
        h = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{h}  {name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate each stub against api.app.integrations.bedrock_sow_extract.validate_extract",
    )
    parser.add_argument(
        "--hash",
        action="store_true",
        help="Print sha256 of each generated PDF",
    )
    parser.add_argument(
        "--out",
        default=str(_HERE),
        help="Output directory (defaults to fixtures/sample_sows/)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, fixture in sorted(FIXTURES.items()):
        _compose(name, fixture, out_dir / name)

    # Also emit a JSON export the TS e2e layer consumes.
    export_json(_HERE / "extraction_stubs.json")

    print(
        f"wrote {len(FIXTURES)} PDFs to {out_dir} "
        f"(SOURCE_DATE_EPOCH={os.environ.get('SOURCE_DATE_EPOCH')})"
    )

    if args.validate:
        _validate_all()
    if args.hash:
        _hash_all(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
