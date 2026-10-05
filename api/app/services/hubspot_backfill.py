"""HubSpot backfill worker (S18 §2).

Pages every deal in the portal, upserts opportunities via the same
``_upsert_opportunity`` primitive the webhook path uses. Idempotency
comes from that primitive — a second full run reports zero deltas.

Counts (returned by :func:`run_backfill`):

    deals_seen           — every deal returned by the paged fetch
    deals_created        — new opportunity rows
    deals_updated        — existing rows where any HubSpot column changed
    deals_unchanged      — existing rows already in sync
    deals_archived       — opportunities that no longer appear in HubSpot
    companies_matched    — deals whose company resolved to an existing client
    companies_created    — deals whose company resolved to a new client
    owners_matched       — deals whose owner mapped to an existing user
    owners_unassigned    — deals with no owner or an unmatched owner
    errors               — deals that failed and were logged

The routing endpoint (``POST /integrations/hubspot/backfill``) is
SystemAdmin only. The staging smoke calls it once end-to-end.
"""

from __future__ import annotations

import uuid
import copy
import httpx
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import append_audit
from app.db import session_factory as default_session_factory
from app.integrations.hubspot import HubSpotClient
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.services.hubspot_intake import (
    BusinessUnitSelection,
    _business_unit_selection,
    _dedup_company_ids,
    _extract_company_id,
    _deal_props,
    _resolve_client,
    _resolve_owner,
    _resolve_secondary_clients,
    _upsert_opportunity,
)
from app.services.hubspot_owners import sync_owner_mirror
from app.services.hubspot_properties import HubspotPropertyMapping, discover_business_unit
from app.services.hubspot_stage_mirror import StageMap, sync_stage_mirror
from app.services.sync_status import (
    ScanConflict,
    acquire_scan,
    checkpoint_scan,
    complete_scan,
    fail_scan,
    record_scan_attempt_failure,
    _owned_scan,
    touch_source,
)

log = structlog.get_logger("hubspot_backfill")


@dataclass
class BackfillCounts:
    deals_seen: int = 0
    deals_created: int = 0
    deals_updated: int = 0
    deals_unchanged: int = 0
    deals_archived: int = 0
    companies_matched: int = 0
    companies_created: int = 0
    owners_matched: int = 0
    owners_unassigned: int = 0
    multi_company_deals: int = 0
    errors: int = 0
    error_deal_ids: list[str] = field(default_factory=list)
    # S20 W1 A3 · T33 — scan generation, so a failed run never archives.
    scan_generation: int | None = None
    scan_completed: bool = False
    # S20 W1 D2 · D10 — auxiliary mirror counts so ops can see the whole
    # picture without reading three tables.
    owners_mirror_active: int = 0
    owners_mirror_archived: int = 0
    business_unit_property_found: bool = False

    def as_dict(self) -> dict[str, int | list[str] | bool | None]:
        return asdict(self)


def _extract_deal_id(deal_payload: dict) -> str:
    did = deal_payload.get("id") if "id" in deal_payload else (deal_payload.get("properties") or {}).get("hs_object_id")
    if (not isinstance(did, (str, int)) or isinstance(did, bool)
        or not str(did).strip() or str(did).strip() != str(did) or len(str(did)) > 64):
        raise ValueError("deal payload has invalid source identity")
    return str(did)


def _utc(value):
    return value.replace(tzinfo=UTC) if value and value.tzinfo is None else value


def _validate_page(page, after):
    if not isinstance(page, dict) or not isinstance(page.get("results"), list):
        raise ValueError("Invalid HubSpot page results")
    identities = set()
    for payload in page["results"]:
        if not isinstance(payload, dict) or not isinstance(payload.get("properties"), dict):
            raise ValueError("Invalid HubSpot deal payload")
        identity = _extract_deal_id(payload)
        if not identity or identity in identities:
            raise ValueError("Duplicate or empty deal identity in page")
        identities.add(identity)
    paging = page.get("paging", {})
    if not isinstance(paging, dict):
        raise ValueError("Invalid HubSpot paging")
    if "next" not in paging:
        return page["results"], None
    following = paging["next"]
    cursor = following.get("after") if isinstance(following, dict) else None
    if not isinstance(cursor, (str, int)) or isinstance(cursor, bool):
        raise ValueError("Missing HubSpot next cursor")
    cursor = str(cursor)
    if not cursor or len(cursor) > 255 or cursor == after:
        raise ValueError("Invalid or nonadvancing HubSpot cursor")
    return page["results"], cursor


