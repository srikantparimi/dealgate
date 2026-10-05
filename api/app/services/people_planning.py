"""Managed cost-free supply imports. No reservation or hiring mutation surface."""
import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select

from app.audit import append_audit
from app.gm.demand import Capacity, Commitment, allocate_demand
from app.models.people_planning import PeopleSource, PeopleImportBatch, WorkforcePerson, WorkforceVersion, WorkforceInterval
from app.models.user import User
from app.services.forecast_plans import runtime
from app.services.test_fixtures import is_test_user


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IntervalInput(StrictInput):
    kind: Literal["gross", "committed", "reserved", "hired"]
    allocation: str = Field(max_length=128)
    start_date: date
    end_date: date
    assignment_key: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_interval(self):
        try:
            allocation = Decimal(self.allocation)
        except Exception as error:
            raise ValueError("Allocation must be an exact decimal string") from error
        if not allocation.is_finite() or not 0 < allocation <= 1:
            raise ValueError("Allocation must be in (0,1]")
        if allocation.as_tuple().exponent < -28:
            raise ValueError("Allocation supports at most 28 fractional decimal places")
        if self.end_date < self.start_date or self.end_date == date.max:
            raise ValueError("Invalid inclusive date interval")
        if self.kind == "gross":
            if self.assignment_key is not None:
                raise ValueError("Gross capacity is not an assignment")
        elif not self.assignment_key or not self.assignment_key.strip() or self.assignment_key != self.assignment_key.strip():
            raise ValueError("Commitments need a stable assignment key")
        return self


class PersonInput(StrictInput):
    person_key: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    role: str = Field(max_length=128)
    skills: list[str] = Field(max_length=100)
    level: str = Field(max_length=128)
    location: str = Field(max_length=128)
    timezone: str = Field(max_length=128)
    evidence: list[str] = Field(min_length=1, max_length=100)
    intervals: list[IntervalInput] = Field(max_length=500)

    @model_validator(mode="after")
    def validate_person(self):
        if any(not value.strip() or value != value.strip() for value in (self.person_key, self.display_name, *self.skills, *self.evidence)):
            raise ValueError("Identity and evidence keys must be nonblank and normalized")
        if len(set(self.skills)) != len(self.skills):
            raise ValueError("Duplicate skill keys")
        try:
            ZoneInfo(self.timezone)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("Explicit valid IANA timezone required") from error
        capacities, commitments = [], []
        for item in self.intervals:
            if item.kind == "gross":
                capacities.append(Capacity(self.person_key, self.role, tuple(self.skills), self.level,
                    self.location, self.timezone, Decimal(item.allocation), item.start_date, item.end_date))
            else:
                commitments.append(Commitment(self.person_key, item.assignment_key, Decimal(item.allocation),
                    item.start_date, item.end_date, item.kind))
        allocate_demand((), tuple(capacities), tuple(commitments), policy_version="validate-gross-import-v1")
        return self


