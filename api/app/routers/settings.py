"""Finance-owned direct-cost category settings."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.models.direct_cost_settings import DirectCostSettings
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/settings", tags=["settings"])
DEFAULT_CATEGORIES = [
    "Travel", "Meals & lodging", "Software/licenses", "Subcontractor", "Equipment", "Other",
]
SETTINGS_KEY = "direct_cost_categories"
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class Categories(BaseModel):
    model_config = ConfigDict(extra="forbid")
    categories: list[Category] = Field(min_length=1, max_length=50)

    @field_validator("categories")
    @classmethod
    def unique_categories(cls, values: list[str]) -> list[str]:
        if len({value.casefold() for value in values}) != len(values):
            raise ValueError("categories must be unique")
        return values


@router.get("/direct-cost-categories", response_model=Categories)
async def get_categories(
    _user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Categories:
    row = await session.get(DirectCostSettings, SETTINGS_KEY)
    return Categories(categories=row.categories if row else DEFAULT_CATEGORIES)


@router.put("/direct-cost-categories", response_model=Categories)
async def save_categories(
    body: Categories,
    actor: AuthUser = Depends(require_role("Finance", "SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> Categories:
    user = await ensure_user(session, actor)
    row = await session.get(DirectCostSettings, SETTINGS_KEY, with_for_update=True)
    before = {"categories": list(row.categories if row else DEFAULT_CATEGORIES)}
    if row is None:
        row = DirectCostSettings(key=SETTINGS_KEY, categories=body.categories, updated_by=user.id)
        session.add(row)
    else:
        row.categories = list(body.categories)
        row.updated_by = user.id
    await append_audit(
        session, actor_id=user.id, action="direct_cost_categories.updated",
        entity="direct_cost_settings", entity_id=SETTINGS_KEY,
        before=before, after=body.model_dump(),
    )
    await session.commit()
    return body
