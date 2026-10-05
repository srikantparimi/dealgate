"""Managed supply preserves history and rejects invalid persisted capacity."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.base import Base

from app.models.people_planning import (
    PeopleSource, PeopleImportBatch, WorkforcePerson, WorkforceVersion, WorkforceInterval,
)
from app.models.user import User


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:")
    @event.listens_for(database.sync_engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def snapshot(session, tenant="tenant-a", revision=1, source=None, person=None):
    actor = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic HR", groups=["HR"])
    source = source or PeopleSource(id=uuid.uuid4(), tenant_id=tenant, environment="local", source_system="managed-roster")
    session.add_all([actor, source])
    await session.flush()
    batch = PeopleImportBatch(id=uuid.uuid4(), source_id=source.id, revision=revision,
        request_key=str(uuid.uuid4()), request_hash="a" * 64, source_as_of=datetime(2026, 10, revision, tzinfo=UTC),
        imported_by=actor.id, reason="Synthetic explicitly gross capacity snapshot", person_count=1)
    person = person or WorkforcePerson(id=uuid.uuid4(), source_id=source.id, person_key="person-one")
    session.add_all([batch, person])
    await session.flush()
    version = WorkforceVersion(id=uuid.uuid4(), source_id=source.id, person_id=person.id, batch_id=batch.id,
        display_name="Synthetic engineer", role="Engineer", skills=["python"], level="senior",
        location="US", timezone="America/Los_Angeles", evidence=["Managed roster row 1"])
    session.add(version)
    await session.flush()
    return source, person, batch, version


async def test_full_source_snapshots_retain_stable_people_and_immutable_versions(session):
    source, person, first, version = await snapshot(session)
    await session.commit()
    _, _, second, newer = await snapshot(session, revision=2, source=source, person=person)
    await session.commit()
    versions = list((await session.scalars(select(WorkforceVersion).where(WorkforceVersion.person_id == person.id))).all())
    assert {row.id for row in versions} == {version.id, newer.id}
    assert first.id != second.id and newer.person_id == version.person_id


async def test_same_external_person_key_is_isolated_between_sources_and_tenants(session):
    _, first, _, _ = await snapshot(session, tenant="tenant-a")
    _, second, _, _ = await snapshot(session, tenant="tenant-b")
    await session.commit()
    assert first.id != second.id and first.person_key == second.person_key


@pytest.mark.parametrize("changes", [
    {"allocation": Decimal("0")}, {"allocation": Decimal("1.01")},
    {"end_date": date(2026, 10, 31)}, {"kind": "net_available"},
    {"kind": "committed", "assignment_key": None},
    {"kind": "gross", "assignment_key": "ambiguous-assignment"},
])
async def test_invalid_workforce_interval_is_rejected_by_storage(session, changes):
    *_, version = await snapshot(session)
    values = dict(version_id=version.id, kind="gross", assignment_key=None,
        start_date=date(2026, 11, 1), end_date=date(2026, 11, 30), allocation=Decimal("1"))
    session.add(WorkforceInterval(**(values | changes)))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_duplicate_person_version_in_snapshot_is_rejected(session):
    _, person, batch, version = await snapshot(session)
    session.add(WorkforceVersion(source_id=person.source_id, person_id=person.id, batch_id=batch.id,
        display_name=version.display_name, role=version.role, skills=version.skills,
        level=version.level, location=version.location, timezone=version.timezone, evidence=[]))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_version_cannot_bind_person_from_another_source_snapshot(session):
    source, _, batch, _ = await snapshot(session, tenant="tenant-a")
    _, foreign, _, version = await snapshot(session, tenant="tenant-b")
    session.add(WorkforceVersion(source_id=source.id, person_id=foreign.id, batch_id=batch.id,
        display_name=version.display_name, role=version.role, skills=version.skills,
        level=version.level, location=version.location, timezone=version.timezone, evidence=[]))
    with pytest.raises(IntegrityError):
        await session.commit()


def test_people_storage_has_no_cost_rate_or_salary_columns():
    for model in (PeopleSource, PeopleImportBatch, WorkforcePerson, WorkforceVersion, WorkforceInterval):
        assert not any(term in col.name for col in model.__table__.columns for term in ("cost", "salary", "rate"))
