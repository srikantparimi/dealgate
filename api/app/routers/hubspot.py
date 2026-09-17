"""HubSpot integration endpoints: webhook receiver + manual replay.

Webhook flow (blueprint §6.1):
1. Verify `X-HubSpot-Signature-v3` against the raw request body.
2. Reject timestamps older than 5 minutes (replay defense).
3. Dedupe on `integration_event.source_event_id`, insert rows, commit.
4. Return 200. The worker (`worker.hubspot_intake`) or an explicit call to
   `handle_event` does the actual upsert asynchronously.

CLAUDE.md rule 7: HubSpot payloads are untrusted — the worker re-reads the
deal via the HubSpot API before touching state.
"""

from __future__ import annotations

import os
import time

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.hubspot import HubSpotClient, get_hubspot_client
from app.integrations.hubspot_signature import verify_v3
from app.models.integration import IntegrationEvent
from app.services.hubspot_intake import replay_event, store_events

log = structlog.get_logger("hubspot_router")

router = APIRouter(prefix="/integrations/hubspot", tags=["hubspot"])


MAX_TIMESTAMP_SKEW_SECONDS = 5 * 60


def _reconstruct_uri(request: Request) -> str:
    """Return the URI HubSpot signed: scheme + host + path + query.

    Behind an ALB the app sees `http://` internally; HubSpot signs the public
    HTTPS URL. `HUBSPOT_WEBHOOK_URL` overrides when set so the two agree.
    """

    override = os.environ.get("HUBSPOT_WEBHOOK_URL", "").strip()
    if override:
        # If the caller included a query string, tack it on so signing stays
        # accurate when we add query params in the future.
        if request.url.query:
            sep = "&" if "?" in override else "?"
            return f"{override}{sep}{request.url.query}"
        return override
    return str(request.url)


def _reject_replay(timestamp_header: str) -> None:
    try:
        ts_seconds = int(timestamp_header) / 1000.0
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid timestamp"
        )
    if abs(time.time() - ts_seconds) > MAX_TIMESTAMP_SKEW_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="stale timestamp"
        )


@router.post("/webhook")
async def hubspot_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Verify signature, dedupe, persist, and return 200.

    The response body reports how many events were newly stored (`stored`)
    vs. dropped as duplicates (`duplicates`). HubSpot only requires the
    200 — the counts are for local ops.
    """

    secret = os.environ.get("HUBSPOT_APP_SECRET", "")
    signature = request.headers.get("X-HubSpot-Signature-v3", "")
    timestamp = request.headers.get("X-HubSpot-Request-Timestamp", "")

    if not signature or not timestamp:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing signature headers"
        )

    _reject_replay(timestamp)

    body = await request.body()
    uri = _reconstruct_uri(request)
    if not verify_v3(secret, request.method, uri, body, timestamp, signature):
        # No body persisted, no audit — exactly per AC #4.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature"
        )

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json"
        ) from exc

    events = payload if isinstance(payload, list) else [payload]
    stored_rows = await store_events(session, events)
    log.info(
        "hubspot_webhook_accepted",
        received=len(events),
        stored=len(stored_rows),
    )
    return {
        "received": len(events),
        "stored": len(stored_rows),
        "duplicates": len(events) - len(stored_rows),
    }


@router.post("/events/{event_id}/replay")
async def replay_hubspot_event(
    event_id: str,
    session: AsyncSession = Depends(get_session),
    client: HubSpotClient = Depends(get_hubspot_client),
    user: AuthUser = Depends(require_role("SystemAdmin")),
) -> dict[str, object]:
    """Re-run intake for a previously received event. SystemAdmin only."""

    result = await session.execute(
        select(IntegrationEvent).where(IntegrationEvent.source_event_id == event_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")

    await replay_event(session, row, client, actor_id=user.id)
    return {"event_id": event_id, "status": "replayed"}
