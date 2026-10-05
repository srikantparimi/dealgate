"""Independent CO-09 parent/fixture checks, not PostgreSQL or cloud acceptance."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.audit import append_audit
from app.auth import AuthUser
from app.models.actual import ActualPeriod, FinancialActual, FinancialImportBatch
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.deletion import DeletionFence, DeletionJob
from app.models.forecast import ForecastPlan
from app.models.gm_model import GmModel, ResourceLine
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.models.user import User
from app.services.actuals_import import financial_records
from app.services.deletion import DeletionError
from app.services.deletion_cleanup import process_deletion_jobs
from app.services.fixture_cleanup import cleanup_manifest
from app.services.parent_deletion import request_client_deletion, request_opportunity_deletion
from app.services.projects import list_projects
from app.services.test_fixtures import ISSUED, create_fixture

TENANT = "independent-parent-cleanup"


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await session.execute(text("PRAGMA foreign_keys=ON"))
        await session.commit()
        assert await session.scalar(text("PRAGMA foreign_keys")) == 1
        await session.commit()
        yield session


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("DEALGATE_TENANT_ID", TENANT)
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    monkeypatch.setenv("SOW_BUCKET", "qa-parent-sows")
    monkeypatch.setenv("AGREEMENTS_BUCKET", "qa-parent-agreements")


async def _seed(session, *, with_package):
    owner = User(id=uuid.uuid4(), email=f"owner-{uuid.uuid4()}@example.test", name="QA owner", groups=["Sales"])
    client = Client(id=uuid.uuid4(), name="Independent parent account")
    session.add_all([owner, client])
    await session.flush()
    deal = Opportunity(id=uuid.uuid4(), source="test", owner_id=owner.id, client_id=client.id, governance_status="Intake")
    session.add(deal)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
        file_s3_key="independent/one.pdf", file_hash=uuid.uuid4().hex, extract_status="complete")
    session.add(version)
    await session.flush()
    if with_package:
        gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
            version=1, engagement_type="fixed_price")
        session.add(gm)
        await session.flush()
        session.add(ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
            gm_model_id=gm.id, package_hash=uuid.uuid4().hex, status="pending_delivery_hr",
            submitted_by=owner.id, submitted_at=datetime.now(UTC)))
        await session.flush()
    return owner, deal, sow


async def issued(session):
    actor = User(id=uuid.uuid4(), email=f"issuer-{uuid.uuid4()}@example.test", name="QA issuer",
                 groups=["officeapp-e2e", "SystemAdmin"])
    session.add(actor)
    await session.flush()
    fixture = await create_fixture(session, actor_id=actor.id, label="Independent cleanup", reviewer_ids=[])
    await session.commit()
    grant = await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(fixture["client_id"])))
    return actor, fixture, grant


@pytest.mark.asyncio
async def test_manifest_dry_read_and_exact_zero_age_preserve_active_run(session):
    actor, fixture, _ = await issued(session)
    bounded = dict(run_id=fixture["run_id"], owner_id=actor.id, min_age=timedelta(0))
    assert await cleanup_manifest(session, now=datetime.now(UTC), **bounded) == []
    later = datetime.now(UTC) + timedelta(hours=25)
    rows = await cleanup_manifest(session, now=later, **bounded)
    assert [row["client_id"] for row in rows] == [str(fixture["client_id"])]
    assert rows[0]["run_id"] == str(fixture["run_id"])
    assert await session.get(Client, fixture["client_id"]) is not None
    assert list((await session.scalars(select(DeletionJob.id))).all()) == []
    assert await cleanup_manifest(session, now=later, **{**bounded, "run_id": uuid.uuid4()}) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", [
    "participant_mapping", "real_uploader", "mirrored_source", "bad_correlation", "foreign_tenant",
    "foreign_environment", "missing_owner", "duplicate_grant", "ungranted_uploader", "revoked_issuer",
    "ungranted_agreement", "ungranted_upload_job",
])
async def test_corrupted_or_untrusted_fixture_graph_is_not_a_cleanup_target(session, fault):
    actor, fixture, grant = await issued(session)
    deal = await session.get(Opportunity, fixture["opportunity_id"])
    data = dict(grant.after)
    if fault == "participant_mapping":
        data["participant_ids"] = {str(actor.id): "not the issued list schema"}
    elif fault in {"real_uploader", "ungranted_uploader"}:
        uploader = User(id=uuid.uuid4(), email=f"business-{uuid.uuid4()}@example.test", name="Business uploader", groups=["Sales"])
        session.add(uploader)
        sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
        session.add(sow)
        await session.flush()
        session.add(SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=uploader.id,
            file_s3_key="business-upload.pdf", file_hash=uuid.uuid4().hex, extract_status="complete"))
        if fault == "real_uploader":
            data["participant_ids"] = [str(actor.id), str(uploader.id)]
    elif fault == "mirrored_source":
        deal.source = "hubspot"
    elif fault == "bad_correlation":
        grant.correlation_id = str(uuid.uuid4())
    elif fault == "foreign_tenant":
        data["tenant_id"] = "other-tenant"
    elif fault == "foreign_environment":
        data["environment"] = "dev"
    elif fault == "missing_owner":
        data.pop("owner_id")
    elif fault == "duplicate_grant":
        await append_audit(session, actor_id=actor.id, action=ISSUED, entity="client",
            entity_id=str(fixture["client_id"]), before=None, after=data, correlation_id=str(fixture["run_id"]))
    elif fault == "revoked_issuer":
        actor.groups = ["officeapp-e2e"]
    elif fault in {"ungranted_agreement", "ungranted_upload_job"}:
        outsider = User(id=uuid.uuid4(), email=f"outsider-{uuid.uuid4()}@example.test", name="Not a participant", groups=["Sales"])
        session.add(outsider)
        await session.flush()
        if fault == "ungranted_agreement":
            session.add(Agreement(id=uuid.uuid4(), client_id=fixture["client_id"], kind="MSA",
                file_key="business/msa.pdf", filename="msa.pdf", file_size=10, uploaded_by=outsider.id))
        else:
            session.add(SowUploadJob(id=uuid.uuid4(), opportunity_id=deal.id, uploader_id=outsider.id,
                s3_key="business/pending.pdf", file_hash=uuid.uuid4().hex, status="needs_pick"))
    # Intentional SQLite corruption fixture, never an application audit update.
    grant.after = data
    await session.commit()
    rows = await cleanup_manifest(session, now=datetime.now(UTC) + timedelta(hours=25))
    assert rows == [], f"Untrusted {fault} graph must not enter an apply manifest"
    assert await session.get(Client, fixture["client_id"]) is not None


@pytest.mark.parametrize("age", ["-0.01", "NaN", "Infinity", "garbage", "0"])
def test_worker_age_configuration_never_authorizes_an_unbounded_unsafe_sweep(monkeypatch, age):
    from worker.e2e_cleanup import _min_age
    monkeypatch.setenv("E2E_MIN_AGE_HOURS", age)
    with pytest.raises(ValueError):
        _min_age()


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension,value", [("tenant_id", "foreign"), ("environment", "dev")])
async def test_opportunity_delete_refuses_foreign_linked_forecast_before_mutation(session, dimension, value):
    owner, deal, sow = await _seed(session, with_package=False)
    values = {"tenant_id": TENANT, "environment": "staging", dimension: value}
    plan = ForecastPlan(id=uuid.uuid4(), account_id=deal.client_id, opportunity_id=deal.id,
        owner_id=owner.id, request_key="foreign-plan", request_hash="a" * 64, **values)
    session.add(plan)
    await session.commit()
    with pytest.raises(DeletionError) as error:
        await request_opportunity_deletion(session, actor_id=owner.id, opportunity_id=deal.id)
    assert error.value.status_code in {403, 404}
    assert await session.get(Sow, sow.id) is not None
    assert (await session.get(ForecastPlan, plan.id)).opportunity_id == deal.id
    assert list((await session.scalars(select(DeletionJob.id))).all()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["client_id", "deal_id", "deal_source"])
async def test_mirrored_parent_refused_without_job_or_fence(session, boundary):
    owner, deal, sow = await _seed(session, with_package=False)
    client = await session.get(Client, deal.client_id)
    if boundary == "client_id":
        client.hubspot_company_id = "crm-client"
    elif boundary == "deal_id":
        deal.hubspot_deal_id = "crm-deal"
    else:
        deal.source = "hubspot"
    await session.commit()
    with pytest.raises(DeletionError, match="mirrored"):
        await request_client_deletion(session, actor_id=owner.id, client_id=client.id)
    assert await session.get(Sow, sow.id) is not None
    assert list((await session.scalars(select(DeletionJob.id))).all()) == []
    assert list((await session.scalars(select(DeletionFence.subject_id))).all()) == []


@pytest.mark.asyncio
async def test_parent_rollback_restores_earlier_child_removal_and_all_tombstones(session):
    owner, deal, sow = await _seed(session, with_package=False)
    orphan = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=deal.client_id,
        title="Unresolved source ownership", baseline_snapshot_json={"revenue_us": "812.50"}, created_by=owner.id)
    session.add(orphan)
    account_id, sow_id = deal.client_id, sow.id
    await session.commit()
    with pytest.raises(DeletionError, match="ownership"):
        async with session.begin():
            await request_client_deletion(session, actor_id=owner.id, client_id=account_id)
    assert await session.get(Client, account_id) is not None
    assert await session.get(Sow, sow_id) is not None
    assert list((await session.scalars(select(DeletionJob.id))).all()) == []
    assert list((await session.scalars(select(DeletionFence.subject_id))).all()) == []
    assert list((await session.scalars(select(AuditEvent.id).where(AuditEvent.action.like("%.deleted")))).all()) == []


@pytest.mark.asyncio
async def test_parent_retention_is_readable_with_exact_facts_and_original_ids(session):
    owner, deal, _ = await _seed(session, with_package=True)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    account_id, gm_id, version_id = deal.client_id, package.gm_model_id, package.sow_version_id
    baseline = {"revenue_us": "36924.125", "cost_us": "812.50"}
    project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=account_id,
        sow_version_id=version_id, gm_model_id=gm_id, package_id=package.id, title="Retained contract",
        baseline_snapshot_json=baseline, created_by=owner.id)
    resource = ResourceLine(id=uuid.uuid4(), gm_model_id=gm_id, role="Engineer", seniority="Senior", location="US",
        start_date=date(2026, 10, 1), end_date=date(2026, 10, 31), allocation_pct=Decimal("1"),
        billable_hours=Decimal("8"), hourly_bill_rate=Decimal("100"))
    batch = FinancialImportBatch(id=uuid.uuid4(), tenant_id=TENANT, environment="staging", source_system="qa",
        request_key="fact-batch", request_hash="b" * 64, uploaded_by=owner.id, status="committed", row_count=1)
    session.add_all([project, resource, batch])
    await session.flush()
    legacy = ActualPeriod(id=uuid.uuid4(), gm_model_id=gm_id, resource_line_id=resource.id, period_month=date(2026, 10, 1),
        actual_hours=Decimal("3.25"), actual_cost=Decimal("162.50"), actual_revenue=Decimal("812.50"), imported_by=owner.id)
    fact = FinancialActual(id=uuid.uuid4(), tenant_id=TENANT, environment="staging", source_system="qa", source_id="invoice",
        revision=1, batch_id=batch.id, account_id=account_id, original_account_id=account_id,
        gm_model_id=gm_id, original_gm_model_id=gm_id, period_month=date(2026, 10, 1), measure="billed_revenue",
        amount=Decimal("36924.125"), currency="USD", source_date=date(2026, 10, 15), reason="Known independent invoice")
    session.add_all([legacy, fact])
    await session.commit()
    job = await request_client_deletion(session, actor_id=owner.id, client_id=account_id)
    await session.commit()
    await session.refresh(legacy)
    assert legacy.gm_model_id is None and legacy.resource_line_id is None
    assert legacy.original_gm_model_id == gm_id and legacy.original_resource_line_id == resource.id
    assert (legacy.actual_hours, legacy.actual_cost, legacy.actual_revenue) == (Decimal("3.25"), Decimal("162.50"), Decimal("812.50"))
    actor = AuthUser(owner.id, owner.email, owner.name, ("Finance",))
    records = await financial_records(session, actor=actor, account_id=account_id)
    assert len(records) == 1 and records[0]["amount"] == "36924.125"
    assert records[0]["source_detached"] and records[0]["gm_model_id"] == str(gm_id)
    projects = await list_projects(session, actor=actor)
    retained = next(row for row in projects if row["project_id"] == str(project.id))
    assert retained["source_deleted"] and retained["baseline"] == baseline
    assert retained["provenance"]["client_id"] == str(account_id)
    assert retained["provenance"]["sow_version_id"] == str(version_id)
    repeated = await request_client_deletion(session, actor_id=owner.id, client_id=account_id)
    assert repeated.id == job.id and job.status == "pending"


class EmptyStorage:
    def __init__(self):
        self.queried = []

    def get_paginator(self, name):
        return self

    def paginate(self, *, Bucket, Prefix):
        self.queried.append((Bucket, Prefix))
        return [{}]

    def delete_objects(self, **kwargs):
        raise AssertionError("Empty storage must not receive unversioned deletes")


@pytest.mark.asyncio
async def test_shared_parent_agreement_key_survives_another_clients_cleanup(session):
    owner, deal, _ = await _seed(session, with_package=False)
    other = Client(id=uuid.uuid4(), name="Independent surviving client")
    session.add(other)
    await session.flush()
    agreements = [Agreement(id=uuid.uuid4(), client_id=account, kind="MSA", file_key="shared/msa.pdf",
        filename="msa.pdf", file_size=8, uploaded_by=owner.id) for account in (deal.client_id, other.id)]
    session.add_all(agreements)
    await session.commit()
    root = await request_client_deletion(session, actor_id=owner.id, client_id=deal.client_id)
    await session.commit()
    assert root.objects == []
    storage = EmptyStorage()
    await process_deletion_jobs(session, s3=storage)
    assert ("qa-parent-agreements", "shared/msa.pdf") not in storage.queried
    assert await session.get(Agreement, agreements[1].id) is not None
    assert await session.get(Client, other.id) is not None


@pytest.mark.asyncio
async def test_malformed_parent_dependency_is_visible_failure_not_worker_poison(session):
    now = datetime.now(UTC)
    bad = DeletionJob(id=uuid.uuid4(), subject_type="client", subject_id=uuid.uuid4(),
        tenant_id=TENANT, environment="staging", status="pending", objects=[],
        summary={"child_job_ids": ["invalid-child-id"]}, created_at=now - timedelta(hours=1))
    good = DeletionJob(id=uuid.uuid4(), subject_type="client", subject_id=uuid.uuid4(),
        tenant_id=TENANT, environment="staging", status="pending", objects=[], summary={}, created_at=now)
    session.add_all([bad, good])
    await session.commit()
    await process_deletion_jobs(session, s3=EmptyStorage(), limit=2)
    assert bad.status == "failed" and bad.last_error
    assert good.status == "done"
