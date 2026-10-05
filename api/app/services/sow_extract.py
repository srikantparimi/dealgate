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
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.services.document_text import (
    DocumentText,
    UnreadableDocument,
    extract_document_text,
    is_low_density,
    text_document_from_string,
)
from app.integrations.bedrock_sow_extract import (
    EXTRACTED_FIELDS,
    OPTIONAL_EXTRACTED_FIELDS,
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


class SowReplayConflict(SowError):
    """A source change or immutable version cannot be re-extracted in place."""


class SowSubmissionIncomplete(SowError):
    """Raised when submit is called before every field is confirmed."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"cannot submit — {len(missing)} field(s) not confirmed")


class SowInvalidField(SowError):
    """Raised when a confirm targets an unknown field name."""


@dataclass(frozen=True)
class PreparedExtractionDocument:
    """Document evidence shared by classification and field extraction."""

    text: DocumentText | None
    extract_source: str
    error: str | None = None


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
    # S15: extract failure reason surfaces alongside the status so consumers
    # (confirmation API, admin, backfill scripts) don't need a second read.
    extract_error: str | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    engagement_type_suggested: str | None
    engagement_type_confirmed: str | None
    version_no: int = 1


# --- helpers --------------------------------------------------------------


async def _load_or_create_sow(session: AsyncSession, opportunity_id: uuid.UUID) -> Sow:
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
        await session.execute(select(SowVersion).where(SowVersion.id == version_id))
    ).scalar_one_or_none()
    if row is None:
        raise SowNotFound(f"sow_version {version_id} not found")
    return row


async def _opportunity_id_for(session: AsyncSession, sow_id: uuid.UUID) -> uuid.UUID:
    row = (
        await session.execute(select(Sow.opportunity_id).where(Sow.id == sow_id))
    ).scalar_one()
    return row


def _snapshot(version: SowVersion, opportunity_id: uuid.UUID) -> SowVersionState:
    return SowVersionState(
        id=version.id,
        version_no=version.version_no,
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
        extract_error=version.extract_error,
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
        name: wrap_provenance(None, provenance="manual", page_ref=1, status="disputed")
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
    names = (
        *EXTRACTED_FIELDS,
        *(key for key in OPTIONAL_EXTRACTED_FIELDS if key in extracted),
    )
    for name in names:
        entry = extracted.get(name, {})
        value = entry.get("value")
        status = entry.get("status", "unconfirmed")

        # A field the model reported as absent or contradicted is NOT
        # "extracted". Wrapping it that way put an "extracted · p.78" chip
        # next to an empty row on the confirm screen — the badge asserting the
        # value came from the document while the row said it did not. The
        # reader cannot tell a real citation from a blank that way.
        #
        # There is no provenance flavour for "we looked and it is not there",
        # and inventing one would ripple through the schema, the six fixtures
        # and the UI. Instead the envelope keeps `page_ref` (where we looked,
        # which is genuinely useful) and carries a warning the chip renders
        # instead of a false citation.
        missing = value in (None, "", [], {}) or status == "disputed"
        out[name] = wrap_provenance(
            value,
            provenance="extracted",
            page_ref=entry.get("page_ref"),
            source_id=source_id,
            confidence=entry.get("confidence"),
            status=status,
            warning=("not stated in the document — needs a value" if missing else None),
        )
    return out


def to_provenance_fields(
    extracted: dict[str, dict[str, Any]],
    *,
    model: str,
    prompt_version: str,
) -> dict[str, dict[str, Any]]:
    """Public alias for :func:`_to_provenance_fields`.

    The revision endpoint needs the same extract-to-provenance mapping the
    original upload uses; re-implementing it there would be the surest way to
    let the two drift apart.
    """

    return _to_provenance_fields(extracted, model=model, prompt_version=prompt_version)


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
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise SowNotFound(f"opportunity {opportunity_id} not found")

    sow = await _load_or_create_sow(session, opportunity_id)
    from app.services.sow_lifecycle import reserve_version_no

    version_no = await reserve_version_no(session, sow.id)

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        version_no=version_no,
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


def _needs_textract(pdf_bytes: bytes) -> bool:
    """True when the PDF has fewer than ``TEXT_DENSITY_MIN_CHARS_PER_PAGE``
    chars/page.

    Zero-byte payloads (test-only shortcut) skip Textract — the stub
    Bedrock in the S3-E5 suite passes ``b""`` and would otherwise trigger
    a spurious OCR call.
    """

    if not pdf_bytes:
        return False
    try:
        doc = extract_document_text(pdf_bytes)
    except UnreadableDocument:
        # Unparseable → try OCR; safer than running Bedrock over an empty
        # string. Textract will give its own error if it cannot read it.
        return True
    if doc.kind != "pdf":
        # DOCX carries a real text layer or none at all — Textract does not
        # accept Word files, so OCR is never the answer for one.
        return False
    return is_low_density(doc)


def prepare_extraction_document(
    file_bytes: bytes,
    *,
    content_type: str | None = None,
    textract: TextractClient | None = None,
) -> PreparedExtractionDocument:
    """Parse native text or recover an image-only PDF through Textract.

    The returned error is explicit and non-fabricating. Callers that already
    have a client/deal binding can preserve the source file and open manual
    review; callers without a binding can retain the upload job for a picker.
    """

    if not file_bytes:
        return PreparedExtractionDocument(
            text=text_document_from_string(""),
            extract_source=_EXTRACT_SOURCE_PDF,
        )

    try:
        parsed = extract_document_text(file_bytes, content_type)
    except UnreadableDocument as exc:
        if not file_bytes.startswith(b"%PDF-"):
            return PreparedExtractionDocument(
                text=None,
                extract_source=_EXTRACT_SOURCE_PDF,
                error=f"could not read document: {exc.reason}",
            )
        parsed = None

    needs_ocr = parsed is None or (parsed.kind == "pdf" and is_low_density(parsed))
    if not needs_ocr:
        return PreparedExtractionDocument(
            text=parsed,
            extract_source=_EXTRACT_SOURCE_PDF,
        )

    client = textract if textract is not None else TextractClient()
    try:
        recovered = client.extract_text(file_bytes)
    except TextractError as exc:
        return PreparedExtractionDocument(
            text=None,
            extract_source=_EXTRACT_SOURCE_TEXTRACT,
            error=f"OCR unavailable: {exc}",
        )
    if not recovered.strip():
        return PreparedExtractionDocument(
            text=None,
            extract_source=_EXTRACT_SOURCE_TEXTRACT,
            error="OCR unavailable: no text was recovered",
        )
    return PreparedExtractionDocument(
        text=text_document_from_string(recovered),
        extract_source=_EXTRACT_SOURCE_TEXTRACT,
    )


async def _locked_source(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> tuple[SowVersion, uuid.UUID]:
    version = await _load_version(session, sow_version_id)
    opportunity_id = await _opportunity_id_for(session, version.sow_id)
    # Match approval's parent-first lock order and refresh cached JSON before writing.
    parent = (
        await session.execute(
            select(Opportunity)
            .where(Opportunity.id == opportunity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    locked_version = (
        await session.execute(
            select(SowVersion)
            .where(SowVersion.id == sow_version_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if parent is None or locked_version is None:
        raise SowNotFound("SOW source no longer exists")
    return locked_version, opportunity_id


async def _mutable_source(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> tuple[SowVersion, uuid.UUID]:
    version, opportunity_id = await _locked_source(session, sow_version_id)
    from app.services.sow_lifecycle import was_ever_submitted

    sow = await session.get(Sow, version.sow_id)
    if (
        version.confirmed_at is not None
        or version.confirmed_by is not None
        or version.execution_state not in (None, "draft")
        or version.discarded_at is not None
        or version.superseded_by is not None
        or sow is None
        or sow.archived_at is not None
        or await was_ever_submitted(session, version.id)
    ):
        raise SowReplayConflict(
            "Submitted or immutable SOW source requires a new reviewed version"
        )
    return version, opportunity_id


async def run_extract(
    session: AsyncSession,
    *,
    sow_version_id: uuid.UUID,
    bedrock: BedrockSowExtract,
    file_bytes: bytes = b"",
    textract: TextractClient | None = None,
    replay: bool = False,
) -> SowVersionState:
    """Invoke Bedrock and persist the validated extract or fall through to
    manual-entry mode when the model is unavailable.

    Same-document replay preserves explicit human confirmations. Conflicting
    candidates remain separate and require review; failed attempts never erase
    prior evidence or claim completion. Submitted versions are immutable.

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

    version, opportunity_id = await _mutable_source(session, sow_version_id)
    previous = copy.deepcopy(version.extracted_fields or {})
    protected = {
        name: entry
        for name, entry in previous.items()
        if name != "metadata"
        and isinstance(entry, dict)
        and entry.get("status") == "confirmed"
    }
    if replay or version.extract_status != "pending" or protected:
        if hashlib.sha256(file_bytes).hexdigest() != version.file_hash:
            raise SowReplayConflict(
                "Document bytes differ from this version; source-change review is required"
            )

    prepared = prepare_extraction_document(file_bytes, textract=textract)
    extract_source = prepared.extract_source
    text_doc = prepared.text
    ocr_error = prepared.error

    result: ExtractedFields | ManualRequired
    error: str | None = None
    if ocr_error is not None or text_doc is None:
        result = ManualRequired(reason=ocr_error or "OCR unavailable")
    else:
        try:
            raw = bedrock.extract(text_doc)
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
        # S15: preserve the reason on the version itself so the confirm
        # page can render an honest banner. Was previously only in the
        # audit trail — the UI had no way to reach it.
        version.extract_error = result.reason
        fields_out = previous or _blank_manual_fields()
        metadata = fields_out.get("metadata")
        fields_out["metadata"] = {
            **(metadata if isinstance(metadata, dict) else {}),
            "extract_source": extract_source,
        }
        version.extracted_fields = fields_out
        action = "sow.extract_failed"
        after: dict[str, Any] = {
            "extract_status": "manual_required",
            "reason": result.reason,
            "extract_source": extract_source,
        }
    else:
        version.extract_status = "complete"
        version.extract_error = None
        fields_out = _to_provenance_fields(
            result.fields,
            model=result.model,
            prompt_version=result.prompt_version,
        )
        conflicts = {
            name: copy.deepcopy(fields_out[name])
            for name, entry in protected.items()
            if name in fields_out
            and fields_out[name].get("value") != entry.get("value")
        }
        fields_out.update(protected)
        fields_out["metadata"] = {
            "extract_source": extract_source,
            "reextract_conflicts": conflicts,
        }
        version.extracted_fields = fields_out
        version.extract_model = result.model
        version.extract_prompt_version = result.prompt_version
        suggested = fields_out.get("engagement_type_suggested", {}).get("value")
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
        if conflicts:
            version.extract_status = "manual_required"
            version.extract_error = (
                "Re-extraction conflicts with confirmed fields: "
                + ", ".join(sorted(conflicts))
            )
            action = "sow.extract_failed"
            after.update(
                extract_status="manual_required",
                reason=version.extract_error,
                conflicting_fields=sorted(conflicts),
            )

    after["preserved_confirmed_fields"] = sorted(protected)
    after["document_hash"] = version.file_hash

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

    version, opportunity_id = await _mutable_source(session, sow_version_id)

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

    version, opportunity_id = await _locked_source(session, sow_version_id)

    missing = _unconfirmed_fields(version.extracted_fields)
    conflicts = ((version.extracted_fields or {}).get("metadata") or {}).get(
        "reextract_conflicts"
    ) or {}
    missing.extend(f"extraction_conflict:{field}" for field in sorted(conflicts))
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
    "PreparedExtractionDocument",
    "SowSubmissionIncomplete",
    "SowVersionState",
    "confirm_field",
    "create_sow_version",
    "latest_version_for",
    "load_version_state",
    "prepare_extraction_document",
    "run_extract",
    "submit_sow",
]
