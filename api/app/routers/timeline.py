"""S20 W6 · combined activity timeline on deal + client pages.

Merges four sources into one time-sorted stream:
- Comments (author, body, source=internal|hubspot_note).
- Next-action events (create / status_change / reassign / edit).
- Approval-package status changes (from ApprovalPackage.status_at column).
- SOW version events (created_at on SowVersion).

Every entry carries a `source` label so the UI renders prose per type.
Nothing is JSON.stringify'd in the UI — the server hands a rendered
sentence per entry.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.approval import ApprovalPackage
from app.models.deal_comment import DealComment
from app.models.next_action import NextAction, NextActionEvent
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.models.audit import AuditEvent
from app.routers.deal_comments import _can_read_comments
from app.services.tracking_access import require_deal_access, visible_deal_ids


router = APIRouter(tags=["timeline"])


class TimelineEntry(BaseModel):
    ts: datetime
    source: str  # comment | next_action | approval | sow
    kind: str  # per-source refinement: e.g. status_change / created / edited
    actor_name: str | None
    body: str  # prose sentence
    entity_id: uuid.UUID | None = None
    comment_source: str | None = None


class TimelineResponse(BaseModel):
    items: list[TimelineEntry]


def _actor(user_row: User | None, fallback: str | None = None) -> str | None:
    if user_row is not None:
        return user_row.name or user_row.email
    return fallback


async def _comment_entry(session, comment, author):
    actor_name = _actor(author, comment.author_name_fallback)
    if comment.edited_at:
        event = await session.scalar(select(AuditEvent).where(
            AuditEvent.entity == "deal_comment", AuditEvent.entity_id == str(comment.id),
            AuditEvent.action.in_(("deal_comment.edited", "deal_comment.hubspot_note_updated")),
        ).order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(1))
        if event and event.actor_id:
            actor_name = _actor(await session.get(User, event.actor_id))
    verb = "edited comment" if comment.edited_at else "commented"
    pinned = " (pinned)" if comment.pinned else ""
    return TimelineEntry(ts=comment.edited_at or comment.created_at, source="comment",
        kind="edited" if comment.edited_at else comment.source, comment_source=comment.source,
        actor_name=actor_name, body=f"{verb}{pinned}: {comment.body}", entity_id=comment.id)


def _time_key(entry):
    return entry.ts.replace(tzinfo=UTC) if entry.ts.tzinfo is None else entry.ts


@router.get(
    "/deals/{opportunity_id}/timeline", response_model=TimelineResponse
)
async def deal_timeline(
    opportunity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    await require_deal_access(session, user, opportunity_id)

    entries: list[TimelineEntry] = []

    # Comments.
    comment_rows = (
        await session.execute(
            select(DealComment, User)
            .join(User, User.id == DealComment.author_id, isouter=True)
            .where(
                DealComment.opportunity_id == opportunity_id,
                DealComment.deleted_at.is_(None),
            )
        )
    ).all()
    for c, author in comment_rows:
        if _can_read_comments(user):
            entries.append(await _comment_entry(session, c, author))

    # Next-action events.
    na_events = (
        await session.execute(
            select(NextActionEvent, NextAction, User)
            .join(NextAction, NextAction.id == NextActionEvent.next_action_id)
            .join(User, User.id == NextActionEvent.actor_id, isouter=True)
            .where(NextAction.opportunity_id == opportunity_id)
        )
    ).all()
    for ev, na, actor in na_events:
        title = na.title or "next action"
        if ev.kind == "created":
            body = f"created next action “{title}”"
        elif ev.kind == "status_change":
            body = (
                f"marked next action “{title}” "
                f"{ev.to_status or 'updated'}"
            )
        elif ev.kind == "reassigned":
            body = f"reassigned next action “{title}”"
        elif ev.kind == "blocker_set":
            body = f"set blocker on “{title}”: {ev.note or ''}".strip()
        elif ev.kind == "blocker_cleared":
            body = f"cleared blocker on “{title}”"
        elif ev.kind == "outcome_set":
            body = f"set outcome on “{title}”"
        else:
            body = f"edited next action “{title}”"
        entries.append(
            TimelineEntry(
                ts=ev.ts,
                source="next_action",
                kind=ev.kind,
                actor_name=_actor(actor),
                body=body,
                entity_id=na.id,
            )
        )

    # Approval package status transitions.
    packages = (
        await session.execute(
            select(ApprovalPackage).where(
                ApprovalPackage.opportunity_id == opportunity_id
            )
        )
    ).scalars().all()
    for p in packages:
        if p.submitted_at is not None:
            entries.append(
                TimelineEntry(
                    ts=p.submitted_at,
                    source="approval",
                    kind="submitted",
                    actor_name=None,
                    body=f"approval package submitted; current status {p.status}",
                    entity_id=p.id,
                )
            )

    # SOW versions.
    sow_versions = (
        await session.execute(
            select(SowVersion, Sow)
            .join(Sow, Sow.id == SowVersion.sow_id)
            .where(Sow.opportunity_id == opportunity_id)
        )
    ).all()
    for v, s in sow_versions:
        entries.append(
            TimelineEntry(
                ts=v.uploaded_at,
                source="sow",
                kind="version_created",
                actor_name=None,
                body=f"SOW version {v.version_no} uploaded",
                entity_id=v.id,
            )
        )

    entries.sort(key=_time_key, reverse=True)
    return TimelineResponse(items=entries[:limit])


@router.get(
    "/clients/{client_id}/timeline", response_model=TimelineResponse
)
async def client_timeline(
    client_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    """Union of the timelines of every non-archived opportunity under the client."""

    opps = await visible_deal_ids(session, user, client_id=client_id)
    if not opps:
        return TimelineResponse(items=[])

    entries: list[TimelineEntry] = []
    # Reuse the deal_timeline logic per opp — this stays under the
    # 3-query budget for a single client because we batch by opp id lists.
    comment_rows = (
        await session.execute(
            select(DealComment, User, Opportunity.hubspot_deal_id)
            .join(User, User.id == DealComment.author_id, isouter=True)
            .join(Opportunity, Opportunity.id == DealComment.opportunity_id)
            .where(
                DealComment.opportunity_id.in_(opps),
                DealComment.deleted_at.is_(None),
            )
        )
    ).all()
    for c, author, deal_hs in comment_rows:
        if _can_read_comments(user):
            entries.append(await _comment_entry(session, c, author))

    na_events = (
        await session.execute(
            select(NextActionEvent, NextAction, User)
            .join(NextAction, NextAction.id == NextActionEvent.next_action_id)
            .join(User, User.id == NextActionEvent.actor_id, isouter=True)
            .where(NextAction.opportunity_id.in_(opps))
        )
    ).all()
    for ev, na, actor in na_events:
        entries.append(
            TimelineEntry(
                ts=ev.ts,
                source="next_action",
                kind=ev.kind,
                actor_name=_actor(actor),
                body=(
                    f"next action “{na.title or 'next action'}” "
                    f"{ev.kind.replace('_', ' ')}"
                ),
                entity_id=na.id,
            )
        )

    entries.sort(key=_time_key, reverse=True)
    return TimelineResponse(items=entries[:limit])
