"""Audit log viewer — S1-E1.

Read-only endpoints. All writes to `audit_event` happen from inside workflow
transitions via `app.audit.append_audit` (CLAUDE.md rule 5). Role-gated to
Finance / Legal / CEO / SystemAdmin; anyone else gets 403.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.audit_query import (
    AuditFilters,
    build_count_query,
    build_list_query,
    verify_slice,
)

router = APIRouter(prefix="/audit", tags=["audit"])

_ALLOWED_ROLES = ("Finance", "Legal", "CEO", "SystemAdmin")


class AuditListRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ts: datetime
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    entity: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    correlation_id: str | None
    prev_hash: str | None
    row_hash: str


class AuditListResponse(BaseModel):
    items: list[AuditListRow]
    page: int
    size: int
    total: int


class VerifyResponse(BaseModel):
    ok: bool
    first_broken_row: uuid.UUID | None
    checked: int
    message: str


def _filters(
    entity: str | None,
    entity_id: str | None,
    actor_id: uuid.UUID | None,
    action: str | None,
    since: datetime | None,
    until: datetime | None,
    page: int,
    size: int,
) -> AuditFilters:
    return AuditFilters(
        entity=entity,
        entity_id=entity_id,
        actor_id=actor_id,
        action=action,
        since=since,
        until=until,
        page=page,
        size=size,
    )


@router.get("", response_model=AuditListResponse)
async def list_audit(
    entity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _: AuthUser = Depends(require_role(*_ALLOWED_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> AuditListResponse:
    filters = _filters(entity, entity_id, actor_id, action, since, until, page, size)
    rows = (await session.execute(build_list_query(filters))).all()
    total = (await session.execute(build_count_query(filters))).scalar_one()
    items = [
        AuditListRow(
            id=event.id,
            ts=event.ts,
            actor_id=event.actor_id,
            actor_email=email,
            action=event.action,
            entity=event.entity,
            entity_id=event.entity_id,
            before=event.before,
            after=event.after,
            correlation_id=event.correlation_id,
            prev_hash=event.prev_hash,
            row_hash=event.row_hash,
        )
        for event, email in rows
    ]
    return AuditListResponse(items=items, page=page, size=size, total=int(total))


@router.get("/verify", response_model=VerifyResponse)
async def verify_audit(
    entity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    _: AuthUser = Depends(require_role(*_ALLOWED_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> VerifyResponse:
    filters = AuditFilters(entity=entity, entity_id=entity_id)
    result = await verify_slice(session, filters)
    return VerifyResponse(
        ok=result.ok,
        first_broken_row=result.first_broken_row,
        checked=result.checked,
        message=result.message,
    )
