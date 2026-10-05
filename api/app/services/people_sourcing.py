"""Persist HR-reviewed lead times and source-bound, cost-free sourcing proposals."""
import uuid
from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.audit import append_audit
from app.gm.sourcing import prepare_sourcing, validate_rules
from app.models.forecast import ForecastPlan
from app.models.project import Project
from app.models.people_demand import DemandPublication, DemandPublicationVersion
from app.models.people_sourcing import SourcingDraft, SourcingDraftVersion, SourcingRuleSet, SourcingRuleVersion
from app.services.forecast_plans import _account_allowed, _digest, runtime
from app.services.people_allocation import demand_allocation
from app.services.people_demand import _source_rows
from app.services.test_fixtures import is_test_user
from app.services.project_source import project_scope_allowed


class ReasonedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("request_key", "reason")
    @classmethod
    def normalized(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit normalized value required")
        return value


class RulesInput(ReasonedInput):
    expected_version_id: uuid.UUID | None
    rules: list[dict] = Field(max_length=1000)

    @field_validator("rules")
    @classmethod
    def valid_rules(cls, value):
        return validate_rules(value)


class DraftInput(ReasonedInput):
    publication_id: uuid.UUID
    expected_demand_version_id: uuid.UUID
    expected_rule_version_id: uuid.UUID
    expected_draft_version_id: uuid.UUID | None


def _authorized(actor):
    if not set(actor.groups) & {"HR", "SystemAdmin"}:
        raise HTTPException(403, "Sourcing management requires HR or SystemAdmin")


def _scope(actor):
    tenant, environment = runtime()
    return dict(tenant_id=tenant, environment=environment, test_fixture=is_test_user(actor))


async def _root(session, actor, *, create=False):
    scope = _scope(actor)
    if create:
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        await session.execute(insert(SourcingRuleSet).values(id=uuid.uuid4(), **scope).on_conflict_do_nothing())
    query = select(SourcingRuleSet).filter_by(**scope)
    if create:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def _current_rules(session, root):
    return await session.scalar(select(SourcingRuleVersion).where(SourcingRuleVersion.rule_set_id == root.id)
        .order_by(SourcingRuleVersion.revision.desc()).limit(1)) if root else None


def _rules_result(row):
    if row is None:
        return {"state": "unconfigured", "id": None, "revision": None, "rules": []}
    return {"state": "configured", "id": str(row.id), "revision": row.revision, "rules": row.rules,
        "reason": row.reason, "created_by": str(row.created_by), "created_at": row.created_at.isoformat()}


async def get_rules(session, *, actor):
    _authorized(actor)
    return _rules_result(await _current_rules(session, await _root(session, actor)))


async def save_rules(session, *, actor, body: RulesInput):
    _authorized(actor)
    root = await _root(session, actor, create=True)
    digest = _digest(body.model_dump(mode="json"))
    replay = await session.scalar(select(SourcingRuleVersion).where(
        SourcingRuleVersion.rule_set_id == root.id, SourcingRuleVersion.request_key == body.request_key))
    if replay:
        if replay.request_hash != digest or replay.created_by != actor.id:
            raise HTTPException(409, "Rule request key belongs to different inputs or actor")
        result = _rules_result(replay)
        await session.commit()
        return result
    prior = await _current_rules(session, root)
    if (prior.id if prior else None) != body.expected_version_id:
        raise HTTPException(409, "Sourcing rules changed; reload before saving")
    row = SourcingRuleVersion(id=uuid.uuid4(), rule_set_id=root.id, revision=prior.revision + 1 if prior else 1,
        request_key=body.request_key, request_hash=digest, rules=body.rules, reason=body.reason, created_by=actor.id)
    session.add(row)
    await session.flush()
    await append_audit(session, actor_id=actor.id, action="people.sourcing_rules_revised", entity="sourcing_rule_set",
        entity_id=str(root.id), before={"version_id": str(prior.id)} if prior else None,
        after={"version_id": str(row.id), "revision": row.revision, "reason": body.reason}, correlation_id=body.request_key)
    result = _rules_result(row)
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"sourcing_rules:{row.id}")
    await session.commit()
    return result


def _draft_result(row):
    return {"id": str(row.id), "draft_id": str(row.draft_id), "revision": row.revision,
        "demand_version_id": str(row.demand_version_id), "rule_version_id": str(row.rule_version_id),
        "source_watermark": row.source_watermark, "snapshot": row.snapshot, "reason": row.reason,
        "created_by": str(row.created_by), "created_at": row.created_at.isoformat(), "is_reservation": False}