class WorkforceImportInput(StrictInput):
    source_system: str = Field(min_length=1, max_length=128)
    request_key: str = Field(min_length=1, max_length=128)
    expected_previous_batch_id: uuid.UUID | None
    source_as_of: datetime
    reason: str = Field(min_length=1, max_length=2000)
    basis: Literal["gross_with_commitments"]
    people: list[PersonInput] = Field(max_length=10000)

    @field_validator("source_system", "request_key", "reason")
    @classmethod
    def nonblank(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit normalized value required")
        return value

    @field_validator("source_as_of")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Source observation requires a timezone")
        return value.astimezone(UTC)

    @field_validator("source_as_of", mode="before")
    @classmethod
    def explicit_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Source observation requires an explicit timezone-bearing timestamp")
        return value

    @model_validator(mode="after")
    def unique_people(self):
        if len({person.person_key for person in self.people}) != len(self.people):
            raise ValueError("Duplicate workforce person identity")
        return self


def _authorized(actor):
    if not set(actor.groups) & {"HR", "SystemAdmin"}:
        raise HTTPException(403, "Named workforce supply requires HR or SystemAdmin")


def _batch_result(batch):
    observed = batch.source_as_of
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    return {"id": str(batch.id), "revision": batch.revision, "person_count": batch.person_count,
        "source_as_of": observed.astimezone(UTC).isoformat(), "status": "committed"}


async def import_workforce(session, *, actor, body: WorkforceImportInput):
    _authorized(actor)
    tenant, environment = runtime()
    values = dict(tenant_id=tenant, environment=environment, source_system=body.source_system,
        test_fixture=is_test_user(actor))
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Workforce source locking requires PostgreSQL or SQLite")
    await session.execute(insert(PeopleSource).values(id=uuid.uuid4(), **values).on_conflict_do_nothing())
    source = (await session.execute(select(PeopleSource).filter_by(**values)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    digest = hashlib.sha256(json.dumps(body.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    replay = await session.scalar(select(PeopleImportBatch).where(
        PeopleImportBatch.source_id == source.id, PeopleImportBatch.request_key == body.request_key))
    if replay:
        if replay.request_hash != digest:
            raise HTTPException(409, "Import request key already has different content")
        result = _batch_result(replay)
        await session.commit()
        return result
    previous = await session.scalar(select(PeopleImportBatch).where(PeopleImportBatch.source_id == source.id)
        .order_by(PeopleImportBatch.revision.desc()).limit(1))
    if body.expected_previous_batch_id != (previous.id if previous else None):
        raise HTTPException(409, "Workforce source changed; reload its current snapshot")
    if previous:
        observed = previous.source_as_of
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if body.source_as_of < observed:
            raise HTTPException(409, "Source observation predates current workforce evidence")
    if body.source_as_of > datetime.now(UTC):
        raise HTTPException(422, "Workforce source observation cannot be in the future")
    batch = PeopleImportBatch(id=uuid.uuid4(), source_id=source.id,
        revision=previous.revision + 1 if previous else 1, request_key=body.request_key,
        request_hash=digest, source_as_of=body.source_as_of, imported_by=actor.id,
        reason=body.reason, person_count=len(body.people), previous_batch_id=previous.id if previous else None)
    session.add(batch)
    await session.flush()
    for person in body.people:
        identity = await session.scalar(select(WorkforcePerson).where(
            WorkforcePerson.source_id == source.id, WorkforcePerson.person_key == person.person_key))
        if identity is None:
            identity = WorkforcePerson(id=uuid.uuid4(), source_id=source.id, person_key=person.person_key)
            session.add(identity)
            await session.flush()
        version = WorkforceVersion(id=uuid.uuid4(), source_id=source.id, person_id=identity.id,
            batch_id=batch.id, **person.model_dump(exclude={"person_key", "intervals"}))
        session.add(version)
        await session.flush()
        for interval in person.intervals:
            session.add(WorkforceInterval(version_id=version.id,
                **interval.model_dump(exclude={"allocation"}), allocation=Decimal(interval.allocation)))
    await append_audit(session, actor_id=actor.id, action="people.supply_imported", entity="people_source",
        entity_id=str(source.id), before={"batch_id": str(previous.id)} if previous else None,
        after={"batch_id": str(batch.id), "revision": batch.revision, "person_count": batch.person_count,
            "reason": body.reason, "source_as_of": body.source_as_of.isoformat()}, correlation_id=body.request_key)
    result = _batch_result(batch)
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"supply:{batch.id}")
    await session.commit()
    return result


async def availability(session, *, actor):
    _authorized(actor)
    return await _scoped_supply(session, actor=actor)


async def _scoped_supply(session, *, actor):
    tenant, environment = runtime()
    sources = list((await session.scalars(select(PeopleSource).where(
        PeopleSource.tenant_id == tenant, PeopleSource.environment == environment,
        PeopleSource.test_fixture == is_test_user(actor)).order_by(PeopleSource.source_system))).all())
    result = {"basis": "gross_with_commitments", "is_reservation": False, "sources": [], "people": []}
    for source in sources:
        batch = await session.scalar(select(PeopleImportBatch).where(PeopleImportBatch.source_id == source.id)
            .order_by(PeopleImportBatch.revision.desc()).limit(1))
        if batch is None:
            continue
        result["sources"].append({**_batch_result(batch), "source_system": source.source_system})
        versions = (await session.execute(select(WorkforceVersion, WorkforcePerson.person_key).join(WorkforcePerson,
            WorkforceVersion.person_id == WorkforcePerson.id).where(WorkforceVersion.batch_id == batch.id)
            .order_by(WorkforceVersion.person_id))).all()
        for version, person_key in versions:
            intervals = (await session.scalars(select(WorkforceInterval).where(WorkforceInterval.version_id == version.id)
                .order_by(WorkforceInterval.start_date, WorkforceInterval.kind.desc(), WorkforceInterval.id))).all()
            result["people"].append({"person_id": str(version.person_id), "version_id": str(version.id),
                "person_key": person_key,
                "source_system": source.source_system, "batch_id": str(batch.id), "display_name": version.display_name,
                "role": version.role, "skills": version.skills, "level": version.level,
                "location": version.location, "timezone": version.timezone, "evidence": version.evidence,
                "intervals": [{"kind": row.kind, "assignment_key": row.assignment_key,
                    "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat(),
                    "allocation": _allocation_text(row.allocation)} for row in intervals]})
    return result


def _allocation_text(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


async def import_history(session, *, actor, page=1, size=50):
    _authorized(actor)
    tenant, environment = runtime()
    query = select(PeopleImportBatch, PeopleSource.source_system, User.name).join(PeopleSource,
        PeopleImportBatch.source_id == PeopleSource.id).join(User, PeopleImportBatch.imported_by == User.id).where(PeopleSource.tenant_id == tenant,
        PeopleSource.environment == environment, PeopleSource.test_fixture == is_test_user(actor))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (await session.execute(query.order_by(PeopleImportBatch.imported_at.desc(), PeopleImportBatch.id)
        .offset((page - 1) * size).limit(size))).all()
    return {"items": [{**_batch_result(batch), "source_system": source,
        "imported_at": batch.imported_at.isoformat(), "imported_by": str(batch.imported_by),
        "imported_by_name": imported_by_name,
        "reason": batch.reason, "previous_batch_id": str(batch.previous_batch_id) if batch.previous_batch_id else None}
        for batch, source, imported_by_name in rows], "page": page, "size": size, "total": total}
