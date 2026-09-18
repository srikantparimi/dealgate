"""Bedrock (Claude) SOW field extraction.

Rule 6 (CLAUDE.md) — AI output is a *draft with sources and page refs,
validated against a JSON schema*, and needs human confirmation before it
affects a record. This module produces that draft. The service layer
persists it as ``extract_status="complete"``; the confirm endpoint is what
transitions each field to ``confirmed``.

Contract (build-guide §6.3):

- The extract emits one entry per field name, each shaped as
  ``{"value": <str|number|dict|list|null>, "page_ref": <int>, "status":
  "unconfirmed" | "disputed"}``.
- ``page_ref`` is 1-based. Extraction cannot produce a field without a
  page ref — a missing / conflicting field is emitted with
  ``value=None, status="disputed"`` so the confirm screen surfaces it.
- If Bedrock model access is not enabled in the account, ``extract()``
  returns :class:`ManualRequired` instead of a fabricated payload. The
  service marks the version ``extract_status="manual_required"`` and the
  confirm screen switches to a full manual-entry form.

The real Bedrock call is deferred to a later story — for Sprint 3 wave 1
this module exposes the interface and a deterministic :class:`StubBedrock`
that returns a canned :class:`ExtractedFields`. That keeps the API and UI
end-to-end testable while infra flips the Bedrock model-access flag.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

EXTRACT_PROMPT_VERSION = "sow-v1"
EXTRACT_MODEL = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# The field list is the union of build-guide §6.3 plus the
# ``engagement_type_suggested`` field the story calls out separately.
EXTRACTED_FIELDS: tuple[str, ...] = (
    "scope_summary",
    "price",
    "currency",
    "billing_basis",
    "term_start",
    "term_end",
    "notice_date",
    "deliverables",
    "milestones",
    "acceptance_criteria",
    "assumptions",
    "exclusions",
    "signatories",
    "engagement_type_suggested",
)


class BedrockUnavailable(Exception):
    """Raised when Bedrock rejects with 403 / model access disabled."""


@dataclass(frozen=True)
class ManualRequired:
    """Signal object returned when Bedrock cannot be called.

    The service maps this to ``extract_status = "manual_required"`` and
    seeds every field as unconfirmed with a ``None`` value so the confirm
    screen renders a data-entry form. No fabricated content is ever passed
    off as an extraction result — CLAUDE.md rule 6.
    """

    reason: str


@dataclass
class ExtractedFields:
    """Validated extract payload. Keys are :data:`EXTRACTED_FIELDS`.

    ``fields`` maps a field name to
    ``{"value": ..., "page_ref": int, "status": "unconfirmed" | "disputed"}``.
    """

    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    model: str = EXTRACT_MODEL
    prompt_version: str = EXTRACT_PROMPT_VERSION


def _validate_field(name: str, entry: Any) -> dict[str, Any]:
    """Enforce the wire schema for a single field.

    Any deviation from ``{value, page_ref, status}`` is rejected — a real
    extraction that returned junk will surface as an extract failure,
    which is safer than silently persisting a partial payload.
    """

    if not isinstance(entry, dict):
        raise ValueError(f"field {name!r} must be an object, got {type(entry).__name__}")
    if "page_ref" not in entry:
        raise ValueError(f"field {name!r} missing page_ref")
    page_ref = entry["page_ref"]
    if not isinstance(page_ref, int) or page_ref < 1:
        raise ValueError(f"field {name!r} page_ref must be a positive int")
    status = entry.get("status", "unconfirmed")
    if status not in {"unconfirmed", "disputed"}:
        raise ValueError(f"field {name!r} status must be unconfirmed|disputed")
    return {
        "value": entry.get("value"),
        "page_ref": page_ref,
        "status": status,
    }


def validate_extract(payload: dict[str, Any]) -> ExtractedFields:
    """Validate a raw model payload against the extract JSON schema.

    Every :data:`EXTRACTED_FIELDS` name must be present. Extra keys are
    rejected so a hallucinated field cannot leak into the confirm screen.
    """

    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    fields_in = payload.get("fields")
    if not isinstance(fields_in, dict):
        raise ValueError("payload.fields must be a dict")
    unknown = set(fields_in) - set(EXTRACTED_FIELDS)
    if unknown:
        raise ValueError(f"unknown fields in extract: {sorted(unknown)}")
    missing = set(EXTRACTED_FIELDS) - set(fields_in)
    if missing:
        raise ValueError(f"extract missing required fields: {sorted(missing)}")
    validated: dict[str, dict[str, Any]] = {}
    for name in EXTRACTED_FIELDS:
        validated[name] = _validate_field(name, fields_in[name])
    return ExtractedFields(
        fields=validated,
        model=str(payload.get("model", EXTRACT_MODEL)),
        prompt_version=str(payload.get("prompt_version", EXTRACT_PROMPT_VERSION)),
    )


class BedrockSowExtract:
    """Real Bedrock caller — Sprint 3 wave 2 fills in the API call.

    Sprint 3 wave 1 ships the interface + :class:`StubBedrock`. The real
    caller is deferred to the story that flips the Bedrock model-access
    flag in the dev account (see :file:`docs/questions.md`).
    """

    def extract(self, file_bytes: bytes) -> ExtractedFields | ManualRequired:
        # Placeholder: real invoke_model call lands in the wave 2 story.
        # For now the safe answer is "manual" — never fabricate output.
        return ManualRequired(reason="bedrock caller not yet implemented")


class StubBedrock(BedrockSowExtract):
    """Deterministic canned extractor for tests / offline dev.

    Returns a full :class:`ExtractedFields` with plausible values so the UI
    and confirm flow can be exercised end-to-end without hitting AWS.

    Toggle :attr:`unavailable` to simulate the model-access-disabled path;
    :meth:`extract` then returns :class:`ManualRequired`.
    """

    def __init__(self, *, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[int] = []

    def extract(self, file_bytes: bytes) -> ExtractedFields | ManualRequired:
        self.calls.append(len(file_bytes))
        if self.unavailable:
            return ManualRequired(reason="bedrock model access not enabled")
        canned: dict[str, dict[str, Any]] = {
            "scope_summary": {
                "value": "Modernise loan-origination platform onto AWS.",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "250000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {
                "value": "2026-10-01",
                "page_ref": 3,
                "status": "unconfirmed",
            },
            "term_end": {
                "value": "2027-03-31",
                "page_ref": 3,
                "status": "unconfirmed",
            },
            "notice_date": {
                "value": "2027-01-31",
                "page_ref": 3,
                "status": "unconfirmed",
            },
            "deliverables": {
                "value": ["Discovery report", "Cutover plan", "Runbook"],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [
                    {"name": "Discovery", "date": "2026-10-31"},
                    {"name": "Cutover", "date": "2027-02-28"},
                ],
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "UAT sign-off by client sponsor.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "Client provides AWS account and IAM access day 1.",
                "page_ref": 7,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Third-party tool licences.",
                "page_ref": 7,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "J. Doe", "role": "Client sponsor"},
                    {"name": "A. Roe", "role": "Delivery lead"},
                ],
                "page_ref": 8,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        }
        return validate_extract(
            {
                "fields": canned,
                "model": EXTRACT_MODEL,
                "prompt_version": EXTRACT_PROMPT_VERSION,
            }
        )


def get_bedrock_sow() -> BedrockSowExtract:
    """FastAPI dependency. Override with :class:`StubBedrock` in tests."""

    return BedrockSowExtract()


_ = uuid  # kept for future correlation-id plumbing


__all__ = [
    "BedrockSowExtract",
    "BedrockUnavailable",
    "EXTRACT_MODEL",
    "EXTRACT_PROMPT_VERSION",
    "EXTRACTED_FIELDS",
    "ExtractedFields",
    "ManualRequired",
    "StubBedrock",
    "get_bedrock_sow",
    "validate_extract",
]
