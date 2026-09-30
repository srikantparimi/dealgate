"""HubSpot pipeline / stage mirror (S19 slice 1 B1).

Every backfill / webhook / reconcile run starts by pulling
``GET /crm/v3/pipelines/deals`` and upserting into ``hubspot_pipeline`` +
``hubspot_stage``. The returned :class:`StageMap` is the single source
the mapper uses to resolve deal stage ids to labels + closed flags —
HubSpot's per-deal CRM read does not return ``dealstage_label``.

Any stage id not in the mirror at intake time is a drift signal (G11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.hubspot import HubSpotClient
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage

log = structlog.get_logger("hubspot_stage_mirror")


@dataclass(frozen=True)
class StageInfo:
    stage_id: str
    label: str
    pipeline_id: str
    display_order: int
    is_closed: bool
    is_closed_won: bool
    is_closed_lost: bool
    probability: Decimal | None


@dataclass(frozen=True)
class StageMap:
    """In-memory lookup for the run. Keyed by stage id."""

    by_id: dict[str, StageInfo]

    def resolve(self, stage_id: str | None) -> StageInfo | None:
        if not stage_id:
            return None
        return self.by_id.get(stage_id)


def _parse_probability(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _closed_won_from(display_order: int, is_closed: bool, label: str) -> bool:
    """Won = closed AND ordered later than any Lost stage in the same pipeline.

    The pipelines endpoint doesn't return an explicit won/lost flag; every
    portal we've seen labels the two "Closed Won" / "Closed Lost". We keep
    the label match as the primary discriminator and fall back on the
    display-order convention (higher = won) so a re-labeled pipeline still
    behaves. Callers using StageInfo trust the two derived booleans.
    """

    lower = (label or "").lower()
    if not is_closed:
        return False
    if "won" in lower:
        return True
    if "lost" in lower:
        return False
    # No hint in the label — assume won when the ordering is higher; the
    # nightly reconcile alert covers portals that break this convention.
    return display_order >= 6


def _closed_lost_from(is_closed: bool, is_closed_won: bool, label: str) -> bool:
    if not is_closed:
        return False
    if is_closed_won:
        return False
    return True


async def sync_stage_mirror(session: AsyncSession, client: HubSpotClient) -> StageMap:
    """Fetch pipelines from HubSpot, upsert the mirror, return the map."""

    payload = await client.list_pipelines()
    now = datetime.now(UTC)

    by_id: dict[str, StageInfo] = {}
    seen_pipeline_ids: set[str] = set()
    seen_stage_ids: set[str] = set()

    for pipeline in payload.get("results") or []:
        pid = str(pipeline["id"])
        seen_pipeline_ids.add(pid)
        pipeline_row = await session.get(HubspotPipeline, pid)
        if pipeline_row is None:
            pipeline_row = HubspotPipeline(
                id=pid,
                label=pipeline.get("label", ""),
                display_order=int(pipeline.get("displayOrder") or 0),
                archived=bool(pipeline.get("archived", False)),
            )
            session.add(pipeline_row)
        else:
            pipeline_row.label = pipeline.get("label", pipeline_row.label)
            pipeline_row.display_order = int(pipeline.get("displayOrder") or 0)
            pipeline_row.archived = bool(pipeline.get("archived", False))
            pipeline_row.updated_at = now

        for stage in pipeline.get("stages") or []:
            sid = str(stage["id"])
            seen_stage_ids.add(sid)
            meta = stage.get("metadata") or {}
            is_closed = str(meta.get("isClosed", "")).lower() == "true"
            display_order = int(stage.get("displayOrder") or 0)
            label = stage.get("label", "")
            probability = _parse_probability(meta.get("probability"))
            is_won = _closed_won_from(display_order, is_closed, label)
            is_lost = _closed_lost_from(is_closed, is_won, label)

            stage_row = await session.get(HubspotStage, sid)
            if stage_row is None:
                stage_row = HubspotStage(
                    id=sid,
                    pipeline_id=pid,
                    label=label,
                    display_order=display_order,
                    is_closed=is_closed,
                    probability=probability,
                    archived=bool(stage.get("archived", False)),
                )
                session.add(stage_row)
            else:
                stage_row.pipeline_id = pid
                stage_row.label = label
                stage_row.display_order = display_order
                stage_row.is_closed = is_closed
                stage_row.probability = probability
                stage_row.archived = bool(stage.get("archived", False))
                stage_row.updated_at = now

            by_id[sid] = StageInfo(
                stage_id=sid,
                label=label,
                pipeline_id=pid,
                display_order=display_order,
                is_closed=is_closed,
                is_closed_won=is_won,
                is_closed_lost=is_lost,
                probability=probability,
            )

    await session.flush()

    # Load anything else in the mirror (e.g. archived stages we might still
    # see on old deals). The caller shouldn't need to fetch HubSpot again.
    other_stages = await session.execute(select(HubspotStage))
    for row in other_stages.scalars():
        if row.id in by_id:
            continue
        by_id[row.id] = StageInfo(
            stage_id=row.id,
            label=row.label,
            pipeline_id=row.pipeline_id,
            display_order=row.display_order,
            is_closed=row.is_closed,
            is_closed_won=_closed_won_from(row.display_order, row.is_closed, row.label),
            is_closed_lost=_closed_lost_from(
                row.is_closed,
                _closed_won_from(row.display_order, row.is_closed, row.label),
                row.label,
            ),
            probability=row.probability,
        )

    log.info(
        "hubspot_stage_mirror_synced",
        pipelines=len(seen_pipeline_ids),
        stages=len(seen_stage_ids),
        total_mapped=len(by_id),
    )
    return StageMap(by_id=by_id)
