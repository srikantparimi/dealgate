"""Admin replay endpoints (S6).

Three DLQ surfaces — HubSpot writeback jobs, notifications, and stuck
integration events — plus one replay POST per surface. All endpoints are
gated behind ``require_role("SystemAdmin")``; the router is deliberately
thin (auth + shape conversion), with every write emitting an audit row in
:mod:`app.services.admin_replay`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.integrations.hubspot import HubSpotClient, get_hubspot_client
from app.services.admin_replay import (
    list_failed_hubspot_writeback,
    list_failed_integration_events,
    list_failed_notifications,
    replay_hubspot_writeback,
    replay_integration_event,
    replay_notification,
)

router = APIRouter(prefix="/admin/replay", tags=["admin"])


# --- schemas --------------------------------------------------------------


class HubspotWritebackRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    opportunity_id: uuid.UUID
    hubspot_deal_id: str
    target_state: dict[str, Any]
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class HubspotWritebackListResponse(BaseModel):
    items: list[HubspotWritebackRow]
    page: int
    size: int
    total: int


class NotificationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    category: str
    channel: str
    subject: str
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    created_at: datetime
    sent_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationRow]
    page: int
    size: int
    total: int


class IntegrationEventRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source: str
    source_event_id: str
    received_at: datetime
    processed_at: datetime | None
    payload: dict[str, Any] = Field(default_factory=dict)


class IntegrationEventListResponse(BaseModel):
    items: list[IntegrationEventRow]
    page: int
    size: int
    total: int


class ReplayResponse(BaseModel):
    id: uuid.UUID
    status: str


# --- HubSpot writeback ----------------------------------------------------


@router.get("/hubspot-writeback", response_model=HubspotWritebackListResponse)
async def list_hubspot_writeback_endpoint(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> HubspotWritebackListResponse:
    result = await list_failed_hubspot_writeback(session, page=page, size=size)
    return HubspotWritebackListResponse(
        items=[HubspotWritebackRow.model_validate(r) for r in result.items],
        page=result.page,
        size=result.size,
        total=result.total,
    )


@router.post("/hubspot-writeback/{job_id}", response_model=ReplayResponse)
async def replay_hubspot_writeback_endpoint(
    job_id: uuid.UUID,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
    hubspot: HubSpotClient = Depends(get_hubspot_client),
) -> ReplayResponse:
    job = await replay_hubspot_writeback(
        session,
        actor=actor.id,
        job_id=job_id,
        hubspot_client=hubspot,
    )
    return ReplayResponse(id=job.id, status=job.status)


# --- Notifications --------------------------------------------------------


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications_endpoint(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> NotificationListResponse:
    result = await list_failed_notifications(session, page=page, size=size)
    return NotificationListResponse(
        items=[NotificationRow.model_validate(r) for r in result.items],
        page=result.page,
        size=result.size,
        total=result.total,
    )


@router.post("/notifications/{notification_id}", response_model=ReplayResponse)
async def replay_notification_endpoint(
    notification_id: uuid.UUID,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> ReplayResponse:
    row = await replay_notification(
        session,
        actor=actor.id,
        notification_id=notification_id,
    )
    return ReplayResponse(id=row.id, status=row.status)


# --- Integration events ---------------------------------------------------


@router.get("/integration-events", response_model=IntegrationEventListResponse)
async def list_integration_events_endpoint(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    _user: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
) -> IntegrationEventListResponse:
    result = await list_failed_integration_events(session, page=page, size=size)
    return IntegrationEventListResponse(
        items=[IntegrationEventRow.model_validate(r) for r in result.items],
        page=result.page,
        size=result.size,
        total=result.total,
    )


@router.post("/integration-events/{event_id}", response_model=ReplayResponse)
async def replay_integration_event_endpoint(
    event_id: uuid.UUID,
    actor: AuthUser = Depends(require_role("SystemAdmin")),
    session: AsyncSession = Depends(get_session),
    hubspot: HubSpotClient = Depends(get_hubspot_client),
) -> ReplayResponse:
    row = await replay_integration_event(
        session,
        actor=actor.id,
        event_id=event_id,
        hubspot_client=hubspot,
    )
    return ReplayResponse(
        id=row.id,
        status="processed" if row.processed_at is not None else "replayed",
    )
