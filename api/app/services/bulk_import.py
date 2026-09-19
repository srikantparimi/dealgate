"""Bulk SOW import orchestrator (S10-02).

Fan-out over N files. Each file gets its own row in ``import_file`` and
is driven through ``sow_upload_pipeline.apply_pipeline`` — the very
same code path a single upload uses. Bulk is not a parallel
implementation, it is a second entry.

Batch counters are recomputed after every file so the UI can refresh
the summary card without a second round-trip.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import BedrockSowExtract
from app.models.import_batch import (
    IMPORT_FILE_STATUSES,
    ImportBatch,
    ImportFile,
)
from app.models.client import Client
from app.services.sow_upload_pipeline import (
    PipelineOutcome,
    PipelineResult,
    apply_pipeline,
    sha256_hex,
)


BULK_IMPORT_ROLES: tuple[str, ...] = (
    "SystemAdmin",
    "Finance",
    "Delivery",
    "CEO",
)


@dataclass
class InputFile:
    filename: str
    payload: bytes


@dataclass
class BatchOverview:
    batch: ImportBatch
    files: list[ImportFile] = field(default_factory=list)


# ---- role gate ------------------------------------------------------------


def assert_bulk_role(user_groups: Iterable[str]) -> None:
    from fastapi import HTTPException, status

    if not any(r in BULK_IMPORT_ROLES for r in user_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="bulk import is SysAdmin / Finance / Delivery / CEO only",
        )


# ---- payload helpers ------------------------------------------------------


def expand_zip_or_files(files: list[InputFile]) -> list[InputFile]:
    """If the caller sent one ``.zip``, expand it into member files.

    Members named with a leading dot or a subdir prefix are kept as
    given so filenames remain traceable in the queue.
    """

    if len(files) == 1 and files[0].filename.lower().endswith(".zip"):
        out: list[InputFile] = []
        with zipfile.ZipFile(io.BytesIO(files[0].payload)) as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                with zf.open(name) as member:
                    out.append(InputFile(filename=name, payload=member.read()))
        return out
    return files


# ---- batch lifecycle ------------------------------------------------------


async def create_batch(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    files: list[InputFile],
) -> ImportBatch:
    """Create a fresh batch envelope with one queued ImportFile per input."""

    batch = ImportBatch(
        id=uuid.uuid4(),
        run_by=actor_id,
        status="processing",
        file_count=len(files),
        queued_count=len(files),
    )
    session.add(batch)
    await session.flush()
    for f in files:
        row = ImportFile(
            id=uuid.uuid4(),
            batch_id=batch.id,
            filename=f.filename,
            size_bytes=len(f.payload),
            sha256=sha256_hex(f.payload),
            status="queued",
            warnings=[],
            errors=[],
        )
        session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="bulk_import.batch_created",
        entity="import_batch",
        entity_id=str(batch.id),
        before=None,
        after={"file_count": len(files), "status": "processing"},
    )
    await session.commit()
    await session.refresh(batch)
    return batch


async def process_batch(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload_by_sha: dict[str, bytes],
    bedrock: BedrockSowExtract | None = None,
) -> BatchOverview:
    """Drive every queued file in the batch through the shared pipeline.

    ``payload_by_sha`` maps the ``ImportFile.sha256`` back to the raw
    bytes — the router keeps the request payload in memory long enough
    to seed this call so we do not need per-batch S3 storage. Files
    whose bytes are missing are marked ``rejected`` with a matching
    error.
    """

    batch = await _load_batch(session, batch_id)
    files = await _load_files(session, batch_id)

    for row in files:
        if row.status not in ("queued", "rejected", "duplicate"):
            # Idempotent re-run: already-terminal SOW rows stay put.
            continue
        payload = payload_by_sha.get(row.sha256)
        if payload is None:
            row.status = "rejected"
            row.errors = _append(row.errors, "payload missing on rerun")
            continue

        row.status = "extracting"
        await session.flush()
        try:
            result = await apply_pipeline(
                session,
                file_bytes=payload,
                uploader_id=actor_id,
                source="bulk_import",
                bedrock=bedrock,
            )
            # Bulk imports have no picker UI mid-flight — a NEEDS_PICK
            # result carries the extracted legal_name; we auto-create the
            # client and re-drive the pipeline. The record still lands
            # as ``legacy_not_evidenced`` so a human confirms it later
            # from the Needs-review queue.
            if result.outcome == PipelineOutcome.NEEDS_PICK:
                result = await _auto_create_and_retry(
                    session,
                    payload=payload,
                    actor_id=actor_id,
                    previous=result,
                    bedrock=bedrock,
                )
        except Exception as exc:  # noqa: BLE001 — never let one file kill the batch
            row.status = "rejected"
            row.errors = _append(row.errors, f"pipeline crashed: {exc}")
            await session.flush()
            continue

        _apply_result(row, result)
        await append_audit(
            session,
            actor_id=actor_id,
            action=f"bulk_import.file_{row.status}",
            entity="import_file",
            entity_id=str(row.id),
            before=None,
            after={
                "sha256": row.sha256,
                "detected_type": row.detected_type,
                "status": row.status,
                "sow_version_id": (
                    str(row.sow_version_id) if row.sow_version_id else None
                ),
                "duplicate_of": (
                    str(row.duplicate_of) if row.duplicate_of else None
                ),
            },
        )
        await session.flush()

    files = await _load_files(session, batch_id)
    _recount(batch, files)
    await session.flush()
    await session.commit()
    await session.refresh(batch)
    return BatchOverview(batch=batch, files=files)


async def rerun_batch(
    session: AsyncSession,
    *,
    batch_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload_by_sha: dict[str, bytes],
    bedrock: BedrockSowExtract | None = None,
) -> BatchOverview:
    """Re-drive the pipeline for every non-imported file in the batch.

    Idempotent: rows already in ``imported`` / ``duplicate`` / ``rejected``
    stay put; ``needs_review`` rows are re-queued.
    """

    files = await _load_files(session, batch_id)
    for row in files:
        if row.status in ("needs_review",):
            row.status = "queued"
    await session.flush()
    await session.commit()
    return await process_batch(
        session,
        batch_id=batch_id,
        actor_id=actor_id,
        payload_by_sha=payload_by_sha,
        bedrock=bedrock,
    )


# ---- helpers --------------------------------------------------------------


async def _auto_create_and_retry(
    session: AsyncSession,
    *,
    payload: bytes,
    actor_id: uuid.UUID,
    previous: PipelineResult,
    bedrock: BedrockSowExtract | None,
) -> PipelineResult:
    """Auto-create a Client from the pipeline's extracted signals + retry.

    The single-upload path opens a picker; the bulk path has no such
    UI, so we materialise the ``create_new`` block into a real Client
    row and hand the same bytes back through :func:`apply_pipeline`.
    The retry hits the hash dedupe branch if the pipeline already
    persisted a row (belt-and-braces).
    """

    create_new = previous.create_new or {}
    legal_name = (create_new.get("legal_name") or "").strip()
    if not legal_name:
        # Nothing to key on — keep the NEEDS_PICK outcome so the file
        # stays in the Needs-review queue for a human to disposition.
        return previous
    # Reuse an existing client with the same name if the caller races
    # us — otherwise mint a fresh row.
    existing = (
        await session.execute(select(Client).where(Client.name == legal_name))
    ).scalar_one_or_none()
    if existing is None:
        client = Client(id=uuid.uuid4(), name=legal_name)
        session.add(client)
        await session.flush()
    return await apply_pipeline(
        session,
        file_bytes=payload,
        uploader_id=actor_id,
        source="bulk_import",
        bedrock=bedrock,
    )


async def _load_batch(session: AsyncSession, batch_id: uuid.UUID) -> ImportBatch:
    from fastapi import HTTPException, status

    row = (
        await session.execute(
            select(ImportBatch).where(ImportBatch.id == batch_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="import_batch not found"
        )
    return row


async def _load_files(
    session: AsyncSession, batch_id: uuid.UUID
) -> list[ImportFile]:
    stmt = (
        select(ImportFile)
        .where(ImportFile.batch_id == batch_id)
        .order_by(ImportFile.created_at.asc(), ImportFile.id.asc())
    )
    return list((await session.execute(stmt)).scalars())


def _apply_result(row: ImportFile, result: PipelineResult) -> None:
    row.detected_type = result.detected_type
    row.matched_client_id = result.matched_client_id
    row.matched_confidence = result.matched_confidence
    if result.opportunity_id is not None:
        row.opportunity_id = result.opportunity_id
    if result.sow_version_id is not None:
        row.sow_version_id = result.sow_version_id
    if result.duplicate_of is not None:
        row.duplicate_of = result.duplicate_of
    row.warnings = list(row.warnings or []) + list(result.warnings)
    row.errors = list(row.errors or []) + list(result.errors)
    row.status = _outcome_to_status(result.outcome)


def _outcome_to_status(outcome: PipelineOutcome) -> str:
    return {
        PipelineOutcome.IMPORTED: "imported",
        PipelineOutcome.NEEDS_REVIEW: "needs_review",
        PipelineOutcome.NEEDS_PICK: "needs_review",
        PipelineOutcome.DUPLICATE: "duplicate",
        PipelineOutcome.REJECTED: "rejected",
    }[outcome]


def _append(existing: list[str] | None, message: str) -> list[str]:
    out = list(existing or [])
    out.append(message)
    return out


def _recount(batch: ImportBatch, files: list[ImportFile]) -> None:
    batch.file_count = len(files)
    batch.queued_count = sum(1 for f in files if f.status == "queued")
    batch.imported_count = sum(1 for f in files if f.status == "imported")
    batch.rejected_count = sum(1 for f in files if f.status == "rejected")
    batch.duplicate_count = sum(1 for f in files if f.status == "duplicate")
    batch.needs_review_count = sum(1 for f in files if f.status == "needs_review")
    processing = any(
        f.status in {"queued", "extracting", "classifying", "matching_client", "deriving_gm"}
        for f in files
    )
    batch.status = "processing" if processing else "completed"


# ---- read side ------------------------------------------------------------


async def load_overview(
    session: AsyncSession, batch_id: uuid.UUID
) -> BatchOverview:
    batch = await _load_batch(session, batch_id)
    files = await _load_files(session, batch_id)
    return BatchOverview(batch=batch, files=files)


def csv_rows(overview: BatchOverview) -> list[list[str]]:
    """Streaming rows for ``GET /admin/bulk-imports/{id}/log.csv``."""

    header = [
        "batch_id",
        "filename",
        "sha256",
        "size",
        "detected_type",
        "status",
        "matched_client",
        "confidence",
        "opportunity_id",
        "sow_version_id",
        "warnings",
        "errors",
        "created_at",
        "updated_at",
        "record_url",
    ]
    rows: list[list[str]] = [header]
    for f in overview.files:
        record_url = (
            f"/sows/{f.opportunity_id}"
            if f.opportunity_id is not None
            else ""
        )
        rows.append(
            [
                str(overview.batch.id),
                f.filename,
                f.sha256,
                str(f.size_bytes),
                f.detected_type or "",
                f.status,
                str(f.matched_client_id) if f.matched_client_id else "",
                format(f.matched_confidence, "f") if f.matched_confidence else "",
                str(f.opportunity_id) if f.opportunity_id else "",
                str(f.sow_version_id) if f.sow_version_id else "",
                "; ".join(str(w) for w in (f.warnings or [])),
                "; ".join(str(e) for e in (f.errors or [])),
                f.created_at.isoformat() if f.created_at else "",
                f.updated_at.isoformat() if f.updated_at else "",
                record_url,
            ]
        )
    return rows


__all__ = [
    "BULK_IMPORT_ROLES",
    "BatchOverview",
    "InputFile",
    "assert_bulk_role",
    "create_batch",
    "csv_rows",
    "expand_zip_or_files",
    "load_overview",
    "process_batch",
    "rerun_batch",
]

# Re-export the pipeline status alphabet so callers can validate.
__all__.append("IMPORT_FILE_STATUSES")