class _FetchedPage:
    """Fetch remote dependencies before acquiring scan/record transaction locks."""
    def __init__(self, additional):
        self.additional = additional
        self.companies = {}
        self.owners = {}

    async def get_company(self, identity, *, additional_properties=()):
        if tuple(additional_properties) != self.additional:
            raise ScanConflict("Company property selection changed during fetch")
        return copy.deepcopy(self.companies[identity])

    async def get_deal_owner(self, identity):
        value = self.owners[identity]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


async def _fetch_dependencies(hub, payloads, business_unit):
    additional = business_unit.properties("company") if business_unit else ()
    fetched = _FetchedPage(additional)
    for payload in payloads:
        owner_id = _deal_props(payload).get("hubspot_owner_id")
        if owner_id is not None and not isinstance(owner_id, str):
            raise ValueError("Invalid HubSpot owner identity")
        if owner_id and owner_id not in fetched.owners:
            try:
                fetched.owners[owner_id] = await hub.get_deal_owner(owner_id)
            except KeyError as error:
                fetched.owners[owner_id] = error
            except httpx.HTTPStatusError as error:
                if error.response.status_code != 404:
                    raise
                fetched.owners[owner_id] = error
        company_ids = _dedup_company_ids(payload)
        primary = _extract_company_id(payload)
        if primary and primary not in company_ids:
            company_ids.append(primary)
        for identity in company_ids:
            if identity not in fetched.companies:
                fetched.companies[identity] = await hub.get_company(identity, **(
                    {"additional_properties": additional} if additional else {}))
    return fetched


async def _assert_mapping(session, business_unit):
    await session.get(HubspotPropertyMapping, "business_unit", with_for_update=True, populate_existing=True)
    if await _business_unit_selection(session) != business_unit:
        raise ScanConflict("Business Unit mapping changed during source fetch")


async def _finalize_scan(factory, hub, lease, correlation_id, business_unit):
    async with factory() as session:
        state = await session.get(SyncStatus, lease.source)
        started = _utc(state.scan_started_at)
        candidates = (await session.scalars(select(Opportunity).where(
            Opportunity.source == "hubspot", Opportunity.archived_at.is_(None),
            or_(Opportunity.hubspot_seen_generation.is_(None),
                Opportunity.hubspot_seen_generation < lease.generation)))).all()
        snapshots = {row.id: (row.hubspot_deal_id, row.hubspot_last_modified_at,
            row.hubspot_last_seen_at, row.updated_at) for row in candidates
            if _utc(row.created_at) <= started and
            (row.hubspot_last_seen_at is None or _utc(row.hubspot_last_seen_at) <= started)}
    for identity, snapshot in snapshots.items():
        evidence = await hub.get_archived_deal(snapshot[0])
        if not isinstance(evidence, dict) or str(evidence.get("id")) != snapshot[0] or evidence.get("archived") is not True:
            raise ValueError("Source deletion unconfirmed; live-list absence is insufficient")
    async with factory() as session:
        await _owned_scan(session, lease, {"finalizing"})
        await _assert_mapping(session, business_unit)
        archived = 0
        for identity, snapshot in snapshots.items():
            row = await session.get(Opportunity, identity, with_for_update=True, populate_existing=True)
            if row is None or row.archived_at is not None:
                continue
            current = (row.hubspot_deal_id, row.hubspot_last_modified_at, row.hubspot_last_seen_at, row.updated_at)
            if current != snapshot or (row.hubspot_seen_generation or 0) >= lease.generation:
                continue
            row.archived_at = datetime.now(UTC)
            row.archived_by = None
            row.archived_reason = "hubspot_deleted"
            await append_audit(session, actor_id=None, action="opportunity.archived", entity="opportunity",
                entity_id=str(row.id), before={"archived_at": None}, after={
                    "archived_at": row.archived_at.isoformat(), "reason": "hubspot_deleted",
                    "scan_generation": lease.generation, "evidence": "explicit_provider_archived"},
                correlation_id=correlation_id)
            archived += 1
        await complete_scan(session, lease)
        await session.commit()
        return archived


