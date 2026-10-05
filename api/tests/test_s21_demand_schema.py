"""Demand is source-owned, versioned and cost-free; unknown is not zero."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.people_demand import DemandPublication, DemandPublicationVersion, DemandLine
from app.models.project import Project
from app.models.user import User
from tests.test_s21_workforce_schema import engine  # noqa: F401


async def publication(session):
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic delivery", groups=["Delivery"])
    project = Project(id=uuid.uuid4(), title="Synthetic retained project", baseline_snapshot_json={})
    session.add_all([user, project])
    await session.flush()
    parent = DemandPublication(id=uuid.uuid4(), tenant_id="synthetic", environment="local",
        project_id=project.id, owner_id=user.id, test_fixture=True)
    session.add(parent)
    await session.flush()
    version = DemandPublicationVersion(id=uuid.uuid4(), publication_id=parent.id, version=1,
        source_version="project-baseline-1", source_hash="a" * 64, request_key=str(uuid.uuid4()),
        request_hash="b" * 64, created_by=user.id, reason="Publish explicit synthetic source staffing",
        source_metadata={"source_name": project.title, "lifecycle": "committed"}, missing=[])
    session.add(version)
    await session.flush()
    return parent, version


def line(version_id, **changes):
    return DemandLine(**(dict(version_id=version_id, line_key="implementation:engineering",
        component_id="implementation", assignment_id="engineering", role="Engineer", skills=["python"],
        level="senior", location="US", timezone="America/Los_Angeles", quantity=7,
        allocation=Decimal("1"), start_date=date(2026, 11, 1), end_date=date(2027, 4, 30),
        delivery_model="fixed_assignment", retained_person_ids=[], evidence=["Source staffing row 1"], missing=[])
        | changes))


async def test_unknown_staffing_values_are_preserved_not_defaulted_to_zero(session):
    _, version = await publication(session)
    row = line(version.id, quantity=None, allocation=None, start_date=None, end_date=None,
        missing=["quantity", "allocation", "dates"])
    session.add(row)
    await session.commit()
    session.expunge_all()
    saved = await session.get(DemandLine, row.id)
    assert saved.quantity is None and saved.allocation is None
    assert saved.start_date is None and saved.end_date is None
    assert saved.missing == ["quantity", "allocation", "dates"]


@pytest.mark.parametrize("changes", [
    {"quantity": 0}, {"quantity": -1}, {"allocation": Decimal("0")},
    {"allocation": Decimal("1.1")}, {"end_date": date(2026, 10, 1)},
])
async def test_invalid_persisted_demand_fails_storage_constraints(session, changes):
    _, version = await publication(session)
    session.add(line(version.id, **changes))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_same_assignment_cannot_be_counted_twice_in_one_publication_version(session):
    _, version = await publication(session)
    session.add_all([line(version.id), line(version.id)])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_publication_requires_one_source(session):
    parent, _ = await publication(session)
    session.add(DemandPublication(tenant_id="synthetic", environment="local", owner_id=parent.owner_id))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_project_deletion_removes_owned_demand_not_unrelated_publications(session):
    parent, version = await publication(session)
    other, _ = await publication(session)
    session.add(line(version.id))
    await session.commit()
    await session.delete(await session.get(Project, parent.project_id))
    await session.commit()
    session.expunge_all()
    assert await session.get(DemandPublication, parent.id) is None
    assert await session.get(DemandPublicationVersion, version.id) is None
    assert (await session.scalars(select(DemandLine))).all() == []
    assert await session.get(DemandPublication, other.id) is not None


def test_demand_storage_has_no_financial_columns():
    for model in (DemandPublication, DemandPublicationVersion, DemandLine):
        assert not any(term in column.name for column in model.__table__.columns for term in ("cost", "rate", "salary", "fee", "revenue"))
