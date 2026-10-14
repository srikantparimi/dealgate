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
    errors               — every error of the run (per-record and fatal)

The routing endpoint (``POST /integrations/hubspot/backfill``) is
SystemAdmin only. The staging smoke calls it once end-to-end.

S23-PL1 items 3 and 4 — the run reports what really happened:

- Per-record isolation. A bad stage, company, owner lookup or deal is caught,
  listed in ``record_errors`` with its HubSpot id and a short reason (never a
  name or payload text), and the run continues. Each deal is written inside its
  own SAVEPOINT, so one failure cannot roll back the rest of the page. A deal
  that was listed by HubSpot but not written is still marked seen, so the
  archive pass never mistakes it for a deletion.
- Fatal errors. When HubSpot cannot be read at all (the deal list, the stage
  metadata, an authorization failure) or the scan protocol refuses to
  continue, ``fatal_error`` names the phase and the reason.

:mod:`app.services.hubspot_sync_runs` turns these counts into the run record.
"""

from __future__ import annotations

import uuid
import copy
import httpx
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta

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
from app.services.hubspot_intake import UnmappedStageError
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
    # S23-PL1 — every per-record error as {"hubspot_id", "reason"} (ids and
    # short codes only) and the reason the run stopped, when it stopped.
    record_errors: list[dict[str, str]] = field(default_factory=list)
    fatal_error: str | None = None

    @property
    def deals_written(self) -> int:
        """Deals saved from HubSpot by this run (created, changed or re-confirmed)."""
        return self.deals_created + self.deals_updated + self.deals_unchanged

    def record_error(self, hubspot_id: str, reason: str) -> None:
        entry = {"hubspot_id": str(hubspot_id)[:64], "reason": reason[:200]}
        if entry in self.record_errors:
            return
        self.record_errors.append(entry)
        self.errors += 1

    def as_dict(self) -> dict[str, int | list[str] | bool | None]:
        values = asdict(self)
        values["deals_written"] = self.deals_written
        return values


_MERGED_COUNTS = ("deals_seen", "deals_created", "deals_updated", "deals_unchanged",
    "companies_matched", "companies_created", "owners_matched", "owners_unassigned",
    "multi_company_deals")


def _merge_counts(target: BackfillCounts, source: BackfillCounts) -> None:
    for key in _MERGED_COUNTS:
        setattr(target, key, getattr(target, key) + getattr(source, key))
    for entry in source.record_errors:
        target.record_error(entry["hubspot_id"], entry["reason"])
    for deal_id in source.error_deal_ids:
        if deal_id not in target.error_deal_ids:
            target.error_deal_ids.append(deal_id)


_SYSTEMIC_HTTP = {401, 403}
# Unconfirmed deletions (among deals present at the previous scan) tolerated
# before the archive check stops asking HubSpot, and a hard cap per run.
_MAX_UNCONFIRMED_ABSENCES = 5
_MAX_ARCHIVE_CHECKS = 25
# A failed scan is resumed only while its first pages are recent; older ones
# restart from page 1 so a "fresh" run never rests on days-old pages.
SCAN_RESUME_MAX_AGE = timedelta(hours=12)


def short_reason(error: BaseException) -> str:
    """A reason safe to store and show: status codes, ids and type names only."""
    if isinstance(error, UnmappedStageError):
        return str(error)
    if isinstance(error, httpx.HTTPStatusError):
        return f"HTTP {error.response.status_code}"
    if isinstance(error, ScanConflict):
        return f"ScanConflict: {error}"[:200]
    if isinstance(error, KeyError):
        return "not found"
    return type(error).__name__


def _systemic(error: BaseException) -> bool:
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in _SYSTEMIC_HTTP


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
        # S23-PL1 — dependencies HubSpot would not return: (kind, id) -> reason.
        self.unavailable: dict[tuple[str, str], str] = {}

    def blocking_reason(self, payload) -> str | None:
        """Why this deal cannot be written safely from this page, if it cannot."""
        owner_id = _deal_props(payload).get("hubspot_owner_id")
        if owner_id is not None and not isinstance(owner_id, str):
            return "invalid owner identity"
        if owner_id and ("owner", owner_id) in self.unavailable:
            return f"owner {owner_id} unavailable ({self.unavailable[('owner', owner_id)]})"
        companies = _dedup_company_ids(payload)
        primary = _extract_company_id(payload)
        if primary and primary not in companies:
            companies.append(primary)
        # Secondary companies too: writing the deal without one would replace
        # its stored secondary list with a shorter one.
        for company in companies:
            if ("company", company) in self.unavailable:
                return f"company {company} unavailable ({self.unavailable[('company', company)]})"
        return None

    async def get_company(self, identity, *, additional_properties=()):
        if tuple(additional_properties) != self.additional:
            raise ScanConflict("Company property selection changed during fetch")
        return copy.deepcopy(self.companies[identity])

    async def get_deal_owner(self, identity):
        value = self.owners[identity]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


async def _fetch_dependencies(hub, payloads, business_unit, counts: BackfillCounts | None = None):
    """Fetch owners and companies for a page.

    S23-PL1 item 4: a company or owner HubSpot will not return is recorded with
    its id and the deals that need it are skipped; the page continues. A 401 or
    403 means HubSpot cannot be read at all and stays fatal. A missing owner
    (404) keeps its existing meaning: the deal falls back to the Unassigned
    owner.
    """
    counts = counts if counts is not None else BackfillCounts()
    additional = business_unit.properties("company") if business_unit else ()
    fetched = _FetchedPage(additional)
    for payload in payloads:
        owner_id = _deal_props(payload).get("hubspot_owner_id")
        if owner_id is not None and not isinstance(owner_id, str):
            continue  # the deal is refused by blocking_reason and listed there
        if owner_id and owner_id not in fetched.owners and ("owner", owner_id) not in fetched.unavailable:
            try:
                fetched.owners[owner_id] = await hub.get_deal_owner(owner_id)
            except KeyError as error:
                fetched.owners[owner_id] = error
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 404:
                    fetched.owners[owner_id] = error
                elif _systemic(error):
                    raise
                else:
                    fetched.unavailable[("owner", owner_id)] = short_reason(error)
                    counts.record_error(owner_id, f"owner: {short_reason(error)}")
            except Exception as error:
                fetched.unavailable[("owner", owner_id)] = short_reason(error)
                counts.record_error(owner_id, f"owner: {short_reason(error)}")
        company_ids = _dedup_company_ids(payload)
        primary = _extract_company_id(payload)
        if primary and primary not in company_ids:
            company_ids.append(primary)
        for identity in company_ids:
            if identity in fetched.companies or ("company", identity) in fetched.unavailable:
                continue
            try:
                fetched.companies[identity] = await hub.get_company(identity, **(
                    {"additional_properties": additional} if additional else {}))
            except Exception as error:
                if _systemic(error):
                    raise
                fetched.unavailable[("company", identity)] = short_reason(error)
                counts.record_error(identity, f"company: {short_reason(error)}")
    return fetched


async def _assert_mapping(session, business_unit):
    await session.get(HubspotPropertyMapping, "business_unit", with_for_update=True, populate_existing=True)
    if await _business_unit_selection(session) != business_unit:
        raise ScanConflict("Business Unit mapping changed during source fetch")


async def _finalize_scan(factory, hub, lease, correlation_id, business_unit,
                         counts: BackfillCounts | None = None):
    async with factory() as session:
        state = await session.get(SyncStatus, lease.source)
        started = _utc(state.scan_started_at)
        candidates = (await session.scalars(select(Opportunity).where(
            Opportunity.source == "hubspot", Opportunity.archived_at.is_(None),
            or_(Opportunity.hubspot_seen_generation.is_(None),
                Opportunity.hubspot_seen_generation < lease.generation)))).all()
        eligible = [row for row in candidates
            if _utc(row.created_at) <= started and
            (row.hubspot_last_seen_at is None or _utc(row.hubspot_last_seen_at) <= started)]
        # S23-PL1: deals that vanished since the previous scan are checked first,
        # most recently seen first; long-standing absences HubSpot never confirms
        # (merged, purged) come after them, so they cannot starve real deletions.
        fresh_ids = {row.id for row in eligible
            if (row.hubspot_seen_generation or 0) == lease.generation - 1}
        eligible.sort(key=lambda row: (row.id not in fresh_ids,
            -(_utc(row.hubspot_last_seen_at).timestamp() if row.hubspot_last_seen_at else 0), str(row.id)))
        snapshots = {row.id: (row.hubspot_deal_id, row.hubspot_last_modified_at,
            row.hubspot_last_seen_at, row.updated_at) for row in eligible}
    counts = counts if counts is not None else BackfillCounts()
    unconfirmed = set()
    fresh_unconfirmed = 0
    for position, (identity, snapshot) in enumerate(snapshots.items()):
        # S23-PL1 item 4: an absence HubSpot will not confirm is listed and left
        # alone (never archived); the rest of the scan still completes. When
        # several deals that were present last scan all vanish unconfirmed, the
        # live list itself is suspect (an empty page during an outage): stop
        # asking HubSpot and archive nothing that was not checked. A hard cap
        # keeps long-standing absences from outrunning the scan lease.
        if fresh_unconfirmed >= _MAX_UNCONFIRMED_ABSENCES or position >= _MAX_ARCHIVE_CHECKS:
            remaining = list(snapshots)[position:]
            unconfirmed.update(remaining)
            counts.record_error("", f"deal: {len(remaining)} more deals missing from HubSpot were not checked")
            break
        try:
            evidence = await hub.get_archived_deal(snapshot[0])
        except Exception as error:
            if _systemic(error):
                raise
            counts.record_error(snapshot[0], f"deal: archive check failed ({short_reason(error)})")
            unconfirmed.add(identity)
            fresh_unconfirmed += identity in fresh_ids
            continue
        if not isinstance(evidence, dict) or str(evidence.get("id")) != snapshot[0] or evidence.get("archived") is not True:
            counts.record_error(snapshot[0], "deal: missing from HubSpot but deletion not confirmed")
            unconfirmed.add(identity)
            fresh_unconfirmed += identity in fresh_ids
    snapshots = {identity: snapshot for identity, snapshot in snapshots.items()
        if identity not in unconfirmed}
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
        problem = None
        if counts.errors:
            outcome = "failed" if counts.deals_written == 0 else "partial"
            problem = f"{outcome}: {counts.errors} record errors"
        await complete_scan(session, lease, error=problem)
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

    S23-PL1: never raises for a sync failure. Per-record problems land in
    ``record_errors``; a run that cannot continue sets ``fatal_error`` (phase
    and reason). The caller (:func:`app.services.hubspot_sync_runs.run_deal_sync`)
    turns both into the run record and the exit status.
    """

    hub = client or HubSpotClient()
    factory = session_factory or default_session_factory
    run_started = datetime.now(UTC)
    correlation_id = f"hubspot:backfill:{run_started.isoformat()}"
    counts = BackfillCounts()

    lease = None
    after = None
    phase = "stage metadata"
    try:
        # S19 B1: sync pipeline / stage mirror before any deal upsert. The map
        # feeds every _upsert_opportunity so label / closed flags are resolved
        # from the same source every time. S23-PL1: without a map nothing can be
        # written safely, so a failed refresh is fatal; one bad stage is not.
        async with factory() as session:
            stage_map: StageMap = await sync_stage_mirror(session, hub)
            await touch_source(
                session,
                source="hubspot_pipeline_mirror",
                success=not stage_map.errors,
                error=f"{len(stage_map.errors)} stage errors" if stage_map.errors else None,
            )
            await session.commit()
        for error in stage_map.errors:
            counts.record_error(error["hubspot_id"], error["reason"])

        # S20 W1 D2 — refresh owner mirror (active + archived). Display-only:
        # a failed owner list is recorded and the deals still sync.
        phase = "owner mirror"
        async with factory() as session:
            owner_counts = await sync_owner_mirror(session, hub)
            counts.owners_mirror_active = owner_counts.active_seen
            counts.owners_mirror_archived = owner_counts.archived_seen
            await session.commit()
        if owner_counts.errors:
            counts.record_error("owners", "owner mirror: owner list fetch failed")

        # S20 W1 D10 — discover the Business Unit custom property. A failed or
        # unusable discovery is recorded; deals keep the stored mapping, and
        # the writer never clears a value it did not observe.
        phase = "business unit property"
        business_unit: BusinessUnitSelection | None = None
        try:
            async with factory() as session:
                discovery = await discover_business_unit(session, hub)
                counts.business_unit_property_found = discovery.found
                if discovery.availability_state not in {"configured", "absent"}:
                    counts.record_error("business_unit",
                        f"business unit property: {discovery.availability_state}"[:120])
                await session.commit()
        except Exception as error:
            if _systemic(error):
                raise
            log.exception("hubspot_bu_discovery_failed")
            counts.record_error("business_unit", f"business unit property: {short_reason(error)}")
        async with factory() as session:
            business_unit = await _business_unit_selection(session)

        phase = "deal scan"
        if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 100:
            raise ValueError("HubSpot page size must be between 1 and 100")
        additional = business_unit.properties("deal") if business_unit else ()
        context = {"schema_version": 1, **hub.scan_scope(), "page_size": page_size,
            "properties": [*HubSpotClient._DEAL_PROPERTIES.split(","), *additional],
            "mapping": asdict(business_unit) if business_unit else None,
            "coverage_mode": "all_active_deals_with_explicit_archive_revalidation"}
        async with factory() as session:
            lease = await acquire_scan(session, source="hubspot_backfill", context=context,
                max_resume_age=SCAN_RESUME_MAX_AGE)
            counts.scan_generation = lease.generation
            await session.commit()
        after = lease.cursor
        while lease.phase != "finalizing":
            page = await hub.list_deals_page(after=after, limit=page_size, **(
                {"additional_properties": additional} if additional else {}))
            results, next_after = _validate_page(page, after)
            page_counts = BackfillCounts()
            fetched = await _fetch_dependencies(hub, results, business_unit, page_counts)
            async with factory() as session:
                await _owned_scan(session, lease, {"scanning"})
                await _assert_mapping(session, business_unit)
                for payload in results:
                    await _sync_one_deal(session, fetched, payload, page_counts, correlation_id,
                        stage_map, business_unit, lease.generation)
                await _assert_mapping(session, business_unit)
                await checkpoint_scan(session, lease, expected_cursor=after, next_cursor=next_after)
                await session.commit()
            _merge_counts(counts, page_counts)
            if next_after is None:
                break
            after = next_after
        phase = "archive check"
        counts.deals_archived = await _finalize_scan(factory, hub, lease, correlation_id,
            business_unit, counts)
        counts.scan_completed = True
    except Exception as error:
        counts.errors += 1
        counts.fatal_error = f"{phase}: {short_reason(error)}"[:255]
        log.exception("hubspot_backfill_failed", generation=counts.scan_generation, after=after,
            phase=phase)
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
            except Exception:
                scope = None
            if scope is not None:
                async with factory() as session:
                    await record_scan_attempt_failure(session, source="hubspot_backfill",
                        scope=scope, error=type(error).__name__)
                    await session.commit()

    summary = {k: v for k, v in counts.as_dict().items() if isinstance(v, (int, bool))}
    if counts.fatal_error:
        log.error("hubspot_backfill_stopped", **summary, fatal_error=counts.fatal_error)
    elif counts.errors:
        log.warning("hubspot_backfill_completed_with_errors", **summary)
    else:
        log.info("hubspot_backfill_complete", **summary)
    return counts


