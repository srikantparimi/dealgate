"""HubSpot intake service — turn a webhook event into an opportunity + task.

CLAUDE.md rule 5: every state change writes an `audit_event` in the same
transaction. CLAUDE.md rule 7: handlers are idempotent; dedupe on event id;
HubSpot is master — re-read the deal via the API.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.hubspot import HubSpotClient
from app.models.client import Client
from app.models.integration import IntegrationEvent
from app.models.opportunity import Opportunity
from app.models.task import Task
from app.models.user import User
from app.services.clients import (
    upsert_client_from_hubspot,
    upsert_unknown_client_for_deal,
)

log = structlog.get_logger("hubspot_intake")


INTAKE_SUBJECT = "Confirm engagement type and next client check-in"
INTAKE_DUE_BUSINESS_DAYS = 1


def _next_business_day(from_date: date, business_days: int) -> date:
    """Return `from_date` + `business_days` skipping Sat/Sun."""

    d = from_date
    added = 0
    while added < business_days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            added += 1
    return d


def _sales_leader_email() -> str:
    email = os.environ.get("SALES_LEADER_EMAIL", "").strip()
    if not email:
        # Loud failure: leaving intake tasks unassigned violates AC #5.
        raise RuntimeError("SALES_LEADER_EMAIL is not configured")
    return email


async def _find_or_create_user(session: AsyncSession, email: str, name: str) -> User:
    """Lookup a user by email; insert a fresh row if missing."""

    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email, name=name or email, groups=[])
    session.add(user)
    await session.flush()
    return user


async def _resolve_owner(
    session: AsyncSession,
    client: HubSpotClient,
    hubspot_owner_id: str | None,
) -> User:
    """Owner from HubSpot when present, otherwise fall back to the Sales leader."""

    if hubspot_owner_id:
        try:
            owner_payload = await client.get_deal_owner(hubspot_owner_id)
            email = (owner_payload.get("email") or "").strip()
            if email:
                first = owner_payload.get("firstName")
                last = owner_payload.get("lastName")
                name = " ".join(p for p in [first, last] if p).strip() or email
                return await _find_or_create_user(session, email, name)
        except KeyError:
            # Owner id present in webhook but missing/inactive in HubSpot API.
            log.info("hubspot_owner_missing", owner_id=hubspot_owner_id)

    leader_email = _sales_leader_email()
    return await _find_or_create_user(session, leader_email, "Sales Leader")


def _deal_props(deal_payload: dict[str, Any]) -> dict[str, Any]:
    return deal_payload.get("properties") or {}


def _extract_event_id(event: dict[str, Any]) -> str:
    """HubSpot events carry `eventId` (int) — coerce to string for our unique key."""

    eid = event.get("eventId") or event.get("event_id") or event.get("id")
    if eid is None:
        raise ValueError("event missing eventId")
    return str(eid)


def _extract_deal_id(event: dict[str, Any]) -> str:
    obj_id = event.get("objectId") or event.get("object_id")
    if obj_id is None:
        raise ValueError("event missing objectId")
    return str(obj_id)


def _extract_company_id(deal_payload: dict[str, Any]) -> str | None:
    """Pull the primary associated company id out of a HubSpot deal payload.

    HubSpot returns associations either at the top level (``associations``)
    or under ``properties.associations`` depending on the API version. We
    look at both and fall back to a bare ``company_id`` property some pilot
    portals still emit.
    """

    associations = deal_payload.get("associations") or {}
    companies = (
        associations.get("companies")
        if isinstance(associations, dict)
        else None
    )
    if isinstance(companies, dict):
        results = companies.get("results") or []
        if results and isinstance(results, list):
            first = results[0]
            if isinstance(first, dict):
                cid = first.get("id") or first.get("toObjectId")
                if cid is not None:
                    return str(cid)
    props = _deal_props(deal_payload)
    company_id = props.get("associatedcompanyid") or props.get("company_id")
    return str(company_id) if company_id else None


async def _resolve_client(
    session: AsyncSession,
    client: HubSpotClient,
    deal_id: str,
    deal_payload: dict[str, Any],
    correlation_id: str,
) -> Client:
    """Upsert the client for a deal — real company or the "Unknown" fallback.

    Never returns ``None``: every opportunity gets ``client_id`` set (blueprint
    §6.2 wants coverage to attach to a legal entity, and the ad-hoc client is
    the seam a human can later re-point at the real HubSpot company).
    """

    company_id = _extract_company_id(deal_payload)
    if company_id:
        try:
            company_payload = await client.get_company(company_id)
        except KeyError:
            log.info("hubspot_company_missing", company_id=company_id, deal_id=deal_id)
        else:
            return await upsert_client_from_hubspot(
                session,
                company_payload=company_payload,
                correlation_id=correlation_id,
            )
    return await upsert_unknown_client_for_deal(
        session, deal_id=deal_id, correlation_id=correlation_id
    )


async def _upsert_opportunity(
    session: AsyncSession,
    deal_id: str,
    deal_payload: dict[str, Any],
    owner: User,
    client_row: Client,
    correlation_id: str,
) -> tuple[Opportunity, bool]:
    """Insert or update the `opportunity` row keyed by `hubspot_deal_id`.

    Returns `(opportunity, created)` where `created` is True on insert.
    Emits `opportunity.created` or `opportunity.updated` audit inside the
    caller's transaction.
    """

    props = _deal_props(deal_payload)
    stage = props.get("dealstage")
    engagement = props.get("engagement_type")

    result = await session.execute(
        select(Opportunity).where(Opportunity.hubspot_deal_id == deal_id)
    )
    opp = result.scalar_one_or_none()

    if opp is None:
        opp = Opportunity(
            hubspot_deal_id=deal_id,
            owner_id=owner.id,
            client_id=client_row.id,
            engagement_type=engagement,
            sales_stage=stage,
            governance_status="Intake",
        )
        session.add(opp)
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="opportunity.created",
            entity="opportunity",
            entity_id=str(opp.id),
            before=None,
            after={
                "hubspot_deal_id": deal_id,
                "owner_id": str(owner.id),
                "client_id": str(client_row.id),
                "engagement_type": engagement,
                "sales_stage": stage,
                "governance_status": "Intake",
            },
            correlation_id=correlation_id,
        )
        return opp, True

    before = {
        "owner_id": str(opp.owner_id) if opp.owner_id else None,
        "client_id": str(opp.client_id) if opp.client_id else None,
        "engagement_type": opp.engagement_type,
        "sales_stage": opp.sales_stage,
    }
    changed = False
    if opp.owner_id != owner.id:
        opp.owner_id = owner.id
        changed = True
    if opp.client_id != client_row.id:
        opp.client_id = client_row.id
        changed = True
    if engagement is not None and opp.engagement_type != engagement:
        opp.engagement_type = engagement
        changed = True
    if stage is not None and opp.sales_stage != stage:
        opp.sales_stage = stage
        changed = True

    if changed:
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="opportunity.updated",
            entity="opportunity",
            entity_id=str(opp.id),
            before=before,
            after={
                "owner_id": str(opp.owner_id) if opp.owner_id else None,
                "client_id": str(opp.client_id) if opp.client_id else None,
                "engagement_type": opp.engagement_type,
                "sales_stage": opp.sales_stage,
            },
            correlation_id=correlation_id,
        )
    return opp, False


async def _create_intake_task(
    session: AsyncSession,
    opportunity: Opportunity,
    owner: User,
    correlation_id: str,
) -> Task:
    task = Task(
        owner_id=owner.id,
        subject=INTAKE_SUBJECT,
        category="intake",
        due_date=_next_business_day(datetime.now(UTC).date(), INTAKE_DUE_BUSINESS_DAYS),
        status="Open",
    )
    session.add(task)
    await session.flush()
    await append_audit(
        session,
        actor_id=None,
        action="task.created",
        entity="task",
        entity_id=str(task.id),
        before=None,
        after={
            "owner_id": str(owner.id),
            "subject": task.subject,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "opportunity_id": str(opportunity.id),
            "kind": "intake",
        },
        correlation_id=correlation_id,
    )
    return task


async def _intake_task_exists(session: AsyncSession, opportunity: Opportunity) -> bool:
    """Check whether an intake task already exists for this opportunity.

    We match on subject since the Task model does not carry an opportunity FK
    (see Agent A's schema); the intake subject is unique per opportunity for
    S1's purposes.
    """

    result = await session.execute(
        select(Task).where(Task.subject == INTAKE_SUBJECT).where(
            Task.owner_id == opportunity.owner_id
        )
    )
    # Refine using the audit log: only count tasks whose creation audit was
    # linked to this opportunity. Cheap because the audit chain is small.
    from app.models.audit import AuditEvent  # local import to avoid cycles

    r = await session.execute(
        select(AuditEvent).where(
            AuditEvent.action == "task.created",
            AuditEvent.entity == "task",
        )
    )
    linked_task_ids: set[str] = set()
    for row in r.scalars():
        after = row.after or {}
        if after.get("opportunity_id") == str(opportunity.id) and after.get("kind") == "intake":
            linked_task_ids.add(row.entity_id)

    for t in result.scalars():
        if str(t.id) in linked_task_ids:
            return True
    return False


async def _store_event(
    session: AsyncSession,
    event: dict[str, Any],
) -> tuple[IntegrationEvent, bool]:
    """Insert the raw event if not already stored. Returns `(row, created)`."""

    source_event_id = _extract_event_id(event)
    result = await session.execute(
        select(IntegrationEvent).where(IntegrationEvent.source_event_id == source_event_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing, False

    row = IntegrationEvent(
        source="hubspot",
        source_event_id=source_event_id,
        payload=event,
    )
    session.add(row)
    await session.flush()
    return row, True


async def store_events(
    session: AsyncSession, events: list[dict[str, Any]]
) -> list[IntegrationEvent]:
    """Persist a batch of webhook events. Dedupes on `source_event_id`.

    Called synchronously inside the webhook so the HTTP 200 means "durable".
    Does not process the events — the worker (or explicit replay) does that.
    Only newly inserted rows are returned; duplicates are silently dropped.
    """

    stored: list[IntegrationEvent] = []
    for event in events:
        try:
            row, created = await _store_event(session, event)
        except ValueError as exc:
            log.warning("hubspot_event_skipped", reason=str(exc), event=event)
            continue
        if created:
            stored.append(row)
    await session.commit()
    return stored


async def handle_event(
    session: AsyncSession,
    event: dict[str, Any],
    client: HubSpotClient,
) -> None:
    """Idempotent: process one HubSpot webhook event end-to-end.

    - Skips if the event is already stored *and* `processed_at` is set.
    - Re-reads the deal from HubSpot.
    - Upserts the opportunity, resolves owner, creates the intake task
      (only when we just created the opportunity, to preserve idempotency
      on retries).
    - Emits audits for every state change in the same transaction, then
      stamps `integration_event.processed_at`.
    """

    event_row, _ = await _store_event(session, event)
    if event_row.processed_at is not None:
        log.info("hubspot_event_already_processed", event_id=event_row.source_event_id)
        return

    subscription = event.get("subscriptionType") or event.get("subscription_type") or ""
    if subscription and not (
        subscription.startswith("deal.") or subscription == "deal"
    ):
        log.info("hubspot_event_ignored", subscriptionType=subscription)
        event_row.processed_at = datetime.now(UTC)
        await session.commit()
        return

    deal_id = _extract_deal_id(event)
    correlation_id = f"hubspot:{event_row.source_event_id}"

    deal_payload = await client.get_deal(deal_id)
    props = _deal_props(deal_payload)
    hubspot_owner_id = props.get("hubspot_owner_id")

    owner = await _resolve_owner(session, client, hubspot_owner_id)
    client_row = await _resolve_client(
        session, client, deal_id, deal_payload, correlation_id
    )
    opportunity, created = await _upsert_opportunity(
        session, deal_id, deal_payload, owner, client_row, correlation_id
    )
    from app.services.agreement_tracking import ensure_agreement_tasks

    await ensure_agreement_tasks(session, client_id=client_row.id, owner_id=owner.id, actor_id=None, correlation_id=correlation_id)

    if created:
        await _create_intake_task(session, opportunity, owner, correlation_id)
    else:
        # Second event for an existing deal — only create the intake task if
        # it somehow got dropped (defensive; keeps idempotency guarantee).
        if not await _intake_task_exists(session, opportunity):
            await _create_intake_task(session, opportunity, owner, correlation_id)

    event_row.processed_at = datetime.now(UTC)
    await session.commit()


async def replay_event(
    session: AsyncSession,
    event_row: IntegrationEvent,
    client: HubSpotClient,
    actor_id: Any,
) -> None:
    """Re-run `handle_event` for an already-stored event. Audits the replay."""

    correlation_id = f"hubspot:replay:{event_row.source_event_id}"
    # Reset `processed_at` so `handle_event` runs the full path again; the
    # opportunity + task upsert stays idempotent by construction.
    event_row.processed_at = None
    await append_audit(
        session,
        actor_id=actor_id,
        action="integration_event.replayed",
        entity="integration_event",
        entity_id=str(event_row.id),
        before=None,
        after={"source_event_id": event_row.source_event_id},
        correlation_id=correlation_id,
    )
    await session.commit()
    await handle_event(session, event_row.payload, client)
