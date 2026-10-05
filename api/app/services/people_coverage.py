"""Immutable, explicitly reviewed staffing replacement between published sources."""
import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator
from sqlalchemy import select

from app.audit import append_audit
from app.gm.demand import Demand
from app.gm.demand_coverage import DemandCoverage, validate_coverage
from app.models.forecast import ForecastPlan
from app.models.people_coverage import DemandCoverageRoot, DemandCoverageVersion
from app.models.people_demand import DemandPublication, DemandPublicationVersion
from app.models.project import Project
from app.services.forecast_plans import _digest, runtime
from app.services.people_demand import DEMAND_READ, _source_rows
from app.services.project_source import project_scope_allowed
from app.services.test_fixtures import is_test_user


class MappingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_line_key: str = Field(min_length=1)
    project_line_key: str = Field(min_length=1)
    plan_slots: list[StrictInt] = Field(min_length=1, max_length=10000)
    project_slots: list[StrictInt] = Field(min_length=1, max_length=10000)
    start_date: date
    end_date: date


class CoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_publication_id: uuid.UUID
    project_publication_id: uuid.UUID
    expected_plan_version_id: uuid.UUID
    expected_project_version_id: uuid.UUID
    expected_mapping_version_id: uuid.UUID | None
    request_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)
    mappings: list[MappingInput] = Field(max_length=1000)

    @field_validator("request_key", "reason")
    @classmethod
    def normalized(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit normalized value required")
        return value


def _scope(actor):
    tenant, environment = runtime()
    return dict(tenant_id=tenant, environment=environment, test_fixture=is_test_user(actor))


def line_demand(source, line):
    return Demand(id=line["demand_key"], account_id=source["account_id"], role=line["role"],
        skills=tuple(line["skills"]), level=line["level"], location=line["location"], timezone=line["timezone"],
        quantity=line["quantity"], allocation=Decimal(line["allocation"]),
        start=date.fromisoformat(line["start_date"]), end=date.fromisoformat(line["end_date"]),
        probability=Decimal(source["probability"]) if source["probability"] is not None else None,
        lifecycle=source["lifecycle"], selected=source["selected"],
        retained_person_ids=tuple(line["retained_person_ids"]))


def _mappings(plan, project, mappings):
    plans = {line["line_key"]: line for line in plan["lines"]}
    projects = {line["line_key"]: line for line in project["lines"]}
    return tuple(DemandCoverage(plans[row["plan_line_key"]]["demand_key"],
        projects[row["project_line_key"]]["demand_key"], tuple(row["plan_slots"]), tuple(row["project_slots"]),
        date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])) for row in mappings)


async def _latest(session, root):
    return await session.scalar(select(DemandCoverageVersion).where(DemandCoverageVersion.root_id == root.id)
        .order_by(DemandCoverageVersion.revision.desc()).limit(1)) if root else None


async def _historical_project_allowed(session, actor, publication_id):
    publication = await session.scalar(select(DemandPublication).filter_by(id=publication_id, **_scope(actor)))
    if publication is None or publication.project_id is None:
        return False
    if not set(actor.groups) & (DEMAND_READ - {"Sales", "SalesLeader"}) and publication.owner_id != actor.id:
        return False
    project = await session.get(Project, publication.project_id)
    return bool(project and await project_scope_allowed(session, actor=actor, project=project))


def _fresh(root, row, sources):
    plan, project = sources.get(str(root.plan_publication_id)), sources.get(str(root.project_publication_id))
    return bool(plan and project and plan["state"] == project["state"] == "current"
        and plan["publication_version_id"] == str(row.plan_version_id)
        and project["publication_version_id"] == str(row.project_version_id))


def _result(root, row, sources):
    return dict(id=str(root.id), version_id=str(row.id), revision=row.revision,
        plan_publication_id=str(root.plan_publication_id), project_publication_id=str(root.project_publication_id),
        plan_version_id=str(row.plan_version_id), project_version_id=str(row.project_version_id),
        mappings=row.mappings, reason=row.reason, created_by=str(row.created_by), created_at=row.created_at.isoformat(),
        state="current" if _fresh(root, row, sources) else "stale", is_reservation=False)


async def allocation_coverage(session, *, actor, sources, replacing=None):
    """Resolve global mappings before display filtering; stale maps are never rebound."""
    indexed = {row["publication_id"]: row for row in sources if row["publication_id"]}
    roots = (await session.scalars(select(DemandCoverageRoot).filter_by(**_scope(actor))
        .order_by(DemandCoverageRoot.id))).all()
    mappings, missing, versions = [], [], []
    for root in roots:
        if root.id == replacing:
            continue
        row = await _latest(session, root)
        if row is None:
            continue
        versions.append(str(row.id))
        if not row.mappings:
            continue
        if not _fresh(root, row, indexed):
            missing.append("staffing_coverage_stale")
            continue
        try:
            mappings.extend(_mappings(indexed[str(root.plan_publication_id)],
                indexed[str(root.project_publication_id)], row.mappings))
        except (KeyError, ValueError, TypeError):
            missing.append("staffing_coverage_invalid")
    return tuple(mappings), sorted(set(missing)), versions


