"""Source-owned immutable demand publications; never reservations or hires."""
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.audit import append_audit
from app.gm.demand_source import project_staffing
from app.models.client import Client
from app.models.forecast import ForecastPlan, ForecastPlanVersion
from app.models.people_demand import DemandLine, DemandPublication, DemandPublicationVersion
from app.models.people_planning import PeopleSource, PeopleImportBatch, WorkforceVersion
from app.services.commercial_models import parse_component
from app.services.forecast_plans import _account_allowed, _digest, runtime
from app.services.test_fixtures import is_test_user


class PublishDemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: uuid.UUID
    expected_source_version_id: uuid.UUID
    expected_publication_version_id: uuid.UUID | None
    request_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)
    enrichments: dict[str, dict] = Field(default_factory=dict, max_length=1000)

    @field_validator("request_key", "reason")
    @classmethod
    def normalized(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit normalized value required")
        return value


def _result(row):
    return {"publication_id": str(row.publication_id), "version_id": str(row.id),
        "revision": row.version, "source_version_id": row.source_version,
        "missing": row.missing, "is_reservation": False}


async def _validate_continuity(session, *, actor, lines):
    for line in lines:
        try:
            canonical = [str(uuid.UUID(value)) for value in line["retained_person_ids"]]
        except (ValueError, TypeError) as error:
            raise HTTPException(422, "Continuity requires current workforce identities") from error
        if len(set(canonical)) != len(canonical):
            raise HTTPException(422, "Continuity requires distinct workforce identities")
        line["retained_person_ids"] = canonical
    retained = {person for line in lines for person in line["retained_person_ids"]}
    if not retained:
        return
    try:
        identities = {uuid.UUID(value) for value in retained}
    except (ValueError, TypeError) as error:
        raise HTTPException(422, "Continuity requires current workforce identities") from error
    tenant, environment = runtime()
    sources = (await session.scalars(select(PeopleSource).where(PeopleSource.tenant_id == tenant,
        PeopleSource.environment == environment, PeopleSource.test_fixture == is_test_user(actor)))).all()
    current = set()
    for source in sources:
        batch = await session.scalar(select(PeopleImportBatch.id).where(PeopleImportBatch.source_id == source.id)
            .order_by(PeopleImportBatch.revision.desc()).limit(1))
        if batch:
            current.update((await session.scalars(select(WorkforceVersion.person_id).where(
                WorkforceVersion.batch_id == batch, WorkforceVersion.person_id.in_(identities)))).all())
    if current != identities:
        raise HTTPException(422, "Continuity requires current workforce identities in this planning scope")


async def publish_plan_demand(session, *, actor, body: PublishDemandInput, commit=True):
    if not set(actor.groups) & {"Delivery", "SystemAdmin"}:
        raise HTTPException(403, "Delivery demand publication permission required")
    tenant, environment = runtime()
    # The source lock serializes publication creation as well as source edits.
    plan = await session.scalar(select(ForecastPlan).where(ForecastPlan.id == body.plan_id,
        ForecastPlan.tenant_id == tenant, ForecastPlan.environment == environment)
        .with_for_update().execution_options(populate_existing=True))
    if plan is None:
        raise HTTPException(404, "Planning source unavailable")
    if not await _account_allowed(session, actor, plan.account_id):
        raise HTTPException(403, "Source is outside the trusted planning scope")
    publication = await session.scalar(select(DemandPublication).where(
        DemandPublication.plan_id == plan.id, DemandPublication.tenant_id == tenant,
        DemandPublication.environment == environment,
        DemandPublication.test_fixture == is_test_user(actor)).with_for_update())
    digest = _digest(body.model_dump(mode="json"))
    if publication:
        replay = await session.scalar(select(DemandPublicationVersion).where(
            DemandPublicationVersion.publication_id == publication.id,
            DemandPublicationVersion.request_key == body.request_key))
        if replay:
            if replay.request_hash != digest or replay.created_by != actor.id:
                raise HTTPException(409, "Publication request key already has different inputs or actor")
            return _result(replay)
    source = await session.scalar(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == plan.id)
        .order_by(ForecastPlanVersion.version.desc()).limit(1))
    if source is None or source.id != body.expected_source_version_id:
        raise HTTPException(409, "Source version changed; refresh before publishing demand")
    prior = await session.scalar(select(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == publication.id)
        .order_by(DemandPublicationVersion.version.desc()).limit(1)) if publication else None
    if (prior.id if prior else None) != body.expected_publication_version_id:
        raise HTTPException(409, "Demand publication changed; refresh before publishing")
    projected = await _project_lines(session, actor=actor, inputs=source.component_inputs,
        prior=prior, changes=body.enrichments)
    if publication is None:
        publication = DemandPublication(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
            test_fixture=is_test_user(actor), plan_id=plan.id, account_id=plan.account_id, owner_id=plan.owner_id)
        session.add(publication)
        await session.flush()
    row = DemandPublicationVersion(id=uuid.uuid4(), publication_id=publication.id,
        version=prior.version + 1 if prior else 1, source_version=str(source.id),
        source_hash=_digest(source.component_inputs), request_key=body.request_key, request_hash=digest,
        source_metadata={"title": source.title, "lifecycle": source.lifecycle, "selected": source.selected,
            "probability": str(source.probability) if source.probability is not None else None,
            "account_id": str(plan.account_id), "owner_id": str(plan.owner_id),
            "source_revision": source.version, "schema_version": "people-demand-v1"},
        missing=projected["missing"], reason=body.reason, created_by=actor.id)
    return await _save_publication(session, actor=actor, body=body, publication=publication,
        row=row, prior=prior, projected=projected, commit=commit)


