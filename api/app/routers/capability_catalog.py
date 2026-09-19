"""Capability catalog admin — CRUD for the curated capability list.

Delivery Lead / SystemAdmin can add and edit entries; every other
governance role (Presales, Marketing, Sales) reads so the intake form
can show the same catalog the adviser retrieves against.

Role gates:

- ``GET``    → Delivery/Presales/Marketing/Sales/SystemAdmin
- ``POST``   → Delivery/SystemAdmin (create; embed on write)
- ``PATCH``  → Delivery/SystemAdmin (edit; re-embed when description changes)
- ``DELETE`` → SystemAdmin only

Every write emits an ``audit_event`` in the same transaction (CLAUDE.md
rule 5). Rows are mutable — a curator refining a description is the
whole point — so the audit trail is what preserves the history.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.bedrock_embeddings import default_embedder
from app.models.capability import CapabilityCatalog
from app.services.embeddings import embed_capability

router = APIRouter(prefix="/admin/capability-catalog", tags=["admin"])


READ_ROLES = ("Delivery", "Presales", "Marketing", "Sales", "SystemAdmin")
WRITE_ROLES = ("Delivery", "SystemAdmin")
DELETE_ROLES = ("SystemAdmin",)


# --- schemas --------------------------------------------------------------


class CapabilityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list)


class CapabilityPatch(BaseModel):
    # All optional so the caller can nudge one field at a time.
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1, max_length=4000)
    tags: list[str] | None = None


def _serialize(row: CapabilityCatalog) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "tags": list(row.tags or []),
        # We never leak the raw embedding to the browser — it's a 1536-float
        # blob and readers care about the flag only.
        "has_embedding": bool(row.embedding),
        "curated_by": str(row.curated_by) if row.curated_by else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# --- endpoints ------------------------------------------------------------


@router.get("")
async def list_capabilities(
    search: str | None = Query(default=None, max_length=255),
    tag: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    stmt = select(CapabilityCatalog)
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(CapabilityCatalog.name).like(like),
                func.lower(CapabilityCatalog.description).like(like),
            )
        )
    # `tag` filter runs in Python for portability — Postgres has native
    # array containment (`= ANY`) and SQLite carries a JSON list; the
    # capability catalog is expected to be small (hundreds of rows) so a
    # post-fetch filter is cheap and keeps the code path identical.
    stmt = stmt.order_by(CapabilityCatalog.name)
    rows = list((await session.execute(stmt)).scalars().all())
    if tag:
        tag_l = tag.lower()
        rows = [r for r in rows if any(t.lower() == tag_l for t in (r.tags or []))]
    total = len(rows)
    offset = max(0, (page - 1) * size)
    items = [_serialize(r) for r in rows[offset : offset + size]]
    return {"items": items, "page": page, "size": size, "total": total}


@router.get("/{capability_id}")
async def get_capability(
    capability_id: uuid.UUID,
    _: AuthUser = Depends(require_role(*READ_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == capability_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="capability not found"
        )
    return _serialize(row)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_capability(
    body: CapabilityCreate,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    # UNIQUE constraint on ``name`` catches races; we short-circuit with a
    # readable 409 before the flush so clients get a specific error.
    existing = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.name == body.name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="capability with this name already exists",
        )

    row = CapabilityCatalog(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        tags=list(body.tags),
        curated_by=actor.id,
    )
    session.add(row)
    await session.flush()

    # Embed on create so the row lands in the ANN index immediately.
    try:
        await embed_capability(
            session, capability_id=row.id, embedder=default_embedder()
        )
    except Exception:  # noqa: BLE001 — embed is best-effort
        pass

    await append_audit(
        session,
        actor_id=actor.id,
        action="capability.created",
        entity="capability_catalog",
        entity_id=str(row.id),
        before=None,
        after={
            "name": row.name,
            "tags": list(row.tags or []),
            "has_embedding": bool(row.embedding),
        },
    )
    await session.commit()
    await session.refresh(row)
    return _serialize(row)


@router.patch("/{capability_id}")
async def patch_capability(
    capability_id: uuid.UUID,
    body: CapabilityPatch,
    actor: AuthUser = Depends(require_role(*WRITE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    row = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == capability_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="capability not found"
        )

    before = {
        "name": row.name,
        "description": row.description,
        "tags": list(row.tags or []),
    }

    description_changed = (
        body.description is not None and body.description != row.description
    )
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.tags is not None:
        row.tags = list(body.tags)

    await session.flush()

    if description_changed or body.name is not None:
        # A name change also affects the embedding text (we concatenate
        # ``name + description``); either mutation forces a re-embed.
        try:
            await embed_capability(
                session,
                capability_id=row.id,
                embedder=default_embedder(),
                force=True,
            )
        except Exception:  # noqa: BLE001 — embed is best-effort
            pass

    after = {
        "name": row.name,
        "description": row.description,
        "tags": list(row.tags or []),
        "re_embedded": description_changed or body.name is not None,
    }

    await append_audit(
        session,
        actor_id=actor.id,
        action="capability.updated",
        entity="capability_catalog",
        entity_id=str(row.id),
        before=before,
        after=after,
    )
    await session.commit()
    await session.refresh(row)
    return _serialize(row)


@router.delete("/{capability_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_capability(
    capability_id: uuid.UUID,
    actor: AuthUser = Depends(require_role(*DELETE_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> None:
    row = (
        await session.execute(
            select(CapabilityCatalog).where(CapabilityCatalog.id == capability_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="capability not found"
        )
    before = {"name": row.name, "tags": list(row.tags or [])}
    await session.delete(row)
    await append_audit(
        session,
        actor_id=actor.id,
        action="capability.deleted",
        entity="capability_catalog",
        entity_id=str(capability_id),
        before=before,
        after=None,
    )
    await session.commit()
    return None
