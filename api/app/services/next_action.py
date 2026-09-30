"""Structured next-action service (S20 · W6).

Owns the CRUD and history logic for :class:`app.models.next_action.NextAction`
and the append-only history table :class:`NextActionEvent`. Every
state-changing call:

- Enforces server-side authorization (rule 5).
- Writes an ``audit_event`` in the same transaction (rule 5).
- Writes one ``next_action_event`` row per transition so the field-
  level history is queryable per action without scanning the audit
  chain.

T16 requirement: a next-action linked to an approval package
(``approval_package_id`` non-null) is refused to transition to
``complete`` — the caller must go through the approval decision path.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.approval import ApprovalPackage
from app.models.next_action import (
    VALID_NEXT_ACTION_STATUSES,
    NextAction,
    NextActionEvent,
)
from app.models.opportunity import Opportunity
from app.models.user import User


LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "HR", "SystemAdmin"}
)


# --- Data classes ---------------------------------------------------------


@dataclass(frozen=True)
class NextActionCreate:
    opportunity_id: uuid.UUID
    title: str
    assignee_user_id: uuid.UUID
    due_date: date | None = None
    blocker: str | None = None
    outcome: str | None = None
    approval_package_id: uuid.UUID | None = None


@dataclass(frozen=True)
class NextActionPatch:
    title: str | None = None
    assignee_user_id: uuid.UUID | None = None
    due_date: date | None = None
    status: str | None = None
    blocker: str | None = None
    outcome: str | None = None
    # Sentinel: when patch.clear_due_date is True, due_date is nulled.
    clear_due_date: bool = False
    clear_blocker: bool = False
    clear_outcome: bool = False


# --- Errors --------------------------------------------------------------


class ApprovalCompletionForbidden(HTTPException):
    """T16: completing an approval-linked next-action must go through
    the approval endpoint, not this service."""

    def __init__(self, package_id: uuid.UUID) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "This next-action is tied to an approval package; "
                    "complete it by recording the approval decision."
                ),
                "approval_package_id": str(package_id),
                "next_step": f"/approvals/{package_id}/decision",
                "error_type": "next_action.approval_completion_forbidden",
            },
        )


# --- Helpers --------------------------------------------------------------


def _is_leader(user: AuthUser) -> bool:
    return any(r in LEADER_ROLES for r in user.groups)


def _row_to_dict(action: NextAction) -> dict[str, Any]:
    return {
        "id": str(action.id),
        "opportunity_id": str(action.opportunity_id),
        "title": action.title or action.description,
        "description": action.description,
        "assignee_user_id": str(action.assignee_user_id or action.owner_user_id),
        "owner_user_id": str(action.owner_user_id),
        "due_date": action.due_date.isoformat() if action.due_date else None,
        "status": action.status,
        "blocker": action.blocker,
        "outcome": action.outcome,
        "approval_package_id": (
            str(action.approval_package_id) if action.approval_package_id else None
        ),
    }


async def _write_event(
    session: AsyncSession,
    *,
    action: NextAction,
    actor: AuthUser,
    kind: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
) -> NextActionEvent:
    event = NextActionEvent(
        id=uuid.uuid4(),
        next_action_id=action.id,
        actor_id=actor.id,
        kind=kind,
        from_status=from_status,
        to_status=to_status,
        before=before,
        after=after,
        note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def _assert_opportunity_exists(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )
    return opp


async def _assert_user_exists(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="assignee not found"
        )
    return user


async def _assert_approval_package_exists(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    pkg = await session.get(ApprovalPackage, package_id)
    if pkg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="approval package not found",
        )
    return pkg


# --- Public API -----------------------------------------------------------


async def load_action(
    session: AsyncSession, action_id: uuid.UUID
) -> NextAction:
    action = await session.get(NextAction, action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="next-action not found"
        )
    return action


async def list_actions(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID | None = None,
    assignee_user_id: uuid.UUID | None = None,
    status_in: tuple[str, ...] = (),
) -> tuple[NextAction, ...]:
    stmt = select(NextAction)
    if opportunity_id is not None:
        stmt = stmt.where(NextAction.opportunity_id == opportunity_id)
    if assignee_user_id is not None:
        stmt = stmt.where(
            (NextAction.assignee_user_id == assignee_user_id)
            | (
                (NextAction.assignee_user_id.is_(None))
                & (NextAction.owner_user_id == assignee_user_id)
            )
        )
    if status_in:
        stmt = stmt.where(NextAction.status.in_(status_in))
    stmt = stmt.order_by(
        NextAction.status.asc(),
        NextAction.due_date.asc().nullslast(),
        NextAction.created_at.desc(),
    )
    result = await session.execute(stmt)
    return tuple(result.scalars())


async def list_events(
    session: AsyncSession, action_id: uuid.UUID
) -> tuple[NextActionEvent, ...]:
    stmt = (
        select(NextActionEvent)
        .where(NextActionEvent.next_action_id == action_id)
        .order_by(NextActionEvent.ts.asc())
    )
    result = await session.execute(stmt)
    return tuple(result.scalars())


async def create_action(
    session: AsyncSession,
    *,
    actor: AuthUser,
    payload: NextActionCreate,
) -> NextAction:
    if not payload.title or not payload.title.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="title is required",
        )
    await _assert_opportunity_exists(session, payload.opportunity_id)
    await _assert_user_exists(session, payload.assignee_user_id)
    if payload.approval_package_id is not None:
        await _assert_approval_package_exists(
            session, payload.approval_package_id
        )

    title = payload.title.strip()[:255]
    action = NextAction(
        id=uuid.uuid4(),
        opportunity_id=payload.opportunity_id,
        description=title,  # backcompat mirror; S19 aggregate uses description
        title=title,
        owner_user_id=payload.assignee_user_id,
        assignee_user_id=payload.assignee_user_id,
        due_date=payload.due_date,
        status="open",
        blocker=payload.blocker,
        outcome=payload.outcome,
        approval_package_id=payload.approval_package_id,
        created_by=actor.id,
    )
    session.add(action)
    await session.flush()

    after = _row_to_dict(action)
    await _write_event(
        session,
        action=action,
        actor=actor,
        kind="created",
        before=None,
        after=after,
        to_status="open",
    )
    await append_audit(
        session,
        actor_id=actor.id,
        action="next_action.created",
        entity="next_action",
        entity_id=str(action.id),
        before=None,
        after=after,
    )
    return action


async def _authorize_mutation(
    action: NextAction, actor: AuthUser
) -> None:
    """Assignee, creator or a leader may mutate."""

    if _is_leader(actor):
        return
    if actor.id in {
        action.assignee_user_id,
        action.owner_user_id,
        action.created_by,
    }:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="not authorised to modify this next-action",
    )


async def patch_action(
    session: AsyncSession,
    *,
    actor: AuthUser,
    action: NextAction,
    patch: NextActionPatch,
) -> NextAction:
    await _authorize_mutation(action, actor)

    before = _row_to_dict(action)
    kind = "edited"
    from_status = action.status
    to_status: str | None = None
    changed = False

    if patch.title is not None:
        stripped = patch.title.strip()
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="title cannot be blank",
            )
        action.title = stripped[:255]
        action.description = stripped[:1024]
        changed = True

    if patch.assignee_user_id is not None:
        await _assert_user_exists(session, patch.assignee_user_id)
        if action.assignee_user_id != patch.assignee_user_id:
            kind = "reassigned"
            action.assignee_user_id = patch.assignee_user_id
            # Keep S19's owner_user_id in sync so pipeline aggregate SQL
            # continues to attribute the action to the current assignee.
            action.owner_user_id = patch.assignee_user_id
            changed = True

    if patch.clear_due_date:
        if action.due_date is not None:
            action.due_date = None
            changed = True
    elif patch.due_date is not None:
        if action.due_date != patch.due_date:
            action.due_date = patch.due_date
            changed = True

    if patch.clear_blocker:
        if action.blocker is not None:
            action.blocker = None
            kind = "blocker_cleared"
            changed = True
    elif patch.blocker is not None:
        if action.blocker != patch.blocker:
            action.blocker = patch.blocker
            kind = "blocker_set"
            changed = True

    if patch.clear_outcome:
        if action.outcome is not None:
            action.outcome = None
            changed = True
    elif patch.outcome is not None:
        if action.outcome != patch.outcome:
            action.outcome = patch.outcome
            kind = "outcome_set"
            changed = True

    if patch.status is not None:
        if patch.status not in VALID_NEXT_ACTION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"invalid status; must be one of "
                    f"{sorted(VALID_NEXT_ACTION_STATUSES)}"
                ),
            )
        if patch.status != action.status:
            if patch.status == "complete" and action.approval_package_id is not None:
                # T16: cannot complete an approval-linked action here.
                raise ApprovalCompletionForbidden(action.approval_package_id)
            action.status = patch.status
            to_status = patch.status
            if patch.status == "complete":
                action.completed_at = datetime.now(UTC)
            else:
                # If a completed action is reopened, clear the timestamp
                # so it does not falsely claim completion.
                action.completed_at = None
            kind = "status_change"
            changed = True

    if not changed:
        return action

    after = _row_to_dict(action)
    await _write_event(
        session,
        action=action,
        actor=actor,
        kind=kind,
        before=before,
        after=after,
        from_status=from_status if to_status else None,
        to_status=to_status,
    )
    await append_audit(
        session,
        actor_id=actor.id,
        action=f"next_action.{kind}",
        entity="next_action",
        entity_id=str(action.id),
        before=before,
        after=after,
    )
    return action


async def complete_via_approval(
    session: AsyncSession,
    *,
    actor: AuthUser,
    action: NextAction,
    approval_decision_id: uuid.UUID,
) -> NextAction:
    """Internal API: called by the approval decision path so an
    approval-linked next-action can flip to ``complete`` without the
    T16 refusal. Never wired to a router — only invoked in-process by
    W3's approval decision service.
    """

    if action.approval_package_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="next-action is not tied to an approval package",
        )

    before = _row_to_dict(action)
    action.status = "complete"
    action.completed_at = datetime.now(UTC)
    after = _row_to_dict(action)
    await _write_event(
        session,
        action=action,
        actor=actor,
        kind="status_change",
        from_status=before["status"],
        to_status="complete",
        before=before,
        after=after,
        note=f"via approval decision {approval_decision_id}",
    )
    await append_audit(
        session,
        actor_id=actor.id,
        action="next_action.completed_via_approval",
        entity="next_action",
        entity_id=str(action.id),
        before=before,
        after=after,
    )
    return action


__all__ = [
    "ApprovalCompletionForbidden",
    "LEADER_ROLES",
    "NextActionCreate",
    "NextActionPatch",
    "complete_via_approval",
    "create_action",
    "list_actions",
    "list_events",
    "load_action",
    "patch_action",
]
