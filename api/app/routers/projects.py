from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.projects import list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
async def projects(
    actor: AuthUser = Depends(
        require_role(
            "Sales",
            "SalesLeader",
            "Presales",
            "Delivery",
            "HR",
            "Finance",
            "Legal",
            "CEO",
            "SystemAdmin",
        )
    ),
    session: AsyncSession = Depends(get_session),
):
    return {"items": await list_projects(session, actor=actor)}
