"""Public deletion outcomes remain authorized, durable and honest about cleanup."""

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.auth.deps import current_user
from app.auth import AuthUser
from app.db import get_session
from app.main import app
from app.models.sow import Sow
from tests.test_deletion_by_state import _seed


@pytest_asyncio.fixture
async def deletion_api(session, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "deletion-api")
    monkeypatch.setenv("SOW_BUCKET", "unit-owned")
    owner, _, sow = await _seed(session, with_package=True)
    await session.commit()
    async def database():
        yield session
    app.dependency_overrides[get_session] = database
    app.dependency_overrides[current_user] = lambda: AuthUser(owner.id, owner.email, owner.name, ("Finance",))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client, owner, sow
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(current_user, None)


@pytest.mark.asyncio
async def test_governed_delete_returns_pollable_job_without_storage_payload(deletion_api, session):
    client, _, sow = deletion_api
    response = await client.delete(f"/sows/{sow.id}")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "pending" and body["source_deleted"] is True
    assert body["job_id"] and "objects" not in body and "unit-owned" not in response.text
    assert await session.scalar(select(Sow.id).where(Sow.id == sow.id)) is None
    polled = await client.get(f"/deletion-jobs/{body['job_id']}")
    assert polled.status_code == 200 and polled.json()["status"] == "pending"
    repeated = await client.delete(f"/sows/{sow.id}")
    assert repeated.status_code == 202 and repeated.json()["job_id"] == body["job_id"]


@pytest.mark.asyncio
async def test_sales_cannot_delete_or_read_job(deletion_api, session):
    client, owner, sow = deletion_api
    app.dependency_overrides[current_user] = lambda: AuthUser(owner.id, owner.email, owner.name, ("Sales",))
    response = await client.delete(f"/sows/{sow.id}")
    assert response.status_code == 403
    assert await session.get(Sow, sow.id) is not None
    assert (await client.get(f"/deletion-jobs/{sow.id}")).status_code == 403


@pytest.mark.asyncio
async def test_cleanup_job_is_not_visible_across_runtime_tenants(deletion_api, monkeypatch):
    client, _, sow = deletion_api
    deleted = await client.delete(f"/sows/{sow.id}")
    assert deleted.status_code == 202, deleted.text
    monkeypatch.setenv("DEALGATE_TENANT_ID", "different-tenant")
    assert (await client.get(f"/deletion-jobs/{deleted.json()['job_id']}")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["clients", "opportunities"])
async def test_parent_deletion_returns_scoped_repeatable_cleanup_job(deletion_api, session, kind):
    from app.models.opportunity import Opportunity
    client, _, sow = deletion_api
    deal = await session.get(Opportunity, sow.opportunity_id)
    identity = deal.client_id if kind == "clients" else deal.id
    deleted = await client.delete(f"/{kind}/{identity}")
    assert deleted.status_code == 202, deleted.text
    body = deleted.json()
    assert body["status"] == "pending" and body["source_deleted"]
    assert body["subject_type"] == ("client" if kind == "clients" else "opportunity")
    assert "unit-owned" not in deleted.text
    assert (await client.get(f"/deletion-jobs/{body['job_id']}")).status_code == 200
    repeated = await client.delete(f"/{kind}/{identity}")
    assert repeated.status_code == 202 and repeated.json()["job_id"] == body["job_id"]


@pytest.mark.asyncio
async def test_parent_retry_resets_failed_descendants_without_recreating_sources(deletion_api, session):
    from app.models.deletion import DeletionJob
    from app.models.opportunity import Opportunity
    client, _, sow = deletion_api
    deal = await session.get(Opportunity, sow.opportunity_id)
    deleted = await client.delete(f"/clients/{deal.client_id}")
    assert deleted.status_code == 202, deleted.text
    jobs = (await session.scalars(select(DeletionJob))).all()
    assert len(jobs) == 3
    for job in jobs:
        job.status, job.attempts, job.last_error = "failed", 5, "Storage unavailable"
    await session.commit()
    retry = await client.post(f"/deletion-jobs/{deleted.json()['job_id']}/retry")
    assert retry.status_code == 200 and retry.json()["status"] == "pending"
    for job in jobs:
        await session.refresh(job)
        assert job.status == "pending" and job.attempts == 0 and job.last_error is None
    assert await session.scalar(select(Sow.id).where(Sow.id == sow.id)) is None
