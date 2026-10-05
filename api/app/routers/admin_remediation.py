"""S21-07 admin remediation endpoints (T07.05/T07.06).

Thin auth + shape layer over :mod:`app.services.approval_remediation`.
SystemAdmin only; every write audits inside the service transaction.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.approval_remediation import (
    quarantine_recorded_decision,
    repair_pending_assignment,
)

router = APIRouter(prefix="/admin/approvals", tags=["admin"])


class RepairAssignmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function: str = Field(min_length=1, max_length=32)
    new_approver_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=2000)


class QuarantineDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function: str = Field(min_length=1, max_length=32)
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/{package_id}/repair-assignment")
async def repair_assignment_endpoint(
    package_id: uuid.UUID,
    body: RepairAssignmentBody,
    user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await repair_pending_assignment(
        session,
        actor=user,
        package_id=package_id,
        function=body.function,
        new_approver_id=body.new_approver_id,
        reason=body.reason,
    )


@router.post("/{package_id}/quarantine-decision")
async def quarantine_decision_endpoint(
    package_id: uuid.UUID,
    body: QuarantineDecisionBody,
    user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    return await quarantine_recorded_decision(
        session,
        actor=user,
        package_id=package_id,
        function=body.function,
        reason=body.reason,
    )
