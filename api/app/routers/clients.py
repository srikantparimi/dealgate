"""Clients API — S2 E3.

Endpoints:

- ``GET /clients``          — paginated list, role-gated.
- ``GET /clients/{id}``     — client detail (entities, agreements,
  opportunities, recent audit), role-gated.

Role gating (built to the story ACs):

- Leader roles (Finance, Legal, CEO, SystemAdmin, Delivery, HR, SalesLeader)
  see every client. Presales too — build-guide §3 gives them read.
- Everyone else sees only clients they own at least one opportunity on.

Mutation is out of scope this sprint; Agent K's story owns agreement CRUD
and Sprint 3 adds client-level admin.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.client import LegalEntity
from app.models.opportunity import Opportunity
from app.services.clients import (
    ClientListFilters,
    accessible_client_ids_for,
    get_client_detail,
    list_clients,
)
from app.services.deals import LEADER_ROLES, is_leader
from app.services.redact import redact_costs

router = APIRouter(prefix="/clients", tags=["clients"])


# Roles that get read access to the client surface. Presales joins the
# leader read set because build-guide §3 places them alongside Sales for
# governance visibility.
CLIENT_READ_ROLES: frozenset[str] = frozenset(LEADER_ROLES | {"Presales"})


# --- schemas ---------------------------------------------------------------


class LegalEntityRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str | None


class AgreementRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_entity_id: uuid.UUID
    kind: str
    effective_date: date | None
    expiry_date: date | None


class OpportunityLink(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Nullable since 0028: an opportunity created from a SOW upload has
    # no HubSpot deal behind it. Requiring a string here made every
    # SOW-first opportunity 500 the list it appeared in.
    hubspot_deal_id: str | None = None
    governance_status: str
    sales_stage: str | None
    engagement_type: str | None
    owner_id: uuid.UUID | None
    next_client_action: str | None
    next_client_date: date | None


class RecentAuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ts: datetime
    actor_id: uuid.UUID | None
    action: str
    entity: str
    entity_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class ClientDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    timezone: str | None
    coverage_state: str
    legal_entities: list[LegalEntityRow]
    agreements: list[AgreementRow]
    opportunities: list[OpportunityLink]
    recent_activity: list[RecentAuditRow] = Field(default_factory=list)


class OwnerRefResponse(BaseModel):
    id: uuid.UUID
    name: str


class ClientListRow(BaseModel):
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    coverage_state: str
    opportunity_count: int
    owner_ids: list[uuid.UUID]
    # S13a defect §2.2 — the FE renders `owners[*].name` (never `owner_ids[*]`)
    # so the Pipeline Owner column shows a person, not a UUID.
    owners: list[OwnerRefResponse] = Field(default_factory=list)
    # S13a defect §2.3 — distinct opportunity `source` values so the
    # Commercial-stage column reads "SOW upload" / "Bulk import" / "HubSpot"
    # truthfully instead of a hardcoded "HubSpot · from CRM" label.
    sources: list[str] = Field(default_factory=list)


class ClientListResponse(BaseModel):
    items: list[ClientListRow]
    page: int
    size: int
    total: int


# --- helpers ---------------------------------------------------------------


def _can_read_clients(user: AuthUser) -> bool:
    return any(role in CLIENT_READ_ROLES for role in user.groups) or is_leader(user)


async def _access_or_forbid(
    session: AsyncSession, user: AuthUser, client_id: uuid.UUID
) -> None:
    """Non-leader users may read a client iff they own at least one of its
    opportunities. Missing client → 404; missing access → 403.
    """

    if is_leader(user) or "Presales" in user.groups:
        return
    accessible = await accessible_client_ids_for(session, owner_id=user.id)
    if client_id not in accessible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )


# --- endpoints -------------------------------------------------------------


@router.get("", response_model=ClientListResponse)
async def list_clients_endpoint(
    owner: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=25, ge=1, le=200),
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> ClientListResponse:
    if not _can_read_clients(user) and "Sales" not in user.groups:
        # Reject users with no role at all before we do any DB work.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )

    # Non-leader Sales users only see clients on their own opportunities.
    accessible: set[uuid.UUID] | None
    if _can_read_clients(user):
        accessible = None
    else:
        accessible = await accessible_client_ids_for(session, owner_id=user.id)

    # ``owner=me`` collapses to the caller's user id; anything else is
    # forwarded as-is (service layer validates the uuid shape).
    effective_owner = owner
    if owner == "me":
        effective_owner = str(user.id)

    filters = ClientListFilters(
        owner=effective_owner, search=search, page=page, size=size
    )
    rows, total = await list_clients(
        session, filters=filters, accessible_client_ids=accessible
    )
    return ClientListResponse(
        items=[
            ClientListRow(
                id=r.id,
                name=r.name,
                hubspot_company_id=r.hubspot_company_id,
                coverage_state=r.coverage_state,
                opportunity_count=r.opportunity_count,
                owner_ids=r.owner_ids,
                owners=[
                    OwnerRefResponse(id=o.id, name=o.name) for o in r.owners
                ],
                sources=r.sources,
            )
            for r in rows
        ],
        page=page,
        size=size,
        total=total,
    )


@router.get("/{client_id}", response_model=None)
async def get_client_endpoint(
    client_id: uuid.UUID,
    user: AuthUser = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if not (_can_read_clients(user) or "Sales" in user.groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="not authorised"
        )

    detail = await get_client_detail(session, client_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="client not found"
        )

    # Sales without ownership → 403. Do this after the 404 check so we do
    # not leak the existence of clients the caller isn't allowed to see.
    await _access_or_forbid(session, user, client_id)

    recent = await _load_recent_activity(session, detail)

    response = ClientDetailResponse(
        id=detail.id,
        name=detail.name,
        hubspot_company_id=detail.hubspot_company_id,
        timezone=detail.timezone,
        coverage_state=detail.coverage_state,
        legal_entities=[
            LegalEntityRow(id=e.id, name=e.name, country=e.country)
            for e in detail.legal_entities
        ],
        agreements=[
            AgreementRow(
                id=a.id,
                legal_entity_id=a.legal_entity_id,
                kind=a.kind,
                effective_date=a.effective_date,
                expiry_date=a.expiry_date,
            )
            for a in detail.agreements
        ],
        opportunities=[
            OpportunityLink(
                id=o.id,
                hubspot_deal_id=o.hubspot_deal_id,
                governance_status=o.governance_status,
                sales_stage=o.sales_stage,
                engagement_type=o.engagement_type,
                owner_id=o.owner_id,
                next_client_action=o.next_client_action,
                next_client_date=o.next_client_date,
            )
            for o in detail.opportunities
        ],
        recent_activity=recent,
    )
    return redact_costs(response.model_dump(mode="json"), set(user.groups))


async def _load_recent_activity(session: AsyncSession, detail: Any) -> list[RecentAuditRow]:
    """Return the last 10 audit rows across the client + its entities/agreements/opportunities."""

    ids: list[str] = [str(detail.id)]
    ids.extend(str(e.id) for e in detail.legal_entities)
    ids.extend(str(a.id) for a in detail.agreements)
    ids.extend(str(o.id) for o in detail.opportunities)

    # Also include audits keyed on entities that touch this client but were
    # not returned in the payload (task follow-ups, integration events for
    # the client's opportunities). For Sprint 2 the four listed entity kinds
    # cover the human-relevant activity — Agent M's notifications story
    # will fold task audits in later.
    stmt = (
        select(AuditEvent)
        .where(
            AuditEvent.entity.in_(("client", "legal_entity", "agreement", "opportunity")),
            AuditEvent.entity_id.in_(ids),
        )
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
        .limit(10)
    )
    rows = list((await session.execute(stmt)).scalars())
    return [RecentAuditRow.model_validate(r) for r in rows]


# Silence unused-import warnings for entities we may reference via the
# recent-activity query in a future revision.
_ = LegalEntity
_ = Opportunity
_ = or_
