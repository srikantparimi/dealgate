"""Staffing sheet endpoints for the SOW-first flow (S10-05).

Two endpoints, both in service of one rule: a gross margin is only as good as
the staffing plan under it, and that plan has to come from a person when the
SOW does not carry one.

- ``GET  /sows/staffing-template.xlsx``            — the blank sheet.
- ``POST /sows/{opportunity_id}/staffing/import``  — upload it back.

Import **parses and returns**; it does not save. The rows land in the grid
where the reviewer can see the live gross margin before committing, because
uploading a spreadsheet should not silently become an approved cost basis.
Saving goes through the existing ``POST /delivery-model/{id}/versions``, which
already writes the immutable GM version and its audit row.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

import anyio

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.models.opportunity import Opportunity
from app.audit import append_audit
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
    get_bedrock_sow,
)
from app.integrations.s3_sow import SowS3, get_sow_s3
from app.models.sow import SowVersion
from app.services.document_text import UnreadableDocument, extract_document_text
from app.services.document_type import ALLOWED_START_TYPES, classify_document
from app.services.sow_extract import to_provenance_fields
from app.services.sow_lifecycle import (
    SowLifecycleError,
    delete_version,
    discard_version,
    list_versions,
    reserve_version_no,
    sow_for_opportunity,
    supersede,
)
from app.services.sow_upload_job_service import sha256_hex
from app.services.staffing_sheet import (
    StaffingSheetError,
    build_template_xlsx,
    parse_staffing_xlsx,
)
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/sows", tags=["sows"])

# Whoever owns the delivery plan owns these. Finance and Legal can read the
# template but do not staff an engagement.
_STAFFING_ROLES: tuple[str, ...] = (
    "Sales",
    "SalesLeader",
    "Delivery",
    "Finance",
    "CEO",
    "SystemAdmin",
)

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_MAX_SHEET_BYTES = 5 * 1024 * 1024


@router.get("/staffing-template.xlsx")
async def staffing_template(
    _user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
) -> Response:
    """Download the blank staffing sheet."""

    return Response(
        content=build_template_xlsx(),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="dealgate-staffing.xlsx"'
        },
    )


@router.post("/{opportunity_id}/staffing/import")
async def import_staffing(
    opportunity_id: uuid.UUID,
    file: UploadFile = File(...),
    _user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Parse an uploaded staffing sheet into resource lines.

    Returns the parsed rows for review. Nothing is written — the reviewer sees
    the resulting gross margin first, then saves.
    """

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "the uploaded file is empty", "errors": []},
        )
    if len(payload) > _MAX_SHEET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": f"sheet exceeds {_MAX_SHEET_BYTES // (1024 * 1024)}MB",
                "errors": [],
            },
        )

    try:
        rows = parse_staffing_xlsx(payload)
    except StaffingSheetError as exc:
        # Every problem at once — fixing one row at a time across repeated
        # uploads is the worst possible version of this.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc

    return {
        "resource_lines": [r.to_resource_line() for r in rows],
        "row_count": len(rows),
        "source": "sheet_upload",
    }


# --- version lifecycle (S10-06) -------------------------------------------
#
# Revising a SOW used to create a *second opportunity* for the same
# engagement, because the SOW-first upload path always called
# `_ensure_opportunity`, which despite its name only ever creates. These
# endpoints attach a revision to the SOW it revises, and give a bad upload a
# way out of the system.

_DISCARD_ROLES: tuple[str, ...] = (
    "SalesLeader",
    "Delivery",
    "Finance",
    "Legal",
    "CEO",
    "SystemAdmin",
)


