"""S23-PL2 B3 — the HubSpot region value → business unit map, as Settings edits it.

Deals carry HubSpot region values ("US", "South Africa", ...). Deal rows join
``hubspot_region_map`` at read time, so replacing the map here changes every
deal's business unit immediately, with no resync. Settings also lists the
region values that appear on live deals but have no row yet, with their deal
counts, so an admin can map them.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.auth import AuthUser
from app.models.client import Client
from app.models.hubspot_region_map import BUSINESS_UNITS, HubspotRegionMap
from app.models.opportunity import Opportunity
from app.services.hubspot_pipeline import (
    PipelineFilters,
    _base_opportunity_filter,
    _effective_bu_column,
    scope_pipeline_filters,
)

MAX_VALUE, MAX_REGION, MAX_NOTE = 255, 64, 128


@dataclass(frozen=True)
class RegionRow:
    hubspot_value: str
    business_unit: str
    region: str
    note: str | None


def _ordered(rows: list[RegionRow]) -> list[RegionRow]:
    return sorted(rows, key=lambda r: (r.hubspot_value.casefold(), r.hubspot_value))


async def load_region_map(session: AsyncSession) -> list[RegionRow]:
    rows = (
        await session.execute(
            select(
                HubspotRegionMap.hubspot_value,
                HubspotRegionMap.business_unit,
                HubspotRegionMap.region,
                HubspotRegionMap.note,
            )
        )
    ).all()
    return _ordered([RegionRow(*row) for row in rows])


async def unmapped_region_counts(
    session: AsyncSession, actor: AuthUser, mapped: set[str]
) -> tuple[list[dict[str, Any]], int]:
    """Region values on live, visible deals (any status) that no map row covers.

    Returns ``([{hubspot_value, deals}], deals_without_region)``: the deal
    count per unmapped value, most deals first, and separately the number of
    deals that carry no region at all.
    """

    filters = await scope_pipeline_filters(
        session, actor, PipelineFilters(include_closed=True, open_closed="any")
    )
    values = (
        await session.scalars(
            select(_effective_bu_column())
            .select_from(Opportunity)
            .join(Client, Client.id == Opportunity.client_id, isouter=True)
            .where(*_base_opportunity_filter(filters))
        )
    ).all()
    counts = Counter(values)
    without_region = counts.pop(None, 0)
    unmapped = [{"hubspot_value": value, "deals": n} for value, n in counts.items() if value not in mapped]
    unmapped.sort(key=lambda row: (-row["deals"], row["hubspot_value"].casefold()))
    return unmapped, without_region


async def region_map_view(session: AsyncSession, actor: AuthUser) -> dict[str, Any]:
    """The Settings → Business units payload."""

    rows = await load_region_map(session)
    unmapped, without_region = await unmapped_region_counts(
        session, actor, {row.hubspot_value for row in rows}
    )
    return {
        "rows": [asdict(row) for row in rows],
        "unmapped_on_deals": unmapped,
        "deals_without_region": without_region,
        "business_units": list(BUSINESS_UNITS),
    }


def _invalid(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


def clean_region_rows(rows_in: list[dict[str, Any]]) -> list[RegionRow]:
    """Trim and validate a submitted map; every message names the row it is about."""

    seen: set[str] = set()
    out: list[RegionRow] = []
    for raw in rows_in:
        value = str(raw.get("hubspot_value") or "").strip()
        if not value:
            raise _invalid("Each row needs the HubSpot value it maps.")
        if len(value) > MAX_VALUE:
            raise _invalid(f"A HubSpot value can be at most {MAX_VALUE} characters.")
        if value in seen:
            raise _invalid(f"“{value}” is mapped twice. Each HubSpot value maps to one business unit.")
        seen.add(value)
        business_unit = str(raw.get("business_unit") or "").strip()
        if business_unit not in BUSINESS_UNITS:
            raise _invalid(f"Choose ST21, IT Avalon or Retro Rabbit for “{value}”.")
        region = str(raw.get("region") or "").strip()
        if not region:
            raise _invalid(f"Enter the region shown beside {business_unit} for “{value}”.")
        if len(region) > MAX_REGION:
            raise _invalid(f"The region for “{value}” can be at most {MAX_REGION} characters.")
        note = str(raw.get("note") or "").strip() or None
        if note is not None and len(note) > MAX_NOTE:
            raise _invalid(f"The note for “{value}” can be at most {MAX_NOTE} characters.")
        out.append(RegionRow(value, business_unit, region, note))
    return _ordered(out)


async def replace_region_map(
    session: AsyncSession, *, actor_id: uuid.UUID, rows_in: list[dict[str, Any]]
) -> bool:
    """Replace every row in one transaction and audit it. False when nothing changed."""

    new_rows = clean_region_rows(rows_in)
    current = await load_region_map(session)
    if new_rows == current:
        return False
    now = datetime.now(UTC)
    await session.execute(delete(HubspotRegionMap))
    if new_rows:
        await session.execute(
            insert(HubspotRegionMap),
            [{**asdict(row), "updated_at": now, "updated_by": actor_id} for row in new_rows],
        )
    await append_audit(
        session,
        actor_id=actor_id,
        action="business_unit_map.replaced",
        entity="hubspot_region_map",
        entity_id="hubspot_region_map",
        before={"rows": [asdict(row) for row in current]},
        after={"rows": [asdict(row) for row in new_rows]},
    )
    return True