async def save_coverage(session, *, actor, body: CoverageInput):
    if not set(actor.groups) & {"Delivery", "SystemAdmin"}:
        raise HTTPException(403, "Staffing coverage requires Delivery or SystemAdmin")
    publications = []
    # Match publisher lock order, including the source lock, before testing CAS.
    for identifier, kind, model in ((body.plan_publication_id, "plan_id", ForecastPlan),
            (body.project_publication_id, "project_id", Project)):
        publication = await session.scalar(select(DemandPublication).filter_by(id=identifier, **_scope(actor)))
        if publication is None or getattr(publication, kind) is None:
            raise HTTPException(404, "Staffing publication unavailable")
        await session.scalar(select(model).where(model.id == getattr(publication, kind))
            .with_for_update().execution_options(populate_existing=True))
        await session.scalar(select(DemandPublication).where(DemandPublication.id == identifier).with_for_update())
        publications.append(publication)
    population = (await _source_rows(session, actor=actor, portfolio=False, named=True))["items"]
    sources = {row["publication_id"]: row for row in population if row["publication_id"]}
    plan, project = sources.get(str(body.plan_publication_id)), sources.get(str(body.project_publication_id))
    root = await session.scalar(select(DemandCoverageRoot).filter_by(**_scope(actor),
        plan_publication_id=body.plan_publication_id, project_publication_id=body.project_publication_id).with_for_update())
    if plan is None or (project is None and (body.mappings or root is None
        or not await _historical_project_allowed(session, actor, body.project_publication_id))):
        raise HTTPException(404, "Staffing source unavailable")
    digest = _digest(body.model_dump(mode="json"))
    if root:
        replay = await session.scalar(select(DemandCoverageVersion).filter_by(root_id=root.id, request_key=body.request_key))
        if replay:
            if replay.request_hash != digest or replay.created_by != actor.id:
                raise HTTPException(409, "Coverage request key belongs to different inputs or actor")
            result = _result(root, replay, sources)
            await session.commit()
            return result
    prior = await _latest(session, root)
    if (prior.id if prior else None) != body.expected_mapping_version_id:
        raise HTTPException(409, "Staffing coverage changed; reload before saving")
    if body.mappings and (plan["state"] != "current" or project["state"] != "current"
        or plan["publication_version_id"] != str(body.expected_plan_version_id)
        or project["publication_version_id"] != str(body.expected_project_version_id)):
        raise HTTPException(409, "Staffing publication changed; reload before saving")
    if not body.mappings:
        if root is None:
            raise HTTPException(422, "Existing staffing coverage is required to clear it")
        # Clearing adds no staffing assertion; historical source versions suffice,
        # but they must belong to these exact authorized publication roots.
        for identifier, publication_id in ((body.expected_plan_version_id, body.plan_publication_id),
                (body.expected_project_version_id, body.project_publication_id)):
            version = await session.get(DemandPublicationVersion, identifier)
            if version is None or version.publication_id != publication_id:
                raise HTTPException(409, "Coverage source version does not belong to this publication")
    wire = [row.model_dump(mode="json") for row in body.mappings]
    existing, _, _ = await allocation_coverage(session, actor=actor, sources=population,
        replacing=root.id if root else None)
    try:
        if wire:
            demands = tuple(line_demand(source, line) for source in population if source["state"] == "current"
                for line in source["lines"] if not line["missing"])
            validate_coverage(demands, existing + _mappings(plan, project, wire))
    except (KeyError, ValueError, TypeError, ArithmeticError) as error:
        raise HTTPException(422, f"Invalid staffing coverage: {error}") from error
    if root is None:
        root = DemandCoverageRoot(id=uuid.uuid4(), **_scope(actor), plan_publication_id=body.plan_publication_id,
            project_publication_id=body.project_publication_id)
        session.add(root)
        await session.flush()
    row = DemandCoverageVersion(id=uuid.uuid4(), root_id=root.id, revision=prior.revision + 1 if prior else 1,
        plan_version_id=body.expected_plan_version_id, project_version_id=body.expected_project_version_id,
        mappings=wire, request_key=body.request_key, request_hash=digest, reason=body.reason, created_by=actor.id)
    session.add(row)
    await session.flush()
    await append_audit(session, actor_id=actor.id, action="people.staffing_coverage_revised", entity="demand_coverage",
        entity_id=str(root.id), before={"version_id": str(prior.id)} if prior else None,
        after={"version_id": str(row.id), "revision": row.revision, "reason": body.reason}, correlation_id=body.request_key)
    result = _result(root, row, sources)
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"coverage:{row.id}")
    await session.commit()
    return result


async def list_coverage(session, *, actor, plan_publication_id, root_id=None, page=1, size=50):
    sources = {row["publication_id"]: row for row in
        (await _source_rows(session, actor=actor, named=False))["items"] if row["publication_id"]}
    if str(plan_publication_id) not in sources or sources[str(plan_publication_id)]["source_kind"] != "plan":
        raise HTTPException(404, "Staffing plan unavailable")
    query = select(DemandCoverageRoot).filter_by(**_scope(actor), plan_publication_id=plan_publication_id)
    if root_id:
        query = query.where(DemandCoverageRoot.id == root_id)
    roots = (await session.scalars(query.order_by(DemandCoverageRoot.id))).all()
    items, current = [], None
    for root in roots:
        if str(root.project_publication_id) not in sources and not await _historical_project_allowed(
            session, actor, root.project_publication_id):
            continue
        latest = await _latest(session, root)
        if latest is None:
            continue
        if root_id:
            current = str(latest.id)
            rows = (await session.scalars(select(DemandCoverageVersion).where(DemandCoverageVersion.root_id == root.id)
                .order_by(DemandCoverageVersion.revision.desc()).offset((page - 1) * size).limit(size))).all()
        else:
            rows = [latest]
        items.extend(_result(root, row, sources) for row in rows)
    if not root_id:
        items = items[(page - 1) * size:page * size]
    return dict(items=items, current_version_id=current, is_reservation=False)
