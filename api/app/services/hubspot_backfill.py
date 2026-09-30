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
from app.services.hubspot_stage_mirror import StageMap, sync_stage_mirror

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

    def as_dict(self) -> dict[str, int | list[str]]:
        return asdict(self)


def _extract_deal_id(deal_payload: dict) -> str:
    did = deal_payload.get("id") or (deal_payload.get("properties") or {}).get("hs_object_id")
    if did is None:
        raise ValueError("deal payload missing id")
    return str(did)


async def _archive_missing(
    session: AsyncSession, seen_ids: set[str], correlation_id: str, run_started: datetime
) -> int:
    """Any HubSpot-sourced, non-archived opportunity we didn't see gets archived.

    The nightly reconcile job also drives this, so backfill archiving is
    the initial pass; incremental drift is caught later.
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
            after={"archived_at": run_started.isoformat(), "reason": "hubspot_deleted"},
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
    """Full backfill entry point. Called by the router and the smoke script."""

    hub = client or HubSpotClient()
    factory = session_factory or default_session_factory
    run_started = datetime.now(UTC)
    correlation_id = f"hubspot:backfill:{run_started.isoformat()}"
    counts = BackfillCounts()
    seen_ids: set[str] = set()

    # S19 B1: sync pipeline / stage mirror before any deal upsert. The map
    # feeds every _upsert_opportunity so label / closed flags are resolved
    # from the same source every time.
    stage_map: StageMap | None = None
    try:
        async with factory() as session:
            stage_map = await sync_stage_mirror(session, hub)
            await session.commit()
    except Exception:
        log.exception("hubspot_stage_mirror_sync_failed")
        # A stage-map failure isn't fatal — intake falls back to the naked
        # stage id (mapper bug degrades gracefully). Continue but count the
        # error.
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

    # S18 §2 · F8 backend half — a partial run must never archive stale
    # rows. If pagination failed OR any deal errored we skip the sweep so
    # a HubSpot outage cannot mass-archive deals we simply didn't reach.
    # The nightly reconcile (later slice) still catches drift on the next
    # healthy pass.
    if pagination_ok and counts.errors == 0:
        async with factory() as session:
            counts.deals_archived = await _archive_missing(
                session, seen_ids, correlation_id, run_started
            )
            await session.commit()
    else:
        log.warning(
            "hubspot_backfill_skipping_archive_sweep",
            errors=counts.errors,
            pagination_ok=pagination_ok,
        )

    log.info("hubspot_backfill_complete", **{k: v for k, v in counts.as_dict().items() if isinstance(v, int)})
    return counts
