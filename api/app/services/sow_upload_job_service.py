"""SOW upload job envelope (S10-01).

Wraps :func:`app.services.sow_upload_pipeline.apply_pipeline` for the
single-file, human-in-the-loop path the ``POST /sows/upload`` router
serves. The bulk import story (S10-02) uses ``apply_pipeline`` directly
and manages its own envelope (``ImportFile``); this module owns
``sow_upload_job`` and layers on:

- Real S3 PUT via :mod:`app.integrations.s3_sow` (SigV4 pre-signed URL
  in prod, in-process stub in tests). ``StubS3`` short-circuits the
  network call so unit tests never touch AWS.
- Per-step ``audit_event`` writes keyed to the job — one per status
  transition (``queued`` → ``extracting`` → ``matching_client`` →
  ``deriving_gm`` → ``done`` / ``needs_pick`` / ``failed``).
- A durable :class:`SowUploadJob` envelope that survives a page reload
  so the picker can resume after the human chooses a client.

The public surface is small on purpose:

- :func:`find_by_hash` — dedupe lookup used by the router pre-flight.
- :func:`start_upload` — kick off the pipeline from raw bytes.
- :func:`resume_after_pick` — continue a paused job.
- :func:`serialize_job` — job → JSON for the router.
"""

from __future__ import annotations

import functools
import uuid
from datetime import UTC, datetime
from typing import Any

import anyio
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    StubBedrock,
    validate_extract,
)
from app.integrations.s3_sow import FileTooLarge, SowS3, UnsupportedContentType
from app.integrations.textract import TextractClient
from app.models.client import Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.services.document_type import (
    ALLOWED_START_TYPES,
    classify_text_document,
)
from app.services.sow_extract import (
    PreparedExtractionDocument,
    prepare_extraction_document,
)
from app.services.sow_upload_pipeline import (
    PipelineOutcome,
    apply_pipeline,
    sha256_hex,
)

log = structlog.get_logger("sow_upload_job_service")


class UploadPipelineError(Exception):
    """Base for expected pipeline failures the router surfaces to the human."""


class RejectedDocumentType(UploadPipelineError):
    """Document we will not start a pipeline for — the router maps this to 422.

    Two distinct cases share this type, and ``message`` is what keeps them
    apart for the user: we read the file and it is not a SOW, or we could not
    open the file at all. Telling someone "this does not look like a SOW"
    when the real problem is a corrupt upload sends them hunting for the
    wrong thing.
    """

    def __init__(
        self, detected_type: str, confidence: float, message: str | None = None
    ) -> None:
        self.detected_type = detected_type
        self.confidence = confidence
        self.message = message or (
            f"This file does not look like a SOW. Detected: {detected_type}."
        )
        super().__init__(
            f"file classified as {detected_type!r} at confidence {confidence:.2f}"
        )


# --- job helpers ----------------------------------------------------------


async def find_by_hash(session: AsyncSession, file_hash: str) -> SowUploadJob | None:
    """Return the existing job for this SHA-256, if any.

    S13a "fresh-start" rule: the hash only counts as a duplicate when the
    resulting record is still LIVE. A job whose ``sow_version_id`` was hard
    deleted (the row is gone) or whose ``sow`` was archived is not a live
    hit; the user must be allowed to re-upload the same bytes and produce
    a new record. Returning ``None`` here re-runs the pipeline.
    """

    from app.models.sow import Sow, SowVersion  # local: avoid cycles

    job = (
        await session.execute(
            select(SowUploadJob).where(SowUploadJob.file_hash == file_hash)
        )
    ).scalar_one_or_none()
    if job is None:
        return None
    # No downstream record ever landed → treat as reusable (retry/failed).
    if job.sow_version_id is None:
        return job
    row = (
        await session.execute(
            select(SowVersion, Sow.archived_at)
            .join(Sow, Sow.id == SowVersion.sow_id)
            .where(SowVersion.id == job.sow_version_id)
        )
    ).first()
    if row is None:
        # The sow_version was hard-deleted. Detach the job pointer so the
        # unique(file_hash) row can be reused for the fresh upload.
        job.sow_version_id = None
        job.opportunity_id = None
        return job
    _version, sow_archived_at = row
    if sow_archived_at is not None:
        # Archived → informational, not blocking. The caller (upload service)
        # decides whether to run again; today we let a fresh upload proceed
        # and the confirm screen shows a note that an archived SOW existed.
        job.sow_version_id = None
        job.opportunity_id = None
        return job
    return job


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> SowUploadJob | None:
    return (
        await session.execute(select(SowUploadJob).where(SowUploadJob.id == job_id))
    ).scalar_one_or_none()


