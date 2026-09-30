"""Deal comments service (S20 · W6).

Internal comments are user-writable; ``hubspot_note`` rows are a
read-only mirror maintained by W1's HubSpot sync. Editing or deleting
a hubspot_note is refused with 409.

Every mutation writes an ``audit_event`` in the same transaction.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.deal_comment import DealComment
from app.models.opportunity import Opportunity


LEADER_ROLES: frozenset[str] = frozenset(
    {"SalesLeader", "HR", "SystemAdmin"}
)


@dataclass(frozen=True)
class CommentCreate:
    opportunity_id: uuid.UUID
    body: str
    pinned: bool = False


@dataclass(frozen=True)
class CommentPatch:
    body: str | None = None
    pinned: bool | None = None


def _is_leader(user: AuthUser) -> bool:
    return any(r in LEADER_ROLES for r in user.groups)


def _row_to_dict(c: DealComment) -> dict[str, Any]:
    return {
        "id": str(c.id),
        "opportunity_id": str(c.opportunity_id),
        "author_id": str(c.author_id) if c.author_id else None,
        "author_name_fallback": c.author_name_fallback,
        "body": c.body,
        "pinned": bool(c.pinned),
        "source": c.source,
        "hubspot_note_id": c.hubspot_note_id,
        "edited_at": c.edited_at.isoformat() if c.edited_at else None,
        "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
    }


def _assert_internal(c: DealComment) -> None:
    if c.source != "internal":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": (
                    "HubSpot-note comments are a read-only mirror; edit the "
                    "note in HubSpot to change it."
                ),
                "source": c.source,
                "error_type": "deal_comment.hubspot_note_readonly",
            },
        )


async def _assert_opportunity_exists(
    session: AsyncSession, opportunity_id: uuid.UUID
) -> Opportunity:
    opp = await session.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="opportunity not found"
        )
    return opp


async def load_comment(
    session: AsyncSession, comment_id: uuid.UUID
) -> DealComment:
    c = await session.get(DealComment, comment_id)
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="comment not found"
        )
    return c


async def list_comments(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    include_deleted: bool = False,
) -> tuple[DealComment, ...]:
    stmt = select(DealComment).where(DealComment.opportunity_id == opportunity_id)
    if not include_deleted:
        stmt = stmt.where(DealComment.deleted_at.is_(None))
    # Pinned first (regardless of source), then most recent.
    stmt = stmt.order_by(
        DealComment.pinned.desc(),
        DealComment.created_at.desc(),
    )
    result = await session.execute(stmt)
    return tuple(result.scalars())


async def latest_visible_comment(
    session: AsyncSession, *, opportunity_id: uuid.UUID
) -> DealComment | None:
    """The most recent non-deleted comment across sources.

    W2's list surfaces call this per-deal to render "Latest comment +
    author + time" alongside the deal row.
    """

    stmt = (
        select(DealComment)
        .where(DealComment.opportunity_id == opportunity_id)
        .where(DealComment.deleted_at.is_(None))
        .order_by(DealComment.created_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def create_comment(
    session: AsyncSession,
    *,
    actor: AuthUser,
    payload: CommentCreate,
) -> DealComment:
    if not payload.body or not payload.body.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="body is required",
        )
    await _assert_opportunity_exists(session, payload.opportunity_id)

    c = DealComment(
        id=uuid.uuid4(),
        opportunity_id=payload.opportunity_id,
        author_id=actor.id,
        body=payload.body.strip(),
        pinned=payload.pinned,
        source="internal",
    )
    session.add(c)
    await session.flush()
    after = _row_to_dict(c)
    await append_audit(
        session,
        actor_id=actor.id,
        action="deal_comment.created",
        entity="deal_comment",
        entity_id=str(c.id),
        before=None,
        after=after,
    )
    return c


async def _authorize_edit(c: DealComment, actor: AuthUser) -> None:
    if _is_leader(actor):
        return
    if c.author_id is not None and actor.id == c.author_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="not authorised to modify this comment",
    )


async def patch_comment(
    session: AsyncSession,
    *,
    actor: AuthUser,
    comment: DealComment,
    patch: CommentPatch,
) -> DealComment:
    _assert_internal(comment)
    if comment.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="comment has been deleted",
        )
    await _authorize_edit(comment, actor)

    before = _row_to_dict(comment)
    changed = False

    if patch.body is not None:
        stripped = patch.body.strip()
        if not stripped:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="body cannot be blank",
            )
        if stripped != comment.body:
            comment.body = stripped
            comment.edited_at = datetime.now(UTC)
            changed = True

    if patch.pinned is not None:
        if bool(patch.pinned) != bool(comment.pinned):
            comment.pinned = bool(patch.pinned)
            changed = True

    if not changed:
        return comment

    after = _row_to_dict(comment)
    await append_audit(
        session,
        actor_id=actor.id,
        action="deal_comment.edited",
        entity="deal_comment",
        entity_id=str(comment.id),
        before=before,
        after=after,
    )
    return comment


async def delete_comment(
    session: AsyncSession,
    *,
    actor: AuthUser,
    comment: DealComment,
) -> DealComment:
    _assert_internal(comment)
    if comment.deleted_at is not None:
        return comment
    await _authorize_edit(comment, actor)

    before = _row_to_dict(comment)
    comment.deleted_at = datetime.now(UTC)
    comment.deleted_by = actor.id
    after = _row_to_dict(comment)
    await append_audit(
        session,
        actor_id=actor.id,
        action="deal_comment.deleted",
        entity="deal_comment",
        entity_id=str(comment.id),
        before=before,
        after=after,
    )
    return comment


async def upsert_hubspot_note(
    session: AsyncSession,
    *,
    opportunity_id: uuid.UUID,
    hubspot_note_id: str,
    body: str,
    author_name: str | None,
    created_at: datetime,
) -> DealComment:
    """Idempotent write path for W1's HubSpot sync.

    Not exposed via HTTP router. Called by ``services/hubspot_sync``
    when a Note engagement lands. Distinct from the user-writable
    ``create_comment`` because the source is ``hubspot_note`` and the
    audit action name differs.
    """

    stmt = select(DealComment).where(
        DealComment.hubspot_note_id == hubspot_note_id
    )
    result = await session.execute(stmt)
    existing = result.scalars().first()
    if existing is not None:
        # Update body only if the source changed; keep author metadata.
        if existing.body != body:
            before = _row_to_dict(existing)
            existing.body = body
            existing.edited_at = datetime.now(UTC)
            after = _row_to_dict(existing)
            await append_audit(
                session,
                actor_id=None,
                action="deal_comment.hubspot_note_updated",
                entity="deal_comment",
                entity_id=str(existing.id),
                before=before,
                after=after,
            )
        return existing

    c = DealComment(
        id=uuid.uuid4(),
        opportunity_id=opportunity_id,
        author_id=None,
        author_name_fallback=author_name,
        body=body,
        pinned=False,
        source="hubspot_note",
        hubspot_note_id=hubspot_note_id,
        created_at=created_at,
    )
    session.add(c)
    await session.flush()
    after = _row_to_dict(c)
    await append_audit(
        session,
        actor_id=None,
        action="deal_comment.hubspot_note_ingested",
        entity="deal_comment",
        entity_id=str(c.id),
        before=None,
        after=after,
    )
    return c


__all__ = [
    "CommentCreate",
    "CommentPatch",
    "create_comment",
    "delete_comment",
    "latest_visible_comment",
    "list_comments",
    "load_comment",
    "patch_comment",
    "upsert_hubspot_note",
]
