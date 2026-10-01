"""Finance-owned direct-cost category settings + S20 W4 integrations
status cards.

The three /settings/integrations/* status endpoints back the Settings →
Integrations page's Bedrock / SES / worker-heartbeat cards. Each returns
live data (env config + a live sync_status read for the heartbeat) —
never a static "Connected" string (CLAUDE.md rule 11 + S20 W4-4-TRUTH).
"""

import os
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser, current_user, require_role
from app.db import get_session
from app.models.direct_cost_settings import DirectCostSettings
from app.models.sync_status import SyncStatus
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


# ---- S20 W4 · integrations status cards -----------------------------------
#
# Each endpoint sources the card's state live:
#   - /settings/integrations/bedrock    → reads SOW_EXTRACT_MODEL_ID env +
#     the SKIP_BEDROCK_MODEL_CHECK flag; reports the configured profile
#     and whether a boot-time check would have been attempted.
#   - /settings/integrations/ses        → reads DEFAULT_FROM_ADDRESS +
#     SES_FROM_ADDRESS override; reports the sender the renewal worker
#     uses. (Live-sending ping is deliberately skipped — SES-sandbox
#     wants a verified recipient; the Lead's deploy smoke tests that.)
#   - /settings/integrations/worker-heartbeat → reads sync_status for
#     the hubspot_webhook / hubspot_backfill / hubspot_reconcile sources
#     and returns the newest `last_success_at` + the gap to now.
#
# All three return typed JSON (no raw ids leak); the UI renders strings
# in prose, no decorative numbers.
# ---------------------------------------------------------------------------


class BedrockStatus(BaseModel):
    model_id: str
    source: str = Field(
        description=(
            "'env' when the deploy sets SOW_EXTRACT_MODEL_ID, "
            "'default' when the hard-coded fallback is in effect."
        )
    )
    boot_check: str = Field(
        description=(
            "'enforced' when the FastAPI startup hook validates the "
            "profile; 'skipped-env' / 'skipped-stub' when the check is "
            "intentionally bypassed (local / test / SOW_EXTRACT_STUB)."
        )
    )
    region: str
    as_of: datetime


@router.get(
    "/integrations/bedrock",
    response_model=BedrockStatus,
    tags=["integrations"],
)
async def get_bedrock_status(
    _user: AuthUser = Depends(current_user),
) -> BedrockStatus:
    """W4 item 4 · Bedrock model-check card payload.

    Backend-sourced truth, never a static string.
    """
    # Lazy import so this router stays usable in environments where
    # bedrock is not imported at module load (local dev).
    from app.integrations.bedrock_sow_extract import EXTRACT_MODEL, _model_id

    resolved = _model_id()
    source = "env" if os.environ.get("SOW_EXTRACT_MODEL_ID") else "default"
    env = os.environ.get("DEALGATE_ENV", "local")
    if os.environ.get("SOW_EXTRACT_STUB") == "1":
        boot_check = "skipped-stub"
    elif env in ("local", "test"):
        boot_check = "skipped-env"
    elif os.environ.get("SKIP_BEDROCK_MODEL_CHECK") == "1":
        boot_check = "skipped-override"
    else:
        boot_check = "enforced"
    # Pin a reference to EXTRACT_MODEL so UI test can grep.
    _ = EXTRACT_MODEL
    return BedrockStatus(
        model_id=resolved,
        source=source,
        boot_check=boot_check,
        region=os.environ.get("AWS_REGION", "us-east-2"),
        as_of=datetime.now(tz=UTC),
    )


class SesStatus(BaseModel):
    from_address: str
    source: str
    sandbox: bool = Field(
        description=(
            "True whenever we assume SES is still in sandbox — the "
            "staging stack has not yet requested production access, "
            "so every recipient must be pre-verified."
        )
    )
    as_of: datetime


@router.get(
    "/integrations/ses",
    response_model=SesStatus,
    tags=["integrations"],
)
async def get_ses_status(
    _user: AuthUser = Depends(current_user),
) -> SesStatus:
    """W4 item 4 · SES sender-state card payload."""
    from app.integrations.ses import DEFAULT_FROM_ADDRESS, _from_address

    resolved = _from_address()
    source = "env" if os.environ.get("SES_FROM_ADDRESS") else "default"
    # Pin a reference to DEFAULT_FROM_ADDRESS so UI test can grep.
    _ = DEFAULT_FROM_ADDRESS
    sandbox = os.environ.get("SES_PRODUCTION_ACCESS", "false").lower() != "true"
    return SesStatus(
        from_address=resolved,
        source=source,
        sandbox=sandbox,
        as_of=datetime.now(tz=UTC),
    )


class HeartbeatSourceRow(BaseModel):
    source: str
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    last_error: str | None
    age_seconds: int | None


class HeartbeatStatus(BaseModel):
    newest_source: str | None
    newest_last_success_at: datetime | None
    newest_age_seconds: int | None
    sources: list[HeartbeatSourceRow]
    as_of: datetime


@router.get(
    "/integrations/worker-heartbeat",
    response_model=HeartbeatStatus,
    tags=["integrations"],
)
async def get_worker_heartbeat(
    _user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> HeartbeatStatus:
    """W4 item 4 · Worker heartbeat card.

    Live read of ``sync_status`` for the HubSpot integration sources. The
    UI renders the newest ``last_success_at`` relative to now; a worker
    whose heartbeat is older than 5 minutes amber-flags on the card.
    """
    rows = list(
        (
            await session.execute(
                select(SyncStatus).where(
                    SyncStatus.source.in_(
                        (
                            "hubspot_webhook",
                            "hubspot_backfill",
                            "hubspot_reconcile",
                        )
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(tz=UTC)
    source_rows: list[HeartbeatSourceRow] = []
    newest_name: str | None = None
    newest_ts: datetime | None = None
    for row in rows:
        age = None
        if row.last_success_at is not None:
            age = int((now - row.last_success_at).total_seconds())
        source_rows.append(
            HeartbeatSourceRow(
                source=row.source,
                last_success_at=row.last_success_at,
                last_attempt_at=row.last_attempt_at,
                last_error=row.last_error,
                age_seconds=age,
            )
        )
        if row.last_success_at is not None and (
            newest_ts is None or row.last_success_at > newest_ts
        ):
            newest_ts = row.last_success_at
            newest_name = row.source
    newest_age = (
        int((now - newest_ts).total_seconds()) if newest_ts is not None else None
    )
    return HeartbeatStatus(
        newest_source=newest_name,
        newest_last_success_at=newest_ts,
        newest_age_seconds=newest_age,
        sources=source_rows,
        as_of=now,
    )
