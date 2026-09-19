"""SOW upload + extraction + confirmation service (build-guide §6.3).

Every state change here writes an ``audit_event`` in the same transaction
(CLAUDE.md rule 5). SOW versions are immutable rows (rule 4) — the only
field the service mutates after creation is the ``extracted_fields`` JSONB
(via extract + per-field confirm) and the confirmation columns
(``confirmed_by`` / ``confirmed_at`` / ``engagement_type_confirmed``).

Actions emitted:

- ``sow.uploaded``     — a new version row lands, status=pending.
- ``sow.extracted``    — Bedrock returned validated fields.
- ``sow.extract_failed`` — Bedrock returned :class:`ManualRequired` or the
  payload failed schema validation.
- ``sow.field_confirmed`` — a human confirmed / overrode one field.
- ``sow.confirmed``    — the whole version is submitted (all fields
  confirmed). Opportunity governance_status moves to ``SOWDraft.confirmed``.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import (
    EXTRACT_MODEL,
    EXTRACT_PROMPT_VERSION,
    EXTRACTED_FIELDS,
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
    validate_extract,
)
from app.integrations.textract import TextractClient, TextractError
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.provenance import read as read_provenance, wrap as wrap_provenance

ALLOWED_EXTRACT_STATUSES: tuple[str, ...] = (
    "pending",
    "complete",
    "failed",
    "manual_required",
)

# A PDF with fewer than this many text chars per page is treated as
# image-only / scanned and routed through Textract for OCR before the
# Bedrock schema extract runs. Tuned against the "clean typeset SOW" corpus
# in fixtures/ — real SOWs land north of 800 chars/page; anything below 40
# is almost always a photocopy or scan.
TEXT_DENSITY_MIN_CHARS_PER_PAGE = 40

_EXTRACT_SOURCE_PDF = "pdf_text"
_EXTRACT_SOURCE_TEXTRACT = "textract"


class SowError(Exception):
    """Base for expected service errors."""


class SowNotFound(SowError):
    """The opportunity / version does not exist."""


class SowSubmissionIncomplete(SowError):
    """Raised when submit is called before every field is confirmed."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"cannot submit — {len(missing)} field(s) not confirmed")


class SowInvalidField(SowError):
    """Raised when a confirm targets an unknown field name."""


@dataclass(frozen=True)
class SowVersionState:
    """Read-side snapshot of a SOW version — what the API returns."""

    id: uuid.UUID
    sow_id: uuid.UUID
    opportunity_id: uuid.UUID
    uploaded_by: uuid.UUID | None
    uploaded_at: datetime
    file_s3_key: str
    file_hash: str
    extracted_fields: dict[str, Any] | None
    extract_status: str
    extract_model: str | None
    extract_prompt_version: str | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    engagement_type_suggested: str | None
    engagement_type_confirmed: str | None


# --- helpers --------------------------------------------------------------


