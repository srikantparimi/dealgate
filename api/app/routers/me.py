from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthUser, current_user

router = APIRouter()


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    groups: list[str]


@router.get("/me", response_model=MeResponse)
async def get_me(user: AuthUser = Depends(current_user)) -> MeResponse:
    return MeResponse(id=user.id, email=user.email, name=user.name, groups=list(user.groups))
