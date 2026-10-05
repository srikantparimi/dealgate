"""CO-09 parent deletion cannot bypass retained facts or durable cleanup."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.actual import FinancialActual, FinancialImportBatch
from app.models.approval import ApprovalPackage
from app.models.client import Agreement, Client
from app.models.deletion import DeletionJob
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import Sow
from app.services.deletion import DeletionError, delete_client
from tests.test_deletion_by_state import _seed


@pytest.fixture(autouse=True)
def parent_scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "test")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "parent-delete")
    monkeypatch.setenv("SOW_BUCKET", "parent-sows")
    monkeypatch.setenv("AGREEMENTS_BUCKET", "parent-agreements")


@pytest.mark.asyncio
async def test_legacy_client_entry_retains_project_and_exact_account_actuals(session):
    owner, deal, sow = await _seed(session, with_package=True)
    account_id = deal.client_id
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    baseline = {"revenue_us": "24680.12", "cost_us": "12340.06"}
    project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=account_id,
        sow_version_id=package.sow_version_id, gm_model_id=package.gm_model_id, package_id=package.id,
        title="Retained parent delivery", baseline_snapshot_json=baseline, created_by=owner.id)
    batch = FinancialImportBatch(id=uuid.uuid4(), tenant_id="parent-delete", environment="test",
        source_system="parent-proof", request_key="parent-import", request_hash="a" * 64,
        uploaded_by=owner.id, status="committed", row_count=1)
    session.add_all([project, batch])
    await session.flush()
    fact = FinancialActual(id=uuid.uuid4(), tenant_id="parent-delete", environment="test",
        source_system="parent-proof", source_id="retained-fact", revision=1, batch_id=batch.id,
        account_id=account_id, original_account_id=account_id, gm_model_id=package.gm_model_id,
        original_gm_model_id=package.gm_model_id, period_month=date(2026, 9, 1),
        measure="recognized_revenue", amount=Decimal("24680.125"), currency="USD",
        source_date=date(2026, 9, 30), reason="Independent known recognized amount")
    session.add(fact)
    await session.commit()
    await delete_client(session, actor_id=owner.id, client_id=account_id)
    await session.commit()
    await session.refresh(project)
    await session.refresh(fact)
    assert project.client_id is None and project.opportunity_id is None
    assert project.source_deleted_at and project.retained_source["client_id"] == str(account_id)
    assert project.baseline_snapshot_json == baseline
    assert fact.account_id is None and fact.gm_model_id is None
    assert fact.original_account_id == account_id and fact.amount == Decimal("24680.125")
    assert await session.get(Client, account_id) is None
    assert await session.get(Sow, sow.id) is None


@pytest.mark.asyncio
async def test_empty_mirrored_client_refused_before_any_mutation(session):
    client = Client(name="Mirrored no SOW", hubspot_company_id="mirror-owned")
    session.add(client)
    await session.commit()
    with pytest.raises(DeletionError, match="mirrored"):
        await delete_client(session, actor_id=None, client_id=client.id)
    assert await session.get(Client, client.id) is not None


@pytest.mark.asyncio
async def test_parent_job_waits_for_child_storage_and_is_repeat_safe(session):
    from app.services.parent_deletion import request_client_deletion
    from app.services.deletion_cleanup import process_deletion_jobs
    owner, deal, _ = await _seed(session, with_package=False)
    account_id = deal.client_id
    job = await request_client_deletion(session, actor_id=owner.id, client_id=account_id)
    await session.commit()
    assert job.subject_type == "client" and job.subject_id == account_id and job.sow_id is None
    assert job.status == "pending" and job.summary["source_deleted"]
    repeated = await request_client_deletion(session, actor_id=owner.id, client_id=account_id)
    assert repeated.id == job.id

    class Failure:
        def get_paginator(self, name):
            raise OSError("Storage unavailable")

    await process_deletion_jobs(session, s3=Failure(), limit=10)
    await session.refresh(job)
    assert job.status != "done"
    children = (await session.scalars(select(DeletionJob).where(DeletionJob.sow_id.is_not(None)))).all()
    assert len(children) == 1 and children[0].status == "failed"
    assert await session.get(Client, account_id) is None


@pytest.mark.asyncio
async def test_agreement_only_client_has_durable_exact_key_cleanup(session):
    from app.services.parent_deletion import request_client_deletion
    client = Client(name="Only agreements")
    session.add(client)
    await session.flush()
    session.add(Agreement(client_id=client.id, kind="MSA", file_key="owned/msa.pdf",
        filename="msa.pdf", file_size=10, uploaded_by=uuid.uuid4()))
    await session.commit()
    job = await request_client_deletion(session, actor_id=None, client_id=client.id)
    await session.commit()
    assert job.status == "pending" and job.objects == [{"bucket": "parent-agreements", "key": "owned/msa.pdf"}]
    assert job.summary["counts"]["agreements"] == 1
    assert await session.get(Client, client.id) is None
