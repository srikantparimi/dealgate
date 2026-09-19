"""MSA rate-schedule import — S9 wave 1.

The extractor that reads a SOW also reads an MSA rate schedule. This
service takes an MSA file, invokes the Bedrock extractor with a variant
prompt for rate-schedule tables, and returns a **draft** client rate card
with per-row confidence + a ``source_document_id`` pointing at the MSA.

CLAUDE.md rule 6: AI output is a draft with sources and page refs and
**needs human confirmation before it affects a record**. This service
never auto-publishes — a human confirms the draft via
``POST /clients/{id}/rate-card``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    ManualRequired,
    StubBedrock,
)

RATE_SCHEDULE_PROMPT_VERSION = "msa-rate-schedule-v1"

# Fields the extractor is expected to return per rate schedule row.
RATE_ROW_FIELDS: tuple[str, ...] = (
    "role",
    "seniority",
    "location",
    "bill_rate",
    "currency",
    "unit",
)


@dataclass
class DraftRateRow:
    role: str
    seniority: str
    location: str
    bill_rate: Decimal
    currency: str
    unit: str
    page_ref: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "seniority": self.seniority,
            "location": self.location,
            "bill_rate": format(self.bill_rate, "f"),
            "currency": self.currency,
            "unit": self.unit,
            "page_ref": self.page_ref,
            "confidence": self.confidence,
        }


@dataclass
class DraftClientRateCard:
    client_id: uuid.UUID
    source_document_id: uuid.UUID
    rows: list[DraftRateRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    manual_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "client_id": str(self.client_id),
            "source_document_id": str(self.source_document_id),
            "rows": [r.to_dict() for r in self.rows],
            "warnings": list(self.warnings),
            "manual_required": self.manual_required,
        }


# --- extractor variant -----------------------------------------------------


class MsaRateExtractor:
    """Adapter around :class:`BedrockSowExtract` for rate schedules.

    The real Bedrock caller is deferred to a later story; for now the
    adapter simply invokes the underlying extractor and re-shapes the
    result (or in ``StubBedrock`` mode, returns a canned schedule).
    """

    def __init__(self, bedrock: BedrockSowExtract | None = None) -> None:
        self._bedrock = bedrock or BedrockSowExtract()

    def extract(self, msa_bytes: bytes) -> list[DraftRateRow] | ManualRequired:
        # In production the real caller will send a variant prompt that
        # asks for rate schedule rows. For Sprint 9 wave 1 we reuse the
        # stub's canned interface and (for a StubBedrock) synthesise a
        # small rate table so the UI + tests are exercisable.
        if isinstance(self._bedrock, StubBedrock):
            if self._bedrock.unavailable:
                return ManualRequired(reason="bedrock model access not enabled")
            self._bedrock.calls.append(len(msa_bytes))
            return _stub_rate_schedule()
        result = self._bedrock.extract(msa_bytes)
        if isinstance(result, ManualRequired):
            return result
        # Real path would parse a rate-schedule variant payload here.
        return ManualRequired(
            reason="bedrock rate-schedule caller not yet implemented"
        )


def _stub_rate_schedule() -> list[DraftRateRow]:
    return [
        DraftRateRow(
            role="Engineer",
            seniority="Mid",
            location="US",
            bill_rate=Decimal("175.0000"),
            currency="USD",
            unit="hourly",
            page_ref=2,
            confidence=0.92,
        ),
        DraftRateRow(
            role="Engineer",
            seniority="Senior",
            location="US",
            bill_rate=Decimal("225.0000"),
            currency="USD",
            unit="hourly",
            page_ref=2,
            confidence=0.90,
        ),
        DraftRateRow(
            role="Engineer",
            seniority="Mid",
            location="India",
            bill_rate=Decimal("85.0000"),
            currency="USD",
            unit="hourly",
            page_ref=3,
            confidence=0.88,
        ),
    ]


# --- import service --------------------------------------------------------


def parse_row_from_extract(entry: dict[str, Any]) -> DraftRateRow:
    """Validate + coerce one row emitted by the extractor.

    Raises ``ValueError`` when a required field is missing or malformed.
    The caller decides whether that becomes a warning or a hard 422.
    """

    missing = [f for f in RATE_ROW_FIELDS if entry.get(f) in (None, "")]
    if missing:
        raise ValueError(f"row missing fields: {missing}")
    try:
        rate = Decimal(str(entry["bill_rate"]))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"bill_rate not a decimal: {entry.get('bill_rate')!r}") from exc
    if rate <= 0:
        raise ValueError("bill_rate must be > 0")
    return DraftRateRow(
        role=str(entry["role"]).strip(),
        seniority=str(entry["seniority"]).strip(),
        location=str(entry["location"]),
        bill_rate=rate,
        currency=str(entry["currency"]),
        unit=str(entry["unit"]),
        page_ref=int(entry.get("page_ref", 1)),
        confidence=float(entry.get("confidence", 0.8)),
    )


async def import_rate_schedule(
    session,  # AsyncSession, unused today — reserved for source_document lookup
    *,
    actor_id: uuid.UUID | None,  # noqa: ARG001 — reserved for audit hook
    client_id: uuid.UUID,
    msa_file_key: str,
    extractor: MsaRateExtractor | None = None,
    msa_bytes: bytes | None = None,
) -> DraftClientRateCard:
    """Extract a rate schedule from an MSA file and return a **draft**.

    Never publishes. Never touches the DB. The caller (router) returns
    the draft to the browser for human review; the human confirms via
    ``POST /clients/{id}/rate-card``.

    ``msa_bytes`` is an explicit override for tests. The real path
    fetches the object from S3 using ``msa_file_key``.
    """

    if extractor is None:
        extractor = MsaRateExtractor()

    if msa_bytes is None:
        # In production we'd read from S3 here; leave a placeholder so
        # tests inject bytes directly and the router path is exercised.
        msa_bytes = msa_file_key.encode("utf-8") if msa_file_key else b""

    # Derive a deterministic source_document_id from the file key so
    # re-imports don't spawn a new source id per attempt. The router
    # stores this on the eventually-published card.
    source_document_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"dealgate:msa:{msa_file_key}"
    )

    result = extractor.extract(msa_bytes)
    if isinstance(result, ManualRequired):
        return DraftClientRateCard(
            client_id=client_id,
            source_document_id=source_document_id,
            rows=[],
            warnings=[f"extractor unavailable: {result.reason}"],
            manual_required=True,
        )

    draft = DraftClientRateCard(
        client_id=client_id,
        source_document_id=source_document_id,
        rows=list(result),
        warnings=[],
    )
    for row in draft.rows:
        if row.confidence < 0.85:
            draft.warnings.append(
                f"low confidence ({row.confidence:.2f}) for "
                f"{row.role}/{row.seniority}/{row.location} — please confirm"
            )
    return draft


def draft_to_row_inputs(draft: DraftClientRateCard):
    """Convenience: convert a draft into publisher-ready row inputs."""

    from app.services.client_rate_cards import ClientRateCardRowInput

    return [
        ClientRateCardRowInput(
            role=r.role,
            seniority=r.seniority,
            location=r.location,
            bill_rate=r.bill_rate,
            currency=r.currency,
            unit=r.unit,
        )
        for r in draft.rows
    ]


__all__ = [
    "DraftClientRateCard",
    "DraftRateRow",
    "MsaRateExtractor",
    "RATE_ROW_FIELDS",
    "RATE_SCHEDULE_PROMPT_VERSION",
    "draft_to_row_inputs",
    "import_rate_schedule",
    "parse_row_from_extract",
]
