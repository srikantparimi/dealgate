"""S20 W4 Session 5 item 0a · per-user preference store (saved view id, etc.).

Backs the pipeline-page's "last saved view" (previously localStorage) so
a view the user applies on one browser survives on another. The table
`user_preference` already exists (migration 0038); this is just a router.

S23-PL2 B11: keyed on the caller's DealGate user id (a read resolves it
without writing; a write provisions it first), and every change is audited.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.user_preference import UserPreference
from app.services.canonical_user import canonical_actor
from app.services.pipeline_personal import reading_actor


router = APIRouter(prefix="/user-preferences", tags=["user-preferences"])


class PreferenceBody(BaseModel):
    value: Any


class PreferenceOut(BaseModel):
    key: str
    value: Any


@router.get("/{key}", response_model=PreferenceOut)
async def get_preference(
    key: str,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PreferenceOut:
    user = await reading_actor(session, user)
    row = (
        await session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user.id,
                UserPreference.key == key,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not set")
    return PreferenceOut(key=row.key, value=row.value)


@router.put("/{key}", response_model=PreferenceOut)
async def put_preference(
    key: str,
    body: PreferenceBody,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> PreferenceOut:
    user = await canonical_actor(session, user)
    existing = (
        await session.execute(
            select(UserPreference).where(
                UserPreference.user_id == user.id,
                UserPreference.key == key,
            )
        )
    ).scalar_one_or_none()
    before = None if existing is None else {"key": key, "value": existing.value}
    if existing is None:
        session.add(
            UserPreference(user_id=user.id, key=key, value=body.value)
        )
    elif existing.value != body.value:
        existing.value = body.value
    else:
        await session.commit()
        return PreferenceOut(key=key, value=body.value)
    await session.flush()
    await append_audit(
        session, actor_id=user.id, action="user_preference.set", entity="user_preference",
        entity_id=f"{user.id}:{key}", before=before, after={"key": key, "value": body.value},
    )
    await session.commit()
    return PreferenceOut(key=key, value=body.value)
