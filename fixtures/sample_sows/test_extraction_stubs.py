"""Pytest that validates the six extraction stubs (S9 wave 2).

Run from the api virtualenv so `app.integrations.bedrock_sow_extract`
resolves::

    cd api && . .venv/bin/activate
    pytest ../fixtures/sample_sows/test_extraction_stubs.py -q

The E2E specs depend on these payloads matching:

- The Bedrock extract JSON schema (:func:`validate_extract`).
- The engagement classifier's rule-first path
  (:func:`engagement_classifier.classify` — every fixture must land on
  its declared ``expected_engagement_type`` via its declared
  ``expected_rule``).
- The set of six fixture PDFs actually present on disk.

Anyone touching the stubs must run this test before pushing so the
Wave-2 E2E specs stay green.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest


# Make the sibling `extraction_stubs.py` module importable regardless of
# pytest's rootdir. `conftest.py` isn't guaranteed to exist here — we
# only need this one file, so the manual sys.path prepend is fine.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from extraction_stubs import FIXTURES  # noqa: E402


# ---------------------------------------------------------------------------
# 1. Every stub validates against the Bedrock extract JSON schema.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_stub_matches_extract_schema(name: str) -> None:
    from app.integrations.bedrock_sow_extract import (
        EXTRACT_MODEL,
        EXTRACT_PROMPT_VERSION,
        validate_extract,
    )

    fixture = FIXTURES[name]
    payload = {
        "fields": fixture["fields"],
        "model": EXTRACT_MODEL,
        "prompt_version": EXTRACT_PROMPT_VERSION,
    }
    result = validate_extract(payload)
    # Sanity-check that no fields were silently dropped.
    assert set(result.fields) == set(fixture["fields"])


# ---------------------------------------------------------------------------
# 2. Every stub lands on the declared engagement type via the rule engine.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_stub_classifier_outcome(name: str) -> None:
    from app.services.engagement_classifier import classify

    fixture = FIXTURES[name]

    # The classifier reads *both* the schema fields (`billing_basis`,
    # `deliverables`, ...) and the auxiliary hints (`resource_table`,
    # `monthly_fee`, `coverage_hours`). E2E seeding writes both, so the
    # test mirrors that layered write.
    merged: dict[str, object] = {}
    for field_name, entry in fixture["fields"].items():
        merged[field_name] = entry
    for field_name, value in fixture.get("aux", {}).items():
        # Aux fields are written to the sow_version's extracted_fields
        # via the same PATCH .../fields/<name> path; the classifier
        # tolerates both raw and provenance-wrapped values.
        merged[field_name] = value

    result = classify(merged)
    assert result.primary.type == fixture["expected_engagement_type"], (
        f"{name}: classifier returned {result.primary.type!r}, "
        f"expected {fixture['expected_engagement_type']!r}"
    )
    # Rule assertion — the assessment fixture accepts either rule id.
    if fixture["expected_rule"] == "rule.assessment_short_term":
        assert result.rule_matched in {
            "rule.assessment_short_term",
            "rule.assessment_workshop",
        }, f"{name}: unexpected rule {result.rule_matched!r}"
    else:
        assert result.rule_matched == fixture["expected_rule"], (
            f"{name}: rule matched {result.rule_matched!r}, "
            f"expected {fixture['expected_rule']!r}"
        )
    # Rule-matched classifications are auto-confirmable (confidence=1.0).
    assert result.auto_confirm, f"{name}: rule match should auto-confirm"


# ---------------------------------------------------------------------------
# 3. Every stub's PDF exists on disk (checks the generator ran).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_stub_pdf_present(name: str) -> None:
    path = _HERE / name
    assert path.exists(), (
        f"{name} PDF missing — run `python fixtures/sample_sows/generate.py`"
    )
    # And it must be a real PDF, not an empty placeholder.
    header = path.read_bytes()[:4]
    assert header == b"%PDF", f"{name}: not a PDF ({header!r})"


# ---------------------------------------------------------------------------
# 4. The generator emits deterministic bytes on rebuild.
# ---------------------------------------------------------------------------


def test_generator_is_deterministic(tmp_path: Path) -> None:
    from generate import main as generate_main  # type: ignore

    generate_main(["--out", str(tmp_path)])
    first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.pdf")}
    # Rebuild in place; hashes must match.
    generate_main(["--out", str(tmp_path)])
    second = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.pdf")}
    assert first == second, "generator produced different bytes on rerun"
    # And they must match the checked-in PDFs so a developer can trust
    # the hashes recorded in the README.
    checked_in = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in _HERE.glob("*.pdf")
    }
    assert first == checked_in, (
        "regenerated bytes differ from the checked-in PDFs; "
        "did SOURCE_DATE_EPOCH or the fixtures change?"
    )
