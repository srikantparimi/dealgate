"""S24-AG1 B6 — one client's NDA and MSA: the shared client panel and every per-client action.

The Agreements page and the Pipeline client panel both read ``GET /clients/{id}/agreements``; every action
returns the kind's card (or the client's agreements) recomputed by the one shared ``agreement_status``
service. Roles are enforced here whatever the page shows (B11): every role reads and downloads; Legal and
SystemAdmin upload, attach, mark, detach and change the relationship. A client the caller may not see is a
404 (test fixtures are invisible to real users, and a test identity sees only its own).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.s3_evidence import EvidenceS3, get_evidence_s3
from app.models.user import User
from app.services import agreements_service as svc
from app.services.agreement_files import check_upload
from app.services.agreements_service import ADMIN_ROLES, READ_ROLES, WRITE_ROLES
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/clients", tags=["agreements"])

Kind = Literal["NDA", "MSA"]


class MarkRequest(BaseModel):
    reason: Literal["signed_outside_dealgate", "covered_by_earlier_work", "confirmed_with_client", "other"]
    marked_on: date
    note: str | None = Field(default=None, max_length=svc.NOTE_MAX)


class RelationshipRequest(BaseModel):
    relationship: Literal["existing", "net_new"]
    note: str | None = Field(default=None, max_length=svc.NOTE_MAX)


async def _actor(session: AsyncSession, user: AuthUser) -> User:
    actor = await ensure_user(session, user)
    await session.commit()  # release identity/audit locks before locking business rows
    return actor


def _rights(user: AuthUser) -> dict[str, bool]:
    return {"can_write": user.has_any_role(WRITE_ROLES), "is_admin": user.has_any_role(ADMIN_ROLES)}


@router.get("/{client_id}/agreements")
async def client_agreements(
    client_id: uuid.UUID,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    viewer = await svc.reader(session, user)
    return await svc.panel(session, viewer, client_id, **_rights(user))


@router.post("/{client_id}/agreements/{kind}/client-copy", status_code=status.HTTP_201_CREATED)
async def upload_client_copy(
    client_id: uuid.UUID,
    kind: Kind,
    file: UploadFile = File(...),
    note: str | None = Form(default=None),
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    """A first copy, a new version, or a replacement for the standard copy (or a mark) for this client only."""
    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)  # before any file rule, so nothing leaks
    svc.clean_note(note)
    checked = await check_upload(file)
    await svc.store_client_copy(session, s3, actor=actor, client_id=client_id, kind=kind, checked=checked, note=note)
    return await svc.card(session, actor, client_id, kind)


@router.post("/{client_id}/agreements/{kind}/attach-standard", status_code=status.HTTP_201_CREATED)
async def attach_standard(
    client_id: uuid.UUID,
    kind: Kind,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)
    await svc.attach_standard(session, actor=actor, client_id=client_id, kind=kind)
    return await svc.card(session, actor, client_id, kind)


@router.put("/{client_id}/agreements/{kind}/mark")
async def mark_covered(
    client_id: uuid.UUID,
    kind: Kind,
    body: MarkRequest,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)
    await svc.set_mark(session, actor=actor, client_id=client_id, kind=kind, reason=body.reason,
                       marked_on=body.marked_on, note=body.note)
    return await svc.card(session, actor, client_id, kind)


@router.delete("/{client_id}/agreements/{kind}/mark")
async def remove_mark(
    client_id: uuid.UUID,
    kind: Kind,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)
    await svc.remove_mark(session, actor=actor, client_id=client_id, kind=kind)
    return await svc.card(session, actor, client_id, kind)


@router.delete("/{client_id}/agreements/{kind}", status_code=status.HTTP_202_ACCEPTED)
async def detach(
    client_id: uuid.UUID,
    kind: Kind,
    response: Response,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
):
    """A client copy starts the existing deletion job (202). A standard attachment removes only this client's
    row and returns the card (200): the shared stored object stays because other clients use it."""
    from app.routers.deletion import _job_response

    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)
    result = await svc.detach(session, actor=actor, client_id=client_id, kind=kind)
    if result.job is not None:
        return _job_response(result.job)
    response.status_code = status.HTTP_200_OK
    return await svc.card(session, actor, client_id, kind)


@router.get("/{client_id}/agreements/{kind}/download")
async def download(
    client_id: uuid.UUID,
    kind: Kind,
    user: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
    s3: EvidenceS3 = Depends(get_evidence_s3),
) -> dict[str, Any]:
    """A presigned link (300 s). Recorded in the audit log with who and which client."""
    actor = await _actor(session, user)
    return await svc.client_download(session, s3, actor=actor, client_id=client_id, kind=kind)


@router.put("/{client_id}/relationship")
async def set_relationship(
    client_id: uuid.UUID,
    body: RelationshipRequest,
    user: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Existing or net new by hand (basis manual). Saving the stored manual value again changes nothing; saving
    the word a provisional (live) value shows stores it by hand."""
    actor = await _actor(session, user)
    await svc.authorize_client(session, actor, client_id)
    await svc.set_relationship(session, actor=actor, client_id=client_id, relationship=body.relationship,
                               note=body.note)
    return await svc.panel(session, actor, client_id, **_rights(user))
