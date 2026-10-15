"""``GET /config`` — S23-PL2 B14: configuration the web app needs at run time.

``hubspot_portal_id`` comes from ``HUBSPOT_PORTAL_ID``, which Terraform
already sets on the API task. Without it the value is null and the web app
hides its links into HubSpot instead of guessing a portal.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthUser, current_user

router = APIRouter(tags=["config"])


class AppConfigOut(BaseModel):
    hubspot_portal_id: str | None


@router.get("/config", response_model=AppConfigOut)
async def get_app_config(_user: AuthUser = Depends(current_user)) -> AppConfigOut:
    portal_id = (os.environ.get("HUBSPOT_PORTAL_ID") or "").strip()
    return AppConfigOut(hubspot_portal_id=portal_id or None)
