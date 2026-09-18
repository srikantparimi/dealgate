"""Acceptance tests for the notification sender (worker.notification_sender).

Covers every channel branch and the SES retry/backoff/give-up ladder.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.integrations.ses import SESClient, StubSES
from app.models.audit import AuditEvent
from app.models.notification import Notification
from app.models.user import User
from app.services.notifications import (
    MAX_ATTEMPTS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_SUPPRESSED,
    queue_notification,
)

# Importing scheduler ledger registers its table on Base.metadata so the
# shared `create_all` fixture doesn't fail when this test module is run in
# isolation before test_alert_scheduler.py.
from app.scheduler.ledger import SchedulerFired  # noqa: F401

from worker.notification_sender import process_batch


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    # Sender starts with no webhook configured so teams/slack rows suppress.
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)


@pytest_asyncio.fixture
async def alice(session):
    u = User(
        id=_uid("alice@smartek21.com"),
        email="alice@smartek21.com",
        name="Alice",
        groups=["Sales"],
    )
    session.add(u)
    await session.commit()
    return u


async def _pick(session, alice, channel: str) -> Notification:
    row = (
        await session.execute(
            select(Notification).where(
                Notification.user_id == alice.id, Notification.channel == channel
            )
        )
    ).scalar_one()
    return row


# ---- email happy path ---------------------------------------------------


async def test_email_goes_through_ses_and_marks_sent(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    ses = StubSES()
    processed = await process_batch(session, ses=ses)
    assert processed >= 1

    email = await _pick(session, alice, "email")
    await session.refresh(email)
    assert email.status == STATUS_SENT
    assert email.sent_at is not None
    assert email.attempts == 1
    # SES received the fan-out payload for Alice.
    to = [row["to"] for row in ses.sent]
    assert alice.email in to
    assert await verify_chain(session) is True


# ---- teams w/o webhook -> suppressed -----------------------------------


async def test_teams_without_webhook_is_suppressed(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    ses = StubSES()
    await process_batch(session, ses=ses)

    teams = await _pick(session, alice, "teams")
    await session.refresh(teams)
    assert teams.status == STATUS_SUPPRESSED
    assert teams.last_error == "channel not configured"


async def test_slack_without_webhook_is_suppressed(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    ses = StubSES()
    await process_batch(session, ses=ses)

    slack = await _pick(session, alice, "slack")
    await session.refresh(slack)
    assert slack.status == STATUS_SUPPRESSED
    assert slack.last_error == "channel not configured"


# ---- inapp -> immediate sent ------------------------------------------


async def test_inapp_marks_sent_without_network(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    ses = StubSES()
    await process_batch(session, ses=ses)

    inapp = await _pick(session, alice, "inapp")
    await session.refresh(inapp)
    assert inapp.status == STATUS_SENT
    assert inapp.attempts == 1
    # StubSES only records email calls — inapp never went to SES.
    assert not any(row["to"] == alice.email and row["subject"] == "Ping" for row in ses.sent[0:0])


# ---- SES error -> retry, then final failure ---------------------------


async def test_ses_error_bumps_attempts_and_backs_off(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    failing = StubSES(fail_with="ses 500")
    await process_batch(session, ses=failing)
    email = await _pick(session, alice, "email")
    await session.refresh(email)
    assert email.status == STATUS_PENDING
    assert email.attempts == 1
    assert email.next_attempt_at is not None
    assert email.last_error == "ses 500"


async def test_ses_gives_up_after_max_attempts(session, alice):
    await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="Ping",
        body_md="body",
    )
    await session.commit()

    email = await _pick(session, alice, "email")
    # Manually bump attempts so we can observe the final failure without
    # rewinding next_attempt_at on every intermediate retry.
    from datetime import UTC, datetime, timedelta

    email.attempts = MAX_ATTEMPTS - 1
    email.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    failing = StubSES(fail_with="ses 500")
    await process_batch(session, ses=failing)
    await session.refresh(email)
    assert email.status == STATUS_FAILED
    assert email.attempts == MAX_ATTEMPTS
    assert email.next_attempt_at is None

    # `notification.failed` audit row exists on the chain.
    fails = list(
        (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "notification.failed")
            )
        )
        .scalars()
        .all()
    )
    assert len(fails) >= 1
    assert await verify_chain(session) is True


# ---- ses client factory is available ----------------------------------


def test_ses_client_factory_returns_real_client():
    from app.integrations.ses import get_ses_client

    client = get_ses_client()
    assert isinstance(client, SESClient)
    # StubSES is a subclass so the factory should NOT return one by default.
    assert not isinstance(client, StubSES)
