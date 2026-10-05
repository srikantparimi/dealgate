"""Retryable exact-key cleanup; database absence never implies object removal."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.models.deletion import DeletionJob


def remove_object_versions(s3, bucket, key):
    if not bucket:
        raise ValueError("Original storage bucket is unresolved")
    objects = []
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=key):
        objects.extend({"Key": key, "VersionId": row["VersionId"]}
                       for row in page.get("Versions", []) + page.get("DeleteMarkers", []) if row["Key"] == key)
    # Unversioned objects are returned with VersionId="null". An empty listing
    # is already clean; a key-only delete could create a new versioned marker.
    for start in range(0, len(objects), 1000):
        result = s3.delete_objects(Bucket=bucket, Delete={"Objects": objects[start:start + 1000]})
        if result.get("Errors"):
            raise RuntimeError("Object storage reported incomplete deletion")
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=key):
        if any(row["Key"] == key for row in page.get("Versions", []) + page.get("DeleteMarkers", [])):
            raise RuntimeError("Object versions remain after cleanup")


async def process_deletion_jobs(session, *, s3=None, limit=25):
    from app.audit import append_audit
    from app.integrations.s3_sow import _client
    from app.services.deletion_storage import key_is_referenced

    tenant = os.environ.get("DEALGATE_TENANT_ID")
    environment = os.environ.get("DEALGATE_ENV", "local")
    if not tenant and environment not in {"local", "test"}:
        raise ValueError("Cleanup requires an explicit tenant")
    tenant = tenant or "local"
    handled = 0
    for _ in range(limit):
        job = await session.scalar(select(DeletionJob).where(
            DeletionJob.tenant_id == tenant, DeletionJob.environment == environment,
            DeletionJob.status.in_(("pending", "failed")), DeletionJob.attempts < 5,
            or_(DeletionJob.next_attempt_at.is_(None), DeletionJob.next_attempt_at <= datetime.now(UTC))
        ).order_by(DeletionJob.created_at).limit(1).with_for_update(skip_locked=True))
        if job is None:
            break
        try:
            dependencies = job.summary.get("child_job_ids", [])
            if not isinstance(dependencies, list):
                raise ValueError("Invalid dependency list")
            child_ids = [uuid.UUID(value) for value in dependencies]
        except (ValueError, TypeError, AttributeError):
            job.attempts += 1
            job.status = "failed"
            job.last_error = "Invalid cleanup dependency manifest"
            job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=60)
            await append_audit(session, actor_id=None, action=f"{job.subject_type}.cleanup_failed",
                entity="deletion_job", entity_id=str(job.id), before=None,
                after={"attempt": job.attempts, "status": job.status, "reason": job.last_error})
            await session.commit()
            handled += 1
            continue
        if child_ids:
            children = (await session.scalars(select(DeletionJob).where(
                DeletionJob.id.in_(child_ids), DeletionJob.tenant_id == tenant,
                DeletionJob.environment == environment))).all()
            if len(children) != len(child_ids) or any(child.status == "failed" for child in children):
                job.status = "failed"
                job.last_error = "Dependent cleanup is incomplete; retry the parent deletion"
                job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=60)
                await session.commit()
                handled += 1
                continue
            if any(child.status != "done" for child in children):
                job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30)
                await session.commit()
                handled += 1
                continue
        job.attempts += 1
        try:
            client = s3 or _client()
            for item in job.objects:
                if await key_is_referenced(session, item["bucket"], item["key"]):
                    continue
                await asyncio.to_thread(remove_object_versions, client, item["bucket"], item["key"])
            job.status, job.last_error, job.next_attempt_at = "done", None, None
            job.objects = []
            job.completed_at = datetime.now(UTC)
        except Exception as exc:
            job.status = "failed"
            job.last_error = f"{type(exc).__name__}: storage cleanup incomplete"
            job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=30 * (2 ** (job.attempts - 1)))
        await append_audit(session, actor_id=None, action=f"{job.subject_type}.cleanup_{job.status}", entity="deletion_job",
            entity_id=str(job.id), before=None, after={"attempt": job.attempts, "status": job.status})
        await session.commit()
        handled += 1
    return handled
