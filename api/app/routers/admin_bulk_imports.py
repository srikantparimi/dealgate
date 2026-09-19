"""Bulk SOW import router (S10-02).

Endpoints:

- ``POST /admin/bulk-imports/sows`` — multipart of PDFs (or one .zip).
  Creates the batch, seeds one ImportFile per file, runs the shared
  pipeline synchronously, and returns the batch id.
- ``GET /admin/bulk-imports/{batch_id}`` — batch summary.
- ``GET /admin/bulk-imports/{batch_id}/files`` — per-file rows.
- ``GET /admin/bulk-imports/{batch_id}/log.csv`` — CSV stream per S10-02 spec.
- ``POST /admin/bulk-imports/{batch_id}/rerun`` — idempotent re-run.

The batch payload lives in memory for the duration of the request; a
re-run reuses whatever payloads the caller re-sends (multipart) or the
persisted rows' status (rows already ``imported`` / ``duplicate`` stay
put; ``needs_review`` rows re-queue). We do not persist the file bytes
— the row's SHA-256 is the identity, and a re-upload of the same bytes
would be recognised as a duplicate by the pipeline's hash dedupe.
"""

from __future__ import annotations

import csv
import io
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.bulk_import import (
    BULK_IMPORT_ROLES,
    BatchOverview,
    InputFile,
    assert_bulk_role,
    create_batch,
    csv_rows,
    expand_zip_or_files,
    load_overview,
    process_batch,
    rerun_batch,
)


router = APIRouter(prefix="/admin/bulk-imports", tags=["bulk-imports"])


# ---- role helper ----------------------------------------------------------


async def _bulk_user(user: AuthUser = Depends(current_user)) -> AuthUser:
    assert_bulk_role(user.groups)
    return user


# ---- serialisation --------------------------------------------------------


class BatchSummary(BaseModel):
    id: uuid.UUID
    run_by: uuid.UUID
    status: str
    file_count: int
    queued_count: int
    imported_count: int
    rejected_count: int
    duplicate_count: int
    needs_review_count: int
    note: str | None
    created_at: str
    updated_at: str


class FileRow(BaseModel):
    id: uuid.UUID
    batch_id: uuid.UUID
    filename: str
    size_bytes: int
    sha256: str
    detected_type: str | None
    status: str
    matched_client_id: uuid.UUID | None
    matched_confidence: str | None
    opportunity_id: uuid.UUID | None
    sow_version_id: uuid.UUID | None
    duplicate_of: uuid.UUID | None
    warnings: list[Any]
    errors: list[Any]
    needs_you: bool
    created_at: str
    updated_at: str


class BatchCreateResponse(BaseModel):
    batch_id: uuid.UUID
    file_count: int


class FileListResponse(BaseModel):
    items: list[FileRow]


def _summary(overview: BatchOverview) -> BatchSummary:
    b = overview.batch
    return BatchSummary(
        id=b.id,
        run_by=b.run_by,
        status=b.status,
        file_count=b.file_count,
        queued_count=b.queued_count,
        imported_count=b.imported_count,
        rejected_count=b.rejected_count,
        duplicate_count=b.duplicate_count,
        needs_review_count=b.needs_review_count,
        note=b.note,
        created_at=b.created_at.isoformat() if b.created_at else "",
        updated_at=b.updated_at.isoformat() if b.updated_at else "",
    )


def _files(overview: BatchOverview) -> list[FileRow]:
    rows: list[FileRow] = []
    for f in overview.files:
        needs_you = f.status == "needs_review"
        rows.append(
            FileRow(
                id=f.id,
                batch_id=f.batch_id,
                filename=f.filename,
                size_bytes=f.size_bytes,
                sha256=f.sha256,
                detected_type=f.detected_type,
                status=f.status,
                matched_client_id=f.matched_client_id,
                matched_confidence=(
                    format(f.matched_confidence, "f")
                    if isinstance(f.matched_confidence, Decimal)
                    else None
                ),
                opportunity_id=f.opportunity_id,
                sow_version_id=f.sow_version_id,
                duplicate_of=f.duplicate_of,
                warnings=list(f.warnings or []),
                errors=list(f.errors or []),
                needs_you=needs_you,
                created_at=f.created_at.isoformat() if f.created_at else "",
                updated_at=f.updated_at.isoformat() if f.updated_at else "",
            )
        )
    return rows


