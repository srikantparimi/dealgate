"""Independent S21-01/CO-09 service checks; no route or cloud acceptance claim."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.actual import ActualPeriod, FinancialActual, FinancialImportBatch
from app.models.approval import ApprovalPackage
from app.models.client import Agreement
from app.models.deletion import DeletionFence, DeletionJob
from app.models.gm_model import GmModel, ResourceLine
from app.models.next_action import NextAction
from app.models.project import Project
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.services.deletion import DeletionError, request_sow_deletion
from app.services.deletion_cleanup import process_deletion_jobs, remove_object_versions
from app.services.deletion_fences import source_deleted
from tests.test_deletion_by_state import _seed


@pytest.fixture(autouse=True)
def isolated_scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "test")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "qa-deletion")
    monkeypatch.setenv("SOW_BUCKET", "qa-owned-bucket")


async def sibling(session, deal, key="sibling.pdf"):
    sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, file_s3_key=key,
                         file_hash=uuid.uuid4().hex, extract_status="complete")
    session.add(version)
    await session.flush()
    return sow, version


class VersionedStorage:
    """Deterministic external-store boundary, including prefix neighbours."""

    def __init__(self):
        self.entries = [{"Key": "del/one.pdf", "VersionId": "v1"},
                        {"Key": "del/one.pdf.neighbour", "VersionId": "v2"}]
        self.markers = [{"Key": "del/one.pdf", "VersionId": "marker"}]
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_object_versions"
        return self

    def paginate(self, **kwargs):
        return [{"Versions": self.entries, "DeleteMarkers": self.markers}]

    def delete_objects(self, *, Bucket, Delete):
        self.deleted.extend(Delete["Objects"])
        self.entries = [row for row in self.entries if row not in Delete["Objects"]]
        self.markers = [row for row in self.markers if row not in Delete["Objects"]]
        return {}


@pytest.mark.asyncio
async def test_preexisting_sibling_shared_key_is_never_queued(session):
    owner, deal, sow = await _seed(session, with_package=False)
    other, version = await sibling(session, deal, "del/one.pdf")
    job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    assert job.objects == [] and job.status == "done"
    assert await session.get(Sow, other.id) is not None
    assert (await session.get(SowVersion, version.id)).file_s3_key == "del/one.pdf"


@pytest.mark.asyncio
async def test_cleanup_rechecks_key_claimed_by_surviving_sow_after_request(session):
    owner, deal, sow = await _seed(session, with_package=False)
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    await sibling(session, deal, "del/one.pdf")
    await session.commit()
    storage = VersionedStorage()
    await process_deletion_jobs(session, s3=storage)
    assert storage.deleted == [], "A surviving SOW owns this exact key at execution time"


@pytest.mark.asyncio
async def test_parent_agreement_same_bucket_key_is_not_queued(session, monkeypatch):
    monkeypatch.setenv("AGREEMENTS_BUCKET", "qa-owned-bucket")
    owner, deal, sow = await _seed(session, with_package=False)
    agreement = Agreement(id=uuid.uuid4(), client_id=deal.client_id, kind="MSA",
        file_key="del/one.pdf", filename="agreement.pdf", file_size=123, uploaded_by=owner.id)
    session.add(agreement)
    await session.flush()
    job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    assert await session.get(Agreement, agreement.id) is not None
    assert job.objects == [], "Deleting SOW storage must not destroy a surviving MSA"


@pytest.mark.asyncio
async def test_supported_default_upload_bucket_is_recorded_for_cleanup(session, monkeypatch):
    monkeypatch.delenv("SOW_BUCKET")
    monkeypatch.setenv("AWS_ACCOUNT_ID", "123456789012")
    owner, _, sow = await _seed(session, with_package=False)
    job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    assert job.objects == [{"bucket": "officeapp-dev-sows-123456789012", "key": "del/one.pdf"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["archived", "rejected", "ready_to_sign", "released"])
async def test_governed_graph_retains_facts_sibling_and_parent_activity(session, state):
    owner, deal, sow = await _seed(session, with_package=True)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    if state == "archived":
        sow.archived_at = datetime.now(UTC)
    else:
        package.status = state
    original_version, original_gm, original_package = package.sow_version_id, package.gm_model_id, package.id
    resource = ResourceLine(id=uuid.uuid4(), gm_model_id=original_gm, role="Engineer",
        seniority="Senior", location="US", start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
        allocation_pct=Decimal("1"), billable_hours=Decimal("160"), hourly_bill_rate=Decimal("100"))
    session.add(resource)
    await session.flush()
    baseline = {"revenue_us": "10000.00", "cost_us": "3700.00"}
    project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=deal.client_id,
        sow_version_id=original_version, gm_model_id=original_gm, package_id=package.id,
        title="Independent retained project", baseline_snapshot_json=baseline, created_by=owner.id)
    legacy = ActualPeriod(id=uuid.uuid4(), gm_model_id=original_gm, resource_line_id=resource.id,
        period_month=date(2026, 9, 1), actual_hours=Decimal("19.25"), actual_cost=Decimal("123.45"),
        actual_revenue=Decimal("456.78"), imported_by=owner.id)
    batch = FinancialImportBatch(id=uuid.uuid4(), tenant_id="qa-deletion", environment="test",
        source_system="independent", request_key="batch", request_hash="a" * 64,
        uploaded_by=owner.id, status="committed", row_count=1)
    session.add_all([project, legacy, batch])
    await session.flush()
    fact = FinancialActual(id=uuid.uuid4(), tenant_id="qa-deletion", environment="test",
        source_system="independent", source_id="invoice-1", revision=1, batch_id=batch.id,
        account_id=deal.client_id, original_account_id=deal.client_id, gm_model_id=original_gm,
        original_gm_model_id=original_gm, period_month=date(2026, 9, 1), measure="billed_revenue",
        amount=Decimal("789.125"), currency="USD", source_date=date(2026, 9, 2), reason="Recorded invoice")
    signed = SignedSowUpload(id=uuid.uuid4(), package_id=package.id, file_s3_key="signed.pdf",
        file_hash="signed-hash", uploaded_by=owner.id, verify_status="verified")
    parent_action = NextAction(id=uuid.uuid4(), opportunity_id=deal.id, description="Parent activity",
        owner_user_id=owner.id, created_by=owner.id)
    owned_action = NextAction(id=uuid.uuid4(), opportunity_id=deal.id, description="SOW review",
        owner_user_id=owner.id, created_by=owner.id, approval_package_id=package.id)
    agreement = Agreement(id=uuid.uuid4(), client_id=deal.client_id, kind="NDA",
        file_key="nda.pdf", filename="nda.pdf", file_size=123, uploaded_by=owner.id)
    session.add_all([fact, signed, parent_action, owned_action, agreement])
    other, other_version = await sibling(session, deal)
    await session.commit()
    job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    for row in (project, legacy, fact):
        await session.refresh(row)
    assert project.baseline_snapshot_json == baseline and project.source_deleted_at
    assert (project.sow_version_id, project.gm_model_id, project.package_id) == (None, None, None)
    assert project.retained_source["sow_version_id"] == str(original_version)
    assert project.retained_source["package_id"] == str(original_package)
    assert legacy.gm_model_id is None and legacy.original_gm_model_id == original_gm
    assert legacy.resource_line_id is None and legacy.original_resource_line_id == resource.id
    assert legacy.source_deleted_at and legacy.actual_revenue == Decimal("456.78")
    assert legacy.actual_cost == Decimal("123.45") and legacy.actual_hours == Decimal("19.25")
    assert fact.gm_model_id is None and fact.original_gm_model_id == original_gm
    assert fact.amount == Decimal("789.125") and fact.account_id == deal.client_id
    assert await session.get(Sow, other.id) is not None
    assert await session.get(SowVersion, other_version.id) is not None
    assert await session.get(NextAction, parent_action.id) is not None
    assert await session.get(Agreement, agreement.id) is not None
    assert await session.get(NextAction, owned_action.id) is None
    assert await session.get(SignedSowUpload, signed.id) is None
    assert {item["key"] for item in job.objects} == {"del/one.pdf", "signed.pdf"}


@pytest.mark.asyncio
@pytest.mark.parametrize("dimension,value", [("tenant_id", "other-tenant"), ("environment", "staging")])
async def test_mismatched_commercial_source_is_not_deleted(session, dimension, value):
    owner, deal, sow = await _seed(session, with_package=True)
    gm = await session.scalar(select(GmModel).where(GmModel.opportunity_id == deal.id))
    gm.commercial_snapshot = {"tenant_id": "qa-deletion", "environment": "test", dimension: value}
    await session.commit()
    with pytest.raises((DeletionError, HTTPException)) as error:
        await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    assert error.value.status_code in {403, 404}
    assert await session.get(Sow, sow.id) is not None
    assert list((await session.scalars(select(DeletionJob.id))).all()) == []


@pytest.mark.asyncio
async def test_stale_bound_upload_cannot_recreate_deleted_sow(session):
    from app.services.sow_upload_job_service import UploadPipelineError, _finish_bound_upload

    owner, deal, sow = await _seed(session, with_package=False)
    version = await session.scalar(select(SowVersion).where(SowVersion.sow_id == sow.id))
    upload = SowUploadJob(id=uuid.uuid4(), uploader_id=owner.id, file_hash="old-upload",
        status="done", sow_version_id=version.id, opportunity_id=deal.id, s3_key=version.file_s3_key)
    session.add(upload)
    await session.commit()
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    # Invalid PDF fails locally before any external extraction can run.
    # 3a75455 moved document preparation to the caller; an unreadable
    # document arrives as a prepared error, never as provider access.
    from app.services.sow_extract import PreparedExtractionDocument

    prepared = PreparedExtractionDocument(
        text=None, extract_source="native", error="unreadable test document"
    )
    with pytest.raises(UploadPipelineError, match="deleted"):
        await _finish_bound_upload(session, job=upload, uploader_id=owner.id,
            file_bytes=b"not a PDF", content_type="application/pdf", s3_key="del/one.pdf",
            bound_client_id=deal.client_id, bound_opportunity_id=deal.id, bedrock_caller=None,
            prepared_document=prepared)
    assert list((await session.scalars(select(Sow.id))).all()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant,environment,blocked", [
    ("qa-deletion", "test", True), ("other-tenant", "test", False), ("qa-deletion", "local", False),
])
async def test_fences_do_not_leak_across_runtime_scope(session, monkeypatch, tenant, environment, blocked):
    owner, _, sow = await _seed(session, with_package=False)
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    monkeypatch.setenv("DEALGATE_TENANT_ID", tenant)
    monkeypatch.setenv("DEALGATE_ENV", environment)
    assert await source_deleted(session, "sow", sow.id) is blocked


@pytest.mark.asyncio
async def test_cleanup_is_scoped_and_replay_has_no_external_side_effect(session):
    owner, _, sow = await _seed(session, with_package=False)
    own = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    foreign = DeletionJob(id=uuid.uuid4(), tenant_id="other-tenant", environment="test",
        sow_id=uuid.uuid4(), actor_id=owner.id, status="pending", summary={},
        objects=[{"bucket": "other-bucket", "key": "foreign.pdf"}])
    session.add(foreign)
    await session.commit()
    storage = VersionedStorage()
    assert await process_deletion_jobs(session, s3=storage) == 1
    assert own.status == "done" and own.objects == []
    assert foreign.status == "pending" and foreign.attempts == 0
    assert storage.entries == [{"Key": "del/one.pdf.neighbour", "VersionId": "v2"}]
    assert storage.markers == []
    assert len(storage.deleted) == 2
    assert await process_deletion_jobs(session, s3=storage) == 0
    repeated = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    assert repeated.id == own.id and repeated.attempts == 1
    assert len(storage.deleted) == 2
    fences = list((await session.scalars(select(DeletionFence).where(DeletionFence.job_id == own.id))).all())
    assert {f.subject_type for f in fences} == {"sow", "sow_version"}


def test_cleanup_errors_do_not_claim_success():
    class RejectedDelete(VersionedStorage):
        def delete_objects(self, **kwargs):
            return {"Errors": [{"Code": "AccessDenied", "Key": "del/one.pdf"}]}

    with pytest.raises(RuntimeError):
        remove_object_versions(RejectedDelete(), "qa-owned-bucket", "del/one.pdf")