async def _sync_one_deal(session: AsyncSession, fetched: _FetchedPage, payload: dict,
                         page_counts: BackfillCounts, correlation_id: str,
                         stage_map: StageMap, business_unit: BusinessUnitSelection | None,
                         generation: int) -> None:
    """Write one deal inside its own SAVEPOINT (S23-PL1 item 4).

    A failure rolls back only this deal, is listed with its HubSpot id, and the
    page continues. The row (if it exists) is still marked seen in this
    generation: HubSpot listed it, so the archive pass must not treat it as
    deleted.
    """
    deal_id = _extract_deal_id(payload)
    blocked = fetched.blocking_reason(payload)
    if blocked is not None:
        page_counts.deals_seen += 1
        page_counts.error_deal_ids.append(deal_id)
        page_counts.record_error(deal_id, f"deal: {blocked}")
    else:
        deal_counts = BackfillCounts()
        try:
            async with session.begin_nested():
                await _process_deal(session, fetched, payload, deal_counts, correlation_id,
                    stage_map=stage_map, business_unit=business_unit)
        except ScanConflict:
            raise
        except Exception as error:
            if _systemic(error):
                raise
            page_counts.deals_seen += 1
            page_counts.error_deal_ids.append(deal_id)
            page_counts.record_error(deal_id, f"deal: {short_reason(error)}")
            log.warning("hubspot_deal_record_refused", deal_id=deal_id, reason=short_reason(error))
        else:
            _merge_counts(page_counts, deal_counts)
    row = await session.scalar(select(Opportunity).where(Opportunity.hubspot_deal_id == deal_id))
    if row is not None:
        row.hubspot_seen_generation = max(row.hubspot_seen_generation or 0, generation)
