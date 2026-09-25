"""S4 E7 — approval packages API.

Router stays thin: role-gate + shape conversion + delegate to
:mod:`app.services.approvals`. Every state change through the service
already writes an ``audit_event`` (CLAUDE.md rule 5).

Endpoints:

- ``POST /approvals/packages/{opportunity_id}``   — submit (owner/admin).
- ``GET  /approvals/packages/{package_id}``       — full detail.
- ``POST /approvals/packages/{package_id}/decisions/{function}`` — approve/reject.
- ``POST /approvals/packages/{package_id}/void``  — manual void (admin).
- ``GET  /approvals/packages``                    — list (governance roles).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.opportunity import Opportunity
from app.services.redact import redact_costs
from app.services.approvals import (
    ApprovalError,
    ListFilters,
    decide,
    list_packages,
    load_package,
    manual_void,
    serialize_package_with_floors,
    submit_package,
)
from app.models.approval_routing import ApprovalAssignment, ApprovalConditionEvidence
from app.services import approval_routing as routing
from app.services.approval_workflow import review_projection


router = APIRouter(prefix="/approvals", tags=["approvals"])


# ---- role gates ---------------------------------------------------------

# Every governance function that reads packages. Kept broad — the story
# says "any governance role reads".
_READ_ROLES: frozenset[str] = frozenset(
    {"Delivery", "HR", "Finance", "Legal", "CEO", "SalesLeader", "SystemAdmin"}
)

# Functions → the role that owns each decision (blueprint §6.5).
_FUNCTION_ROLES: dict[str, frozenset[str]] = {
    "delivery": frozenset({"Delivery", "SystemAdmin"}),
    "hr": frozenset({"HR", "SystemAdmin"}),
    "finance": frozenset({"Finance", "SystemAdmin"}),
    "legal": frozenset({"Legal", "SystemAdmin"}),
}


def _has_any(user: AuthUser, roles: frozenset[str]) -> bool:
    return any(g in roles for g in user.groups)


async def _require_read(user: AuthUser = Depends(current_user)) -> AuthUser:
    if not _has_any(user, _READ_ROLES):
        raise HTTPException(status_code=403, detail="insufficient role")
    return user


async def _require_submit(
    session: AsyncSession, user: AuthUser, opportunity_id: uuid.UUID
) -> None:
    """SystemAdmin or the deal's account owner may submit."""

    if "SystemAdmin" in user.groups:
        return
    opp = (
        await session.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    if opp.owner_id is not None and opp.owner_id == user.id:
        return
    raise HTTPException(
        status_code=403,
        detail="only the account owner or SystemAdmin may submit an approval package",
    )


def _require_function_role(user: AuthUser, function: str) -> None:
    roles = _FUNCTION_ROLES.get(function)
    if roles is None:
        raise HTTPException(
            status_code=422, detail=f"unknown function {function!r}"
        )
    if not _has_any(user, roles):
        raise HTTPException(
            status_code=403,
            detail=f"role required for {function!r} approval: {sorted(roles)}",
        )


# ---- schemas ------------------------------------------------------------


class DecisionBody(BaseModel):
    decision: str = Field(examples=["approve", "reject", "request_changes"])
    reason: str = Field(min_length=1, max_length=4096)


class ReviewerChoice(BaseModel):
    approver_id: uuid.UUID | None = None
    due_date: date | None = None
    use_sla: bool = True


class SubmitBody(BaseModel):
    sow_version_id: uuid.UUID | None = None
    gm_model_id: uuid.UUID | None = None
    assignments: dict[str, ReviewerChoice] = Field(default_factory=dict)


class GroupBody(BaseModel):
    member_ids: list[uuid.UUID]
    backup_ids: list[uuid.UUID] = Field(default_factory=list)
    default_approver_id: uuid.UUID | None = None


class EvidenceBody(BaseModel):
    evidence: str = Field(min_length=1, max_length=4096)


class VoidBody(BaseModel):
    reason: str = Field(min_length=1, max_length=1024)


class PackageListResponse(BaseModel):
    items: list[dict[str, Any]]
    page: int
    size: int
    total: int


# ---- helpers ------------------------------------------------------------


def _wrap(exc: ApprovalError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _read_package(session, user, package):
    if _has_any(user, _READ_ROLES):
        return
    opp = await session.get(Opportunity, package.opportunity_id)
    assigned = await session.scalar(select(ApprovalAssignment).where(ApprovalAssignment.package_id == package.id, ApprovalAssignment.approver_id == user.id).limit(1))
    if not assigned and (not opp or opp.owner_id != user.id):
        raise HTTPException(403, "Only the owner or a reviewer may read this package")


async def _detail(session, pkg, user):
    data = await serialize_package_with_floors(session, pkg)
    data.update(await review_projection(session, pkg, user.id))
    return redact_costs(data, set(user.groups))


# ---- endpoints ----------------------------------------------------------


@router.post("/packages/{opportunity_id}", status_code=201)
async def submit_endpoint(
    opportunity_id: uuid.UUID,
    body: SubmitBody | None = None,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await _require_submit(session, user, opportunity_id)
    try:
        body = body or SubmitBody()
        plan = await routing.submission_plan(session, actor_id=user.id, opportunity_id=opportunity_id,
            expected_sow_version_id=body.sow_version_id, expected_gm_model_id=body.gm_model_id,
            choices={fn: choice.model_dump(exclude_unset=True) for fn, choice in body.assignments.items()})
        pkg = await submit_package(
            session, actor_id=user.id, opportunity_id=opportunity_id, routing=plan
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return await _detail(session, pkg, user)


@router.get("/packages/{package_id}")
async def get_endpoint(
    package_id: uuid.UUID,
    _user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        pkg = await load_package(session, package_id)
        await _read_package(session, _user, pkg)
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return await _detail(session, pkg, _user)


@router.post("/packages/{package_id}/decisions/{function}")
async def decide_endpoint(
    package_id: uuid.UUID,
    function: str,
    body: DecisionBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not body.reason.strip():
        raise HTTPException(422, "A reason is required")
    try:
        pkg = await decide(
            session,
            actor_id=user.id,
            package_id=package_id,
            function=function,
            decision=body.decision,
            reason=body.reason,
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return await _detail(session, pkg, user)


@router.post("/packages/{package_id}/void")
async def void_endpoint(
    package_id: uuid.UUID,
    body: VoidBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if "SystemAdmin" not in user.groups:
        raise HTTPException(
            status_code=403, detail="only SystemAdmin may manually void a package"
        )
    try:
        pkg = await manual_void(
            session, actor_id=user.id, package_id=package_id, reason=body.reason
        )
    except ApprovalError as exc:
        raise _wrap(exc) from exc
    return redact_costs(await serialize_package_with_floors(session, pkg), set(user.groups))


@router.get("/packages", response_model=PackageListResponse)
async def list_endpoint(
    status_: str | None = Query(default=None, alias="status"),
    opportunity_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PackageListResponse:
    filters = ListFilters(
        status=status_, opportunity_id=opportunity_id, page=page, size=size,
        reader_id=None if _has_any(_user, _READ_ROLES) else _user.id,
    )
    rows, total = await list_packages(session, filters)
    return PackageListResponse(
        items=[await review_projection(session, r, _user.id) for r in rows],
        page=page,
        size=size,
        total=total,
    )


@router.get("/groups")
async def list_groups(user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return {"items": await routing.groups(session), "can_edit": "SystemAdmin" in user.groups}


@router.put("/groups/{function}")
async def update_group(function: str, body: GroupBody, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    if "SystemAdmin" not in user.groups:
        raise HTTPException(403, "Only SystemAdmin may configure approval groups")
    return await routing.save_group(session, actor_id=user.id, function=function, **body.model_dump())


@router.get("/plan/{opportunity_id}")
async def plan_endpoint(opportunity_id: uuid.UUID, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    await _require_submit(session, user, opportunity_id)
    return redact_costs(await routing.submission_plan(session, actor_id=user.id, opportunity_id=opportunity_id), set(user.groups))


@router.post("/packages/{package_id}/route")
async def route_endpoint(package_id: uuid.UUID, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    pkg = await load_package(session, package_id)
    await _require_submit(session, user, pkg.opportunity_id)
    await routing.route_missing(session, actor_id=user.id, package_id=package_id)
    return await _detail(session, pkg, user)


@router.post("/packages/{package_id}/condition-evidence")
async def condition_evidence(package_id: uuid.UUID, body: EvidenceBody, user: AuthUser = Depends(current_user), session: AsyncSession = Depends(get_session)):
    from app.audit import append_audit
    from app.models.ceo_exception import CeoException
    pkg = await load_package(session, package_id)
    await _require_submit(session, user, pkg.opportunity_id)
    exception = await session.scalar(select(CeoException).where(CeoException.package_id == pkg.id))
    if pkg.status != 'ready_to_sign' or not exception or not exception.conditions_text or not body.evidence.strip():
        raise HTTPException(409, "No approved conditions awaiting evidence")
    if await session.get(ApprovalConditionEvidence, package_id):
        raise HTTPException(409, "Evidence already recorded")
    session.add(ApprovalConditionEvidence(package_id=package_id, evidence=body.evidence.strip(), recorded_by=user.id))
    await append_audit(session, actor_id=user.id, action='approval.conditions_evidenced', entity='approval_package', entity_id=str(package_id), before=None, after={"evidence": body.evidence.strip()})
    await session.commit()
    return await _detail(session, pkg, user)
