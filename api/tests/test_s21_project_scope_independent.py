"""Independent project scope checks using real capture, grants and deletion.

Approval state is fixture setup, not a proof of signature/release acceptance.
"""

import copy
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.gm.demand_source import project_staffing
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.commercial_models import parse_component, save_commercial_model
from app.services.deletion import request_sow_deletion
from app.services.parent_deletion import request_client_deletion
from app.services.project_lifecycle import create_or_link
from app.services.project_source import capture_project_scope, project_scope_allowed
from app.services.projects import list_projects
from app.services.test_fixtures import ISSUED, create_fixture
from tests.test_s21_commercial_persistence import wire


@pytest_asyncio.fixture
async def engine():
    database = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(database.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield database
    finally:
        await database.dispose()


async def prepared(session, monkeypatch, *, test_fixture=False, capture=True):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "independent-project-scope")
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    groups = ["SystemAdmin", "officeapp-e2e"] if test_fixture else ["Delivery"]
    owner = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Scoped owner", groups=groups)
    session.add(owner)
    await session.flush()
    if test_fixture:
        issued = await create_fixture(session, actor_id=owner.id, label="Independent project scope",
            reviewer_ids=[owner.id], hours=1)
        deal = await session.get(Opportunity, issued["opportunity_id"])
        client = await session.get(Client, issued["client_id"])
    else:
        client = Client(id=uuid.uuid4(), name="Independent real-business fixture")
        session.add(client)
        await session.flush()
        deal = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id,
            source="sow_upload", name="Reviewed delivery scope")
        session.add(deal)
        await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
        file_s3_key="", file_hash="a" * 64, extract_status="complete",
        extracted_fields={"title": {"value": "Retained canonical project", "status": "confirmed"}})
    session.add(version)
    await session.flush()
    gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=owner.id,
        sow_version_id=version.id, expected_gm_model_id=None, inputs=wire(version),
        change_reason="Approved synthetic source for independent scope boundaries")
    package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
        gm_model_id=gm.id, package_hash="b" * 64, status="released", submitted_by=owner.id,
        released_at=datetime.now(UTC))
    session.add(package)
    await session.flush()
    project = (await create_or_link(session, actor_id=owner.id, package=package))[0] if capture else None
    await session.commit()
    return owner, client, deal, sow, version, gm, package, project


async def delete_source(session, data):
    job = await request_sow_deletion(session, actor_id=data[0].id, sow_id=data[3].id)
    await session.commit()
    await session.refresh(data[7])
    return job


@pytest.mark.parametrize("test_fixture", [False, True])
async def test_actual_sow_then_parent_deletion_produces_compatible_retained_scope(session, monkeypatch, test_fixture):
    data = await prepared(session, monkeypatch, test_fixture=test_fixture)
    owner, client, deal, sow, version, gm, package, project = data
    frozen = copy.deepcopy(project.baseline_snapshot_json)
    ids = {"client_id": str(client.id), "opportunity_id": str(deal.id),
        "sow_version_id": str(version.id), "gm_model_id": str(gm.id), "package_id": str(package.id)}
    assert await project_scope_allowed(session, actor=owner, project=project)
    job = await delete_source(session, data)
    assert job.status == "done" and job.objects == []
    assert {key: project.retained_source[key] for key in ids} == ids
    assert project.retained_source["test_fixture"] is test_fixture
    assert project.retained_source["owner_id"] == str(owner.id)
    assert project.source_deleted_at is not None
    assert project.package_id is project.gm_model_id is project.sow_version_id is None
    assert await project_scope_allowed(session, actor=owner, project=project)
    await request_client_deletion(session, actor_id=owner.id, client_id=client.id)
    await session.commit()
    await session.refresh(project)
    assert project.client_id is project.opportunity_id is None
    assert project.baseline_snapshot_json == frozen
    assert await project_scope_allowed(session, actor=owner, project=project)
    assert await session.get(Project, project.id) is project
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert not await project_scope_allowed(session, actor=owner, project=project)


async def test_real_owner_reassignment_before_deletion_does_not_destroy_retained_authority(session, monkeypatch):
    data = await prepared(session, monkeypatch)
    new_owner = User(id=uuid.uuid4(), email="new-owner@example.test", name="New real owner", groups=["Delivery"])
    session.add(new_owner)
    await session.flush()
    data[2].owner_id = new_owner.id
    await session.commit()
    frozen = copy.deepcopy(data[7].baseline_snapshot_json)
    await delete_source(session, data)
    assert data[7].retained_source["owner_id"] == str(new_owner.id)
    assert data[7].baseline_snapshot_json == frozen
    assert await project_scope_allowed(session, actor=new_owner, project=data[7])