async def prepare_draft(session, *, actor, body: DraftInput, commit=True):
    _authorized(actor)
    publication = await session.scalar(select(DemandPublication).filter_by(id=body.publication_id, **_scope(actor)))
    if publication is None:
        raise HTTPException(404, "Published planning source unavailable")
    # Follow publication's source-lock ordering, then serialize this draft history.
    model = ForecastPlan if publication.plan_id else Project
    source_id = publication.plan_id or publication.project_id
    await session.execute(select(model.id).where(model.id == source_id).with_for_update())
    await session.execute(select(DemandPublication.id).where(DemandPublication.id == publication.id).with_for_update())
    if not await _publication_allowed(session, actor, publication):
        raise HTTPException(404, "Published planning source unavailable")
    draft = await session.scalar(select(SourcingDraft).where(SourcingDraft.publication_id == publication.id))
    digest = _digest(body.model_dump(mode="json"))
    if draft:
        replay = await session.scalar(select(SourcingDraftVersion).where(
            SourcingDraftVersion.draft_id == draft.id, SourcingDraftVersion.request_key == body.request_key))
        if replay:
            if replay.request_hash != digest or replay.created_by != actor.id:
                raise HTTPException(409, "Draft request key belongs to different inputs or actor")
            result = _draft_result(replay)
            if commit:
                await session.commit()
            return result
    prior = await session.scalar(select(SourcingDraftVersion).where(SourcingDraftVersion.draft_id == draft.id)
        .order_by(SourcingDraftVersion.revision.desc()).limit(1)) if draft else None
    if (prior.id if prior else None) != body.expected_draft_version_id:
        raise HTTPException(409, "Sourcing draft changed; reload before preparing")
    published = await session.scalar(select(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == publication.id).order_by(DemandPublicationVersion.version.desc()).limit(1))
    if published is None or published.id != body.expected_demand_version_id:
        raise HTTPException(409, "Published demand changed; reload before preparing")
    rules = await _current_rules(session, await _root(session, actor, create=True))
    if rules is None or rules.id != body.expected_rule_version_id:
        raise HTTPException(409, "Sourcing rules changed or are unconfigured")
    population = await _source_rows(session, actor=actor, source_id=source_id)
    source = next((item for item in population["items"] if item["source_id"] == str(source_id)), None)
    if source is None or source["state"] != "current":
        raise HTTPException(409, "Current source demand must be published before preparing sourcing")
    allocation = await demand_allocation(session, actor=actor, account_id=publication.account_id)
    try:
        result = prepare_sourcing(allocation["intervals"], rules.rules)
    except ValueError as error:
        raise HTTPException(422, f"Sourcing inputs require review: {error}") from error
    rows = [row for row in result["rows"] if row["source_id"] == str(source_id)]
    source_url = f"/people/demand#demand-{source_id}"
    for row in rows:
        row["source_url"] = source_url
    verified = await demand_allocation(session, actor=actor, account_id=publication.account_id)
    if allocation["source_watermark"] != verified["source_watermark"]:
        raise HTTPException(409, "Portfolio supply or demand changed while preparing sourcing")
    if draft is None:
        draft = SourcingDraft(id=uuid.uuid4(), publication_id=publication.id)
        session.add(draft)
        await session.flush()
    missing = sorted(set(source["missing"] + [gap for row in rows for gap in row["missing"]]
        + (["allocation_incomplete"] if not allocation["complete"] else [])))
    snapshot = jsonable_encoder({"rows": rows, "missing": missing, "complete": not missing,
        "title": source["title"], "probability": source["probability"], "lifecycle": source["lifecycle"],
        "source_version_id": source["source_version_id"], "source_url": source_url,
        "calculation_version": "sourcing-draft-v1", "is_reservation": False},
        custom_encoder={Decimal: str})
    row = SourcingDraftVersion(id=uuid.uuid4(), draft_id=draft.id, revision=prior.revision + 1 if prior else 1,
        demand_version_id=published.id, rule_version_id=rules.id, source_watermark=allocation["source_watermark"],
        request_key=body.request_key, request_hash=digest, snapshot=snapshot, reason=body.reason, created_by=actor.id)
    session.add(row)
    await session.flush()
    await append_audit(session, actor_id=actor.id, action="people.sourcing_draft_prepared", entity="sourcing_draft",
        entity_id=str(draft.id), before={"version_id": str(prior.id)} if prior else None,
        after={"version_id": str(row.id), "demand_version_id": str(published.id), "revision": row.revision,
            "reason": body.reason, "is_reservation": False}, correlation_id=body.request_key)
    result = _draft_result(row)
    if commit:
        await session.commit()
    return result


async def list_drafts(session, *, actor, publication_id, page=1, size=50):
    _authorized(actor)
    publication = await session.scalar(select(DemandPublication).filter_by(id=publication_id, **_scope(actor)))
    if publication is None or not await _publication_allowed(session, actor, publication):
        raise HTTPException(404, "Published planning source unavailable")
    draft = await session.scalar(select(SourcingDraft).where(SourcingDraft.publication_id == publication.id))
    if draft is None:
        return {"items": [], "current_version_id": None, "state": "missing"}
    current = await session.scalar(select(SourcingDraftVersion).where(SourcingDraftVersion.draft_id == draft.id)
        .order_by(SourcingDraftVersion.revision.desc()).limit(1))
    rules = await _current_rules(session, await _root(session, actor))
    allocation = await demand_allocation(session, actor=actor, account_id=publication.account_id)
    published = await session.scalar(select(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == publication.id).order_by(DemandPublicationVersion.version.desc()).limit(1))
    fresh = bool(current and published and rules and current.demand_version_id == published.id
        and current.rule_version_id == rules.id and current.source_watermark == allocation["source_watermark"])
    rows = (await session.scalars(select(SourcingDraftVersion).where(SourcingDraftVersion.draft_id == draft.id)
        .order_by(SourcingDraftVersion.revision.desc()).offset((page - 1) * size).limit(size))).all()
    return {"items": [_draft_result(row) for row in rows],
        "current_version_id": str(current.id) if current else None, "state": "current" if fresh else "stale"}


async def _publication_allowed(session, actor, publication):
    if publication.plan_id:
        return await _account_allowed(session, actor, publication.account_id)
    project = await session.get(Project, publication.project_id)
    return bool(project and project.archived_at is None and await project_scope_allowed(
        session, actor=actor, project=project))