async def _process_deal(
    session: AsyncSession,
    client: HubSpotClient,
    deal_payload: dict,
    counts: BackfillCounts,
    correlation_id: str,
    stage_map: StageMap | None = None,
    business_unit: BusinessUnitSelection | None = None,
) -> None:
    deal_id = _extract_deal_id(deal_payload)
    counts.deals_seen += 1
    props = _deal_props(deal_payload)
    hubspot_owner_id = props.get("hubspot_owner_id")

    owner = await _resolve_owner(session, client, hubspot_owner_id)
    if hubspot_owner_id:
        counts.owners_matched += 1
    else:
        counts.owners_unassigned += 1

    # `_resolve_client` may create; look for the "created" audit inside
    # this transaction to count deltas.
    client_row_before = None
    if props.get("associatedcompanyid") or (
        (deal_payload.get("associations") or {}).get("companies")
    ):
        client_row_before = "with_company"

    client_row = await _resolve_client(
        session, client, deal_id, deal_payload, correlation_id
    )
    # Cheap heuristic: if the client's created_at is within a few seconds of
    # now, this backfill created it. SQLite returns naive datetimes while
    # Postgres returns tz-aware; normalize both to UTC before comparing.
    created_at = client_row.created_at
    if created_at is not None and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if created_at and (datetime.now(UTC) - created_at).total_seconds() < 5:
        counts.companies_created += 1
    else:
        counts.companies_matched += 1

    # S19 G3: resolve secondary company associations beyond the primary so
    # the Pipeline UI can render "+N others". Primary is the one used to
    # populate `client_row` above (labeled association wins, else first).
    all_company_ids = _dedup_company_ids(deal_payload)
    secondary_ids: list[str] = []
    if len(all_company_ids) > 1:
        secondary_ids = await _resolve_secondary_clients(
            session, client, all_company_ids[1:], correlation_id
        )
        counts.multi_company_deals += 1

    opp, created = await _upsert_opportunity(
        session, deal_id, deal_payload, owner, client_row, correlation_id,
        stage_map=stage_map, secondary_client_ids=secondary_ids,
        business_unit=business_unit,
    )
    if created:
        counts.deals_created += 1
    else:
        # `_upsert_opportunity` always bumps hubspot_last_seen_at; we count
        # "updated" only when something else changed. Check via audit.
        from app.models.audit import AuditEvent  # local import to avoid cycles

        r = await session.execute(
            select(AuditEvent)
            .where(AuditEvent.entity == "opportunity")
            .where(AuditEvent.entity_id == str(opp.id))
            .where(AuditEvent.correlation_id == correlation_id)
        )
        if r.scalar_one_or_none() is not None:
            counts.deals_updated += 1
        else:
            counts.deals_unchanged += 1


