"""Delete routes (S17 single delete service).

The service enforces one contract: hard-delete cascades everywhere.
The router is thin: role check → service call → return the assessment
(counts included so the UI can show the cascade confirmation dialog).

Endpoints (all admin-gated):

- ``GET  /clients/{id}/deletion-assessment``
- ``DELETE /clients/{id}?reason=...``
- ``POST /clients/{id}/archive``               (kept for UI back-compat;
                                                 hard-deletes under the hood)
- ``GET  /opportunities/{id}/deletion-assessment``
- ``DELETE /opportunities/{id}?reason=...``
- ``POST /opportunities/{id}/archive``          (as above)
- ``GET  /sows/{sow_id}/deletion-assessment``   (S17: new SOW-scoped assess)
- ``DELETE /sows/{sow_id}?reason=...``          (S17: hard-delete at any stage)
- ``DELETE /admin/bulk-imports/{batch_id}?reason=...``
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.deletion import (
    DeletionAssessment,
    DeletionError,
    archive_client,
    archive_opportunity,
    archive_sow,
    assess_client,
    assess_opportunity,
    assess_sow,
    delete_client,
    delete_import_batch,
    delete_opportunity,
    delete_sow,
)
from app.services.user_provisioning import ensure_user


router = APIRouter(tags=["deletion"])

# S17 §2: delete is available "at any stage, including approved or signed".
# The role check stays governance-scoped — a random Sales user can't
# vaporise a package — but there is no per-state refusal in the service.
_DELETE_ROLES: tuple[str, ...] = (
    "SystemAdmin",
    "CEO",
    "SalesLeader",
    "Finance",
    "Legal",
)


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str
    reason: str
    counts: dict[str, int] = Field(default_factory=dict)


class ArchiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1024)


def _to_response(a: DeletionAssessment) -> AssessmentResponse:
    return AssessmentResponse(state=a.state, reason=a.reason, counts=a.counts)


def _raise(exc: DeletionError) -> Any:
    raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


# --- client -------------------------------------------------------------


@router.get(
    "/clients/{client_id}/deletion-assessment",
    response_model=AssessmentResponse,
)
async def get_client_deletion_assessment(
    client_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    try:
        return _to_response(await assess_client(session, client_id))
    except DeletionError as exc:
        _raise(exc)


@router.delete("/clients/{client_id}", response_model=AssessmentResponse)
async def delete_client_endpoint(
    client_id: uuid.UUID,
    reason: str | None = Query(default=None),
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    _ = reason
    db_user = await ensure_user(session, user)
    try:
        result = await delete_client(session, client_id=client_id, actor_id=db_user.id)
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return _to_response(result)


@router.post("/clients/{client_id}/archive", response_model=AssessmentResponse)
async def archive_client_endpoint(
    client_id: uuid.UUID,
    body: ArchiveBody,
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    db_user = await ensure_user(session, user)
    try:
        result = await archive_client(
            session, client_id=client_id, actor_id=db_user.id, reason=body.reason or ""
        )
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return _to_response(result)


# --- opportunity --------------------------------------------------------


@router.get(
    "/opportunities/{opportunity_id}/deletion-assessment",
    response_model=AssessmentResponse,
)
async def get_opportunity_deletion_assessment(
    opportunity_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    try:
        return _to_response(await assess_opportunity(session, opportunity_id))
    except DeletionError as exc:
        _raise(exc)


@router.delete("/opportunities/{opportunity_id}", response_model=AssessmentResponse)
async def delete_opportunity_endpoint(
    opportunity_id: uuid.UUID,
    reason: str | None = Query(default=None),
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    _ = reason
    db_user = await ensure_user(session, user)
    try:
        result = await delete_opportunity(
            session, opportunity_id=opportunity_id, actor_id=db_user.id
        )
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return _to_response(result)


@router.post(
    "/opportunities/{opportunity_id}/archive", response_model=AssessmentResponse
)
async def archive_opportunity_endpoint(
    opportunity_id: uuid.UUID,
    body: ArchiveBody,
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    db_user = await ensure_user(session, user)
    try:
        result = await archive_opportunity(
            session,
            opportunity_id=opportunity_id,
            actor_id=db_user.id,
            reason=body.reason or "",
        )
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return _to_response(result)


# --- SOW (S17) ----------------------------------------------------------


@router.get(
    "/sows/{sow_id}/deletion-assessment",
    response_model=AssessmentResponse,
)
async def get_sow_deletion_assessment(
    sow_id: uuid.UUID,
    _user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    try:
        return _to_response(await assess_sow(session, sow_id))
    except DeletionError as exc:
        _raise(exc)


@router.delete("/sows/{sow_id}", response_model=AssessmentResponse)
async def delete_sow_endpoint(
    sow_id: uuid.UUID,
    reason: str | None = Query(default=None),
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    _ = reason
    db_user = await ensure_user(session, user)
    try:
        summary = await delete_sow(session, sow_id=sow_id, actor_id=db_user.id)
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return AssessmentResponse(
        state="draft",
        reason=f"SOW '{summary.sow_title}' deleted from {summary.stage}",
        counts=summary.counts,
    )


@router.post("/sows/{sow_id}/archive", response_model=AssessmentResponse)
async def archive_sow_endpoint(
    sow_id: uuid.UUID,
    body: ArchiveBody = ArchiveBody(),
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    """S20 W3 D6: archive a governed SOW (any SOW that has been
    submitted for approval). Keeps rows + audit trail intact; the SOW is
    excluded from open lists and the deal's rollup headline (see
    `services.sow_rollup`)."""

    db_user = await ensure_user(session, user)
    try:
        summary = await archive_sow(
            session,
            sow_id=sow_id,
            actor_id=db_user.id,
            reason=body.reason or "manual_archive",
        )
    except DeletionError as exc:
        _raise(exc)
    await session.commit()
    return AssessmentResponse(
        state="archived",
        reason=f"SOW '{summary.sow_title}' archived from {summary.stage}",
        counts=summary.counts,
    )


# --- batch --------------------------------------------------------------


@router.delete(
    "/admin/bulk-imports/{batch_id}",
    response_model=AssessmentResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_bulk_import_batch_endpoint(
    batch_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*_DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AssessmentResponse:
    db_user = await ensure_user(session, user)
    result = await delete_import_batch(
        session, batch_id=batch_id, actor_id=db_user.id
    )
    await session.commit()
    return _to_response(result)