async def _live_upload_job(session, job):
    from app.services.deletion_fences import source_deleted

    if await source_deleted(session, "sow_upload_job", job.id):
        raise UploadPipelineError("Upload source was deleted")
    current = await session.scalar(
        select(SowUploadJob)
        .where(
            SowUploadJob.id == job.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if current is None:
        raise UploadPipelineError("Upload source was deleted")
    return current


async def _emit(
    session: AsyncSession,
    *,
    job: SowUploadJob,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    await append_audit(
        session,
        actor_id=job.uploader_id,
        action=action,
        entity="sow_upload_job",
        entity_id=str(job.id),
        before=before,
        after=after,
    )


async def _transition(
    session: AsyncSession,
    *,
    job: SowUploadJob,
    status: str,
    resolution: str | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Move ``job.status`` and audit the transition atomically."""

    before = {
        "status": job.status,
        "resolution": job.resolution,
        "error": job.error,
    }
    job.status = status
    if resolution is not None:
        job.resolution = resolution
    if error is not None:
        job.error = error
    # Stamp `updated_at` explicitly — same reason as `start_upload`:
    # avoid a sync-context lazy-load on serialisation.
    job.updated_at = datetime.now(UTC)
    await session.flush()
    after: dict[str, Any] = {
        "status": job.status,
        "resolution": job.resolution,
        "error": job.error,
    }
    if extra:
        after.update(extra)
    await _emit(
        session,
        job=job,
        action=f"sow_upload_job.{status}",
        before=before,
        after=after,
    )


# --- S3 upload ------------------------------------------------------------


def _upload_to_s3(
    s3: SowS3,
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Upload the bytes and return the ``s3_key``.

    Was: presign a URL, then PUT to it with a blocking ``httpx.Client`` from
    inside an ``async def`` — a round-trip to sign a URL for ourselves, and up
    to 30 seconds of stalled event loop when S3 was slow. Now a direct
    ``put_object``. Synchronous; the caller runs it in a worker thread.
    """

    key = s3.build_key(filename, content_type)
    try:
        return s3.put_object(key, file_bytes, content_type)
    except (UnsupportedContentType, FileTooLarge) as exc:
        raise UploadPipelineError(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — surfaced to the caller as a job failure
        raise UploadPipelineError(f"S3 upload failed: {exc}") from exc


# --- resolution → SowVersion glue ----------------------------------------


async def _load_opportunity(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    return (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one()


async def _load_version(session: AsyncSession, sow_version_id: uuid.UUID) -> SowVersion:
    return (
        await session.execute(select(SowVersion).where(SowVersion.id == sow_version_id))
    ).scalar_one()


async def _stamp_s3_key(
    session: AsyncSession, sow_version_id: uuid.UUID, s3_key: str
) -> None:
    """Overwrite the placeholder ``file_s3_key`` the shared pipeline
    writes (``bulk-import/<hash>``) with the real key from the S3 PUT.

    Kept as a targeted UPDATE because the version row is immutable in
    spirit (rule 4) — the only column we touch is the pointer to the
    file blob, which is a set-once column populated at upload time.
    """

    version = await _load_version(session, sow_version_id)
    version.file_s3_key = s3_key
    await session.flush()


# --- new-client path ------------------------------------------------------


async def _create_new_client(
    session: AsyncSession,
    *,
    uploader_id: uuid.UUID,
    create_new: dict[str, Any],
) -> Client:
    name = str(create_new.get("legal_name") or "").strip()
    if not name:
        raise UploadPipelineError("create_new requires legal_name")
    client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=None, timezone=None)
    session.add(client)
    await session.flush()
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name=name))
    domain = create_new.get("domain")
    if isinstance(domain, str) and domain.strip():
        session.add(
            ClientAlias(
                id=uuid.uuid4(),
                client_id=client.id,
                alias=domain.strip().lower(),
                source="sow_upload",
            )
        )
    await session.flush()
    await append_audit(
        session,
        actor_id=uploader_id,
        action="client.created",
        entity="client",
        entity_id=str(client.id),
        before=None,
        after={"name": name, "source": "sow_upload"},
    )
    return client


async def _adopt_alias(
    session: AsyncSession, *, client: Client, legal_name: str | None
) -> None:
    if not legal_name:
        return
    if legal_name.strip().lower() == client.name.strip().lower():
        return
    session.add(
        ClientAlias(
            id=uuid.uuid4(),
            client_id=client.id,
            alias=legal_name.strip(),
            source="picker",
        )
    )
    await session.flush()


async def _create_opportunity(
    session: AsyncSession,
    *,
    uploader_id: uuid.UUID,
    client_id: uuid.UUID,
) -> Opportunity:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=None,
        source="sow_upload",
        owner_id=uploader_id,
        client_id=client_id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()
    await append_audit(
        session,
        actor_id=uploader_id,
        action="opportunity.created",
        entity="opportunity",
        entity_id=str(opp.id),
        before=None,
        after={
            "source": "sow_upload",
            "client_id": str(client_id),
            "governance_status": "Intake",
        },
    )
    # S17: SOW-first intake no longer auto-creates NDA/MSA tasks.
    return opp


async def _persist_sow_version_from_cache(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    uploader_id: uuid.UUID,
    s3_key: str,
    file_hash: str,
    cached_extract: dict[str, Any] | None,
) -> SowVersion:
    """Create a ``sow_version`` for a paused job that has the extract
    payload cached in ``needs_pick_payload``."""

    from app.services.sow_extract import _to_provenance_fields

    sow = (
        await session.execute(select(Sow).where(Sow.opportunity_id == opportunity.id))
    ).scalar_one_or_none()
    if sow is None:
        sow = Sow(id=uuid.uuid4(), opportunity_id=opportunity.id)
        session.add(sow)
        await session.flush()

    extract_status = "manual_required"
    payload = cached_extract or {}
    extract_source = payload.get("extract_source") or "sow_upload_pipeline"
    fields_out: dict[str, Any] = {"metadata": {"extract_source": extract_source}}
    model = None
    prompt_version = None
    suggested = None

    ex_fields = payload.get("fields")
    ex_model = payload.get("model")
    ex_prompt = payload.get("prompt_version")
    # S15: extract failure reason preserved so the confirm banner can be
    # honest about WHY manual entry is required, not just that it is.
    extract_error = payload.get("error")
    if isinstance(ex_fields, dict) and ex_model and ex_prompt:
        validated = validate_extract(
            {
                "fields": {
                    name: value
                    for name, value in ex_fields.items()
                    if name != "metadata"
                },
                "model": ex_model,
                "prompt_version": ex_prompt,
            }
        )
        fields_out = _to_provenance_fields(
            validated.fields,
            model=validated.model,
            prompt_version=validated.prompt_version,
        )
        cached_metadata = ex_fields.get("metadata")
        fields_out["metadata"] = {
            **(cached_metadata if isinstance(cached_metadata, dict) else {}),
            "extract_source": extract_source,
        }
        model = validated.model
        prompt_version = validated.prompt_version
        suggested = validated.fields.get("engagement_type_suggested", {}).get("value")
        extract_status = "complete"

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=uploader_id,
        file_s3_key=s3_key,
        file_hash=file_hash,
        extract_status=extract_status,
        extract_error=extract_error if extract_status == "manual_required" else None,
        extracted_fields=fields_out,
        extract_model=model,
        extract_prompt_version=prompt_version,
        engagement_type_suggested=(str(suggested) if suggested is not None else None),
    )
    session.add(version)
    await session.flush()

    await append_audit(
        session,
        actor_id=uploader_id,
        action="sow.uploaded",
        entity="sow_version",
        entity_id=str(version.id),
        before=None,
        after={
            "opportunity_id": str(opportunity.id),
            "sow_id": str(sow.id),
            "file_s3_key": s3_key,
            "file_hash": file_hash,
        },
    )
    await append_audit(
        session,
        actor_id=uploader_id,
        action=(
            "sow.extracted" if extract_status == "complete" else "sow.extract_failed"
        ),
        entity="sow_version",
        entity_id=str(version.id),
        before={"extract_status": "pending"},
        after={
            "extract_status": extract_status,
            "model": model,
            "prompt_version": prompt_version,
        },
    )
    return version


async def _run_downstream_from_version(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    version: SowVersion,
    actor_id: uuid.UUID,
) -> dict[str, Any]:
    """Classifier + auto-staff + auto-GM + confirmation build.

    Used when the pipeline resumes after a picker choice — the initial
    ``apply_pipeline`` run happens at pause time; this call finishes the
    chain now that we have a client + opportunity + version.
    """

    from app.services.sow_confirmation import build_confirmation

    payload = await build_confirmation(
        session,
        opportunity_id=opportunity.id,
        actor_id=actor_id,
    )
    return {
        "engagement_type": payload.engagement.primary.type,
        "gm_model_id": (str(payload.gm_model.id) if payload.gm_model else None),
        "needs_you_count": len(payload.needs_you),
    }


# --- pre-bound upload (S20 W3 T11/T37) ------------------------------------


async def _finish_bound_upload(
    session: AsyncSession,
    *,
    job: SowUploadJob,
    uploader_id: uuid.UUID,
    file_bytes: bytes,
    content_type: str,
    s3_key: str,
    bound_client_id: uuid.UUID,
    bound_opportunity_id: uuid.UUID,
    bedrock_caller: BedrockSowExtract,
    prepared_document: PreparedExtractionDocument,
) -> SowUploadJob:
    """T11/T37 short-circuit — the caller pre-bound client + deal.

    Skips the pipeline's client-match step, creates the ``sow_version``
    under the named opportunity, and preserves the file + any extract
    result even when extraction failed. The job's
    ``needs_pick_payload`` records the binding (``binding.client_id``,
    ``binding.opportunity_id``) so the D1 migration can move the values
    into first-class columns without changing the router contract.
    """

    from app.models.opportunity import Opportunity
    from app.services.sow_extract import _to_provenance_fields
    from app.services.sow_upload_pipeline import _run_extract

    job = await _live_upload_job(session, job)
    if job.status == "done":
        return job
    # Load + validate the binding again — the router checked already,
    # but we don't trust anything between here and there.
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == bound_opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None or opp.client_id != bound_client_id:
        await _transition(
            session,
            job=job,
            status="failed",
            error=(
                f"binding rejected: opportunity {bound_opportunity_id} not found or client mismatch"
            ),
        )
        raise UploadPipelineError(
            f"opportunity {bound_opportunity_id} not bound to client {bound_client_id}"
        )

    # Extract now — reuse the same helper `apply_pipeline` uses. This
    # path returns the extracted fields (or a failure reason) without
    # invoking the client-matcher.
    extract_error: str | None
    try:
        if prepared_document.error is not None or prepared_document.text is None:
            extract_outcome = None
            extract_error = prepared_document.error or "OCR unavailable"
        else:
            extract_outcome = await _run_extract(
                prepared_document.text,
                bedrock=bedrock_caller,
            )
            extract_error = extract_outcome.error
    except Exception as exc:  # noqa: BLE001 — always preserve the file
        extract_outcome = None
        extract_error = f"extract crashed: {exc}"

    source_metadata: dict[str, Any] = {
        "extract_source": prepared_document.extract_source
    }
    if prepared_document.text is not None:
        source_metadata.update(
            ref_unit=prepared_document.text.ref_unit,
            document_kind=prepared_document.text.kind,
        )
    fields_out: dict[str, Any] = {"metadata": source_metadata}
    extract_status = "manual_required"
    model: str | None = None
    prompt_version: str | None = None
    suggested = None

    if (
        extract_outcome is not None
        and extract_outcome.fields is not None
        and extract_outcome.model is not None
        and extract_outcome.prompt_version is not None
    ):
        try:
            fields_out = _to_provenance_fields(
                extract_outcome.fields,
                model=extract_outcome.model,
                prompt_version=extract_outcome.prompt_version,
            )
            fields_out["metadata"] = source_metadata
            model = extract_outcome.model
            prompt_version = extract_outcome.prompt_version
            suggested = (
                extract_outcome.fields.get("engagement_type_suggested", {}) or {}
            ).get("value")
            extract_status = "complete"
            extract_error = None
        except Exception as exc:  # noqa: BLE001
            extract_error = f"extract returned invalid schema: {exc}"

    # Create the sow (or reuse the existing one — the D1 uniqueness
    # relax landing later will allow multiple SOWs per deal).
    sow_row = (
        await session.execute(
            select(Sow).where(Sow.opportunity_id == bound_opportunity_id)
        )
    ).scalar_one_or_none()
    if sow_row is None:
        sow_row = Sow(id=uuid.uuid4(), opportunity_id=bound_opportunity_id)
        session.add(sow_row)
        await session.flush()

    from app.services.sow_lifecycle import reserve_version_no

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow_row.id,
        uploaded_by=uploader_id,
        file_s3_key=s3_key,
        file_hash=job.file_hash,
        extract_status=extract_status,
        extract_error=extract_error if extract_status != "complete" else None,
        extracted_fields=fields_out,
        extract_model=model,
        extract_prompt_version=prompt_version,
        engagement_type_suggested=(str(suggested) if suggested is not None else None),
        version_no=await reserve_version_no(session, sow_row.id),
    )
    session.add(version)
    await session.flush()

    await append_audit(
        session,
        actor_id=uploader_id,
        action="sow.uploaded",
        entity="sow_version",
        entity_id=str(version.id),
        before=None,
        after={
            "opportunity_id": str(bound_opportunity_id),
            "sow_id": str(sow_row.id),
            "file_s3_key": s3_key,
            "file_hash": job.file_hash,
            "binding": {
                "source": "explicit",
                "client_id": str(bound_client_id),
                "opportunity_id": str(bound_opportunity_id),
            },
        },
    )
    await append_audit(
        session,
        actor_id=uploader_id,
        action=(
            "sow.extracted" if extract_status == "complete" else "sow.extract_failed"
        ),
        entity="sow_version",
        entity_id=str(version.id),
        before={"extract_status": "pending"},
        after={
            "extract_status": extract_status,
            "model": model,
            "prompt_version": prompt_version,
            "error": extract_error,
        },
    )

    job.opportunity_id = bound_opportunity_id
    job.sow_version_id = version.id
    job.resolution = "matched"
    # `needs_pick_payload` means "the pipeline needs a human to disambiguate";
    # the bound path skipped the picker entirely, so it stays None. The
    # binding is already captured on `job.opportunity_id` + the SowVersion
    # under `Sow.opportunity_id`; a future migration can promote them to
    # first-class columns without needing a JSON envelope here.
    job.needs_pick_payload = None
    await session.flush()

    # If extraction failed, stop here — the file is safe on S3, the
    # binding is recorded, and the confirm page will show the extract
    # error banner + manual-entry form (T12).
    if extract_status != "complete":
        await _transition(
            session,
            job=job,
            status="done",
            extra={
                "opportunity_id": str(bound_opportunity_id),
                "sow_version_id": str(version.id),
                "extract_status": extract_status,
                "extract_error": extract_error,
            },
        )
        return job

    await _transition(session, job=job, status="deriving_gm")
    downstream = await _run_downstream_from_version(
        session,
        opportunity=opp,
        version=version,
        actor_id=uploader_id,
    )
    await _transition(
        session,
        job=job,
        status="done",
        extra={
            "opportunity_id": str(bound_opportunity_id),
            "sow_version_id": str(version.id),
            **downstream,
        },
    )
    return job


# --- public entrypoints ---------------------------------------------------


async def start_upload(
    session: AsyncSession,
    *,
    uploader_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    client_hint: str | None,
    s3: SowS3,
    bedrock_sow: BedrockSowExtract | None = None,
    textract: TextractClient | None = None,
    bound_client_id: uuid.UUID | None = None,
    bound_opportunity_id: uuid.UUID | None = None,
) -> SowUploadJob:
    """Kick off the pipeline for a fresh single-file upload.

    Returns the ``sow_upload_job`` row in its terminal-or-paused state.
    Raises :class:`RejectedDocumentType` when the doc-type gate rejects
    the file — no DB rows are created in that case (per story AC).

    S20 W3 T11/T37: when ``bound_client_id`` and ``bound_opportunity_id``
    are supplied, the pipeline skips the fuzzy-match/picker step. Both
    are stashed on the job's ``needs_pick_payload`` under a ``binding``
    key until the D1 migration adds real columns (see
    `docs/reports/s20/requests.md#W3-2026-09-30-03`). The pipeline
    creates the SOW under the named opportunity directly; extraction
    failure preserves the file + the binding + any entered corrections.
    """

    file_hash = sha256_hex(file_bytes)

    # Hash-first dedupe against previously uploaded jobs. A terminal failure
    # is not a duplicate: `file_hash` is UNIQUE, so without this branch one
    # failed attempt would make those exact bytes permanently un-uploadable.
    # Reuse the row (it keeps the audit trail attached) and run again.
    existing = await find_by_hash(session, file_hash)
    retry_job: SowUploadJob | None = None
    if existing is not None:
        if existing.status != "failed":
            return existing
        retry_job = existing

    prepared = prepare_extraction_document(
        file_bytes,
        content_type=content_type,
        textract=textract,
    )
    if prepared.error is not None and prepared.extract_source != "textract":
        raise RejectedDocumentType(
            "unreadable",
            0.0,
            message=(
                f"We could not read this file. {prepared.error.capitalize()}. "
                "Please upload a PDF or a .docx Word document."
            ),
        )
    if prepared.text is None:
        detected_type = "scanned_document"
        detected_confidence = 0.0
    else:
        doc = classify_text_document(prepared.text)
        detected_type = doc.type
        detected_confidence = doc.confidence
        if doc.type not in ALLOWED_START_TYPES:
            raise RejectedDocumentType(doc.type, doc.confidence)

    bedrock_caller = bedrock_sow if bedrock_sow is not None else StubBedrock()

    # Create job row + `queued` audit. Explicit timestamps so serialization
    # never has to lazy-load a server-default value from within a sync
    # Pydantic path (SQLite/aiosqlite doesn't support that).
    now = datetime.now(UTC)
    if retry_job is not None:
        job = retry_job
        job.status = "queued"
        job.error = None
        job.resolution = None
        job.needs_pick_payload = None
        job.updated_at = now
    else:
        job = SowUploadJob(
            id=uuid.uuid4(),
            uploader_id=uploader_id,
            s3_key=None,
            file_hash=file_hash,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        session.add(job)
    await session.flush()
    await _emit(
        session,
        job=job,
        action="sow_upload_job.queued",
        before=None,
        after={
            "file_hash": file_hash,
            "detected_type": detected_type,
            "detected_confidence": round(detected_confidence, 3),
            "client_hint": client_hint,
        },
    )

    # Real S3 PUT.
    try:
        s3_key = await anyio.to_thread.run_sync(
            functools.partial(
                _upload_to_s3,
                s3,
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        )
    except UploadPipelineError as exc:
        await _transition(session, job=job, status="failed", error=str(exc))
        raise

    job.s3_key = s3_key
    await session.flush()
    await _transition(
        session,
        job=job,
        status="extracting",
        extra={"s3_key": s3_key},
    )

    # Per-step audits framing the shared pipeline call.
    await _transition(session, job=job, status="classifying")
    await _transition(session, job=job, status="matching_client")

    # S20 W3 T11/T37: pre-bound path. The caller has already declared
    # the client + opportunity — the pipeline skips its fuzzy-match /
    # picker step and creates the SOW under the named opportunity. If
    # extraction fails the binding is still preserved on the job so the
    # confirm page can offer manual entry without asking the user to
    # re-pick the client.
    if bound_client_id is not None and bound_opportunity_id is not None:
        return await _finish_bound_upload(
            session,
            job=job,
            uploader_id=uploader_id,
            file_bytes=file_bytes,
            content_type=content_type,
            s3_key=s3_key,
            bound_client_id=bound_client_id,
            bound_opportunity_id=bound_opportunity_id,
            bedrock_caller=bedrock_caller,
            prepared_document=prepared,
        )

    result = await apply_pipeline(
        session,
        file_bytes=file_bytes,
        uploader_id=uploader_id,
        source="sow_upload",
        content_type=content_type,
        bedrock=bedrock_caller,
        textract=textract,
        prepared_document=prepared,
    )

    if result.outcome == PipelineOutcome.NEEDS_PICK:
        # S15: preserve the extract failure reason. Previously the reason
        # from a ManualRequired outcome was stashed in result.warnings and
        # then dropped here; the confirm page had no way to tell the user
        # "we couldn't read this document because <x>" so it presented
        # the failure as N missing-field problems.
        extract_error = next(
            (
                w
                for w in (result.warnings or [])
                if w.startswith("extract manual_required:")
                or w.startswith("extract crashed:")
                or w.startswith("extract returned ")
            ),
            None,
        )
        job.needs_pick_payload = {
            "signals": result.client_signals or {},
            "extract": {
                "fields": result.extract_fields,
                "model": result.extract_model,
                "prompt_version": result.extract_prompt_version,
                "extract_source": result.extract_source,
                "error": extract_error,
            },
            "candidates": result.needs_pick_candidates,
            "create_new": result.create_new or {},
        }
        await _transition(
            session,
            job=job,
            status="needs_pick",
            resolution="needs_pick",
            extra={"candidates": result.needs_pick_candidates},
        )
        return job

    if result.outcome == PipelineOutcome.REJECTED:
        # Guarded above via doc-type gate, but be defensive.
        await _transition(
            session,
            job=job,
            status="failed",
            error=f"pipeline rejected: {result.errors}",
        )
        raise RejectedDocumentType(
            result.detected_type or "other",
            result.detected_confidence or 0.0,
        )

    # IMPORTED / NEEDS_REVIEW: opportunity + sow_version exist. Stamp the
    # real S3 key and drive the confirmation build for the audit trail.
    if result.sow_version_id is None or result.opportunity_id is None:
        await _transition(
            session,
            job=job,
            status="failed",
            error="pipeline returned no opportunity/sow_version",
        )
        return job

    await _stamp_s3_key(session, result.sow_version_id, s3_key)

    job.opportunity_id = result.opportunity_id
    job.sow_version_id = result.sow_version_id
    job.resolution = "matched"
    await session.flush()

    await _transition(session, job=job, status="deriving_gm")

    opportunity = await _load_opportunity(session, result.opportunity_id)
    version = await _load_version(session, result.sow_version_id)
    downstream = await _run_downstream_from_version(
        session,
        opportunity=opportunity,
        version=version,
        actor_id=uploader_id,
    )

    await _transition(
        session,
        job=job,
        status="done",
        extra={
            "opportunity_id": str(opportunity.id),
            "sow_version_id": str(version.id),
            **downstream,
        },
    )
    return job


async def resume_after_pick(
    session: AsyncSession,
    *,
    job: SowUploadJob,
    client_id: uuid.UUID | None,
    create_new: dict[str, Any] | None,
    agreements_signed: bool = False,
) -> SowUploadJob:
    """Resume a paused job once the reviewer has chosen a client.

    Idempotent: a job already in ``done`` returns unchanged. The endpoint
    surfaces ``resolution`` so the caller can see whether the pick was
    ``matched`` (existing client) or ``created`` (new client).
    """

    job = await _live_upload_job(session, job)
    if job.status == "done":
        return job
    if job.status != "needs_pick":
        raise UploadPipelineError(
            f"job {job.id} status is {job.status!r}; expected needs_pick"
        )

    payload = job.needs_pick_payload or {}
    signals = payload.get("signals") or {}
    extract_cache = payload.get("extract") or {}

    if create_new:
        # Merge domain + address from the cached signals when the
        # picker only shipped legal_name.
        merged = dict(create_new)
        merged.setdefault("domain", signals.get("domain"))
        merged.setdefault("address_lines", signals.get("address_lines") or [])
        client = await _create_new_client(
            session, uploader_id=job.uploader_id, create_new=merged
        )
        resolution = "created"
    elif client_id is not None:
        client = (
            await session.execute(select(Client).where(Client.id == client_id))
        ).scalar_one_or_none()
        if client is None:
            raise UploadPipelineError(f"client {client_id} does not exist")
        await _adopt_alias(session, client=client, legal_name=signals.get("legal_name"))
        resolution = "matched"
    else:
        raise UploadPipelineError("pick requires either client_id or create_new")

    opportunity = await _create_opportunity(
        session, uploader_id=job.uploader_id, client_id=client.id
    )
    version = await _persist_sow_version_from_cache(
        session,
        opportunity=opportunity,
        uploader_id=job.uploader_id,
        s3_key=job.s3_key or "unknown",
        file_hash=job.file_hash,
        cached_extract=extract_cache,
    )

    job.opportunity_id = opportunity.id
    job.sow_version_id = version.id
    job.resolution = resolution
    if agreements_signed:
        # S17 checkbox: informational only, no gate. Stamp on the version
        # so the confirmation payload can surface it as a note.
        version.agreements_signed = True
    await session.flush()

    await _transition(session, job=job, status="deriving_gm")
    downstream = await _run_downstream_from_version(
        session,
        opportunity=opportunity,
        version=version,
        actor_id=job.uploader_id,
    )
    await _transition(
        session,
        job=job,
        status="done",
        extra={
            "opportunity_id": str(opportunity.id),
            "sow_version_id": str(version.id),
            **downstream,
        },
    )
    return job


# --- serialisation --------------------------------------------------------


def serialize_job(job: SowUploadJob) -> dict[str, Any]:
    """Job → JSON envelope for the router.

    The ``needs_pick`` payload is echoed verbatim so the frontend can
    render its picker modal from the same object the pipeline stored.
    """

    return {
        "id": str(job.id),
        "status": job.status,
        "resolution": job.resolution,
        "error": job.error,
        "opportunity_id": (str(job.opportunity_id) if job.opportunity_id else None),
        "sow_version_id": (str(job.sow_version_id) if job.sow_version_id else None),
        "file_hash": job.file_hash,
        "s3_key": job.s3_key,
        "needs_pick": job.needs_pick_payload,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


__all__ = [
    "RejectedDocumentType",
    "UploadPipelineError",
    "find_by_hash",
    "get_job",
    "resume_after_pick",
    "serialize_job",
    "start_upload",
]
