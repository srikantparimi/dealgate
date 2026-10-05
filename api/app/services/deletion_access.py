"""Keep deletion jobs and their source records inside the viewer's runtime scope."""

import os

from fastapi import HTTPException
from sqlalchemy import select

from app.models.deletion import DeletionJob
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow
from app.services.test_fixtures import account_scope, is_test_user, user_allowed


async def load_job(session, user, *, job_id=None, sow_id=None, subject_type=None, subject_id=None, lock=False):
    environment = os.environ.get("DEALGATE_ENV", "local")
    tenant = os.environ.get("DEALGATE_TENANT_ID")
    if not tenant and environment in {"local", "test"}:
        tenant = "local"
    query = select(DeletionJob).where(DeletionJob.tenant_id == tenant, DeletionJob.environment == environment)
    if job_id:
        query = query.where(DeletionJob.id == job_id)
    elif subject_type and subject_id:
        query = query.where(DeletionJob.subject_type == subject_type, DeletionJob.subject_id == subject_id)
    else:
        query = query.where(DeletionJob.sow_id == sow_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    job = await session.scalar(query)
    if job is None:
        raise HTTPException(404, "Deletion job not found")
    fixture = bool(job.summary.get("test_fixture"))
    if is_test_user(user) != fixture or (fixture and job.actor_id != user.id):
        raise HTTPException(404, "Deletion job not found")
    return job


async def authorize_sow(session, user, sow_id):
    sow = await session.get(Sow, sow_id)
    if sow is None:
        return await load_job(session, user, sow_id=sow_id)
    deal = await session.get(Opportunity, sow.opportunity_id)
    if deal is None or not user_allowed(user, await account_scope(session, deal.client_id, opportunity_id=deal.id)):
        raise HTTPException(404, "SOW not found")
    return None


async def authorize_parent(session, user, kind, identity):
    model = Client if kind == "client" else Opportunity
    record = await session.get(model, identity)
    if record is None:
        return await load_job(session, user, subject_type=kind, subject_id=identity)
    account_id = record.id if kind == "client" else record.client_id
    scope = await account_scope(session, account_id,
        opportunity_id=record.id if kind == "opportunity" else None) if account_id else None
    if not user_allowed(user, scope):
        raise HTTPException(404, "Deletion source not found")
    return None