@pytest.mark.parametrize("detached", [False, True])
async def test_missing_package_lineage_does_not_authorize_live_or_retained_source(session, monkeypatch, detached):
    data = await prepared(session, monkeypatch)
    project = data[7]
    if detached:
        await delete_source(session, data)
        project.retained_source = {key: value for key, value in project.retained_source.items() if key != "package_id"}
    else:
        project.package_id = None
    await session.commit()
    assert not await project_scope_allowed(session, actor=data[0], project=project)


@pytest.mark.parametrize("test_fixture", [False, True])
async def test_retained_fixture_classification_conflict_is_fail_closed(session, monkeypatch, test_fixture):
    data = await prepared(session, monkeypatch, test_fixture=test_fixture)
    await delete_source(session, data)
    project = data[7]
    project.retained_source = {**project.retained_source, "test_fixture": not test_fixture}
    await session.commit()
    assert not await project_scope_allowed(session, actor=data[0], project=project)


async def test_capture_rejects_mirror_source_even_without_external_ids(session, monkeypatch):
    data = await prepared(session, monkeypatch, test_fixture=True, capture=False)
    data[2].source = "hubspot"
    await session.commit()
    assert data[2].hubspot_deal_id is None and data[1].hubspot_company_id is None
    with pytest.raises(ValueError):
        await capture_project_scope(session, opportunity=data[2], sow_version=data[4], gm_model=data[5])


@pytest.mark.parametrize("corruption", ["mirror_source", "archived_account"])
async def test_surviving_fixture_parent_cannot_invalidate_grant_and_stay_authorized(session, monkeypatch, corruption):
    data = await prepared(session, monkeypatch, test_fixture=True)
    await delete_source(session, data)
    if corruption == "mirror_source":
        data[2].source = "hubspot"
    else:
        data[1].archived_at = datetime.now(UTC)
    await session.commit()
    assert not await project_scope_allowed(session, actor=data[0], project=data[7])


@pytest.mark.parametrize("field,value", [
    ("expires_at", "2000-01-01T00:00:00+00:00"),
    ("owner_id", "00000000-0000-0000-0000-000000000001"),
    ("run_id", "00000000-0000-0000-0000-000000000002"),
])
async def test_detached_actual_fixture_grant_corruption_does_not_fall_back_to_real(session, monkeypatch, field, value):
    data = await prepared(session, monkeypatch, test_fixture=True)
    await delete_source(session, data)
    await request_client_deletion(session, actor_id=data[0].id, client_id=data[1].id)
    await session.commit()
    await session.refresh(data[7])
    grant = await session.scalar(select(AuditEvent).where(AuditEvent.action == ISSUED))
    grant.after = {**grant.after, field: value}
    await session.commit()
    assert not await project_scope_allowed(session, actor=data[0], project=data[7])
    ordinary = User(id=uuid.uuid4(), email="ordinary@example.test", groups=["SystemAdmin"])
    assert not await project_scope_allowed(session, actor=ordinary, project=data[7])


async def test_cost_free_projection_and_hr_project_read_do_not_echo_frozen_financials(session, monkeypatch):
    data = await prepared(session, monkeypatch)
    project = data[7]
    frozen = copy.deepcopy(project.baseline_snapshot_json)
    assert frozen["commercial_inputs"]["pricing"]["total_fee"] == "420000"
    projected = project_staffing(parse_component(frozen["commercial_inputs"]))
    assert "420000" not in repr(projected) and "210000" not in repr(projected)
    assert not {"commercial_inputs", "commercial_snapshot", "costs", "pricing"} & projected.keys()
    data[0].groups = ["HR"]
    await session.commit()
    live = await list_projects(session, actor=data[0])
    assert len(live) == 1 and live[0]["baseline"] is None
    await delete_source(session, data)
    retained = await list_projects(session, actor=data[0])
    assert len(retained) == 1 and retained[0]["baseline"] is None
    assert project.baseline_snapshot_json == frozen


async def test_real_deleted_project_read_does_not_bypass_foreign_runtime_scope(session, monkeypatch):
    data = await prepared(session, monkeypatch)
    await delete_source(session, data)
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert not await project_scope_allowed(session, actor=data[0], project=data[7])
    assert await list_projects(session, actor=data[0]) == []