async def _load_or_create_sow(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Sow:
    row = (
        await session.execute(select(Sow).where(Sow.opportunity_id == opportunity_id))
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = Sow(id=uuid.uuid4(), opportunity_id=opportunity_id)
    session.add(row)
    await session.flush()
    return row


async def _load_version(session: AsyncSession, version_id: uuid.UUID) -> SowVersion:
    row = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == version_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise SowNotFound(f"sow_version {version_id} not found")
    return row


async def _opportunity_id_for(
    session: AsyncSession, sow_id: uuid.UUID
) -> uuid.UUID:
    row = (
        await session.execute(select(Sow.opportunity_id).where(Sow.id == sow_id))
    ).scalar_one()
    return row


def _snapshot(version: SowVersion, opportunity_id: uuid.UUID) -> SowVersionState:
    return SowVersionState(
        id=version.id,
        sow_id=version.sow_id,
        opportunity_id=opportunity_id,
        uploaded_by=version.uploaded_by,
        uploaded_at=version.uploaded_at,
        file_s3_key=version.file_s3_key,
        file_hash=version.file_hash,
        extracted_fields=copy.deepcopy(version.extracted_fields)
        if version.extracted_fields is not None
        else None,
        extract_status=version.extract_status,
        extract_model=version.extract_model,
        extract_prompt_version=version.extract_prompt_version,
        confirmed_by=version.confirmed_by,
        confirmed_at=version.confirmed_at,
        engagement_type_suggested=version.engagement_type_suggested,
        engagement_type_confirmed=version.engagement_type_confirmed,
    )


def _blank_manual_fields() -> dict[str, dict[str, Any]]:
    """Seed the fields dict for a manual-entry version.

    Every field lands as a ``manual`` provenance envelope with
    ``value=None`` and ``status=disputed`` so the UI surfaces each row as
    needing attention. :func:`confirm_field` is the only path that flips
    a row to ``status="confirmed"`` (rule 6).
    """

    return {
        name: wrap_provenance(
            None, provenance="manual", page_ref=1, status="disputed"
        )
        for name in EXTRACTED_FIELDS
    }


def _to_provenance_fields(
    extracted: dict[str, dict[str, Any]],
    *,
    model: str,
    prompt_version: str,
) -> dict[str, dict[str, Any]]:
    """Upgrade the Bedrock extract payload to the provenance envelope.

    The extractor still speaks the legacy ``{value, page_ref, status}``
    shape (kept so its own schema validator stays tight). We wrap every
    field with ``provenance="extracted"`` and stamp the model/prompt as
    ``source_id`` so audit can attribute the write.
    """

    out: dict[str, dict[str, Any]] = {}
    source_id = f"{model}:{prompt_version}"
    for name in EXTRACTED_FIELDS:
        entry = extracted.get(name, {})
        out[name] = wrap_provenance(
            entry.get("value"),
            provenance="extracted",
            page_ref=entry.get("page_ref"),
            source_id=source_id,
            confidence=entry.get("confidence"),
            status=entry.get("status", "unconfirmed"),
        )
    return out


# --- public API -----------------------------------------------------------


async def create_sow_version(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    uploaded_by: uuid.UUID | None,
    file_s3_key: str,
    file_hash: str,
) -> SowVersionState:
    """Create a fresh ``sow_version`` row with ``extract_status=pending``.

    Idempotently anchors a ``sow`` row per opportunity. Emits
    ``sow.uploaded`` in the same transaction. Caller commits.
    """

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise SowNotFound(f"opportunity {opportunity_id} not found")

    sow = await _load_or_create_sow(session, opportunity_id)

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=uploaded_by,
        file_s3_key=file_s3_key,
        file_hash=file_hash,
        extract_status="pending",
    )
    session.add(version)
    await session.flush()

    await append_audit(
        session,
        actor_id=uploaded_by,
        action="sow.uploaded",
        entity="sow_version",
        entity_id=str(version.id),
        before=None,
        after={
            "opportunity_id": str(opportunity_id),
            "sow_id": str(sow.id),
            "file_s3_key": file_s3_key,
            "file_hash": file_hash,
            "extract_status": "pending",
        },
    )

    # S4 E7 hook: any new sow_version voids the active approval package
    # (change-voids-approval). Kept behind a single hook module so this
    # service has no direct dependency on the approvals package.
    from app.services.approvals_hooks import on_sow_version_created

    await on_sow_version_created(
        session,
        opportunity_id=opportunity_id,
        new_sow_version_id=version.id,
        actor_id=uploaded_by,
    )

    return _snapshot(version, opportunity_id)


def _pdf_text_density(pdf_bytes: bytes) -> tuple[int, int]:
    """Parse the PDF locally and return ``(total_chars, page_count)``.

    Returns ``(0, 0)`` if the file cannot be parsed — the caller then
    routes through Textract, which is more tolerant of malformed inputs.
    Kept module-private because it is a heuristic input to the extract
    branch, not a piece of the public API.
    """

    if not pdf_bytes:
        return 0, 0
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes))
        pages = list(reader.pages)
        total = 0
        for page in pages:
            try:
                text = page.extract_text() or ""
            except Exception:  # noqa: BLE001 — one bad page must not blow the run
                text = ""
            total += len(text)
        return total, len(pages)
    except Exception:  # noqa: BLE001 — malformed → fall through to Textract
        return 0, 0


def _needs_textract(pdf_bytes: bytes) -> bool:
    """True when the PDF has fewer than ``TEXT_DENSITY_MIN_CHARS_PER_PAGE``
    chars/page.

    Zero-byte payloads (test-only shortcut) skip Textract — the stub
    Bedrock in the S3-E5 suite passes ``b""`` and would otherwise trigger
    a spurious OCR call.
    """

    if not pdf_bytes:
        return False
    total, pages = _pdf_text_density(pdf_bytes)
    if pages == 0:
        # Malformed / unreadable → try OCR; safer than fabricating a "no text"
        # branch that runs Bedrock over an empty string.
        return True
    return (total / pages) < TEXT_DENSITY_MIN_CHARS_PER_PAGE


