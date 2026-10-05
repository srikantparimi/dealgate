"""Publish frozen delivery staffing independently of deleted commercial parents."""
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.models.client import Client
from app.models.people_demand import DemandLine, DemandPublication, DemandPublicationVersion
from app.models.project import Project
from app.services.forecast_plans import _digest, runtime
from app.services.people_demand import DEMAND_READ, _project_lines, _result, _save_publication
from app.services.project_source import project_scope_allowed
from app.services.test_fixtures import is_test_user


class PublishProjectDemandInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: uuid.UUID
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


async def publish_project_demand(session, *, actor, body: PublishProjectDemandInput, commit=True):
    if not set(actor.groups) & {"Delivery", "SystemAdmin"}:
        raise HTTPException(403, "Delivery demand publication permission required")
    project = await session.scalar(select(Project).where(Project.id == body.project_id)
        .with_for_update().execution_options(populate_existing=True))
    if project is None or project.archived_at is not None or not await project_scope_allowed(
        session, actor=actor, project=project):
        raise HTTPException(404, "Delivery planning source unavailable")
    scope = project.baseline_snapshot_json["source_scope"]
    tenant, environment = runtime()
    publication = await session.scalar(select(DemandPublication).where(
        DemandPublication.project_id == project.id, DemandPublication.tenant_id == tenant,
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
    if str(body.expected_source_version_id) != scope["gm_model_id"]:
        raise HTTPException(409, "Delivery source changed; refresh before publishing")
    prior = await session.scalar(select(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == publication.id)
        .order_by(DemandPublicationVersion.version.desc()).limit(1)) if publication else None
    if (prior.id if prior else None) != body.expected_publication_version_id:
        raise HTTPException(409, "Demand publication changed; refresh before publishing")
    projected = await _project_lines(session, actor=actor,
        inputs=project.baseline_snapshot_json["commercial_inputs"], prior=prior, changes=body.enrichments)
    if publication is None:
        publication = DemandPublication(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
            test_fixture=is_test_user(actor), project_id=project.id,
            account_id=project.client_id, owner_id=uuid.UUID(scope["owner_id"]))
        session.add(publication)
        await session.flush()
    row = DemandPublicationVersion(id=uuid.uuid4(), publication_id=publication.id,
        version=prior.version + 1 if prior else 1, source_version=scope["gm_model_id"],
        source_hash=scope["source_hash"], request_key=body.request_key, request_hash=digest,
        source_metadata={"title": project.title, "lifecycle": "committed", "selected": True,
            "probability": "1", "account_id": scope["account_id"], "owner_id": scope["owner_id"],
            "source_revision": 1, "schema_version": "people-demand-v1"},
        missing=projected["missing"], reason=body.reason, created_by=actor.id)
    return await _save_publication(session, actor=actor, body=body, publication=publication,
        row=row, prior=prior, projected=projected, commit=commit)


async def project_sources(session, *, actor, portfolio, named, source_id=None):
    tenant, environment = runtime()
    organizational = bool(set(actor.groups) & (DEMAND_READ - {"Sales", "SalesLeader"}))
    query = select(Project).where(Project.archived_at.is_(None))
    if source_id is not None:
        query = query.where(Project.id == source_id)
    projects = (await session.scalars(query.order_by(Project.id))).all()
    items = []
    for project in projects:
        if not await project_scope_allowed(session, actor=actor, project=project):
            continue
        scope = project.baseline_snapshot_json["source_scope"]
        if portfolio and not organizational and scope["owner_id"] != str(actor.id):
            continue
        published = await session.scalar(select(DemandPublicationVersion).join(DemandPublication,
            DemandPublicationVersion.publication_id == DemandPublication.id).where(
                DemandPublication.project_id == project.id, DemandPublication.tenant_id == tenant,
                DemandPublication.environment == environment, DemandPublication.test_fixture == is_test_user(actor))
            .order_by(DemandPublicationVersion.version.desc()).limit(1))
        state = "pending" if published is None else "current" if (
            published.source_version == scope["gm_model_id"] and published.source_hash == scope["source_hash"]
        ) else "stale"
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
                if named or set(actor.groups) & {"HR", "SystemAdmin"}:
                    item["retained_person_ids"] = line.retained_person_ids
                lines.append(item)
        account = await session.get(Client, uuid.UUID(scope["account_id"]))
        items.append({"source_id": str(project.id), "source_kind": "project", "plan_id": None,
            "project_id": str(project.id), "account_id": scope["account_id"], "owner_id": scope["owner_id"],
            "account_name": account.name if account else (project.retained_source or {}).get("client_name"),
            "source_url": f"/people/demand#demand-{project.id}", "title": project.title,
            "source_version_id": scope["gm_model_id"], "source_revision": 1,
            "lifecycle": "committed", "selected": True, "probability": "1",
            "publication_id": str(published.publication_id) if published else None,
            "publication_version_id": str(published.id) if published else None,
            "state": state, "missing": published.missing if state == "current" else ["current_source_publication"],
            "lines": lines})
    return items
