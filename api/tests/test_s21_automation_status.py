"""Cost-free operational status and explicit bounded retry under current authority."""
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.automation import AutomationJob
from app.services.automation_jobs import RetryInput, list_jobs, process_jobs, retry_job
from tests.test_s21_automation_jobs import enabled
from tests.test_s21_people_company_x import engine, isolated_scope  # noqa: F401


async def test_status_exposes_persisted_success_and_no_financial_data(session):
    actor, *_ = await enabled(session)
    pending = await list_jobs(session, actor=actor)
    assert pending["items"][0]["status"] == "pending" and pending["last_success_at"] is None
    assert pending["items"][0]["can_retry"] is False
    await process_jobs(session)
    done = await list_jobs(session, actor=actor)
    assert done["items"][0]["status"] == "done" and done["last_success_at"] is not None
    assert not any(field in str(done) for field in ("salary", "cost_rate", "bill_rate", "margin"))


async def test_failed_job_can_be_explicitly_requeued_once_without_resetting_attempts(session):
    actor, *_ = await enabled(session)
    job = await session.scalar(select(AutomationJob))
    job.status, job.attempts = "failed", 2
    job.next_attempt_at = datetime.now(UTC) + timedelta(days=1)
    job.last_error = "Synthetic input fault"
    await session.commit()
    assert (await list_jobs(session, actor=actor))["items"][0]["can_retry"] is True
    body = RetryInput(expected_attempts=2, reason="Source repaired and reviewed")
    result = await retry_job(session, actor=actor, job_id=job.id, body=body)
    assert result["status"] == "pending" and result["attempts"] == 2
    assert result["next_attempt_at"] is None
    with pytest.raises(HTTPException) as replay:
        await retry_job(session, actor=actor, job_id=job.id, body=body)
    assert replay.value.status_code == 409


async def test_foreign_scope_cannot_read_or_retry_job(session, monkeypatch):
    actor, *_ = await enabled(session)
    job = await session.scalar(select(AutomationJob))
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert (await list_jobs(session, actor=actor))["items"] == []
    with pytest.raises(HTTPException) as denied:
        await retry_job(session, actor=actor, job_id=job.id,
            body=RetryInput(expected_attempts=0, reason="Foreign retry attempt"))
    assert denied.value.status_code == 404


async def test_exhausted_job_cannot_reset_bounded_attempt_history(session):
    actor, *_ = await enabled(session)
    job = await session.scalar(select(AutomationJob))
    job.status, job.attempts = "dead", 5
    await session.commit()
    assert (await list_jobs(session, actor=actor))["items"][0]["can_retry"] is False
    with pytest.raises(HTTPException) as refused:
        await retry_job(session, actor=actor, job_id=job.id,
            body=RetryInput(expected_attempts=5, reason="Attempt to erase retry budget"))
    assert refused.value.status_code == 409