async def run_extract(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    bedrock: BedrockSowExtract,
    file_bytes: bytes = b"",
    textract: TextractClient | None = None,
) -> SowVersionState:
    """Invoke Bedrock and persist the validated extract or fall through to
    manual-entry mode when the model is unavailable.

    Idempotent-ish: if the version is already ``complete`` /
    ``manual_required`` the call re-runs and overwrites the status +
    fields (audit row still fires).

    Textract fallback (build-guide §6.3): the service first parses the PDF
    locally with pypdf and counts text chars/page. When the density is
    below :data:`TEXT_DENSITY_MIN_CHARS_PER_PAGE` we hand the bytes to
    Textract for OCR, then feed the recovered text to Bedrock in place of
    the raw PDF. Textract failures land as
    ``extract_status="manual_required"`` with reason ``"OCR unavailable"``
    — CLAUDE.md rule 6, never fabricate.

    The path chosen is recorded on
    ``extracted_fields["metadata"]["extract_source"]`` (``pdf_text`` |
    ``textract``) so the confirm screen and audit reader can tell OCR'd
    fields apart from digital-text ones.
    """

    version = await _load_version(session, sow_version_id)
    opportunity_id = await _opportunity_id_for(session, version.sow_id)

    extract_source = _EXTRACT_SOURCE_PDF
    bedrock_input: bytes = file_bytes
    ocr_error: str | None = None

    if _needs_textract(file_bytes):
        client = textract if textract is not None else TextractClient()
        # Record the *intended* source now: if Textract raises, the version
        # still carries ``extract_source="textract"`` so the audit reader
        # can see the version was routed at OCR — the OCR just failed.
        extract_source = _EXTRACT_SOURCE_TEXTRACT
        try:
            recovered = client.extract_text(file_bytes)
            bedrock_input = recovered.encode("utf-8")
        except TextractError as exc:
            ocr_error = str(exc)

    result: ExtractedFields | ManualRequired
    error: str | None = None
    if ocr_error is not None:
        result = ManualRequired(reason="OCR unavailable")
    else:
        try:
            raw = bedrock.extract(bedrock_input)
            if isinstance(raw, ManualRequired):
                result = raw
            elif isinstance(raw, ExtractedFields):
                # Re-validate through the schema so a stub that hand-crafts a
                # payload cannot bypass the safety net.
                result = validate_extract(
                    {
                        "fields": raw.fields,
                        "model": raw.model,
                        "prompt_version": raw.prompt_version,
                    }
                )
            else:
                raise ValueError(
                    f"bedrock returned {type(raw).__name__}, expected ExtractedFields|ManualRequired"
                )
        except Exception as exc:  # noqa: BLE001 — safety net for LLM misuse
            error = str(exc)
            result = ManualRequired(reason=f"validation failed: {error}")

    before = {"extract_status": version.extract_status}

    if isinstance(result, ManualRequired):
        version.extract_status = "manual_required"
        blank = _blank_manual_fields()
        blank["metadata"] = {"extract_source": extract_source}
        version.extracted_fields = blank
        version.extract_model = None
        version.extract_prompt_version = None
        version.engagement_type_suggested = None
        action = "sow.extract_failed"
        after: dict[str, Any] = {
            "extract_status": "manual_required",
            "reason": result.reason,
            "extract_source": extract_source,
        }
    else:
        version.extract_status = "complete"
        fields_out = _to_provenance_fields(
            result.fields,
            model=result.model,
            prompt_version=result.prompt_version,
        )
        fields_out["metadata"] = {"extract_source": extract_source}
        version.extracted_fields = fields_out
        version.extract_model = result.model
        version.extract_prompt_version = result.prompt_version
        suggested = result.fields.get("engagement_type_suggested", {}).get("value")
        version.engagement_type_suggested = (
            str(suggested) if suggested is not None else None
        )
        action = "sow.extracted"
        after = {
            "extract_status": "complete",
            "model": result.model,
            "prompt_version": result.prompt_version,
            "engagement_type_suggested": version.engagement_type_suggested,
            "extract_source": extract_source,
        }

    await append_audit(
        session,
        actor_id=version.uploaded_by,
        action=action,
        entity="sow_version",
        entity_id=str(version.id),
        before=before,
        after=after,
    )
    return _snapshot(version, opportunity_id)


async def confirm_field(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    sow_version_id: uuid.UUID,
    field_name: str,
    value: Any,
) -> SowVersionState:
    """Confirm or override a single extracted field.

    The value replaces whatever the extract produced (an override is
    treated the same as an acceptance). The field's ``status`` flips to
    ``confirmed`` and an audit row records the before/after value.
    """

    if field_name not in EXTRACTED_FIELDS:
        raise SowInvalidField(f"unknown field {field_name!r}")

    version = await _load_version(session, sow_version_id)
    opportunity_id = await _opportunity_id_for(session, version.sow_id)

    fields = dict(version.extracted_fields or {})
    prev = read_provenance(fields.get(field_name))
    prev_value = prev.get("value")
    # If the human accepted the extracted value verbatim, keep the
    # original provenance (``extracted`` / ``looked_up`` / ...); a change
    # in value flips the row to ``manual`` per rule 10 — a hand-typed
    # value has no upstream source.
    if prev_value == value and prev.get("provenance") in {
        "extracted",
        "looked_up",
        "calculated",
        "defaulted",
    }:
        new_provenance = prev["provenance"]
        source_id = prev.get("source_id")
        confidence = prev.get("confidence")
    else:
        new_provenance = "manual"
        source_id = None
        confidence = None

    updated = wrap_provenance(
        value,
        provenance=new_provenance,
        page_ref=prev.get("page_ref"),
        source_id=source_id,
        confidence=confidence,
        warning=prev.get("warning"),
        status="confirmed",
    )
    fields[field_name] = updated
    # Reassign so SQLAlchemy detects the mutation on the JSONB column.
    version.extracted_fields = fields

    if field_name == "engagement_type_suggested":
        version.engagement_type_confirmed = str(value) if value is not None else None

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow.field_confirmed",
        entity="sow_version",
        entity_id=str(version.id),
        before={
            "field": field_name,
            "value": prev_value,
            "provenance": prev.get("provenance"),
            "status": prev.get("status"),
        },
        after={
            "field": field_name,
            "value": value,
            "provenance": new_provenance,
            "status": "confirmed",
        },
    )
    return _snapshot(version, opportunity_id)


