"""S21-01/CO-09 durable deletion and retained facts, not archive-only behavior."""

import uuid

import pytest
from sqlalchemy import select

from app.models.deletion import DeletionFence, DeletionJob
from app.models.project import Project
from app.models.sow import Sow
from app.models.approval import ApprovalPackage
from app.services.deletion import request_sow_deletion
from tests.test_deletion_by_state import _seed


@pytest.mark.asyncio
async def test_governed_delete_detaches_project_and_persists_cleanup_before_removal(session, monkeypatch):
    monkeypatch.setenv("SOW_BUCKET", "owned-unit-bucket")
    owner, deal, sow = await _seed(session, with_package=True)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    baseline = {"gm_model_id": str(package.gm_model_id), "revenue_us": "42000", "term_end": "2027-01-01"}
    project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=deal.client_id,
        sow_version_id=package.sow_version_id, gm_model_id=package.gm_model_id, package_id=package.id,
        title="Retained delivery project", baseline_snapshot_json=baseline, created_by=owner.id)
    session.add(project)
    await session.commit()
    result = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    assert result.status == "pending"
    assert await session.scalar(select(Sow.id).where(Sow.id == sow.id)) is None
    await session.refresh(project)
    assert project.package_id is None and project.gm_model_id is None and project.sow_version_id is None
    assert project.source_deleted_at and project.baseline_snapshot_json == baseline
    job = await session.get(DeletionJob, result.id)
    assert job.objects == [{"bucket": "owned-unit-bucket", "key": "del/one.pdf"}]
    fences = list((await session.scalars(select(DeletionFence).where(DeletionFence.job_id == job.id))).all())
    assert {f.subject_type for f in fences} >= {"sow", "sow_version", "gm_model", "approval_package"}
    repeated = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    assert repeated.id == result.id


@pytest.mark.asyncio
async def test_retained_project_remains_visible_with_deleted_source_label(session, monkeypatch):
    from app.auth import AuthUser
    from app.services.projects import list_projects
    owner, deal, sow = await _seed(session, with_package=True)
    package = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.opportunity_id == deal.id))
    project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=deal.client_id,
        sow_version_id=package.sow_version_id, gm_model_id=package.gm_model_id, package_id=package.id,
        title="Retained delivery project", baseline_snapshot_json={"revenue_us": "42000"}, created_by=owner.id)
    session.add(project)
    await session.commit()
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    rows = await list_projects(session, actor=AuthUser(owner.id, owner.email, owner.name, ("Finance",)))
    retained = next(row for row in rows if row["project_id"] == str(project.id))
    assert retained["source_deleted"] is True and retained["title"] == "Retained delivery project"
    assert retained["baseline"] == {"revenue_us": "42000"}


@pytest.mark.asyncio
async def test_external_storage_failure_keeps_job_retryable_and_source_absent(session, monkeypatch):
    from datetime import timedelta
    from app.services.deletion_cleanup import process_deletion_jobs
    monkeypatch.setenv("SOW_BUCKET", "owned-unit-bucket")
    owner, _, sow = await _seed(session, with_package=False)
    job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()

    class StorageFault:
        def get_paginator(self, name):
            raise OSError("External object store unavailable")

    assert await process_deletion_jobs(session, s3=StorageFault()) == 1
    assert job.status == "failed" and job.objects and job.next_attempt_at
    assert await process_deletion_jobs(session, s3=StorageFault()) == 0
    assert await session.scalar(select(Sow.id).where(Sow.id == sow.id)) is None

    class ExactStorage:
        entries = [{"Key": "del/one.pdf", "VersionId": "v1"}, {"Key": "del/one.pdf.other", "VersionId": "v2"}]
        deleted = []
        def get_paginator(self, name):
            return self
        def paginate(self, **kwargs):
            return [{"Versions": self.entries}]
        def delete_objects(self, *, Bucket, Delete):
            self.deleted.extend(Delete["Objects"])
            self.entries = [row for row in self.entries if row not in Delete["Objects"]]
            return {}

    storage = ExactStorage()
    job.next_attempt_at -= timedelta(hours=1)
    await session.commit()
    assert await process_deletion_jobs(session, s3=storage) == 1
    assert job.status == "done" and not job.objects
    assert storage.deleted == [{"Key": "del/one.pdf", "VersionId": "v1"}]
    assert storage.entries == [{"Key": "del/one.pdf.other", "VersionId": "v2"}]


def test_already_absent_object_does_not_create_a_new_delete_marker():
    from app.services.deletion_cleanup import remove_object_versions
    class EmptyBucket:
        def get_paginator(self, name):
            return self
        def paginate(self, **kwargs):
            return [{}]
        def delete_objects(self, **kwargs):
            raise AssertionError("Unversioned delete would create a new marker")
    remove_object_versions(EmptyBucket(), "bucket", "gone.pdf")


@pytest.mark.asyncio
async def test_stale_notification_loaded_before_deletion_never_sends(session):
    from app.models.notification import Notification
    from worker.notification_sender import _handle_row
    owner, _, sow = await _seed(session, with_package=False)
    notification = Notification(id=uuid.uuid4(), user_id=owner.id, category="approval_pending",
        channel="email", subject="Deleted source", body_md="Must not be delivered",
        related_entity="sow", related_entity_id=str(sow.id), status="pending")
    session.add(notification)
    await session.commit()
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()

    class NoDelivery:
        def send(self, **kwargs):
            raise AssertionError("Deleted SOW notification reached external delivery")

    await _handle_row(session, NoDelivery(), notification)
    assert await session.get(Notification, notification.id) is None


@pytest.mark.asyncio
async def test_late_notification_cannot_recreate_deleted_source_content(session):
    from fastapi import HTTPException
    from app.services.notifications import queue_notification
    owner, _, sow = await _seed(session, with_package=False)
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    with pytest.raises(HTTPException) as error:
        await queue_notification(session, user_id=owner.id, category="approval_pending",
            subject="Deleted source", body_md="Must not be recreated", related_entity="sow",
            related_entity_id=str(sow.id), channels=("inapp",))
    assert error.value.status_code == 410


@pytest.mark.asyncio
async def test_deleted_upload_job_cannot_resume_from_a_stale_callback(session):
    from app.models.sow import SowVersion
    from app.models.sow_upload_job import SowUploadJob
    from app.services.sow_upload_job_service import resume_after_pick, UploadPipelineError
    owner, deal, sow = await _seed(session, with_package=False)
    version = await session.scalar(select(SowVersion).where(SowVersion.sow_id == sow.id))
    upload = SowUploadJob(id=uuid.uuid4(), uploader_id=owner.id, file_hash="deleted-job-hash",
        status="done", sow_version_id=version.id, opportunity_id=deal.id, s3_key=version.file_s3_key)
    session.add(upload)
    await session.commit()
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    with pytest.raises(UploadPipelineError, match="deleted"):
        await resume_after_pick(session, job=upload, client_id=deal.client_id, create_new=None)
