"""HubSpot intake service — turn a webhook event into an opportunity + task.

CLAUDE.md rule 5: every state change writes an `audit_event` in the same
transaction. CLAUDE.md rule 7: handlers are idempotent; dedupe on event id;
HubSpot is master — re-read the deal via the API.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
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
from app.services.sync_status import touch_source
from app.services.hubspot_properties import HubspotPropertyMapping

log = structlog.get_logger("hubspot_intake")


INTAKE_SUBJECT = "Confirm engagement type and next client check-in"
INTAKE_DUE_BUSINESS_DAYS = 1


@dataclass(frozen=True)
class BusinessUnitSelection:
    name: str
    object_type: str
    version: int

    def properties(self, object_type: str) -> tuple[str, ...]:
        return (self.name,) if self.object_type == object_type else ()


async def _business_unit_selection(session: AsyncSession) -> BusinessUnitSelection | None:
    row = await session.get(HubspotPropertyMapping, "business_unit", populate_existing=True)
    if row and row.availability_state == "configured" and row.internal_name:
        return BusinessUnitSelection(row.internal_name, row.object_type, row.mapping_version)
    return None


async def _selection_current(session: AsyncSession, selection: BusinessUnitSelection | None) -> bool:
    if selection is None:
        return False
    row = await session.get(HubspotPropertyMapping, "business_unit", populate_existing=True,
                            with_for_update=True)
    return bool(row and row.availability_state == "configured"
                and (row.internal_name, row.object_type, row.mapping_version)
                == (selection.name, selection.object_type, selection.version))


def _source_snapshot(row: Client | Opportunity) -> dict[str, Any]:
    return {"hubspot_owner_id": row.hubspot_owner_id,
            "hubspot_last_modified_at": (row.hubspot_last_modified_at.isoformat()
                if row.hubspot_last_modified_at else None),
            "owner_observed": row.hubspot_owner_observed_at is not None,
            "business_unit_value": row.business_unit_value,
            "business_unit_mapping_version": row.business_unit_mapping_version,
            "business_unit_observed": row.business_unit_observed_at is not None}


def _observe_source(row: Client | Opportunity, props: dict[str, Any],
                    selection: BusinessUnitSelection | None, object_type: str,
                    observed_at: datetime) -> None:
    if "hubspot_owner_id" in props:
        value = props["hubspot_owner_id"]
        if value is not None and not isinstance(value, str):
            raise ValueError("invalid_hubspot_owner_id")
        row.hubspot_owner_id = value or None
        row.hubspot_owner_observed_at = observed_at
    if selection and selection.object_type == object_type and selection.name in props:
        value = props[selection.name]
        if value is not None and not isinstance(value, str):
            raise ValueError("invalid_business_unit_value")
        row.business_unit_value = value or None
        row.business_unit_mapping_version = selection.version
        row.business_unit_observed_at = observed_at


def _stale_source(existing: datetime | None, incoming: datetime | None) -> bool:
    if existing is None:
        return False
    if incoming is None:
        return True
    return incoming.replace(tzinfo=incoming.tzinfo or UTC) < existing.replace(tzinfo=existing.tzinfo or UTC)


async def _observed_company(session: AsyncSession, payload: dict[str, Any],
                            correlation_id: str,
                            selection: BusinessUnitSelection | None) -> Client:
    if not await _selection_current(session, selection):
        selection = None
    props = _deal_props(payload)
    modified = _parse_timestamp(props.get("hs_lastmodifieddate"))
    existing = await session.scalar(select(Client).where(
        Client.hubspot_company_id == str(payload["id"])).with_for_update()
        .execution_options(populate_existing=True))
    if existing and _stale_source(existing.hubspot_last_modified_at, modified):
        return existing
    if existing and "name" not in props:
        payload = {**payload, "properties": {**props, "name": existing.name}}
    row = await upsert_client_from_hubspot(
        session, company_payload=payload, correlation_id=correlation_id)
    before = _source_snapshot(row)
    now = datetime.now(UTC)
    _observe_source(row, props, selection, "company", now)
    row.hubspot_last_seen_at = now
    if modified is not None:
        row.hubspot_last_modified_at = modified
    after = _source_snapshot(row)
    if before != after:
        await append_audit(session, actor_id=None, action="client.source_observed",
            entity="client", entity_id=str(row.id), before=before, after=after,
            correlation_id=correlation_id)
    return row


def _next_business_day(from_date: date, business_days: int) -> date:
    """Return `from_date` + `business_days` skipping Sat/Sun."""

    d = from_date
    added = 0
    while added < business_days:
        d = d + timedelta(days=1)
        if d.weekday() < 5:  # 0=Mon .. 4=Fri
            added += 1
    return d


UNASSIGNED_USER_EMAIL = "unassigned@dealgate.local"
UNASSIGNED_USER_NAME = "Unassigned"


def _sales_leader_email() -> str | None:
    """Return the configured Sales-leader email, or ``None`` when unset.

    Historically this raised — the pre-S18 intake made an intake Task
    against the Sales leader, and losing that assignment was a defect.
    S18 §2 F2 replaces that behaviour with an Unassigned sentinel user
    for HubSpot backfill / webhook paths, so the leader email is now
    optional and callers must handle the ``None`` case.
    """

    return os.environ.get("SALES_LEADER_EMAIL", "").strip() or None


async def _unassigned_user(session: AsyncSession) -> User:
    """Upsert the shared Unassigned sentinel used when no HubSpot owner
    can be resolved. F2 checklist requirement."""

    return await _find_or_create_user(session, UNASSIGNED_USER_EMAIL, UNASSIGNED_USER_NAME)


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
            # Stub client raises KeyError; real HubSpot returns 404.
            log.info("hubspot_owner_missing", owner_id=hubspot_owner_id)
        except Exception as exc:  # httpx.HTTPStatusError etc.
            # Live portals do return 404 for deactivated owners — F2 edge case
            # observed during the first §2a backfill run (owner 76287123).
            # Log the specific status when we can, otherwise the type. Never
            # bubble: a missing owner falls back to the Sales leader.
            import httpx as _httpx

            if isinstance(exc, _httpx.HTTPStatusError) and exc.response.status_code == 404:
                log.info("hubspot_owner_missing", owner_id=hubspot_owner_id, status=404)
            else:
                log.warning(
                    "hubspot_owner_lookup_failed",
                    owner_id=hubspot_owner_id,
                    error_type=type(exc).__name__,
                )

    leader_email = _sales_leader_email()
    if leader_email:
        return await _find_or_create_user(session, leader_email, "Sales Leader")
    # F2: no HubSpot owner and no configured Sales leader — assign to the
    # shared Unassigned sentinel. Backfill / webhook / reconcile all share
    # the same user, so the Pipeline UI can filter on it later.
    return await _unassigned_user(session)


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
        selection = await _business_unit_selection(session)
        additional = selection.properties("company") if selection else ()
        try:
            company_payload = await client.get_company(company_id, **(
                {"additional_properties": additional} if additional else {}))
        except KeyError:
            log.info("hubspot_company_missing", company_id=company_id, deal_id=deal_id)
        else:
            return await _observed_company(session, company_payload, correlation_id, selection)
    return await upsert_unknown_client_for_deal(
        session, deal_id=deal_id, correlation_id=correlation_id
    )


def _parse_amount(raw: Any) -> Any:
    """HubSpot returns amount as string; coerce to Decimal, tolerate empty."""

    from decimal import Decimal, InvalidOperation

    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _parse_close_date(raw: Any) -> Any:
    """HubSpot returns closedate as ISO8601 or ms-epoch string."""

    if not raw:
        return None
    s = str(raw)
    # ISO8601 first
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    # ms-epoch fallback
    try:
        return datetime.fromtimestamp(int(s) / 1000, tz=UTC).date()
    except (ValueError, OSError):
        return None


def _parse_timestamp(raw: Any) -> datetime | None:
    """S19 slice 1: HubSpot ISO8601 or ms-epoch string → tz-aware datetime."""

    if not raw:
        return None
    s = str(raw)
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return datetime.fromtimestamp(int(s) / 1000, tz=UTC)
    except (ValueError, OSError):
        return None


def _dedup_company_ids(deal_payload: dict[str, Any]) -> list[str]:
    """S19 G3: HubSpot lists each company association twice (labeled +
    unlabeled). Return ordered unique company ids preserving the labeled
    row first when both types are present.
    """

    associations = deal_payload.get("associations") or {}
    companies = associations.get("companies") if isinstance(associations, dict) else None
    if not isinstance(companies, dict):
        return []
    results = companies.get("results") or []
    labeled_ids: list[str] = []
    unlabeled_ids: list[str] = []
    for row in results:
        if not isinstance(row, dict):
            continue
        cid = row.get("id") or row.get("toObjectId")
        if cid is None:
            continue
        cid = str(cid)
        t = row.get("type") or ""
        if t.endswith("_unlabeled"):
            unlabeled_ids.append(cid)
        else:
            labeled_ids.append(cid)
    seen: set[str] = set()
    out: list[str] = []
    for cid in labeled_ids + unlabeled_ids:
        if cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


async def _resolve_secondary_clients(
    session: AsyncSession,
    client: HubSpotClient,
    company_ids: list[str],
    correlation_id: str,
) -> list[str]:
    """Return DealGate client UUIDs (as strings) for every additional
    company beyond the primary. Never raises; missing companies are
    skipped and logged.
    """

    out: list[str] = []
    for cid in company_ids:
        selection = await _business_unit_selection(session)
        additional = selection.properties("company") if selection else ()
        try:
            payload = await client.get_company(cid, **(
                {"additional_properties": additional} if additional else {}))
        except Exception as exc:  # noqa: BLE001
            log.info(
                "hubspot_secondary_company_missing",
                company_id=cid,
                error_type=type(exc).__name__,
            )
            continue
        row = await _observed_company(session, payload, correlation_id, selection)
        out.append(str(row.id))
    return out


async def _upsert_opportunity(
    session: AsyncSession,
    deal_id: str,
    deal_payload: dict[str, Any],
    owner: User,
    client_row: Client,
    correlation_id: str,
    stage_map: Any | None = None,
    secondary_client_ids: list[str] | None = None,
    business_unit: BusinessUnitSelection | None = None,
) -> tuple[Opportunity, bool]:
    """Insert or update the `opportunity` row keyed by `hubspot_deal_id`.

    Returns `(opportunity, created)` where `created` is True on insert.
    Emits `opportunity.created` or `opportunity.updated` audit inside the
    caller's transaction.
    """

    props = _deal_props(deal_payload)
    if not await _selection_current(session, business_unit):
        business_unit = None
    stage = props.get("dealstage")
    engagement = props.get("engagement_type")
    amount = _parse_amount(props.get("amount"))
    close_date = _parse_close_date(props.get("closedate"))
    currency = props.get("deal_currency_code") or None
    # S20 W2 L04 · dealname → opportunity.name. Trim + None-guard.
    raw_dealname = props.get("dealname")
    dealname = raw_dealname.strip() if isinstance(raw_dealname, str) and raw_dealname.strip() else None
    seen_at = datetime.now(UTC)
    # S19 slice 1 B2 — resolve label + closed flags + order from the mirror.
    stage_info = stage_map.resolve(stage, props.get("pipeline")) if stage_map is not None else None
    stage_label = stage_info.label if stage_info else stage
    is_closed_won = bool(stage_info.is_closed_won) if stage_info else False
    is_closed_lost = bool(stage_info.is_closed_lost) if stage_info else False
    stage_order = stage_info.display_order if stage_info else None
    pipeline_id = stage_info.pipeline_id if stage_info else (props.get("pipeline") or None)
    hubspot_created_at = _parse_timestamp(props.get("createdate"))
    hubspot_last_modified_at = _parse_timestamp(props.get("hs_lastmodifieddate"))
    hubspot_last_activity_at = _parse_timestamp(props.get("notes_last_updated"))
    secondary_ids = list(secondary_client_ids or [])

    result = await session.execute(
        select(Opportunity).where(Opportunity.hubspot_deal_id == deal_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    opp = result.scalar_one_or_none()
    if opp is not None and _stale_source(opp.hubspot_last_modified_at, hubspot_last_modified_at):
        return opp, False
    if opp is not None and opp.archived_at is not None and opp.archived_reason == "hubspot_deleted":
        prior = opp.hubspot_last_modified_at
        incoming = hubspot_last_modified_at
        if incoming is None or (prior is not None and incoming.replace(tzinfo=incoming.tzinfo or UTC)
            <= prior.replace(tzinfo=prior.tzinfo or UTC)):
            return opp, False

    if opp is None:
        opp = Opportunity(
            hubspot_deal_id=deal_id,
            source="hubspot",
            owner_id=owner.id,
            client_id=client_row.id,
            engagement_type=engagement,
            sales_stage=stage,
            stage_label=stage_label,
            name=dealname,
            amount=amount,
            close_date=close_date,
            hubspot_last_seen_at=seen_at,
            governance_status="Intake",
            hubspot_pipeline_id=pipeline_id,
            hubspot_stage_id=stage,
            stage_order=stage_order,
            is_closed_won=is_closed_won,
            is_closed_lost=is_closed_lost,
            currency=currency,
            hubspot_created_at=hubspot_created_at,
            hubspot_last_activity_at=hubspot_last_activity_at,
            hubspot_last_modified_at=hubspot_last_modified_at,
            primary_client_id=client_row.id,
            hubspot_secondary_client_ids=secondary_ids or None,
        )
        session.add(opp)
        _observe_source(opp, props, business_unit, "deal", seen_at)
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
                "source": "hubspot",
                "owner_id": str(owner.id),
                "client_id": str(client_row.id),
                "engagement_type": engagement,
                "sales_stage": stage,
                "stage_label": stage_label,
                "amount": str(amount) if amount is not None else None,
                "close_date": close_date.isoformat() if close_date else None,
                "governance_status": "Intake",
                "hubspot_pipeline_id": pipeline_id,
                "hubspot_stage_id": stage,
                "stage_order": stage_order,
                "is_closed_won": is_closed_won,
                "is_closed_lost": is_closed_lost,
                "currency": currency,
                "primary_client_id": str(client_row.id),
                "secondary_client_ids": secondary_ids or [],
                **_source_snapshot(opp),
            },
            correlation_id=correlation_id,
        )
        return opp, True

    before = {
        **_source_snapshot(opp),
        "owner_id": str(opp.owner_id) if opp.owner_id else None,
        "client_id": str(opp.client_id) if opp.client_id else None,
        "engagement_type": opp.engagement_type,
        "sales_stage": opp.sales_stage,
        "stage_label": opp.stage_label,
        "amount": str(opp.amount) if opp.amount is not None else None,
        "close_date": opp.close_date.isoformat() if opp.close_date else None,
        "archived_at": opp.archived_at.isoformat() if opp.archived_at else None,
        "is_closed_won": opp.is_closed_won,
        "is_closed_lost": opp.is_closed_lost,
        "currency": opp.currency,
        "primary_client_id": str(opp.primary_client_id) if opp.primary_client_id else None,
    }
    changed = False
    _observe_source(opp, props, business_unit, "deal", seen_at)
    if any(before[key] != value for key, value in _source_snapshot(opp).items()):
        changed = True
    if "hubspot_owner_id" in props and opp.owner_id != owner.id:
        opp.owner_id = owner.id
        changed = True
    if opp.client_id != client_row.id:
        opp.client_id = client_row.id
        changed = True
    if "engagement_type" in props and opp.engagement_type != engagement:
        opp.engagement_type = engagement
        changed = True
    if "dealstage" in props and opp.sales_stage != stage:
        opp.sales_stage = stage
        changed = True
    if "dealstage" in props and opp.stage_label != stage_label:
        opp.stage_label = stage_label
        changed = True
    # S20 W2 L04 · dealname update. `getattr` guard so a partial-migrated
    # schema (name column not yet applied) is safe.
    if "dealname" in props and opp.name != dealname:
        opp.name = dealname
        changed = True
    if "amount" in props and amount != opp.amount:
        opp.amount = amount
        changed = True
    if "closedate" in props and close_date != opp.close_date:
        opp.close_date = close_date
        changed = True
    if ("pipeline" in props or stage_info) and opp.hubspot_pipeline_id != pipeline_id:
        opp.hubspot_pipeline_id = pipeline_id
        changed = True
    if "dealstage" in props and opp.hubspot_stage_id != stage:
        opp.hubspot_stage_id = stage
        changed = True
    if "dealstage" in props and opp.stage_order != stage_order:
        opp.stage_order = stage_order
        changed = True
    if "dealstage" in props and opp.is_closed_won != is_closed_won:
        opp.is_closed_won = is_closed_won
        changed = True
    if "dealstage" in props and opp.is_closed_lost != is_closed_lost:
        opp.is_closed_lost = is_closed_lost
        changed = True
    if "deal_currency_code" in props and opp.currency != currency:
        opp.currency = currency
        changed = True
    if "createdate" in props and opp.hubspot_created_at != hubspot_created_at:
        opp.hubspot_created_at = hubspot_created_at
        changed = True
    if "notes_last_updated" in props and opp.hubspot_last_activity_at != hubspot_last_activity_at:
        opp.hubspot_last_activity_at = hubspot_last_activity_at
        changed = True
    if hubspot_last_modified_at and opp.hubspot_last_modified_at != hubspot_last_modified_at:
        opp.hubspot_last_modified_at = hubspot_last_modified_at
        changed = True
    if opp.primary_client_id != client_row.id:
        opp.primary_client_id = client_row.id
        changed = True
    existing_secondary = list(opp.hubspot_secondary_client_ids or [])
    if secondary_ids != existing_secondary:
        opp.hubspot_secondary_client_ids = secondary_ids or None
        changed = True
    # A HubSpot event on an archived opportunity un-archives it — the deal
    # came back (undelete or reconcile-after-outage). Log the change.
    if opp.archived_at is not None:
        opp.archived_at = None
        opp.archived_by = None
        opp.archived_reason = None
        changed = True
    # Always bump last-seen so the reconcile job knows the row is fresh.
    opp.hubspot_last_seen_at = seen_at

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
                **_source_snapshot(opp),
                "owner_id": str(opp.owner_id) if opp.owner_id else None,
                "client_id": str(opp.client_id) if opp.client_id else None,
                "engagement_type": opp.engagement_type,
                "sales_stage": opp.sales_stage,
                "stage_label": opp.stage_label,
                "amount": str(opp.amount) if opp.amount is not None else None,
                "close_date": opp.close_date.isoformat() if opp.close_date else None,
                "archived_at": None,
                "is_closed_won": opp.is_closed_won,
                "is_closed_lost": opp.is_closed_lost,
                "currency": opp.currency,
                "primary_client_id": str(opp.primary_client_id) if opp.primary_client_id else None,
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
    """Insert the raw event if not already stored. Returns `(row, created)`.

    D7 · A4 — dedupe on ``source_event_id`` at the DB level. If the row
    exists we return it; if two workers race the same event id, the
    ``IntegrityError`` losing side re-fetches and returns the existing
    row rather than exploding. That closes the "distinct queue message
    ids carrying the same source event id" case (T34).
    """

    from sqlalchemy.exc import IntegrityError

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
    try:
        await session.flush()
    except IntegrityError:
        # Concurrent insert won the race; the ``source_event_id`` unique
        # index rejected ours. Roll back the failed flush's savepoint and
        # re-fetch the row that won.
        await session.rollback()
        result = await session.execute(
            select(IntegrationEvent).where(
                IntegrationEvent.source_event_id == source_event_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:  # pragma: no cover - defensive
            raise
        return existing, False
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

    - Skips if the event is already stored *and* ``processed_at`` is set
      (dedupe on source_event_id per D7 — the DB constraint is the guard,
      this check just short-circuits the re-read).
    - Re-reads the deal from HubSpot (rule 7 — webhook payload untrusted).
    - Upserts the opportunity, resolves owner, creates the intake task
      (only when we just created the opportunity, to preserve idempotency
      on retries).
    - Emits audits for every state change in the same transaction, stamps
      ``integration_event.processed_at`` and the
      ``hubspot_webhook_processed`` watermark, then commits. **The commit
      is atomic — record + audit + watermark land together before the
      caller acks the SQS message** (contracts §D7, §A4, T34).
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
        # Even an ignored event bumps the processed watermark so the
        # freshness envelope keeps ticking on portals that emit only
        # non-deal events (rare but observed on the SmarTek21 sandbox).
        await touch_source(
            session,
            source="hubspot_webhook_processed",
            success=True,
            error=None,
            mark_processed=True,
        )
        await session.commit()
        return

    deal_id = _extract_deal_id(event)
    correlation_id = f"hubspot:{event_row.source_event_id}"

    # T28 · webhook-side deletion. `deal.deletion` never has the deal
    # available on the CRM API anymore, so we archive the mirror row
    # locally without a `get_deal` call. Downstream governance rows
    # (SOWs, decisions, audit) are preserved per rule 4.
    if subscription == "deal.deletion":
        opp = (
            await session.execute(
                select(Opportunity).where(Opportunity.hubspot_deal_id == deal_id)
            )
        ).scalar_one_or_none()
        if opp is not None and opp.archived_at is None:
            opp.archived_at = datetime.now(UTC)
            opp.archived_reason = "hubspot_deleted"
            await append_audit(
                session,
                actor_id=None,
                action="opportunity.archived",
                entity="opportunity",
                entity_id=str(opp.id),
                correlation_id=correlation_id,
                before={"archived_at": None, "archived_reason": None},
                after={
                    "archived_at": opp.archived_at.isoformat(),
                    "archived_reason": "hubspot_deleted",
                },
            )
        event_row.processed_at = datetime.now(UTC)
        await touch_source(
            session,
            source="hubspot_webhook_processed",
            success=True,
            error=None,
            mark_processed=True,
        )
        await session.commit()
        return

    business_unit = await _business_unit_selection(session)
    additional = business_unit.properties("deal") if business_unit else ()
    deal_payload = await client.get_deal(deal_id, **(
        {"additional_properties": additional} if additional else {}))
    props = _deal_props(deal_payload)
    hubspot_owner_id = props.get("hubspot_owner_id")

    owner = await _resolve_owner(session, client, hubspot_owner_id)
    client_row = await _resolve_client(
        session, client, deal_id, deal_payload, correlation_id
    )
    opportunity, created = await _upsert_opportunity(
        session, deal_id, deal_payload, owner, client_row, correlation_id,
        business_unit=business_unit,
    )
    # T28 · property-clear / owner-clear / association-change / merge /
    # delete-on-remote are all handled by ``_upsert_opportunity`` (it
    # distinguishes explicit blank fields from fields not fetched;
    # ``_archive_missing`` in backfill handles remote deletes).
    #
    # S17: no more auto-created 'obtain NDA/MSA' tasks. NDA/MSA is a doc store now.
    if created:
        await _create_intake_task(session, opportunity, owner, correlation_id)
    else:
        # Second event for an existing deal — only create the intake task if
        # it somehow got dropped (defensive; keeps idempotency guarantee).
        if not await _intake_task_exists(session, opportunity):
            await _create_intake_task(session, opportunity, owner, correlation_id)

    event_row.processed_at = datetime.now(UTC)
    # D4/D7 — watermark advance happens in the same transaction as the
    # record and audit rows. A crash before commit rolls all three back
    # and the SQS message re-delivers; a crash between commit and ack
    # re-delivers the message, sees ``processed_at`` set, and returns.
    await touch_source(
        session,
        source="hubspot_webhook_processed",
        success=True,
        error=None,
        mark_processed=True,
    )
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
