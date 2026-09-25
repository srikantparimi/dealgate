"""GM sandbox API — S2 E4 (M1 sign-off screen).

Finance and Delivery validate the six-template math here before Sales ever
sees a GM UI. Endpoints:

* ``POST /gm/sandbox`` — compute for a template + inputs, return components,
  blended GM, floor pass/fail, min prices, and the policy/rate-card version
  that was used.
* ``GET  /gm/sandbox/schema/{engagement_type}`` — field list for the UI form.

All math flows through :mod:`app.gm.compute` — this router never derives a
number on its own (CLAUDE.md rule 2). Money is Python :class:`Decimal`
end-to-end; JSON serialises Decimal as string.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services.gm_sandbox import (
    SandboxInputError,
    build_response,
    parse_engagement_type,
    resolve_policy,
    run_compute,
    schema_for,
)

router = APIRouter(prefix="/gm", tags=["gm"])

# CEO sees dashboards, not the sandbox math tool — the story explicitly lists
# Finance/Delivery/Presales/SystemAdmin as the read+run set.
_SANDBOX_ROLES = ("Finance", "Delivery", "Presales", "SystemAdmin")


class SandboxRequest(BaseModel):
    engagement_type: str = Field(..., description="One of the six template keys.")
    inputs: dict[str, Any] = Field(default_factory=dict)
    policy_version_id: Optional[UUID] = None
    rate_card_version_id: Optional[UUID] = None


def _bad_request(exc: SandboxInputError) -> HTTPException:
    # 422 is FastAPI's canonical body-validation code; we reuse it for
    # semantic errors so the UI can render both classes the same way.
    return HTTPException(status_code=422, detail=str(exc))


@router.post("/sandbox")
async def post_sandbox(
    body: SandboxRequest,
    _user: AuthUser = Depends(require_role(*_SANDBOX_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        engagement_type = parse_engagement_type(body.engagement_type)
        result = run_compute(engagement_type, body.inputs)
    except SandboxInputError as exc:
        raise _bad_request(exc) from exc
    except ValueError as exc:
        # Bad *data* (negative revenue, unknown location) is caller error.
        raise _bad_request(SandboxInputError(str(exc))) from exc

    policy = await resolve_policy(session, body.policy_version_id, body.rate_card_version_id)
    return build_response(engagement_type, result, policy, body.inputs)


@router.get("/sandbox/schema/{engagement_type}")
async def get_sandbox_schema(
    engagement_type: str,
    _user: AuthUser = Depends(require_role(*_SANDBOX_ROLES)),
) -> dict:
    try:
        return schema_for(parse_engagement_type(engagement_type))
    except SandboxInputError as exc:
        raise _bad_request(exc) from exc
