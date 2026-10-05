"""Minimal source identities retained to reject delayed work after deletion."""

import hashlib
import os
import uuid

from sqlalchemy import select, text

from app.models.deletion import DeletionFence


async def lock_source(session, subject_type, subject_id):
    """Serialize late producers with deletion without retaining source content."""
    if not subject_type or not subject_id or session.bind.dialect.name != "postgresql":
        return
    scope = (os.environ.get("DEALGATE_TENANT_ID", "local"),
             os.environ.get("DEALGATE_ENV", "local"), subject_type, str(subject_id))
    key = int.from_bytes(hashlib.sha256("deletion:".encode() + "|".join(scope).encode()).digest()[:8],
                         "big", signed=True)
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


async def source_deleted(session, subject_type, subject_id):
    if not subject_type or not subject_id:
        return False
    try:
        identity = uuid.UUID(str(subject_id))
    except ValueError:
        return False
    environment = os.environ.get("DEALGATE_ENV", "local")
    tenant = os.environ.get("DEALGATE_TENANT_ID")
    if not tenant and environment in {"local", "test"}:
        tenant = "local"
    return await session.scalar(select(DeletionFence.job_id).where(
        DeletionFence.tenant_id == tenant, DeletionFence.environment == environment,
        DeletionFence.subject_type == subject_type, DeletionFence.subject_id == identity,
    )) is not None