def _lifecycle_http(exc: SowLifecycleError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/{opportunity_id}/versions")
async def list_sow_versions(
    opportunity_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Every version of this SOW, newest first, discarded ones included."""

    sow = await sow_for_opportunity(session, opportunity_id)
    if sow is None:
        return {"sow_id": None, "versions": []}
    versions = await list_versions(session, sow.id)
    return {
        "sow_id": str(sow.id),
        "versions": [
            {
                "id": str(v.id),
                "version_no": v.version_no,
                "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
                "extract_status": v.extract_status,
                "execution_state": v.execution_state,
                "is_current": v.is_current,
                "superseded_by": str(v.superseded_by) if v.superseded_by else None,
                "discarded_at": (
                    v.discarded_at.isoformat() if v.discarded_at else None
                ),
                "discard_reason": v.discard_reason,
                "file_name": v.file_name,
                "ever_submitted": v.ever_submitted,
                # What the UI should offer. Computed here so the rule lives in
                # one place rather than being re-derived in the browser.
                "can_delete": not v.ever_submitted and v.discarded_at is None,
                "can_discard": v.ever_submitted and v.discarded_at is None,
            }
            for v in versions
        ],
    }


@router.post("/{opportunity_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_sow_revision(
    opportunity_id: uuid.UUID,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
    bedrock: BedrockSowExtract = Depends(get_bedrock_sow),
) -> dict[str, Any]:
    """Upload a corrected SOW as the next version of this one.

    Attaches to the existing ``Sow`` — no new opportunity, no client
    resolution, no picker. The caller has said which SOW this revises, so
    none of that has to be guessed from the document.

    The previous current version is superseded, not edited: an approver's
    decision stays attached to the words they approved (CLAUDE.md rule 4).
    """

    sow = await sow_for_opportunity(session, opportunity_id)
    if sow is None:
        raise HTTPException(
            status_code=404, detail="this opportunity has no SOW to revise"
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="uploaded file is empty",
        )

    try:
        doc = extract_document_text(payload, file.content_type)
    except UnreadableDocument as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"We could not read this file. {exc.reason.capitalize()}. "
                "Please upload a PDF or a .docx Word document."
            ),
        ) from exc

    detected = classify_document(payload, content_type=file.content_type)
    if detected.type not in ALLOWED_START_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "detected_type": detected.type,
                "message": (
                    f"This file does not look like a SOW. Detected: {detected.type}."
                ),
            },
        )

    file_hash = sha256_hex(payload)
    current = next(
        (v for v in await list_versions(session, sow.id) if v.is_current), None
    )
    if current is not None:
        existing = (
            await session.execute(
                select(SowVersion).where(SowVersion.id == current.id)
            )
        ).scalar_one()
        if existing.file_hash == file_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"these bytes are already version {existing.version_no} — "
                    "nothing to revise"
                ),
            )
    else:
        existing = None

    db_user = await ensure_user(session, user)

    # Extract off the event loop; boto3 is synchronous.
    raw = await anyio.to_thread.run_sync(bedrock.extract, doc)

    fields: dict[str, Any] | None = None
    extract_status = "manual_required"
    if isinstance(raw, ExtractedFields):
        fields = to_provenance_fields(
            raw.fields, model=raw.model, prompt_version=raw.prompt_version
        )
        fields["metadata"] = {
            "extract_source": "sow_revision",
            "ref_unit": doc.ref_unit,
            "document_kind": doc.kind,
        }
        extract_status = "complete"
    elif isinstance(raw, ManualRequired):
        fields = {"metadata": {"extract_source": "sow_revision"}}

    version_no = await reserve_version_no(session, sow.id)
    s3_key = s3.build_key(file.filename or "sow", file.content_type or "application/pdf")
    try:
        await anyio.to_thread.run_sync(
            s3.put_object, s3_key, payload, file.content_type or "application/pdf"
        )
    except Exception as exc:  # noqa: BLE001 — surfaced, not swallowed
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"could not store the file: {exc}",
        ) from exc

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=db_user.id,
        file_s3_key=s3_key,
        file_hash=file_hash,
        extract_status=extract_status,
        extracted_fields=fields,
        version_no=version_no,
        engagement_type_suggested=detected.type,
    )
    session.add(version)
    await session.flush()

    if existing is not None:
        await supersede(session, old=existing, new=version, actor_id=db_user.id)

    await append_audit(
        session,
        actor_id=db_user.id,
        action="sow_version.revised",
        entity="sow_version",
        entity_id=str(version.id),
        before=None,
        after={
            "version_no": version_no,
            "supersedes": str(existing.id) if existing else None,
            "extract_status": extract_status,
            "file_hash": file_hash,
        },
    )
    await session.commit()

    return {
        "sow_version_id": str(version.id),
        "version_no": version_no,
        "supersedes": str(existing.id) if existing else None,
        "extract_status": extract_status,
    }


@router.delete("/versions/{sow_version_id}", status_code=status.HTTP_200_OK)
async def delete_sow_version(
    sow_version_id: uuid.UUID,
    reason: str | None = None,
    user: AuthUser = Depends(require_role(*_DISCARD_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: SowS3 = Depends(get_sow_s3),
) -> dict[str, Any]:
    """Delete a version that has never been submitted for approval.

    409 once it has been — a submitted version is part of a decision record
    and can only be discarded.
    """

    try:
        result = await delete_version(
            session, sow_version_id=sow_version_id, actor_id=user.id, reason=reason
        )
    except SowLifecycleError as exc:
        raise _lifecycle_http(exc) from exc

    await session.commit()

    # The object goes after the transaction commits. S3 is not transactional
    # with the database, so a failure here must not undo a good delete — the
    # row is gone and the audit row records it; an orphaned object is a
    # janitorial problem, not a correctness one.
    key = result.get("s3_key")
    if key and not key.startswith("bulk-import/"):
        with contextlib.suppress(Exception):
            await anyio.to_thread.run_sync(s3.delete_object, key)

    return {"deleted": True, "sow_version_id": str(sow_version_id)}


@router.post("/versions/{sow_version_id}/discard")
async def discard_sow_version(
    sow_version_id: uuid.UUID,
    body: dict[str, Any],
    user: AuthUser = Depends(require_role(*_DISCARD_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Soft-discard a version. Row and file survive; it leaves every board."""

    try:
        version = await discard_version(
            session,
            sow_version_id=sow_version_id,
            actor_id=user.id,
            reason=str(body.get("reason") or ""),
        )
    except SowLifecycleError as exc:
        raise _lifecycle_http(exc) from exc
    await session.commit()
    return {
        "sow_version_id": str(version.id),
        "discarded_at": version.discarded_at.isoformat()
        if version.discarded_at
        else None,
        "reason": version.discard_reason,
    }