async def _project_lines(session, *, actor, inputs, prior, changes):
    try:
        component = parse_component(inputs)
        source_keys = {line["line_key"] for line in project_staffing(component)["lines"]}
        enrichments = {}
        if prior:
            for line in (await session.scalars(select(DemandLine).where(DemandLine.version_id == prior.id))).all():
                if line.line_key in source_keys:
                    enrichments[line.line_key] = {field: getattr(line, field) for field in (
                        "skills", "level", "retained_person_ids", "evidence")}
        for key, change in changes.items():
            previous = enrichments.get(key, {})
            evidence = change.get("evidence")
            evidence_valid = isinstance(evidence, list) and bool(evidence) and all(
                isinstance(item, str) and item.strip() for item in evidence)
            if any(change.get(field) and change[field] != previous.get(field) for field in (
                "skills", "level", "retained_person_ids")) and not evidence_valid:
                raise ValueError("Changed manual enrichment requires explicit evidence")
            enrichments[key] = previous | change
            if evidence_valid:
                enrichments[key]["evidence"] = list(dict.fromkeys((*previous.get("evidence", []), *evidence)))
        projected = project_staffing(component, enrichments)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    for line in projected["lines"]:
        for field, limit in {"component_id": 255, "assignment_id": 255, "role": 128,
            "level": 128, "location": 128, "timezone": 128, "delivery_model": 64}.items():
            if line[field] is not None and len(line[field]) > limit:
                raise HTTPException(422, f"Demand {field} exceeds {limit} characters")
    await _validate_continuity(session, actor=actor, lines=projected["lines"])
    return projected


async def _save_publication(session, *, actor, body, publication, row, prior, projected, commit=True):
    session.add(row)
    await session.flush()
    for line in projected["lines"]:
        # Canonical zero allocation denotes unresolved staffing, not zero demand.
        values = dict(line, location=line["location"] or "",
            allocation=line["allocation"] if line["allocation"] > 0 else None)
        session.add(DemandLine(version_id=row.id, **values))
    await append_audit(session, actor_id=actor.id, action="people.demand_published", entity="demand_publication",
        entity_id=str(publication.id), before={"version_id": str(prior.id)} if prior else None,
        after={"version_id": str(row.id), "source_version_id": row.source_version, "revision": row.version,
            "reason": body.reason, "missing": row.missing}, correlation_id=body.request_key)
    result = _result(row)
    if commit:
        from app.services.automation_jobs import enqueue_refresh
        await enqueue_refresh(session, actor=actor, event_key=f"publication:{row.id}")
        await session.commit()
    return result


