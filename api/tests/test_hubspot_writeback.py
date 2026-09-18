"""Acceptance tests for the HubSpot write-back service + worker (S4-E2).

Covers every Given/When/Then in docs/backlog/s4-e2-hubspot-writeback.md:

- queue_writeback + process_pending flip the job to ``sent`` and the stub
  HubSpot client records exactly the three governance properties.
- HubSpot 429 → job stays ``pending`` and next_attempt_at is scheduled.
- HubSpot 404 → job moves to ``deal_missing``; audit
  ``hubspot_write.deal_missing`` on the chain.
- MAX_ATTEMPTS exhausted → status ``failed``; audit ``hubspot_write.failed``.
- Properties outside the MAP are rejected by ``queue_writeback`` (HTTP 422)
  AND by the worker's second-line guard.
- The ``on_package_ready_to_sign`` hook queues one job.

All assertions include ``verify_chain`` so a regression in audit ordering
fails the test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.audit import verify_chain
from app.integrations.hubspot import StubHubSpotClient
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.hubspot_writeback import HubspotWritebackJob
from app.models.opportunity import Opportunity
from app.models.user import User

# Registering scheduler ledger so create_all works when this test runs alone.
from app.scheduler.ledger import SchedulerFired  # noqa: F401
from app.services.hubspot_writeback import (
    MAP,
    MAX_ATTEMPTS,
    STATUS_DEAL_MISSING,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    on_package_ready_to_sign,
    process_pending,
    queue_writeback,
)

DEAL_ID = "9001"


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def owner(session):
    u = User(
        id=_uid("owner@smartek21.com"),
        email="owner@smartek21.com",
        name="Owner",
        groups=["Sales"],
    )
    session.add(u)
    await session.commit()
    return u


@pytest_asyncio.fixture
async def opportunity(session, owner):
    opp = Opportunity(
        hubspot_deal_id=DEAL_ID,
        owner_id=owner.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.commit()
    await session.refresh(opp)
    return opp


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("PATCH", f"http://stub/crm/v3/objects/deals/{DEAL_ID}")
    resp = httpx.Response(status_code=status_code, request=req)
    return httpx.HTTPStatusError(
        f"{status_code} error", request=req, response=resp
    )


# --- happy path ---------------------------------------------------------


async def test_queue_and_process_sends_three_governance_properties(
    session, opportunity
):
    await queue_writeback(
        session,
        opportunity,
        {
            "governance_status": "Ready to Sign",
            "approved_gm_pct": 0.4275,
            "dealgate_link": "https://dealgate.example.com/opps/" + str(opportunity.id),
        },
    )
    await session.commit()

    hubspot = StubHubSpotClient()
    processed = await process_pending(session, hubspot)
    assert processed == 1
    assert len(hubspot.updates) == 1
    payload = hubspot.updates[0]
    assert payload["deal_id"] == DEAL_ID
    # Only the three HubSpot property names — nothing else may reach the wire.
    assert set(payload["properties"].keys()) == {
        "dealgate_governance_status",
        "dealgate_approved_gm_pct",
        "dealgate_link",
    }
    assert payload["properties"]["dealgate_governance_status"] == "Ready to Sign"
    assert payload["properties"]["dealgate_approved_gm_pct"] == pytest.approx(0.4275)

    job = (
        await session.execute(select(HubspotWritebackJob))
    ).scalar_one()
    await session.refresh(job)
    assert job.status == STATUS_SENT
    assert job.attempts == 1
    assert job.sent_at is not None

    # Second run is a no-op — the row is no longer pending.
    processed_again = await process_pending(session, hubspot)
    assert processed_again == 0
    assert len(hubspot.updates) == 1

    assert await verify_chain(session) is True


# --- 429 → stays pending, backoff scheduled -----------------------------


async def test_hubspot_429_keeps_job_pending_with_backoff(session, opportunity):
    await queue_writeback(
        session,
        opportunity,
        {"governance_status": "Ready to Sign"},
    )
    await session.commit()

    hubspot = StubHubSpotClient()
    hubspot.update_error = _make_http_error(429)
    processed = await process_pending(session, hubspot)
    assert processed == 1

    job = (
        await session.execute(select(HubspotWritebackJob))
    ).scalar_one()
    await session.refresh(job)
    assert job.status == STATUS_PENDING
    assert job.attempts == 1
    assert job.next_attempt_at is not None
    na = job.next_attempt_at
    if na.tzinfo is None:
        na = na.replace(tzinfo=UTC)
    assert na > datetime.now(UTC)

    # Audit trail records the retry attempt.
    retries = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "hubspot_write.retry")
            )
        )
        .scalars()
        .all()
    )
    assert len(retries) == 1
    assert await verify_chain(session) is True


# --- 404 → deal_missing --------------------------------------------------


async def test_hubspot_404_marks_deal_missing(session, opportunity):
    await queue_writeback(
        session,
        opportunity,
        {"governance_status": "Ready to Sign"},
    )
    await session.commit()

    hubspot = StubHubSpotClient()
    hubspot.update_error = _make_http_error(404)
    processed = await process_pending(session, hubspot)
    assert processed == 1

    job = (
        await session.execute(select(HubspotWritebackJob))
    ).scalar_one()
    await session.refresh(job)
    assert job.status == STATUS_DEAL_MISSING
    assert job.next_attempt_at is None
    assert job.last_error and "404" in job.last_error

    missing = (
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "hubspot_write.deal_missing"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(missing) == 1
    assert await verify_chain(session) is True


# --- MAX_ATTEMPTS → failed -----------------------------------------------


async def test_max_attempts_exhausted_marks_failed(session, opportunity):
    await queue_writeback(
        session,
        opportunity,
        {"governance_status": "Ready to Sign"},
    )
    await session.commit()

    job = (
        await session.execute(select(HubspotWritebackJob))
    ).scalar_one()
    # Fast-forward: pretend this row already exhausted every retry but one.
    job.attempts = MAX_ATTEMPTS - 1
    job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    hubspot = StubHubSpotClient()
    hubspot.update_error = _make_http_error(500)
    await process_pending(session, hubspot)
    await session.refresh(job)
    assert job.status == STATUS_FAILED
    assert job.attempts == MAX_ATTEMPTS
    assert job.next_attempt_at is None

    fails = (
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "hubspot_write.failed")
            )
        )
        .scalars()
        .all()
    )
    assert len(fails) == 1
    assert await verify_chain(session) is True

    # Worker never picks it up again.
    hubspot.update_error = None
    assert await process_pending(session, hubspot) == 0
    assert hubspot.updates == []


# --- allow-list enforcement ---------------------------------------------


async def test_queue_writeback_rejects_property_outside_map(session, opportunity):
    with pytest.raises(HTTPException) as exc:
        await queue_writeback(
            session,
            opportunity,
            {
                "governance_status": "Ready to Sign",
                # Anything HubSpot owns as master is off-limits.
                "dealname": "New name",
            },
        )
    assert exc.value.status_code == 422
    assert "dealname" in str(exc.value.detail)
    # And no job row was written.
    jobs = (
        await session.execute(select(HubspotWritebackJob))
    ).scalars().all()
    assert jobs == []


async def test_worker_second_line_guard_rejects_bad_target_state(
    session, opportunity
):
    """Even if a row is inserted by-hand with a bad key, the worker refuses.

    Belt-and-braces: :func:`queue_writeback` validates at write time; this
    proves :func:`process_pending` also validates before the outbound call.
    """

    hand_written = HubspotWritebackJob(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        hubspot_deal_id=opportunity.hubspot_deal_id,
        target_state={"dealname": "sneaky"},
        status=STATUS_PENDING,
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(hand_written)
    await session.commit()

    hubspot = StubHubSpotClient()
    await process_pending(session, hubspot)
    # Nothing reached HubSpot.
    assert hubspot.updates == []
    await session.refresh(hand_written)
    # Attempts bumped, error recorded, and status not ``sent``.
    assert hand_written.status in (STATUS_PENDING, STATUS_FAILED)
    assert hand_written.attempts == 1
    assert hand_written.last_error and "dealname" in hand_written.last_error


# --- MAP shape ----------------------------------------------------------


def test_map_contains_exactly_three_governance_properties():
    assert set(MAP.keys()) == {
        "governance_status",
        "approved_gm_pct",
        "dealgate_link",
    }
    assert set(MAP.values()) == {
        "dealgate_governance_status",
        "dealgate_approved_gm_pct",
        "dealgate_link",
    }


# --- Agent U hook -------------------------------------------------------


async def test_on_package_ready_to_sign_queues_job(session, opportunity, owner):
    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opportunity.id,
        sow_version_id=uuid.uuid4(),
        gm_model_id=uuid.uuid4(),
        package_hash="hash-abc",
        status="ready_to_sign",
        submitted_by=owner.id,
        released_at=datetime.now(UTC),
    )
    session.add(package)
    await session.flush()

    await on_package_ready_to_sign(
        session,
        opportunity,
        blended_gm_pct=Decimal("0.4275"),
        dealgate_link="https://dealgate.example.com/opps/" + str(opportunity.id),
    )
    await session.commit()

    jobs = (
        await session.execute(
            select(HubspotWritebackJob).where(
                HubspotWritebackJob.opportunity_id == opportunity.id
            )
        )
    ).scalars().all()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == STATUS_PENDING
    assert job.target_state["governance_status"] == "Ready to Sign"
    assert job.target_state["approved_gm_pct"] == pytest.approx(0.4275)
    assert job.target_state["dealgate_link"].startswith("https://")

    # Chain still intact after the queued audit row.
    assert await verify_chain(session) is True


# --- worker main module wiring -----------------------------------------


def test_worker_module_exposes_main():
    from worker import hubspot_writeback as w

    assert callable(w.main)
    assert w.POLL_INTERVAL_SECONDS > 0
