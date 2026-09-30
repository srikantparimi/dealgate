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
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
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


router = APIRouter(tags=["timeline"])


class TimelineEntry(BaseModel):
    ts: datetime
    source: str  # comment | next_action | approval | sow
    kind: str  # per-source refinement: e.g. status_change / created / edited
    actor_name: str | None
    body: str  # prose sentence
    entity_id: uuid.UUID | None = None


class TimelineResponse(BaseModel):
    items: list[TimelineEntry]


def _actor(user_row: User | None, fallback: str | None = None) -> str | None:
    if user_row is not None:
        return user_row.name or user_row.email
    return fallback


@router.get(
    "/deals/{opportunity_id}/timeline", response_model=TimelineResponse
)
async def deal_timeline(
    opportunity_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> TimelineResponse:
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )

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
        pinned = " (pinned)" if c.pinned else ""
        entries.append(
            TimelineEntry(
                ts=c.created_at,
                source="comment",
                kind=c.source,
                actor_name=_actor(author, c.author_name_fallback),
                body=f"commented{pinned}: {c.body}",
                entity_id=c.id,
            )
        )

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
        if p.status_at is not None:
            entries.append(
                TimelineEntry(
                    ts=p.status_at,
                    source="approval",
                    kind=p.status,
                    actor_name=None,
                    body=f"approval package moved to {p.status}",
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
                ts=v.created_at,
                source="sow",
                kind="version_created",
                actor_name=None,
                body=f"SOW version {v.version_number} uploaded",
                entity_id=v.id,
            )
        )

    entries.sort(key=lambda e: e.ts, reverse=True)
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

    opps = (
        await session.execute(
            select(Opportunity.id).where(
                Opportunity.client_id == client_id,
                Opportunity.archived_at.is_(None),
            )
        )
    ).scalars().all()
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
        pinned = " (pinned)" if c.pinned else ""
        entries.append(
            TimelineEntry(
                ts=c.created_at,
                source="comment",
                kind=c.source,
                actor_name=_actor(author, c.author_name_fallback),
                body=f"commented on deal {deal_hs or c.opportunity_id}{pinned}: {c.body}",
                entity_id=c.id,
            )
        )

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

    entries.sort(key=lambda e: e.ts, reverse=True)
    return TimelineResponse(items=entries[:limit])