async def run_backfill(
    client: HubSpotClient | None = None,
    *,
    page_size: int = 100,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> BackfillCounts:
    """Resume owned page checkpoints; only explicit source archives can remove rows.

    Provider page/dependency reads happen before the page transaction. Record,
    audit, seen-generation and cursor writes commit together. A failed page
    preserves its previous cursor; finalization and watermark share a transaction.
    """

    hub = client or HubSpotClient()
    factory = session_factory or default_session_factory
    run_started = datetime.now(UTC)
    correlation_id = f"hubspot:backfill:{run_started.isoformat()}"
    counts = BackfillCounts()

    # S19 B1: sync pipeline / stage mirror before any deal upsert. The map
    # feeds every _upsert_opportunity so label / closed flags are resolved
    # from the same source every time.
    stage_map: StageMap | None = None
    try:
        async with factory() as session:
            stage_map = await sync_stage_mirror(session, hub)
            await touch_source(
                session,
                source="hubspot_pipeline_mirror",
                success=True,
                error=None,
            )
            await session.commit()
    except Exception:
        log.exception("hubspot_stage_mirror_sync_failed")
        # A stage-map failure isn't fatal — intake falls back to the naked
        # stage id (mapper bug degrades gracefully). Continue but count the
        # error.
        counts.errors += 1

    # S20 W1 D2 — refresh owner mirror (active + archived).
    try:
        async with factory() as session:
            owner_counts = await sync_owner_mirror(session, hub)
            counts.owners_mirror_active = owner_counts.active_seen
            counts.owners_mirror_archived = owner_counts.archived_seen
            counts.errors += owner_counts.errors
            await session.commit()
    except Exception:
        log.exception("hubspot_owner_mirror_sync_failed")
        counts.errors += 1

    business_unit: BusinessUnitSelection | None = None
    # S20 W1 D10 — discover the Business Unit custom property.
    try:
        async with factory() as session:
            discovery = await discover_business_unit(session, hub)
            counts.business_unit_property_found = discovery.found
            if discovery.availability_state not in {"configured", "absent"}:
                counts.errors += 1
            business_unit = await _business_unit_selection(session)
            await session.commit()
    except Exception:
        log.exception("hubspot_bu_discovery_failed")
        counts.errors += 1

    lease = None
    after = None
    try:
        if counts.errors:
            raise ValueError("Source metadata refresh failed")
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise ValueError("HubSpot page size must be between 1 and 100")
        additional = business_unit.properties("deal") if business_unit else ()
        context = {"schema_version": 1, **hub.scan_scope(), "page_size": page_size,
            "properties": [*HubSpotClient._DEAL_PROPERTIES.split(","), *additional],
            "mapping": asdict(business_unit) if business_unit else None,
            "coverage_mode": "all_active_deals_with_explicit_archive_revalidation"}
        async with factory() as session:
            lease = await acquire_scan(session, source="hubspot_backfill", context=context)
            counts.scan_generation = lease.generation
            await session.commit()
        after = lease.cursor
        while lease.phase != "finalizing":
            page = await hub.list_deals_page(after=after, limit=page_size, **(
                {"additional_properties": additional} if additional else {}))
            results, next_after = _validate_page(page, after)
            fetched = await _fetch_dependencies(hub, results, business_unit)
            page_counts = BackfillCounts()
            async with factory() as session:
                await _owned_scan(session, lease, {"scanning"})
                await _assert_mapping(session, business_unit)
                for payload in results:
                    await _process_deal(session, fetched, payload, page_counts,
                        correlation_id, stage_map=stage_map, business_unit=business_unit)
                    row = await session.scalar(select(Opportunity).where(
                        Opportunity.hubspot_deal_id == _extract_deal_id(payload)))
                    row.hubspot_seen_generation = max(row.hubspot_seen_generation or 0, lease.generation)
                await _assert_mapping(session, business_unit)
                await checkpoint_scan(session, lease, expected_cursor=after, next_cursor=next_after)
                await session.commit()
            for key in ("deals_seen", "deals_created", "deals_updated", "deals_unchanged",
                "companies_matched", "companies_created", "owners_matched", "owners_unassigned", "multi_company_deals"):
                setattr(counts, key, getattr(counts, key) + getattr(page_counts, key))
            if next_after is None:
                break
            after = next_after
        counts.deals_archived = await _finalize_scan(factory, hub, lease, correlation_id, business_unit)
        counts.scan_completed = True
    except Exception as error:
        counts.errors += 1
        log.exception("hubspot_backfill_failed", generation=counts.scan_generation, after=after)
        if lease is not None:
            async with factory() as session:
                try:
                    # Do not persist raw provider responses, credentials or record payloads.
                    await fail_scan(session, lease, error=type(error).__name__)
                    await session.commit()
                except ScanConflict:
                    await session.rollback()
                    log.warning("hubspot_backfill_stale_owner_refused", generation=lease.generation)
        else:
            try:
                scope = hub.scan_scope()
            except ValueError:
                scope = None
            if scope is not None:
                async with factory() as session:
                    await record_scan_attempt_failure(session, source="hubspot_backfill",
                        scope=scope, error=type(error).__name__)
                    await session.commit()

    log.info(
        "hubspot_backfill_complete",
        **{k: v for k, v in counts.as_dict().items() if isinstance(v, (int, bool))},
    )
    return counts
