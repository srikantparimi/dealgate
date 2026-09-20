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
from app.models.client import Client, LegalEntity
from app.models.client_alias import ClientAlias
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.services.document_text import UnreadableDocument
from app.services.document_type import (
    ALLOWED_START_TYPES,
    classify_document,
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


async def find_by_hash(
    session: AsyncSession, file_hash: str
) -> SowUploadJob | None:
    """Return the existing job for this SHA-256, if any. Dedupe entry point."""

    return (
        await session.execute(
            select(SowUploadJob).where(SowUploadJob.file_hash == file_hash)
        )
    ).scalar_one_or_none()


async def get_job(
    session: AsyncSession, job_id: uuid.UUID
) -> SowUploadJob | None:
    return (
        await session.execute(select(SowUploadJob).where(SowUploadJob.id == job_id))
    ).scalar_one_or_none()


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


async def _load_version(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> SowVersion:
    return (
        await session.execute(
            select(SowVersion).where(SowVersion.id == sow_version_id)
        )
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
    client = Client(
        id=uuid.uuid4(), name=name, hubspot_company_id=None, timezone=None
    )
    session.add(client)
    await session.flush()
    session.add(
        LegalEntity(id=uuid.uuid4(), client_id=client.id, name=name)
    )
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
        await session.execute(
            select(Sow).where(Sow.opportunity_id == opportunity.id)
        )
    ).scalar_one_or_none()
    if sow is None:
        sow = Sow(id=uuid.uuid4(), opportunity_id=opportunity.id)
        session.add(sow)
        await session.flush()

    extract_status = "manual_required"
    fields_out: dict[str, Any] = {
        "metadata": {"extract_source": "sow_upload_pipeline"}
    }
    model = None
    prompt_version = None
    suggested = None

    payload = cached_extract or {}
    ex_fields = payload.get("fields")
    ex_model = payload.get("model")
    ex_prompt = payload.get("prompt_version")
    if isinstance(ex_fields, dict) and ex_model and ex_prompt:
        validated = validate_extract(
            {
                "fields": ex_fields,
                "model": ex_model,
                "prompt_version": ex_prompt,
            }
        )
        fields_out = _to_provenance_fields(
            validated.fields, model=validated.model,
            prompt_version=validated.prompt_version,
        )
        fields_out["metadata"] = {"extract_source": "sow_upload_pipeline"}
        model = validated.model
        prompt_version = validated.prompt_version
        suggested = validated.fields.get("engagement_type_suggested", {}).get(
            "value"
        )
        extract_status = "complete"

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=uploader_id,
        file_s3_key=s3_key,
        file_hash=file_hash,
        extract_status=extract_status,
        extracted_fields=fields_out,
        extract_model=model,
        extract_prompt_version=prompt_version,
        engagement_type_suggested=(
            str(suggested) if suggested is not None else None
        ),
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
            "sow.extracted"
            if extract_status == "complete"
            else "sow.extract_failed"
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
        "gm_model_id": (
            str(payload.gm_model.id) if payload.gm_model else None
        ),
        "needs_you_count": len(payload.needs_you),
    }


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
) -> SowUploadJob:
    """Kick off the pipeline for a fresh single-file upload.

    Returns the ``sow_upload_job`` row in its terminal-or-paused state.
    Raises :class:`RejectedDocumentType` when the doc-type gate rejects
    the file — no DB rows are created in that case (per story AC).
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

    # Doc-type gate — we probe before creating a job row so a résumé
    # rejection leaves no trace beyond the 422 response body.
    try:
        doc = classify_document(file_bytes, content_type=content_type)
    except UnreadableDocument as exc:
        # Accepted MIME type, unreadable bytes. 422 with the real reason —
        # never a 500, and never the misleading "not a SOW" message.
        raise RejectedDocumentType(
            "unreadable",
            0.0,
            message=(
                f"We could not read this file. {exc.reason.capitalize()}. "
                "Please upload a PDF or a .docx Word document."
            ),
        ) from exc
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
            "detected_type": doc.type,
            "detected_confidence": round(doc.confidence, 3),
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
        await _transition(
            session, job=job, status="failed", error=str(exc)
        )
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

    result = await apply_pipeline(
        session,
        file_bytes=file_bytes,
        uploader_id=uploader_id,
        source="sow_upload",
        content_type=content_type,
        bedrock=bedrock_caller,
    )

    if result.outcome == PipelineOutcome.NEEDS_PICK:
        job.needs_pick_payload = {
            "signals": result.client_signals or {},
            "extract": {
                "fields": result.extract_fields,
                "model": result.extract_model,
                "prompt_version": result.extract_prompt_version,
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
) -> SowUploadJob:
    """Resume a paused job once the reviewer has chosen a client.

    Idempotent: a job already in ``done`` returns unchanged. The endpoint
    surfaces ``resolution`` so the caller can see whether the pick was
    ``matched`` (existing client) or ``created`` (new client).
    """

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
        merged.setdefault(
            "address_lines", signals.get("address_lines") or []
        )
        client = await _create_new_client(
            session, uploader_id=job.uploader_id, create_new=merged
        )
        resolution = "created"
    elif client_id is not None:
        client = (
            await session.execute(
                select(Client).where(Client.id == client_id)
            )
        ).scalar_one_or_none()
        if client is None:
            raise UploadPipelineError(f"client {client_id} does not exist")
        await _adopt_alias(
            session, client=client, legal_name=signals.get("legal_name")
        )
        resolution = "matched"
    else:
        raise UploadPipelineError(
            "pick requires either client_id or create_new"
        )

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
        "opportunity_id": (
            str(job.opportunity_id) if job.opportunity_id else None
        ),
        "sow_version_id": (
            str(job.sow_version_id) if job.sow_version_id else None
        ),
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
