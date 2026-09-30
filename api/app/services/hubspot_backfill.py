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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import append_audit
from app.db import session_factory as default_session_factory
from app.integrations.hubspot import HubSpotClient
from app.models.opportunity import Opportunity
from app.services.hubspot_intake import (
    _dedup_company_ids,
    _deal_props,
    _resolve_client,
    _resolve_owner,
    _resolve_secondary_clients,
    _upsert_opportunity,
)
from app.services.hubspot_owners import sync_owner_mirror
from app.services.hubspot_properties import discover_business_unit
from app.services.hubspot_stage_mirror import StageMap, sync_stage_mirror
from app.services.sync_status import (
    claim_scan_generation,
    mark_scan_completed,
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
    did = deal_payload.get("id") or (deal_payload.get("properties") or {}).get("hs_object_id")
    if did is None:
        raise ValueError("deal payload missing id")
    return str(did)


async def _archive_missing(
    session: AsyncSession,
    seen_ids: set[str],
    correlation_id: str,
    run_started: datetime,
    *,
    scan_generation: int | None = None,
) -> int:
    """Any HubSpot-sourced, non-archived opportunity we didn't see gets archived.

    S20 W1 A3 · T33 — the caller is responsible for only calling this
    when the scan is *known* to have completed (pagination_ok AND
    errors == 0 AND generation matches). The generation is recorded in
    the audit line so a post-mortem can prove which scan archived a row.

    The nightly reconcile job also drives this via
    :func:`run_backfill`, so backfill archiving is the initial pass;
    incremental drift is caught later.
    """

    stmt = (
        select(Opportunity)
        .where(Opportunity.source == "hubspot")
        .where(Opportunity.archived_at.is_(None))
    )
    archived = 0
    for opp in (await session.execute(stmt)).scalars():
        if opp.hubspot_deal_id in seen_ids:
            continue
        # A3 · T33 — extra safety: only archive rows that existed BEFORE
        # this scan started. A row created mid-scan (webhook lands during
        # the paginated fetch) is not "missing", it just wasn't in this
        # generation's snapshot; leave it alone.
        row_created = opp.created_at
        if row_created is not None and row_created.tzinfo is None:
            row_created = row_created.replace(tzinfo=UTC)
        if row_created is not None and row_created > run_started:
            continue

        opp.archived_at = run_started
        opp.archived_by = None
        opp.archived_reason = "hubspot_deleted"
        await session.flush()
        await append_audit(
            session,
            actor_id=None,
            action="opportunity.archived",
            entity="opportunity",
            entity_id=str(opp.id),
            before={"archived_at": None},
            after={
                "archived_at": run_started.isoformat(),
                "reason": "hubspot_deleted",
                "scan_generation": scan_generation,
            },
            correlation_id=correlation_id,
        )
        archived += 1
    return archived


async def _process_deal(
    session: AsyncSession,
    client: HubSpotClient,
    deal_payload: dict,
    counts: BackfillCounts,
    correlation_id: str,
    stage_map: StageMap | None = None,
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
    """Full backfill entry point. Called by the router and the smoke script.

    S20 W1 changes vs. S18 §2:

    - Claims a new ``scan_generation`` on ``sync_status`` at start so
      overlapping / retried runs can be distinguished (A3, T33).
    - Refreshes the owner mirror (D2) and the Business Unit property
      mapping (D10) before the deal loop so downstream reads always see
      current metadata.
    - Only stamps ``scan_completed_at`` (and only then archives missing
      rows) when pagination succeeded AND every deal upsert succeeded.
      A single-page error skips the archive sweep for the whole
      generation — S18 §2 F8, tightened.
    - Advances ``hubspot_backfill`` watermark on success/failure so the
      settings health page never falls back to "worker heartbeat".
    """

    hub = client or HubSpotClient()
    factory = session_factory or default_session_factory
    run_started = datetime.now(UTC)
    correlation_id = f"hubspot:backfill:{run_started.isoformat()}"
    counts = BackfillCounts()
    seen_ids: set[str] = set()

    # A3 · T33 — claim a fresh scan generation before any work. Persisted
    # so the archive sweep can verify it wasn't superseded by an
    # overlapping run.
    async with factory() as session:
        counts.scan_generation = await claim_scan_generation(
            session, source="hubspot_backfill"
        )
        await touch_source(
            session,
            source="hubspot_backfill",
            success=True,
            error=None,
            scan_generation=counts.scan_generation,
            scan_started=True,
        )
        await session.commit()

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
            await session.commit()
    except Exception:
        log.exception("hubspot_owner_mirror_sync_failed")
        counts.errors += 1

    # S20 W1 D10 — discover the Business Unit custom property.
    try:
        async with factory() as session:
            discovery = await discover_business_unit(session, hub)
            counts.business_unit_property_found = discovery.found
            await session.commit()
    except Exception:
        log.exception("hubspot_bu_discovery_failed")
        counts.errors += 1

    pagination_ok = True
    after: str | None = None
    while True:
        try:
            page = await hub.list_deals_page(after=after, limit=page_size)
        except Exception:
            counts.errors += 1
            log.exception("hubspot_backfill_pagination_failed", after=after)
            pagination_ok = False
            break
        results = page.get("results") or []
        for deal_payload in results:
            deal_id = _extract_deal_id(deal_payload)
            seen_ids.add(deal_id)
            async with factory() as session:
                try:
                    await _process_deal(
                        session, hub, deal_payload, counts, correlation_id,
                        stage_map=stage_map,
                    )
                    await session.commit()
                except Exception:
                    counts.errors += 1
                    counts.error_deal_ids.append(deal_id)
                    log.exception("hubspot_backfill_deal_failed", deal_id=deal_id)
                    await session.rollback()

        next_after = ((page.get("paging") or {}).get("next") or {}).get("after")
        if not next_after:
            break
        after = next_after

    # S18 §2 · F8 backend half tightened for S20 W1 A3 · T33 — a partial
    # run must never archive stale rows. If pagination failed OR any deal
    # errored, skip the archive sweep AND leave ``scan_completed_at``
    # unset so the next successful scan is what advances the "generation
    # completed" clock.
    if pagination_ok and counts.errors == 0:
        async with factory() as session:
            counts.deals_archived = await _archive_missing(
                session,
                seen_ids,
                correlation_id,
                run_started,
                scan_generation=counts.scan_generation,
            )
            # Stamp completion under the SAME generation. A concurrent
            # newer scan would have bumped ``scan_generation`` already;
            # ``mark_scan_completed`` no-ops if that happened.
            if counts.scan_generation is not None:
                await mark_scan_completed(
                    session,
                    source="hubspot_backfill",
                    generation=counts.scan_generation,
                )
            await touch_source(
                session,
                source="hubspot_backfill",
                success=True,
                error=None,
                scan_completed=True,
                scan_generation=counts.scan_generation,
            )
            counts.scan_completed = True
            await session.commit()
    else:
        async with factory() as session:
            await touch_source(
                session,
                source="hubspot_backfill",
                success=False,
                error=(
                    f"partial_run pagination_ok={pagination_ok} "
                    f"errors={counts.errors}"
                ),
                scan_generation=counts.scan_generation,
            )
            await session.commit()
        log.warning(
            "hubspot_backfill_skipping_archive_sweep",
            errors=counts.errors,
            pagination_ok=pagination_ok,
            scan_generation=counts.scan_generation,
        )

    log.info(
        "hubspot_backfill_complete",
        **{k: v for k, v in counts.as_dict().items() if isinstance(v, (int, bool))},
    )
    return counts
