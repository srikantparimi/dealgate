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

S10-04: the real Bedrock call is live. It takes the *text* of the document
(via :mod:`app.services.document_text`), not raw bytes — the model cannot read
a PDF container, and routing through the text seam is what lets a Word SOW
work at all.

Schema enforcement is by **forced tool use**. This Bedrock deployment rejects
both ``output_config.format`` and ``strict: true`` with a ValidationException,
so ``tool_choice: {"type": "tool"}`` is the mechanism that guarantees a
structurally valid payload. :func:`validate_extract` is still the gate that
decides what may be persisted — the schema check lives in our code, which is
what rule 6 actually asks for.

Model access failures return :class:`ManualRequired`, never a fabricated
payload and never a 500.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.services.document_text import DocumentText, numbered_prompt_text

log = logging.getLogger(__name__)

# Bumped from sow-v1: the prompt is materially different (numbered blocks,
# explicit placeholder handling) and the version is persisted on every
# sow_version for audit attribution.
EXTRACT_PROMPT_VERSION = "sow-v2"

# Every Anthropic model in this account is INFERENCE_PROFILE-only, so the
# bare foundation-model id ("anthropic.claude-opus-5") returns a
# ValidationException: "Invocation of model ID ... with on-demand throughput
# isn't supported." The `us.` prefix is the cross-region inference profile and
# is the id that actually works. Verified against us-east-2 on 2026-09-19.
EXTRACT_MODEL = "us.anthropic.claude-opus-5"

# Read at call time, not import time, so tests can monkeypatch the env.
def _model_id() -> str:
    return os.environ.get("SOW_EXTRACT_MODEL_ID") or EXTRACT_MODEL


def _max_tokens() -> int:
    return int(os.environ.get("SOW_EXTRACT_MAX_TOKENS", "8000"))


def _timeout_s() -> int:
    return int(os.environ.get("SOW_EXTRACT_TIMEOUT_S", "120"))

# The field list is the union of build-guide §6.3 plus the
# ``engagement_type_suggested`` field the story calls out separately.
# The engagement shapes the GM library has templates for. The model maps
# whatever the SOW calls itself onto one of these.
ENGAGEMENT_TYPES: tuple[str, ...] = (
    "fixed_price",
    "time_and_materials",
    "managed_service",
    "staff_aug",
    "single_resource",
    "assessment",
    "permanent_placement",
)

BILLING_BASES: tuple[str, ...] = (
    "fixed_price",
    "time_and_materials",
    "not_to_exceed",
    "monthly_fee",
    "milestone",
    "hourly",
    "daily",
    "placement_fee",
    "other",
)

EXTRACTED_FIELDS: tuple[str, ...] = (
    # Client identity. Added in S10-04: `_client_signals` previously derived
    # the client name only from `signatories`, so a SOW with no signature
    # block (common in a draft) produced a picker with an empty "Legal name"
    # box for the user to type into — a CLAUDE.md rule 10 defect ("a blank
    # form on open is a defect"). The parties clause names the client in
    # essentially every SOW; extract it directly.
    "client_legal_name",
    "client_domain",
    # Normalised alongside the verbatim `billing_basis`, so the rules have
    # something stable to read whatever words the SOW uses.
    "billing_basis_normalized",
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


_SYSTEM_PROMPT = """You extract commercial terms from a Statement of Work.

The document is given to you as numbered blocks. Each block starts with its
number in double brackets, like [[12]].

Rules you must follow exactly:

1. For every field, `page_ref` is the number of the block the value came from.
   Never guess a block number. If you cannot point at a block, the field is
   disputed.
2. Copy values exactly as they appear. Never invent, compute, convert, sum,
   re-date or round a number, amount, date or name. If the document says
   "$50,000.00", emit "$50,000.00" — do not emit 50000.
3. A bracketed placeholder such as [End Date], [Agreement Date], [X] or a
   blank line is NOT a value. Emit value=null and status="disputed", with
   page_ref pointing at the block where you checked.
4. If a field genuinely is not in the document, emit value=null and
   status="disputed". Do not fill it from your general knowledge.
5. status is "unconfirmed" when you found a real value, "disputed" when the
   value is missing, placeholder, or contradicted elsewhere in the document.
6. client_legal_name is the CLIENT's legal entity, not the supplier
   (SmarTek21). It is usually in the opening parties clause.

Return your answer by calling the emit_sow_extract tool. Every field must be
present."""


def _tool_schema() -> dict[str, Any]:
    """JSON schema for the forced tool call.

    `value` is intentionally untyped — a field can be a string, a number, a
    list of deliverables or a list of milestone objects — while `page_ref`
    and `status` are pinned. :func:`validate_extract` re-checks all three
    before anything is persisted.
    """

    def _entry(value_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "value": value_schema
                or {
                    "description": "The value exactly as written, or null if absent."
                },
                "page_ref": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Block number the value came from.",
                },
                "status": {"type": "string", "enum": ["unconfirmed", "disputed"]},
            },
            "required": ["value", "page_ref", "status"],
        }

    # Per-field value schemas.
    #
    # SOWs are written in every format imaginable — "a fixed fee of $50,000",
    # "Fixed Fee", "firm fixed price", "not-to-exceed", "T&M with a cap".
    # Downstream rules used to compare that prose against literals like
    # `"fixed_fee"` with exact equality, so they only ever matched the stub's
    # own output and never a real document. Asking the model for a normalised
    # value alongside the verbatim one moves the interpretation to the thing
    # that can actually read prose, and leaves the deterministic code working
    # on structure. The money itself is still copied verbatim and parsed as
    # Decimal in `api/app/gm` (rule 2) — the model never computes.
    per_field: dict[str, dict[str, Any]] = {
        "engagement_type_suggested": _entry(
            {
                "type": ["string", "null"],
                "enum": [*ENGAGEMENT_TYPES, None],
                "description": (
                    "Which commercial shape this SOW is, whatever words it "
                    "uses. fixed_price: one agreed fee for a defined scope. "
                    "time_and_materials: billed on hours worked, including "
                    "not-to-exceed and capped T&M. managed_service: a "
                    "recurring monthly or annual fee for ongoing service. "
                    "staff_aug: named people placed onto the client's team. "
                    "single_resource: staff_aug with exactly one person. "
                    "assessment: a short study, discovery or audit producing "
                    "findings. permanent_placement: a one-off recruitment "
                    "fee. Null only if the document genuinely does not say."
                ),
            }
        ),
        "billing_basis_normalized": _entry(
            {
                "type": ["string", "null"],
                "enum": [*BILLING_BASES, None],
                "description": (
                    "How money is charged, normalised. The verbatim wording "
                    "goes in billing_basis."
                ),
            }
        ),
        "deliverables": _entry(
            {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "One entry per deliverable. Never one joined string.",
            }
        ),
        "milestones": _entry(
            {
                "type": ["array", "null"],
                "items": {"type": "string"},
                "description": "One entry per milestone. Never one joined string.",
            }
        ),
        "currency": _entry(
            {
                "type": ["string", "null"],
                "description": (
                    "ISO code such as USD. If the document shows $ amounts "
                    "without naming a currency, answer USD."
                ),
            }
        ),
    }

    return {
        "type": "object",
        "properties": {
            "fields": {
                "type": "object",
                "properties": {
                    name: per_field.get(name, _entry())
                    for name in EXTRACTED_FIELDS
                },
                "required": list(EXTRACTED_FIELDS),
            }
        },
        "required": ["fields"],
    }