async def _read_uploads(files: list[UploadFile]) -> list[InputFile]:
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="at least one file is required",
        )
    out: list[InputFile] = []
    for f in files:
        payload = await f.read()
        if not payload:
            continue
        out.append(InputFile(filename=f.filename or "unnamed", payload=payload))
    if not out:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="every uploaded file was empty",
        )
    return expand_zip_or_files(out)


# ---- endpoints ------------------------------------------------------------


@router.post("/sows", response_model=BatchCreateResponse, status_code=201)
async def start_bulk_import(
    files: list[UploadFile] = File(...),
    actor: AuthUser = Depends(_bulk_user),
    session: AsyncSession = Depends(get_session),
) -> BatchCreateResponse:
    inputs = await _read_uploads(files)
    batch = await create_batch(session, actor_id=actor.id, files=inputs)
    payload_by_sha = {
        f.sha256: p.payload
        for f, p in _pair(await _files_for(session, batch.id), inputs)
    }
    await process_batch(
        session,
        batch_id=batch.id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
    )
    return BatchCreateResponse(batch_id=batch.id, file_count=len(inputs))


async def _files_for(session: AsyncSession, batch_id: uuid.UUID):
    overview = await load_overview(session, batch_id)
    return overview.files


def _pair(rows, inputs):
    """Line up ImportFile rows with the InputFiles that produced them.

    The pipeline hashes each payload; the row's ``sha256`` is the join
    key. When two inputs share bytes (duplicate detection) the pair
    still lands correctly — one row per input.
    """

    used: set[uuid.UUID] = set()
    for i in inputs:
        for r in rows:
            if r.id in used:
                continue
            from hashlib import sha256

            if r.sha256 == sha256(i.payload).hexdigest():
                used.add(r.id)
                yield r, i
                break


@router.get("/{batch_id}", response_model=BatchSummary)
async def get_batch(
    batch_id: uuid.UUID,
    _user: AuthUser = Depends(_bulk_user),
    session: AsyncSession = Depends(get_session),
) -> BatchSummary:
    overview = await load_overview(session, batch_id)
    return _summary(overview)


@router.get("/{batch_id}/files", response_model=FileListResponse)
async def get_files(
    batch_id: uuid.UUID,
    _user: AuthUser = Depends(_bulk_user),
    session: AsyncSession = Depends(get_session),
) -> FileListResponse:
    overview = await load_overview(session, batch_id)
    return FileListResponse(items=_files(overview))


@router.get("/{batch_id}/log.csv")
async def get_log_csv(
    batch_id: uuid.UUID,
    _user: AuthUser = Depends(_bulk_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    overview = await load_overview(session, batch_id)
    rows = csv_rows(overview)

    def _stream():
        buf = io.StringIO()
        writer = csv.writer(buf)
        for r in rows:
            writer.writerow(r)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    filename = f"bulk-import-{batch_id}.csv"
    return StreamingResponse(
        _stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{batch_id}/rerun", response_model=BatchSummary)
async def rerun(
    batch_id: uuid.UUID,
    files: list[UploadFile] = File(default=[]),
    actor: AuthUser = Depends(_bulk_user),
    session: AsyncSession = Depends(get_session),
) -> BatchSummary:
    # Accept an optional file re-post so needs_review rows can be re-driven
    # even after the router process forgot the original bytes.
    payload_by_sha: dict[str, bytes] = {}
    if files:
        inputs = await _read_uploads(files)
        for i in inputs:
            from hashlib import sha256

            payload_by_sha[sha256(i.payload).hexdigest()] = i.payload
    overview = await rerun_batch(
        session,
        batch_id=batch_id,
        actor_id=actor.id,
        payload_by_sha=payload_by_sha,
    )
    return _summary(overview)


__all__ = ["BULK_IMPORT_ROLES", "router"]
