"""Independent coverage service boundaries; private SQLite is not a row-lock proof."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gm.demand_source import line_key
from app.models.audit import AuditEvent
from app.models.people_coverage import DemandCoverageVersion
from app.models.people_demand import DemandPublication
from app.models.project import Project
from app.models.user import User
from app.services.forecast_plans import save_plan
from app.services.people_allocation import demand_allocation
from app.services.people_coverage import CoverageInput, list_coverage, save_coverage
from app.services.people_demand import publish_plan_demand
from app.services.people_planning import WorkforceImportInput, import_workforce
from app.services.people_project_demand import publish_project_demand
from tests.test_s21_demand_publication import publication
from tests.test_s21_forecast_plans import actor, body
from tests.test_s21_project_demand import canonical, request  # noqa: F401
from tests.test_s21_project_scope_independent import engine  # noqa: F401
from tests.test_s21_project_source_scope import project


KEY = line_key("build", "team-1")


@pytest_asyncio.fixture
async def sources(session, canonical):
    retained = await project(session, canonical)
    delivery = actor(canonical[0])
    planner = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Separate portfolio owner",
        groups=["Delivery"])
    session.add(planner)
    await session.commit()
    sales_owner = actor(planner)
    plan = body(canonical[1].client_id)
    plan.inputs = retained.baseline_snapshot_json["commercial_inputs"]
    version = await save_plan(session, actor=sales_owner, body=plan)
    enrichment = {KEY: {"skills": ["python"], "level": "senior", "evidence": ["Independent reviewed capability"]}}
    proposed = await publish_plan_demand(session, actor=sales_owner,
        body=publication(version, enrichments=enrichment))
    committed = await publish_project_demand(session, actor=delivery,
        body=request(retained, enrichments=enrichment))
    return dict(delivery=delivery, planner=sales_owner, project=retained, plan=plan, version=version,
        proposed=proposed, committed=committed, enrichment=enrichment)


def mapping(sources, **changes):
    return CoverageInput(**(dict(plan_publication_id=sources["proposed"]["publication_id"],
        project_publication_id=sources["committed"]["publication_id"],
        expected_plan_version_id=sources["proposed"]["version_id"],
        expected_project_version_id=sources["committed"]["version_id"],
        expected_mapping_version_id=None, request_key=str(uuid.uuid4()),
        reason="Independent review of explicit staffing replacement",
        mappings=[dict(plan_line_key=KEY, project_line_key=KEY, plan_slots=[0], project_slots=[0],
            start_date="2026-11-01", end_date="2027-04-30")]) | changes))


async def supply(session, sources, *, one_half_time=False):
    people = [dict(person_key="one-reviewed-person", display_name="Private retained capacity",
        role="Engineer", skills=["python"], level="senior", location="US", timezone="America/New_York",
        evidence=["Approved managed supply snapshot"], intervals=[dict(kind="gross", allocation="0.5",
            start_date="2026-11-01", end_date="2027-04-30")])] if one_half_time else []
    return await import_workforce(session, actor=replace(sources["delivery"], groups=("HR",)),
        body=WorkforceImportInput(source_system="independent-coverage", request_key=str(uuid.uuid4()),
            expected_previous_batch_id=None, source_as_of="2026-10-01T00:00:00Z",
            reason="Independent complete supply evidence", basis="gross_with_commitments", people=people))


@pytest.mark.parametrize("covered", [False, True])
async def test_sales_filters_do_not_release_hidden_committed_capacity(session, sources, covered):
    await supply(session, sources, one_half_time=True)
    if covered:
        await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    result = await demand_allocation(session, actor=replace(sources["planner"], groups=("Sales",)))
    assert result["complete"] is True and result["missing"] == []
    assert result["scope_label"] == "My portfolio" and result["sources"] == []
    assert len(result["months"]) == 6
    for month in result["months"]:
        assert month["peak_headcount"] == (1 if covered else 2)
        assert Decimal(month["gap_fte"]) == (Decimal("0.5") if covered else Decimal("1"))
    for interval in result["intervals"]:
        row, = interval["demands"]
        assert row["plan_id"] == str(sources["version"].plan_id)
        assert Decimal(row["matched_fte"]) == Decimal("0")
        assert "matches" not in row and "overcommitted_person_ids" not in interval
    assert str(sources["project"].id) not in str(result)
    assert "Private retained capacity" not in str(result)


@pytest.mark.parametrize("second_start,accepted", [("2026-11-15", False), ("2026-11-16", True)])
async def test_cross_root_slot_reuse_respects_inclusive_dates(session, sources, second_start, accepted):
    await supply(session, sources)
    first = mapping(sources)
    first.mappings[0].end_date = datetime(2026, 11, 15).date()
    await save_coverage(session, actor=sources["delivery"], body=first)
    version = await save_plan(session, actor=sources["planner"],
        body=sources["plan"].model_copy(update={"idempotency_key": uuid.uuid4()}))
    other = await publish_plan_demand(session, actor=sources["planner"],
        body=publication(version, enrichments=sources["enrichment"]))
    next_body = mapping(sources, plan_publication_id=other["publication_id"], expected_plan_version_id=other["version_id"])
    next_body.mappings[0].start_date = datetime.fromisoformat(second_start).date()
    if accepted:
        await save_coverage(session, actor=sources["delivery"], body=next_body)
        result = await demand_allocation(session, actor=sources["delivery"])
        assert result["complete"] is True
        assert all(month["peak_headcount"] == 5 and Decimal(month["peak_fte"]) == Decimal("2.5")
            for month in result["months"])
        expected_versions = 2
    else:
        with pytest.raises(HTTPException) as error:
            await save_coverage(session, actor=sources["delivery"], body=next_body)
        assert error.value.status_code == 422
        await session.rollback()
        expected_versions = 1
    assert await session.scalar(select(func.count()).select_from(DemandCoverageVersion)) == expected_versions


async def test_separate_session_stale_mapping_cas_cannot_append_or_audit(session, sources, engine):
    stale = mapping(sources)
    await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    async with AsyncSession(engine, expire_on_commit=False) as second_session:
        with pytest.raises(HTTPException) as error:
            await save_coverage(second_session, actor=sources["delivery"], body=stale)
        assert error.value.status_code == 409
        await second_session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandCoverageVersion)) == 1
    assert await session.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.action == "people.staffing_coverage_revised")) == 1


async def test_replay_key_is_actor_bound_even_when_other_actor_can_write(session, sources):
    original = mapping(sources)
    await save_coverage(session, actor=sources["delivery"], body=original)
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=sources["planner"], body=original)
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandCoverageVersion)) == 1


async def test_source_republication_does_not_rebind_mapping_until_explicit_review(session, sources):
    await supply(session, sources)
    first = await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    renewed = await publish_plan_demand(session, actor=sources["planner"],
        body=publication(sources["version"], expected_publication_version_id=sources["proposed"]["version_id"]))
    stale = await demand_allocation(session, actor=sources["delivery"])
    assert stale["complete"] is False and "staffing_coverage_stale" in stale["missing"]
    assert all(month["peak_headcount"] == 4 for month in stale["months"])
    await save_coverage(session, actor=sources["delivery"], body=mapping(sources,
        expected_plan_version_id=renewed["version_id"], expected_mapping_version_id=first["version_id"]))
    current = await demand_allocation(session, actor=sources["delivery"])
    assert current["complete"] is True and current["missing"] == []
    assert all(month["peak_headcount"] == 3 for month in current["months"])
    assert stale["source_watermark"] != current["source_watermark"]


async def test_archived_project_mapping_history_remains_available_to_authorized_reviewer(session, sources):
    first = await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    sources["project"].archived_at = datetime.now(UTC)
    await session.commit()
    history = await list_coverage(session, actor=sources["delivery"],
        plan_publication_id=uuid.UUID(sources["proposed"]["publication_id"]), root_id=uuid.UUID(first["id"]))
    assert history["current_version_id"] == first["version_id"]
    assert len(history["items"]) == 1 and history["items"][0]["state"] == "stale"
    assert history["items"][0]["mappings"] == first["mappings"]


async def test_empty_revision_can_clear_archived_project_mapping_and_restore_completeness(session, sources):
    await supply(session, sources)
    first = await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    sources["project"].archived_at = datetime.now(UTC)
    await session.commit()
    stale = await demand_allocation(session, actor=sources["delivery"])
    assert stale["complete"] is False and "staffing_coverage_stale" in stale["missing"]
    cleared = await save_coverage(session, actor=sources["delivery"], body=mapping(sources,
        expected_mapping_version_id=first["version_id"], mappings=[], reason="Clear obsolete source coverage"))
    assert cleared["revision"] == 2 and cleared["mappings"] == []
    current = await demand_allocation(session, actor=sources["delivery"])
    assert current["complete"] is True and current["missing"] == []
    assert all(month["peak_headcount"] == 2 for month in current["months"])


@pytest.mark.parametrize("fault", ["tenant", "classification", "role"])
async def test_clear_does_not_bypass_runtime_test_or_write_permission(session, sources, monkeypatch, fault):
    first = await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    writer = sources["delivery"]
    if fault == "tenant":
        monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    elif fault == "classification":
        writer = replace(writer, groups=("Delivery", "officeapp-e2e"))
    else:
        writer = replace(writer, groups=("Sales",))
    with pytest.raises(HTTPException) as error:
        await save_coverage(session, actor=writer, body=mapping(sources,
            expected_mapping_version_id=first["version_id"], mappings=[]))
    assert error.value.status_code == (403 if fault == "role" else 404)
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(DemandCoverageVersion)) == 1


async def test_deleted_plan_source_cascades_only_its_coverage_and_not_project_publication(session, sources):
    from sqlalchemy import delete
    from app.models.forecast import ForecastPlan
    from app.models.people_coverage import DemandCoverageRoot
    first = await save_coverage(session, actor=sources["delivery"], body=mapping(sources))
    project_id = sources["project"].id
    project_publication_id = uuid.UUID(sources["committed"]["publication_id"])
    await session.execute(delete(ForecastPlan).where(ForecastPlan.id == sources["version"].plan_id))
    await session.commit()
    assert await session.get(DemandCoverageRoot, uuid.UUID(first["id"]), populate_existing=True) is None
    assert await session.get(DemandCoverageVersion, uuid.UUID(first["version_id"]), populate_existing=True) is None
    assert await session.get(Project, project_id) is not None
    assert await session.get(DemandPublication, project_publication_id) is not None