DEMAND_READ = {"HR", "Delivery", "Finance", "CEO", "SystemAdmin", "Sales", "SalesLeader"}


async def demand_sources(session, *, actor):
    return await _source_rows(session, actor=actor)


async def _source_rows(session, *, actor, portfolio=True, named=False, source_id=None):
    if not set(actor.groups) & DEMAND_READ:
        raise HTTPException(403, "Demand planning permission required")
    tenant, environment = runtime()
    organizational = bool(set(actor.groups) & (DEMAND_READ - {"Sales", "SalesLeader"}))
    query = select(ForecastPlan).where(ForecastPlan.tenant_id == tenant, ForecastPlan.environment == environment)
    if source_id is not None:
        query = query.where(ForecastPlan.id == source_id)
    if portfolio and not organizational:
        query = query.where(ForecastPlan.owner_id == actor.id)
    plans = (await session.scalars(query.order_by(ForecastPlan.id))).all()
    items = []
    for plan in plans:
        if not await _account_allowed(session, actor, plan.account_id):
            continue
        source = await session.scalar(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == plan.id)
            .order_by(ForecastPlanVersion.version.desc()).limit(1))
        if source is None:
            continue
        published = await session.scalar(select(DemandPublicationVersion).join(DemandPublication,
            DemandPublicationVersion.publication_id == DemandPublication.id).where(
                DemandPublication.plan_id == plan.id, DemandPublication.tenant_id == tenant,
                DemandPublication.environment == environment, DemandPublication.test_fixture == is_test_user(actor))
            .order_by(DemandPublicationVersion.version.desc()).limit(1))
        state = "pending" if published is None else "current" if (
            published.source_version == str(source.id) and published.source_hash == _digest(source.component_inputs)) else "stale"
        lines = []
        if state == "current":
            for line in (await session.scalars(select(DemandLine).where(DemandLine.version_id == published.id)
                .order_by(DemandLine.line_key))).all():
                item = {key: getattr(line, key) for key in ("line_key", "component_id", "assignment_id", "role",
                    "skills", "level", "location", "timezone", "quantity", "delivery_model", "evidence", "missing")}
                item.update(allocation=format(line.allocation, "f") if line.allocation is not None else None,
                    demand_key=str(uuid.uuid5(published.publication_id, line.line_key)),
                    start_date=line.start_date.isoformat() if line.start_date else None,
                    end_date=line.end_date.isoformat() if line.end_date else None)
                # Named continuity belongs to HR, not a sales portfolio projection.
                if named or set(actor.groups) & {"HR", "SystemAdmin"}:
                    item["retained_person_ids"] = line.retained_person_ids
                lines.append(item)
        account = await session.get(Client, plan.account_id)
        items.append({"source_id": str(plan.id), "source_kind": "plan", "project_id": None,
            "plan_id": str(plan.id), "account_id": str(plan.account_id), "owner_id": str(plan.owner_id),
            "account_name": account.name if account else None,
            "source_url": f"/forecast?view=opportunities&account_id={plan.account_id}",
            "title": source.title, "source_version_id": str(source.id), "source_revision": source.version,
            "lifecycle": source.lifecycle, "selected": source.selected,
            "probability": str(source.probability) if source.probability is not None else None,
            "publication_id": str(published.publication_id) if published else None,
            "publication_version_id": str(published.id) if published else None,
            "state": state, "missing": published.missing if state == "current" else ["current_source_publication"],
            "lines": lines})
    from app.services.people_project_demand import project_sources
    items.extend(await project_sources(session, actor=actor, portfolio=portfolio, named=named, source_id=source_id))
    return {"items": items, "scope_label": "Company demand" if organizational else "My portfolio",
        "is_reservation": False, "schema_version": "people-demand-v1"}