class BedrockSowExtract:
    """Real Bedrock caller (S10-04).

    Synchronous by design — ``boto3`` has no async client. Async callers wrap
    this in ``anyio.to_thread.run_sync`` so a slow extraction never blocks the
    event loop.

    Every failure mode returns :class:`ManualRequired` rather than raising:
    the confirm screen can always fall back to manual entry, but it can never
    recover from a fabricated payload.
    """

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def _runtime(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3
        from botocore.config import Config

        return boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-2"),
            config=Config(
                read_timeout=_timeout_s(),
                connect_timeout=10,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def extract(self, doc: DocumentText) -> ExtractedFields | ManualRequired:
        from botocore.exceptions import BotoCoreError, ClientError

        text = numbered_prompt_text(doc)
        if not text.strip():
            return ManualRequired(reason="document has no readable text")

        model_id = _model_id()
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": _max_tokens(),
            "system": _SYSTEM_PROMPT,
            "tools": [
                {
                    "name": "emit_sow_extract",
                    "description": "Emit the extracted SOW fields.",
                    "input_schema": _tool_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": "emit_sow_extract"},
            "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
        }

        try:
            resp = self._runtime().invoke_model(
                modelId=model_id, body=json.dumps(body)
            )
            payload = json.loads(resp["body"].read())
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "Unknown")
            if code in ("AccessDeniedException", "UnrecognizedClientException"):
                return ManualRequired(reason="bedrock model access not enabled")
            if code == "ValidationException":
                # Almost always a bad model id — surface it, do not retry.
                log.error("bedrock rejected extract request: %s", exc)
                return ManualRequired(reason=f"bedrock rejected the request: {code}")
            if code in (
                "ThrottlingException",
                "ModelTimeoutException",
                "ServiceUnavailableException",
                "ModelNotReadyException",
            ):
                return ManualRequired(reason="bedrock temporarily unavailable")
            log.exception("bedrock extract failed")
            return ManualRequired(reason=f"bedrock error: {code}")
        except (BotoCoreError, TimeoutError) as exc:
            log.warning("bedrock extract transport failure: %s", exc)
            return ManualRequired(reason="bedrock unreachable")
        except json.JSONDecodeError:
            return ManualRequired(reason="bedrock returned a non-JSON body")

        tool_use = next(
            (
                b
                for b in payload.get("content", [])
                if b.get("type") == "tool_use" and b.get("name") == "emit_sow_extract"
            ),
            None,
        )
        if tool_use is None:
            stop = payload.get("stop_reason")
            return ManualRequired(reason=f"model returned no extract (stop={stop})")

        try:
            return validate_extract(
                {
                    "fields": tool_use.get("input", {}).get("fields", {}),
                    "model": model_id,
                    "prompt_version": EXTRACT_PROMPT_VERSION,
                }
            )
        except ValueError as exc:
            # Schema gate rejected it — better a manual form than bad data.
            log.warning("extract failed schema validation: %s", exc)
            return ManualRequired(reason=f"extract failed validation: {exc}")


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

    def extract(self, doc: DocumentText) -> ExtractedFields | ManualRequired:
        self.calls.append(len(doc.blocks))
        if self.unavailable:
            return ManualRequired(reason="bedrock model access not enabled")
        canned: dict[str, dict[str, Any]] = {
            "client_legal_name": {
                "value": "Northwind Trading Co., LLC",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "northwind.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "billing_basis_normalized": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
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
    """FastAPI dependency. Override with :class:`StubBedrock` in tests.

    ``SOW_EXTRACT_STUB=1`` selects the deterministic stub. That env var was
    already set by ``.github/workflows/e2e.yml`` but read by nothing, so the
    e2e suite believed it was running offline while the code reached for the
    real client. The check is at call time so ``monkeypatch.setenv`` works.
    """

    if os.environ.get("SOW_EXTRACT_STUB") == "1":
        return StubBedrock()
    if os.environ.get("DEALGATE_ENV") in ("local", "test"):
        return StubBedrock()
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
