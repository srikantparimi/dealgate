from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.services.user_provisioning import ensure_user

router = APIRouter()


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    groups: list[str]


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    canonical_user = await ensure_user(session, user)
    await session.commit()
    return MeResponse(
        id=canonical_user.id,
        email=canonical_user.email,
        name=canonical_user.name,
        groups=list(canonical_user.groups),
    )
