"""Pipeline-qualified HubSpot stage metadata.

Deal outcomes follow provider probability, never labels or display order.
Validate the complete response and legacy global-ID bindings before writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
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
    """Qualified lookup; stage-only compatibility is allowed only when unique."""

    by_id: dict[str, StageInfo] = field(default_factory=dict)
    by_pipeline_stage: dict[tuple[str, str], StageInfo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.by_pipeline_stage:
            object.__setattr__(self, "by_pipeline_stage", {
                (info.pipeline_id, info.stage_id): info for info in self.by_id.values()
            })

    def resolve(self, stage_id: str | None, pipeline_id: str | None = None) -> StageInfo | None:
        if not stage_id:
            return None
        if pipeline_id is not None:
            return self.by_pipeline_stage.get((pipeline_id, stage_id))
        matches = [info for (pid, sid), info in self.by_pipeline_stage.items() if sid == stage_id]
        return matches[0] if len(matches) == 1 else None


def _classification(meta: Any) -> tuple[Decimal, bool]:
    if not isinstance(meta, dict) or isinstance(meta.get("probability"), bool):
        raise ValueError("stage_metadata_invalid_probability")
    try:
        probability = Decimal(str(meta.get("probability")))
    except (InvalidOperation, ValueError):
        raise ValueError("stage_metadata_invalid_probability") from None
    if not probability.is_finite() or not Decimal("0") <= probability <= Decimal("1"):
        raise ValueError("stage_metadata_invalid_probability")
    # NUMERIC(3,2) must never round an open probability into a closed outcome.
    if probability != probability.quantize(Decimal("0.01")):
        raise ValueError("stage_metadata_probability_exceeds_storage_precision")
    closed = probability in (Decimal("0"), Decimal("1"))
    if "isClosed" in meta:
        flag = meta["isClosed"]
        if isinstance(flag, str) and flag.lower() in ("true", "false"):
            flag = flag.lower() == "true"
        if type(flag) is not bool or flag != closed:
            raise ValueError("stage_metadata_contradictory_closed_classification")
    return probability, closed


def _identity_fields(raw: Any, prefix: str) -> tuple[str, str, int, bool]:
    if not isinstance(raw, dict):
        raise ValueError(f"{prefix}_invalid_object")
    identifier, label = raw.get("id"), raw.get("label")
    order, archived = raw.get("displayOrder"), raw.get("archived", False)
    if (not isinstance(identifier, str) or not identifier or len(identifier) > 32
            or not isinstance(label, str) or not label or len(label) > 255
            or type(order) is not int or type(archived) is not bool):
        raise ValueError(f"{prefix}_invalid_fields")
    return identifier, label, order, archived


def _validated(payload: Any) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("pipeline_metadata_invalid_response")
    pipelines = []
    seen_pipelines: set[str] = set()
    seen_stages: set[str] = set()
    for raw in payload["results"]:
        pid, label, order, archived = _identity_fields(raw, "pipeline_metadata")
        if pid in seen_pipelines:
            raise ValueError("pipeline_metadata_duplicate_identity")
        seen_pipelines.add(pid)
        if not isinstance(raw.get("stages"), list):
            raise ValueError("pipeline_metadata_invalid_stages")
        stages = []
        for stage in raw["stages"]:
            sid, stage_label, stage_order, stage_archived = _identity_fields(stage, "stage_metadata")
            if sid in seen_stages:
                raise ValueError(f"stage_identity_duplicate:{sid}")
            seen_stages.add(sid)
            try:
                probability, closed = _classification(stage.get("metadata"))
            except ValueError as exc:
                raise ValueError(f"{exc}:{pid}:{sid}") from None
            stages.append({"id": sid, "pipeline_id": pid, "label": stage_label,
                "display_order": stage_order, "archived": stage_archived,
                "probability": probability, "is_closed": closed})
        pipelines.append(({"id": pid, "label": label, "display_order": order, "archived": archived}, stages))
    return pipelines


def _snapshot(row: HubspotPipeline | HubspotStage) -> dict[str, Any]:
    value = {"label": row.label, "display_order": row.display_order, "archived": row.archived}
    if isinstance(row, HubspotStage):
        value.update(pipeline_id=row.pipeline_id, is_closed=row.is_closed,
            probability=str(row.probability.normalize()) if row.probability is not None else None)
    return value


async def _record_change(session: AsyncSession, row: HubspotPipeline | HubspotStage,
                         before: dict[str, Any] | None) -> None:
    after = _snapshot(row)
    if before != after:
        entity = "hubspot_stage" if isinstance(row, HubspotStage) else "hubspot_pipeline"
        await append_audit(session, actor_id=None, action=f"{entity}.metadata_changed",
            entity=entity, entity_id=row.id, before=before, after=after)


async def sync_stage_mirror(session: AsyncSession, client: HubSpotClient) -> StageMap:
    """Refresh atomically; callers commit or roll back metadata and audits."""
    pipelines = _validated(await client.list_pipelines())
    existing_stages = {row.id: row for row in (await session.scalars(
        select(HubspotStage).with_for_update().execution_options(populate_existing=True)
    )).all()}
    # During expansion id is still a global PK. Never silently move a stage.
    for _, stages in pipelines:
        for fields in stages:
            existing = existing_stages.get(fields["id"])
            if existing and existing.pipeline_id != fields["pipeline_id"]:
                raise ValueError(f"stage_identity_pipeline_conflict:{fields['id']}")
    now = datetime.now(UTC)
    for fields, stages in pipelines:
        row = await session.get(HubspotPipeline, fields["id"], populate_existing=True, with_for_update=True)
        before = _snapshot(row) if row else None
        if row is None:
            row = HubspotPipeline(**fields)
            session.add(row)
        else:
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = now
        await _record_change(session, row, before)
        for fields in stages:
            stage_row = existing_stages.get(fields["id"])
            before = _snapshot(stage_row) if stage_row else None
            if stage_row is None:
                stage_row = HubspotStage(**fields)
                session.add(stage_row)
                existing_stages[stage_row.id] = stage_row
            else:
                for key, value in fields.items():
                    setattr(stage_row, key, value)
                stage_row.updated_at = now
            await _record_change(session, stage_row, before)
    await session.flush()

    by_key = {}
    for row in existing_stages.values():
        try:
            probability, closed = _classification({"probability": row.probability, "isClosed": row.is_closed})
        except ValueError:
            log.warning("hubspot_stage_unresolved", pipeline_id=row.pipeline_id, stage_id=row.id)
            continue
        by_key[(row.pipeline_id, row.id)] = StageInfo(
            row.id, row.label, row.pipeline_id, row.display_order, closed,
            probability == Decimal("1"), probability == Decimal("0"), probability)
    by_id = {info.stage_id: info for info in by_key.values()}
    log.info("hubspot_stage_mirror_synced", pipelines=len(pipelines), total_mapped=len(by_key))
    return StageMap(by_id=by_id, by_pipeline_stage=by_key)
