"""S24-AG1 B3, B4, B11 (read side), B15 — the Agreements page's own routes.

* ``GET  /agreements/workspace`` — cutover line, six cards, both standard documents and one page of client
  rows, in one request (docs/reference/openapi-agreements.yaml ``AgreementsWorkspace``).
* ``GET  /agreements/export`` — the entire filtered client view as CSV (UTF-8 with BOM), audited.
* ``GET  /agreements/documents`` — the Documents tab: one row per stored document.
* ``GET  /agreements/activity`` — the Activity tab, read from the audit log.
* ``GET  /agreements/standard``, ``POST /agreements/standard/{kind}``, ``GET /agreements/standard/{kind}/download``.

Every state and count comes from ``app.services.agreement_status``; nothing here classifies. Every role
reads and downloads; Legal and SystemAdmin upload a standard copy; the server answers 403 whatever the page
shows. Reads never write (no user row is created on a read); a download and an export write their audit row
and credit the caller's user row. CloudFront strips ``/api``, so these routes are ``/agreements/...``.
"""

from __future__ import annotations

import csv
import io
import os
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.s3_evidence import EvidenceS3, get_evidence_s3
from app.services import agreement_audit, agreement_standard
from app.services.agreement_files import check_upload
from app.services.agreement_status import (
    EXPORT_FILE_NAME,
    EXPORT_HEADER,
    PAGE_SIZES,
    documents_page,
    export_rows,
    load_agreement_population,
    load_documents,
    visibility_scope,
    visible_client_ids,
    workspace_payload,
)
from app.services.test_fixtures import is_test_user
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/agreements", tags=["agreements"])

# Every role views and downloads (directive item 5, B11); the same ten roles as routers/agreements.py.
READ_ROLES: tuple[str, ...] = (
    "Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO", "SystemAdmin",
)
WRITE_ROLES: tuple[str, ...] = ("Legal", "SystemAdmin")
ADMIN_ROLES: tuple[str, ...] = ("SystemAdmin",)

PAGE_SIZE_DETAIL = "page_size must be one of 25, 50, 100"
TEST_IDENTITY_DETAIL = (
    "A test account cannot upload a standard copy here. A standard copy is shared by every client, so only a "
    "real Legal or SystemAdmin user can upload one."
)

RelationshipFilter = Literal["all", "existing", "net_new"]
StatusFilter = Literal["any", "attention", "missing_nda", "missing_msa", "has_standard", "has_client",
                       "marked_covered", "possible_duplicate"]
StageFilter = Literal["any", "past_stage_1", "stage_1_only", "no_active_deal"]
SortOrder = Literal["attention", "name", "stage"]
BusinessUnitName = Literal["ST21", "IT Avalon", "Retro Rabbit"]
Kind = Literal["NDA", "MSA"]
DocumentSource = Literal["client", "standard"]


def _filters(
    relationship: RelationshipFilter = Query("all"),
    status_: StatusFilter = Query("any", alias="status"),
    stage: StageFilter = Query("any"),
    bu: list[BusinessUnitName] | None = Query(None),
    q: str | None = Query(None, max_length=120),
    sort: SortOrder = Query("attention"),
) -> dict[str, Any]:
    """The client-view filters shared by the workspace and the export (422 on an unknown value)."""
    return {
        "relationship": relationship, "status": status_, "stage": stage,
        "bu": tuple(dict.fromkeys(bu or ())), "q": (q or "").strip(), "sort": sort,
    }


def _page_size(page_size: int = Query(25)) -> int:
    if page_size not in PAGE_SIZES:
        raise HTTPException(422, PAGE_SIZE_DETAIL)
    return page_size


@router.get("/workspace")
async def agreements_workspace(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    filters: dict[str, Any] = Depends(_filters),
    page: int = Query(1, ge=1),
    page_size: int = Depends(_page_size),
) -> dict[str, Any]:
    """Everything the Agreements page needs in one request (8 statements, measured by T13).

    The cards are computed over every client the caller can see and ignore the filters; each card's ``drill``
    applied to the default view returns exactly ``value`` clients. ``can_write`` and ``is_admin`` come from
    the caller's groups so the page can lock (not hide) what the caller may not use.
    """
    pop = await load_agreement_population(session, user, with_activity=True)
    return workspace_payload(
        pop, filters, page=page, page_size=page_size,
        can_write=user.has_any_role(WRITE_ROLES), is_admin=user.has_any_role(ADMIN_ROLES))


