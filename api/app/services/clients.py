"""Client service.

S17 rip-out: `coverage_state`, the `AgreementView` DTO and all queries that
scanned `agreement` rows are gone. NDA/MSA is a flat doc store now — the
list page reads `/agreements` directly and no other page cares about
coverage. `Client.name`, `LegalEntity`, `Opportunity` and the client
detail read stay.

Role gating still lives in :mod:`app.routers.clients` (rule 5).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.client import Client, LegalEntity
from app.models.opportunity import Opportunity
from app.services.user_identity import display_user_name

log = structlog.get_logger("clients")


DEFAULT_LEGAL_ENTITY_SUFFIX = " (default)"


# --- upsert used by the HubSpot intake worker -------------------------------


@dataclass(frozen=True)
class HubSpotCompanyData:
    """Minimal projection of the HubSpot company payload we care about."""

    hubspot_company_id: str
    name: str
    timezone: str | None = None
    country: str | None = None


def _company_from_payload(payload: dict[str, Any]) -> HubSpotCompanyData:
    props = payload.get("properties") or {}
    return HubSpotCompanyData(
        hubspot_company_id=str(payload.get("id") or props.get("hs_object_id") or ""),
        name=(props.get("name") or "").strip() or "Unnamed HubSpot company",
        timezone=(props.get("timezone") or props.get("hs_timezone") or None),
        country=(props.get("country") or None),
    )


async def upsert_client_from_hubspot(
    session: AsyncSession,
    *,
    company_payload: dict[str, Any] | HubSpotCompanyData,
    correlation_id: str | None = None,
) -> Client:
    data = (
        company_payload
        if isinstance(company_payload, HubSpotCompanyData)
        else _company_from_payload(company_payload)
    )
    if not data.hubspot_company_id:
        raise ValueError("hubspot_company_id is required")

    existing = (
        await session.execute(
            select(Client).where(Client.hubspot_company_id == data.hubspot_company_id)
        )
    ).scalar_one_or_none()

    if existing is None:
        client = Client(
            id=uuid.uuid4(),
            name=data.name,
            hubspot_company_id=data.hubspot_company_id,
            timezone=data.timezone,
        )
        session.add(client)
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="client.created",
            entity="client",
            entity_id=str(client.id),
            before=None,
            after={
                "name": client.name,
                "hubspot_company_id": client.hubspot_company_id,
                "timezone": client.timezone,
            },
            correlation_id=correlation_id,
        )
    else:
        client = existing
        before = {"name": client.name, "timezone": client.timezone}
        changed = False
        if client.name != data.name and data.name:
            client.name = data.name
            changed = True
        if client.timezone != data.timezone and data.timezone:
            client.timezone = data.timezone
            changed = True
        if changed:
            await append_audit(
                session,
                actor_id=None,
                action="client.updated",
                entity="client",
                entity_id=str(client.id),
                before=before,
                after={"name": client.name, "timezone": client.timezone},
                correlation_id=correlation_id,
            )

    await ensure_default_legal_entity(
        session, client=client, country=data.country, correlation_id=correlation_id
    )
    return client


async def upsert_unknown_client_for_deal(
    session: AsyncSession,
    *,
    deal_id: str,
    correlation_id: str | None = None,
) -> Client:
    """When HubSpot returns no company for a deal, we still need a client row
    so the opportunity can be created. This upsert keeps its ``hubspot_company_id``
    NULL and derives a stable placeholder name from the deal id."""

    placeholder_name = f"Unknown company (deal {deal_id})"
    existing = (
        await session.execute(select(Client).where(Client.name == placeholder_name))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    client = Client(id=uuid.uuid4(), name=placeholder_name, hubspot_company_id=None)
    session.add(client)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="client.created",
        entity="client",
        entity_id=str(client.id),
        before=None,
        after={"name": client.name, "reason": "no HubSpot company on deal"},
        correlation_id=correlation_id,
    )
    await ensure_default_legal_entity(
        session, client=client, country=None, correlation_id=correlation_id
    )
    return client


async def ensure_default_legal_entity(
    session: AsyncSession,
    *,
    client: Client,
    country: str | None,
    correlation_id: str | None = None,
) -> LegalEntity:
    """Guarantee every client has at least one legal entity. Agreements are
    client-scoped in S17, but many other paths (opportunities, rate cards)
    still key off `legal_entity_id`."""

    existing = (
        await session.execute(
            select(LegalEntity)
            .where(LegalEntity.client_id == client.id)
            .order_by(LegalEntity.created_at.asc())
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    entity = LegalEntity(
        id=uuid.uuid4(),
        client_id=client.id,
        name=(client.name + DEFAULT_LEGAL_ENTITY_SUFFIX)[:255],
        country=country,
    )
    session.add(entity)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="legal_entity.created",
        entity="legal_entity",
        entity_id=str(entity.id),
        before=None,
        after={"client_id": str(client.id), "name": entity.name, "country": entity.country},
        correlation_id=correlation_id,
    )
    return entity


# --- detail read used by GET /clients/{id} ----------------------------------


@dataclass(frozen=True)
class LegalEntityView:
    id: uuid.UUID
    name: str
    country: str | None


@dataclass(frozen=True)
class OpportunityView:
    id: uuid.UUID
    hubspot_deal_id: str | None
    governance_status: str
    sales_stage: str | None
    engagement_type: str | None
    owner_id: uuid.UUID | None
    next_client_action: str | None
    next_client_date: date | None


@dataclass(frozen=True)
class ClientDetail:
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    timezone: str | None
    legal_entities: list[LegalEntityView]
    opportunities: list[OpportunityView]


async def get_client_detail(
    session: AsyncSession, client_id: uuid.UUID, *, today: date | None = None
) -> ClientDetail | None:
    """Load a client detail response. Agreements are read separately from the
    /agreements endpoint (S17)."""

    _ = today  # unused since coverage_state went away
    client = (
        await session.execute(select(Client).where(Client.id == client_id))
    ).scalar_one_or_none()
    if client is None:
        return None

    entities = list(
        (
            await session.execute(
                select(LegalEntity)
                .where(LegalEntity.client_id == client_id)
                .order_by(LegalEntity.created_at.asc())
            )
        ).scalars()
    )
    opportunities = list(
        (
            await session.execute(
                select(Opportunity)
                .where(Opportunity.client_id == client_id)
                .order_by(Opportunity.created_at.asc())
            )
        ).scalars()
    )
    return ClientDetail(
        id=client.id,
        name=client.name,
        hubspot_company_id=client.hubspot_company_id,
        timezone=client.timezone,
        legal_entities=[
            LegalEntityView(id=e.id, name=e.name, country=e.country) for e in entities
        ],
        opportunities=[
            OpportunityView(
                id=o.id,
                hubspot_deal_id=o.hubspot_deal_id,
                governance_status=o.governance_status,
                sales_stage=o.sales_stage,
                engagement_type=o.engagement_type,
                owner_id=o.owner_id,
                next_client_action=o.next_client_action,
                next_client_date=o.next_client_date,
            )
            for o in opportunities
        ],
    )


# --- list used by GET /clients ---------------------------------------------


@dataclass(frozen=True)
class ClientListFilters:
    owner: str | None = None
    search: str | None = None
    page: int = 1
    size: int = 25


@dataclass(frozen=True)
class OwnerRef:
    id: uuid.UUID
    name: str


@dataclass(frozen=True)
class ClientRow:
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    opportunity_count: int
    owner_ids: list[uuid.UUID]
    owners: list[OwnerRef]
    sources: list[str]


async def list_clients(
    session: AsyncSession,
    *,
    filters: ClientListFilters,
    accessible_client_ids: set[uuid.UUID] | None,
    today: date | None = None,
) -> tuple[list[ClientRow], int]:
    _ = today
    base = select(Client)
    if filters.search:
        needle = f"%{filters.search.strip().lower()}%"
        from sqlalchemy import func as _f

        base = base.where(_f.lower(Client.name).like(needle))
    clients = list((await session.execute(base.order_by(Client.name.asc()))).scalars())
    if accessible_client_ids is not None:
        clients = [c for c in clients if c.id in accessible_client_ids]

    client_ids = [c.id for c in clients]
    if client_ids:
        opp_rows = list(
            (
                await session.execute(
                    select(Opportunity).where(Opportunity.client_id.in_(client_ids))
                )
            ).scalars()
        )
        opps_by_client: dict[uuid.UUID, list[Opportunity]] = {}
        for o in opp_rows:
            opps_by_client.setdefault(o.client_id, []).append(o)  # type: ignore[arg-type]
    else:
        opps_by_client = {}

    if filters.owner is not None:
        try:
            owner_uuid = uuid.UUID(filters.owner)
        except ValueError:
            clients = []
        else:
            clients = [
                c
                for c in clients
                if any(o.owner_id == owner_uuid for o in opps_by_client.get(c.id, []))
            ]

    all_owner_ids = {
        o.owner_id
        for opps in opps_by_client.values()
        for o in opps
        if o.owner_id is not None
    }
    owner_names: dict[uuid.UUID, str] = {}
    if all_owner_ids:
        from app.models.user import User as _User

        for u in (
            await session.execute(
                select(_User).where(_User.id.in_(list(all_owner_ids)))
            )
        ).scalars():
            owner_names[u.id] = display_user_name(u.name, u.email)

    _SOURCE_ORDER = ("hubspot", "sow_upload", "bulk_import", "manual")
    rows: list[ClientRow] = []
    for c in clients:
        opps = opps_by_client.get(c.id, [])
        owner_ids_here = [o.owner_id for o in opps if o.owner_id is not None]
        owners_here = [
            OwnerRef(id=oid, name=owner_names.get(oid, "Unassigned"))
            for oid in owner_ids_here
        ]
        seen = {o.source for o in opps if o.source}
        sources_here = [s for s in _SOURCE_ORDER if s in seen] + sorted(
            seen - set(_SOURCE_ORDER)
        )
        rows.append(
            ClientRow(
                id=c.id,
                name=c.name,
                hubspot_company_id=c.hubspot_company_id,
                opportunity_count=len(opps),
                owner_ids=owner_ids_here,
                owners=owners_here,
                sources=sources_here,
            )
        )

    total = len(rows)
    offset = max(0, (filters.page - 1) * filters.size)
    return rows[offset : offset + filters.size], total


async def accessible_client_ids_for(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> set[uuid.UUID]:
    rows = list(
        (
            await session.execute(
                select(Opportunity.client_id).where(Opportunity.owner_id == owner_id)
            )
        ).scalars()
    )
    return {cid for cid in rows if cid is not None}


__all__ = [
    "ClientDetail",
    "ClientListFilters",
    "ClientRow",
    "HubSpotCompanyData",
    "LegalEntityView",
    "OpportunityView",
    "OwnerRef",
    "accessible_client_ids_for",
    "ensure_default_legal_entity",
    "get_client_detail",
    "list_clients",
    "upsert_client_from_hubspot",
    "upsert_unknown_client_for_deal",
]