def _unconfirmed_fields(fields: dict[str, Any] | None) -> list[str]:
    """Names of every field that is not yet ``status="confirmed"``."""

    fields = fields or {}
    missing: list[str] = []
    for name in EXTRACTED_FIELDS:
        entry = read_provenance(fields.get(name))
        if entry.get("status") != "confirmed":
            missing.append(name)
    return missing


async def submit_sow(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    sow_version_id: uuid.UUID,
) -> SowVersionState:
    """Finalise a version once every field is confirmed.

    On success:

    - stamps ``confirmed_by`` / ``confirmed_at``;
    - promotes the opportunity's ``governance_status`` to
      ``SOWDraft.confirmed`` (workflow module will own this end-to-end in
      a follow-up wave — for now the service writes the value directly and
      audits it);
    - emits ``sow.confirmed``.
    """

    version = await _load_version(session, sow_version_id)
    opportunity_id = await _opportunity_id_for(session, version.sow_id)

    missing = _unconfirmed_fields(version.extracted_fields)
    if missing:
        raise SowSubmissionIncomplete(missing)

    now = datetime.now(UTC)
    version.confirmed_by = actor_id
    version.confirmed_at = now

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one()
    old_status = opp.governance_status
    opp.governance_status = "SOWDraft.confirmed"

    await append_audit(
        session,
        actor_id=actor_id,
        action="sow.confirmed",
        entity="sow_version",
        entity_id=str(version.id),
        before={"governance_status": old_status},
        after={
            "governance_status": "SOWDraft.confirmed",
            "confirmed_by": str(actor_id),
        },
    )

    # S7 wave 2: enqueue the embed job on ``sow.confirmed``. Runs
    # synchronously in dev/test; a production worker can wrap the same
    # call in a background task without changing the service surface.
    # Failures are logged-and-swallowed — the confirm itself must not
    # block on a transient Bedrock outage.
    await _enqueue_sow_embed(session, sow_version_id=version.id)

    return _snapshot(version, opportunity_id)


async def _enqueue_sow_embed(
    session: AsyncSession, *, sow_version_id: uuid.UUID
) -> None:
    """Fire-and-forget embed hook. Isolated so tests can monkeypatch."""

    try:
        from app.integrations.bedrock_embeddings import default_embedder
        from app.services.embeddings import embed_sow_version

        await embed_sow_version(
            session,
            sow_version_id=sow_version_id,
            embedder=default_embedder(),
        )
    except Exception:  # noqa: BLE001 — never block confirm on the embed
        import structlog

        structlog.get_logger("sow_extract").warning(
            "sow_embed_failed", sow_version_id=str(sow_version_id)
        )


async def load_version_state(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> SowVersionState:
    """Read helper for ``GET /sow/versions/{id}``."""

    version = await _load_version(session, sow_version_id)
    opportunity_id = await _opportunity_id_for(session, version.sow_id)
    return _snapshot(version, opportunity_id)


async def latest_version_for(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> SowVersionState | None:
    """Return the most recent ``sow_version`` for the opportunity, if any."""

    sow_row = (
        await session.execute(select(Sow).where(Sow.opportunity_id == opportunity_id))
    ).scalar_one_or_none()
    if sow_row is None:
        return None
    version = (
        await session.execute(
            select(SowVersion)
            .where(SowVersion.sow_id == sow_row.id)
            .order_by(SowVersion.uploaded_at.desc(), SowVersion.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if version is None:
        return None
    return _snapshot(version, opportunity_id)


__all__ = [
    "ALLOWED_EXTRACT_STATUSES",
    "SowError",
    "SowInvalidField",
    "SowNotFound",
    "SowSubmissionIncomplete",
    "SowVersionState",
    "confirm_field",
    "create_sow_version",
    "latest_version_for",
    "load_version_state",
    "run_extract",
    "submit_sow",
]