def _csv_bytes(header: tuple[str, ...], rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)  # CRLF line endings, as every DealGate CSV
    writer.writerow(header)
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


@router.get("/export")
async def agreements_export(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    filters: dict[str, Any] = Depends(_filters),
) -> Response:
    """The entire filtered client view as CSV: every row, not one page (UTF-8 with BOM).

    Columns in the contract's order; a business unit is written with its region ("IT Avalon · US"); every
    cell that could run as a spreadsheet formula is prefixed with an apostrophe. The export is recorded in
    the audit log with its row count.
    """
    actor = await ensure_user(session, user)
    await session.commit()
    pop = await load_agreement_population(session, user)
    rows = export_rows(pop, filters)
    applied = {key: value for key, value in (
        ("relationship", filters["relationship"] if filters["relationship"] != "all" else None),
        ("status", filters["status"] if filters["status"] != "any" else None),
        ("stage", filters["stage"] if filters["stage"] != "any" else None),
        ("bu", list(filters["bu"]) or None), ("q", filters["q"] or None),
    ) if value is not None}
    await agreement_audit.record(
        session, actor_id=actor.id, action=agreement_audit.EXPORTED, entity=agreement_audit.EXPORT_ENTITY,
        entity_id=uuid.uuid4(),
        after={"rows": len(rows), "file_name": EXPORT_FILE_NAME, "filters": applied, "sort": filters["sort"]})
    await session.commit()
    return Response(
        content=_csv_bytes(EXPORT_HEADER, rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{EXPORT_FILE_NAME}"'},
    )


@router.get("/documents")
async def agreements_documents(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, max_length=120),
    kind: Kind | None = Query(None),
    source: DocumentSource | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Depends(_page_size),
) -> dict[str, Any]:
    """One row per stored document on a client the caller can see (the old register, extended with source,
    standard version and batch). Search covers client name, kind, file name and uploader."""
    rows = await load_documents(session, user)
    total, items = documents_page(rows, q=q, kind=kind, source=source, page=page, page_size=page_size)
    return {"total": total, "items": items}


@router.get("/activity")
async def agreements_activity(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, max_length=120),
    page: int = Query(1, ge=1),
    page_size: int = Depends(_page_size),
) -> dict[str, Any]:
    """Agreement events from the audit log, newest first (B15). Its total equals the workspace's
    ``activity_count`` when nothing is searched."""
    scope = await visibility_scope(session, user)
    linkable = await visible_client_ids(session, scope)
    total, items = await agreement_audit.activity(
        session, q=q, page=page, page_size=page_size, scope=scope, linkable_client_ids=linkable)
    return {"total": total, "items": items}


@router.get("/standard")
async def agreements_standard(
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The current standard NDA and MSA (null for a kind never uploaded) and how many clients hold each."""
    return await agreement_standard.standard_documents(session, user)


def _refuse_test_identity(user: AuthUser) -> None:
    """A standard copy is global data. Outside local/test a test identity (the e2e user is SystemAdmin) may
    not create one (directive rule 5: never upload a real document on staging)."""
    if is_test_user(user) and os.environ.get("DEALGATE_ENV", "local") not in ("local", "test"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, TEST_IDENTITY_DETAIL)


@router.post("/standard/{kind}", status_code=status.HTTP_201_CREATED)
async def upload_standard_copy(
    kind: Kind,
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    """Upload a standard copy: the next version of ``kind`` (Legal or SystemAdmin).

    The same file rules as every agreement upload (413, 415, 422 with the prototype's messages). The object
    is stored under agreements/standard/{kind}/; copies already attached to clients do not change.
    """
    _refuse_test_identity(user)
    checked = await check_upload(file)
    actor = await ensure_user(session, user)
    await session.commit()
    return await agreement_standard.upload_standard(session, s3, actor=actor, kind=kind, checked=checked)


@router.get("/standard/{kind}/download")
async def download_standard_copy(
    kind: Kind,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    """A presigned link to the current standard copy (300 seconds), recorded in the audit log. 404 when no
    standard copy of this kind has been uploaded yet (and then nothing is written)."""
    info = await agreement_standard.current_standard(session, kind)
    actor = await ensure_user(session, user)
    await session.commit()
    return await agreement_standard.download_standard(session, s3, actor=actor, kind=kind, info=info)
