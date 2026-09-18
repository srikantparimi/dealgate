"""Client service — S2 E3.

Three concerns live here:

- :func:`coverage_state` — a pure function over a list of ``Agreement`` rows
  that returns the short human-readable coverage label used by the client
  page and the deals list. Kept side-effect free so it can be unit-tested
  cheaply and reused from any caller (deals, workflow, notifications).
- :func:`upsert_client_from_hubspot` — used by the HubSpot intake worker to
  upsert a ``client`` row keyed by ``hubspot_company_id`` plus a default
  ``legal_entity``. Emits ``client.created`` / ``client.updated`` audits and
  ``legal_entity.created`` in the caller's transaction (rule 5).
- :func:`get_client_detail` — the DB read that the client detail endpoint
  returns: client + legal_entities + agreements + opportunities +
  ``coverage_state`` derived from the client's agreements.

Role gating lives in :mod:`app.routers.clients` (rule 5 says the endpoint
does the check); the service layer stays authorization-agnostic so callers
like the HubSpot worker can reuse it without a fake user.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.client import Agreement, Client, LegalEntity
from app.models.opportunity import Opportunity

log = structlog.get_logger("clients")


DEFAULT_LEGAL_ENTITY_SUFFIX = " (default)"

# Ordered priority so we can pick the "worst" coverage state deterministically.
_STATE_PRIORITY: tuple[str, ...] = (
    "NDA + MSA missing",
    "NDA missing",
    "MSA missing",
    "NDA expired",
    "MSA expired",
    "Awaiting signature",
    "Complete",
)


# --- pure coverage helper ---------------------------------------------------


def coverage_state(
    agreements: Iterable[Agreement], today: date | None = None
) -> str:
    """Return the short label describing NDA + MSA coverage.

    Pure: takes an iterable of ``Agreement`` rows and today's date, returns
    one of:

    - ``"Complete"`` — NDA and MSA both present, both executed, none expired.
    - ``"NDA missing"`` / ``"MSA missing"`` — one of the two is absent.
    - ``"NDA + MSA missing"`` — both are absent.
    - ``"NDA expired"`` / ``"MSA expired"`` — latest agreement of that kind
      has an ``expiry_date`` in the past.
    - ``"Awaiting signature"`` — an agreement of the missing kind exists but
      has no ``effective_date`` yet (Agent K's CRUD sets that field on sign).

    The "worst" state wins if several apply (e.g. NDA missing + MSA expired
    → ``"NDA missing"``), so callers can render a single badge.
    """

    today = today or date.today()
    ags = list(agreements)

    findings: list[str] = []
    for kind in ("NDA", "MSA"):
        matching = [a for a in ags if a.kind == kind]
        if not matching:
            findings.append(f"{kind} missing")
            continue
        # Pick the freshest by expiry then effective date so we ignore
        # stale historical rows.
        matching.sort(
            key=lambda a: (
                a.expiry_date or date.min,
                a.effective_date or date.min,
            ),
            reverse=True,
        )
        latest = matching[0]
        if latest.effective_date is None:
            findings.append("Awaiting signature")
            continue
        if latest.expiry_date is not None and latest.expiry_date < today:
            findings.append(f"{kind} expired")

    if not findings:
        return "Complete"

    # Combine missing NDA + MSA into a single label the UI can show as one
    # chip; otherwise return the highest-priority single finding.
    if set(findings) == {"NDA missing", "MSA missing"}:
        return "NDA + MSA missing"
    findings.sort(key=lambda f: _STATE_PRIORITY.index(f) if f in _STATE_PRIORITY else 99)
    return findings[0]


# --- upsert used by the HubSpot intake worker -------------------------------


@dataclass(frozen=True)
class HubSpotCompanyData:
    """Minimal projection of the HubSpot company payload we care about."""

    hubspot_company_id: str
    name: str
    timezone: str | None = None
    country: str | None = None


def _company_from_payload(payload: dict[str, Any]) -> HubSpotCompanyData:
    """Coerce a HubSpot ``/crm/v3/objects/companies/{id}`` payload."""

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
    """Upsert a ``client`` (and a default ``legal_entity``) by HubSpot company id.

    Returns the persisted ``Client`` row. Never commits — the caller owns
    the transaction so this write lands together with the opportunity and
    audit rows for the same webhook event.
    """

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
        await _ensure_default_legal_entity(
            session, client, data.country, correlation_id
        )
        return client

    # Update path — only touch fields that changed to keep the audit trail
    # clean and avoid pointless writes.
    before: dict[str, Any] = {
        "name": existing.name,
        "timezone": existing.timezone,
    }
    after: dict[str, Any] = {}
    changed = False
    if data.name and existing.name != data.name:
        existing.name = data.name
        after["name"] = data.name
        changed = True
    if data.timezone and existing.timezone != data.timezone:
        existing.timezone = data.timezone
        after["timezone"] = data.timezone
        changed = True

    if changed:
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="client.updated",
            entity="client",
            entity_id=str(existing.id),
            before=before,
            after=after,
            correlation_id=correlation_id,
        )
    # Make sure the default legal entity exists even if the client row
    # itself did not change (idempotency guarantee for replays).
    await _ensure_default_legal_entity(session, existing, data.country, correlation_id)
    return existing


async def upsert_unknown_client_for_deal(
    session: AsyncSession, *, deal_id: str, correlation_id: str | None = None
) -> Client:
    """Fallback client used when HubSpot returns no company link.

    Keyed by a synthetic ``hubspot_company_id`` (``unknown:deal:<id>``) so a
    replay of the same event does not create duplicate rows. Nothing about
    the shape is user-facing on its own — the client page will show it as
    "Unknown company (deal <id>)" until a human links the real HubSpot
    company (Agent K's CRUD story).
    """

    synthetic_id = f"unknown:deal:{deal_id}"
    data = HubSpotCompanyData(
        hubspot_company_id=synthetic_id,
        name=f"Unknown company (deal {deal_id})",
        timezone=None,
        country=None,
    )
    return await upsert_client_from_hubspot(
        session, company_payload=data, correlation_id=correlation_id
    )


async def _ensure_default_legal_entity(
    session: AsyncSession,
    client: Client,
    country: str | None,
    correlation_id: str | None,
) -> LegalEntity:
    """Guarantee every client has at least one legal entity to hang agreements on."""

    existing = (
        await session.execute(
            select(LegalEntity).where(LegalEntity.client_id == client.id).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    entity = LegalEntity(
        id=uuid.uuid4(),
        client_id=client.id,
        name=f"{client.name}{DEFAULT_LEGAL_ENTITY_SUFFIX}",
        country=(country or None),
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
        after={
            "client_id": str(client.id),
            "name": entity.name,
            "country": entity.country,
        },
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
class AgreementView:
    id: uuid.UUID
    legal_entity_id: uuid.UUID
    kind: str
    effective_date: date | None
    expiry_date: date | None
    # S2-E3 additions — surfaced so the client detail view can render the
    # Agreements panel without a second round-trip. Existing consumers that
    # only care about `kind`/`effective_date`/`expiry_date` keep working
    # because the new fields default to None on rows that predate the
    # `agreement_state` migration.
    state: str = "missing"
    owner_email: str | None = None
    next_action: str | None = None
    due_date: date | None = None
    effective_from: date | None = None
    expiry: date | None = None
    notice_days: int | None = None
    evidence_s3_key: str | None = None


@dataclass(frozen=True)
class OpportunityView:
    id: uuid.UUID
    hubspot_deal_id: str
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
    coverage_state: str
    legal_entities: list[LegalEntityView]
    agreements: list[AgreementView]
    opportunities: list[OpportunityView]


async def get_client_detail(
    session: AsyncSession, client_id: uuid.UUID, *, today: date | None = None
) -> ClientDetail | None:
    """Load a full client detail response. Returns ``None`` if the id is unknown."""

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
    entity_ids = [e.id for e in entities]
    agreements: Sequence[Agreement]
    if entity_ids:
        agreements = list(
            (
                await session.execute(
                    select(Agreement)
                    .where(Agreement.legal_entity_id.in_(entity_ids))
                    .order_by(Agreement.created_at.asc())
                )
            ).scalars()
        )
    else:
        agreements = []

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
        coverage_state=coverage_state(agreements, today=today),
        legal_entities=[
            LegalEntityView(id=e.id, name=e.name, country=e.country) for e in entities
        ],
        agreements=[
            AgreementView(
                id=a.id,
                legal_entity_id=a.legal_entity_id,
                kind=a.kind,
                effective_date=a.effective_date,
                expiry_date=a.expiry_date,
                state=a.state,
                owner_email=a.owner_email,
                next_action=a.next_action,
                due_date=a.due_date,
                effective_from=a.effective_from,
                expiry=a.expiry,
                notice_days=a.notice_days,
                evidence_s3_key=a.evidence_s3_key,
            )
            for a in agreements
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
    owner: str | None = None  # "me", user-id string, or None
    search: str | None = None
    page: int = 1
    size: int = 25


@dataclass(frozen=True)
class ClientRow:
    id: uuid.UUID
    name: str
    hubspot_company_id: str | None
    coverage_state: str
    opportunity_count: int
    owner_ids: list[uuid.UUID]


async def list_clients(
    session: AsyncSession,
    *,
    filters: ClientListFilters,
    accessible_client_ids: set[uuid.UUID] | None,
    today: date | None = None,
) -> tuple[list[ClientRow], int]:
    """Return (rows, total). ``accessible_client_ids=None`` means "no filter"
    (leader roles); otherwise the caller has narrowed the visible set already.

    Simple Python-side pagination: the client table is small in Sprint 2 and
    the coverage state needs a per-client scan of agreements, so we assemble
    the summary and then slice. Sprint 3 can switch to a SQL windowing query
    if this becomes a hotspot.
    """

    base = select(Client)
    if filters.search:
        needle = f"%{filters.search.strip().lower()}%"
        from sqlalchemy import func as _f

        base = base.where(_f.lower(Client.name).like(needle))

    clients = list((await session.execute(base.order_by(Client.name.asc()))).scalars())

    if accessible_client_ids is not None:
        clients = [c for c in clients if c.id in accessible_client_ids]

    # Prefetch agreements + opportunities for every visible client in two
    # queries to avoid an N+1 in the loop below.
    client_ids = [c.id for c in clients]
    if client_ids:
        entity_rows = list(
            (
                await session.execute(
                    select(LegalEntity).where(LegalEntity.client_id.in_(client_ids))
                )
            ).scalars()
        )
        entities_by_client: dict[uuid.UUID, list[LegalEntity]] = {}
        for e in entity_rows:
            entities_by_client.setdefault(e.client_id, []).append(e)
        entity_ids = [e.id for e in entity_rows]
        agreement_rows: list[Agreement] = (
            list(
                (
                    await session.execute(
                        select(Agreement).where(Agreement.legal_entity_id.in_(entity_ids))
                    )
                ).scalars()
            )
            if entity_ids
            else []
        )
        agreements_by_entity: dict[uuid.UUID, list[Agreement]] = {}
        for a in agreement_rows:
            agreements_by_entity.setdefault(a.legal_entity_id, []).append(a)
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
        entities_by_client = {}
        agreements_by_entity = {}
        opps_by_client = {}

    if filters.owner is not None:
        # ``me`` handled by the router (which knows the caller id); here we
        # accept a UUID and drop clients that have no matching opportunity.
        try:
            owner_uuid = uuid.UUID(filters.owner)
        except ValueError:
            clients = []
            owner_uuid = None  # type: ignore[assignment]
        else:
            clients = [
                c
                for c in clients
                if any(o.owner_id == owner_uuid for o in opps_by_client.get(c.id, []))
            ]

    rows: list[ClientRow] = []
    for c in clients:
        client_agreements: list[Agreement] = []
        for e in entities_by_client.get(c.id, []):
            client_agreements.extend(agreements_by_entity.get(e.id, []))
        opps = opps_by_client.get(c.id, [])
        rows.append(
            ClientRow(
                id=c.id,
                name=c.name,
                hubspot_company_id=c.hubspot_company_id,
                coverage_state=coverage_state(client_agreements, today=today),
                opportunity_count=len(opps),
                owner_ids=[o.owner_id for o in opps if o.owner_id is not None],
            )
        )

    total = len(rows)
    offset = max(0, (filters.page - 1) * filters.size)
    return rows[offset : offset + filters.size], total


async def accessible_client_ids_for(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> set[uuid.UUID]:
    """Return the set of client ids this owner has at least one opportunity on."""

    rows = list(
        (
            await session.execute(
                select(Opportunity.client_id).where(Opportunity.owner_id == owner_id)
            )
        ).scalars()
    )
    return {cid for cid in rows if cid is not None}


__all__ = [
    "AgreementView",
    "ClientDetail",
    "ClientListFilters",
    "ClientRow",
    "HubSpotCompanyData",
    "LegalEntityView",
    "OpportunityView",
    "accessible_client_ids_for",
    "coverage_state",
    "get_client_detail",
    "list_clients",
    "upsert_client_from_hubspot",
    "upsert_unknown_client_for_deal",
]
