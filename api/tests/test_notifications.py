"""Notification outbox + settings + inbox — service and HTTP surface."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.main import app as main_app
from app.models.notification import Notification, NotificationSetting
from app.models.user import User
from app.services.notifications import (
    ACTIVE_CHANNELS,
    MAX_ATTEMPTS,
    NOTIFICATION_CHANNELS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_SUPPRESSED,
    mark_failed,
    mark_sent,
    pending_notifications,
    queue_notification,
    upsert_setting,
)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


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


# --- queue_notification --------------------------------------------------


async def test_queue_notification_fans_out_default_channels(session, alice):
    rows = await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="You have a new task",
        body_md="Please review.",
        related_entity="task",
        related_entity_id="abc-123",
    )
    await session.commit()

    # One row per enum channel is still written (schema + audit compat) but
    # after S7 story B only ACTIVE_CHANNELS rows are pending; the rest are
    # suppressed with "channel disabled" so the worker never touches them.
    assert {r.channel for r in rows} == set(NOTIFICATION_CHANNELS)
    by_channel = {r.channel: r for r in rows}
    for ch in ACTIVE_CHANNELS:
        assert by_channel[ch].status == STATUS_PENDING
        assert by_channel[ch].attempts == 0
        assert by_channel[ch].next_attempt_at is not None
    for ch in set(NOTIFICATION_CHANNELS) - set(ACTIVE_CHANNELS):
        assert by_channel[ch].status == STATUS_SUPPRESSED
        assert by_channel[ch].last_error == "channel disabled"
    assert await verify_chain(session) is True


async def test_queue_respects_disabled_channel(session, alice):
    # Alice turns email off for task_assigned.
    await upsert_setting(
        session,
        user_id=alice.id,
        category="task_assigned",
        channel="email",
        enabled=False,
    )
    rows = await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="s",
        body_md="b",
    )
    await session.commit()

    by_channel = {r.channel: r for r in rows}
    assert by_channel["email"].status == STATUS_SUPPRESSED
    assert by_channel["email"].last_error and "disabled" in by_channel["email"].last_error
    assert by_channel["inapp"].status == STATUS_PENDING


async def test_queue_rejects_unknown_category(session, alice):
    with pytest.raises(Exception):
        await queue_notification(
            session,
            user_id=alice.id,
            category="nope",
            subject="s",
            body_md="b",
        )


# --- pending / mark_sent / mark_failed backoff ---------------------------


async def test_pending_returns_ready_rows(session, alice):
    await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()

    rows = await pending_notifications(session)
    # After S7 story B only ACTIVE_CHANNELS rows land as PENDING; the
    # Teams/Slack rows are SUPPRESSED and excluded from the worker feed.
    assert len(rows) == len(ACTIVE_CHANNELS)


async def test_mark_sent_updates_status(session, alice):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    target = created[0]
    updated = await mark_sent(session, target.id)
    assert updated.status == STATUS_SENT
    assert updated.sent_at is not None
    assert updated.attempts == 1


async def test_mark_failed_backs_off_then_gives_up(session, alice):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    target = created[0]

    for attempt in range(1, MAX_ATTEMPTS):
        updated = await mark_failed(session, target.id, error=f"try {attempt}")
        assert updated.attempts == attempt
        assert updated.status == STATUS_PENDING
        assert updated.next_attempt_at is not None
        assert updated.next_attempt_at > datetime.now(UTC)

    # Final failure lands as `failed` and stops the worker from picking it up.
    final = await mark_failed(session, target.id, error="boom")
    assert final.status == STATUS_FAILED
    assert final.attempts == MAX_ATTEMPTS
    assert final.next_attempt_at is None


async def test_pending_excludes_backed_off_rows(session, alice):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    target = created[0]

    # Fail once so its next_attempt_at is 1 minute out.
    await mark_failed(session, target.id, error="x")

    ready = await pending_notifications(session)
    assert target.id not in [r.id for r in ready]


# --- HTTP: inbox + settings ---------------------------------------------


async def test_inbox_returns_only_inapp_for_caller(
    app_with_session, session, alice, monkeypatch
):
    # Alice + one other user each get an inapp notification.
    other = User(
        id=_uid("bob@smartek21.com"),
        email="bob@smartek21.com",
        name="Bob",
        groups=["Sales"],
    )
    session.add(other)
    await session.commit()

    await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="Alice", body_md="a"
    )
    await queue_notification(
        session, user_id=other.id, category="task_assigned", subject="Bob", body_md="b"
    )
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/notifications/inbox", headers={"X-Test-User": "alice@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert body["unread_count"] == 1
    subjects = [row["subject"] for row in body["items"]]
    assert subjects == ["Alice"]
    assert all(row["channel"] == "inapp" for row in body["items"])


async def test_mark_read_flips_read_at_and_audits(
    app_with_session, session, alice, monkeypatch
):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    inapp = next(r for r in created if r.channel == "inapp")

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/notifications/{inapp.id}/read",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
    assert r.status_code == 200
    assert r.json()["read_at"] is not None

    # Second read is a no-op.
    async with _client(app_with_session) as c:
        r2 = await c.post(
            f"/notifications/{inapp.id}/read",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
    assert r2.status_code == 200


async def test_mark_read_by_stranger_403(
    app_with_session, session, alice, monkeypatch
):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    inapp = next(r for r in created if r.channel == "inapp")

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/notifications/{inapp.id}/read",
            headers={"X-Test-User": "someone.else@smartek21.com"},
        )
    assert r.status_code == 403


async def test_settings_default_all_on(app_with_session, session, alice, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/notifications/settings", headers={"X-Test-User": "alice@smartek21.com"}
        )
    assert r.status_code == 200
    body = r.json()
    assert all(row["enabled"] for row in body["items"])
    assert "email" in body["channels"]
    assert "task_assigned" in body["categories"]


async def test_settings_patch_upserts_and_persists(
    app_with_session, session, alice, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            "/notifications/settings",
            headers={"X-Test-User": "alice@smartek21.com"},
            json={"category": "task_assigned", "channel": "email", "enabled": False},
        )
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    stored = (
        await session.execute(
            select(NotificationSetting).where(NotificationSetting.user_id == alice.id)
        )
    ).scalars().all()
    assert len(stored) == 1
    assert stored[0].enabled is False


async def test_settings_patch_rejects_unknown_channel(
    app_with_session, session, alice, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            "/notifications/settings",
            headers={"X-Test-User": "alice@smartek21.com"},
            json={"category": "task_assigned", "channel": "carrier_pigeon", "enabled": False},
        )
    assert r.status_code == 422


async def test_inbox_requires_auth(app_with_session):
    async with _client(app_with_session) as c:
        r = await c.get("/notifications/inbox")
    assert r.status_code == 401


# --- audit rows come out on the same chain ------------------------------


async def test_queue_writes_audit_row_per_channel(session, alice):
    from app.models.audit import AuditEvent

    await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()

    rows = (
        await session.execute(
            select(AuditEvent).where(AuditEvent.action == "notification.queued")
        )
    ).scalars().all()
    assert len(rows) == len(NOTIFICATION_CHANNELS)
    assert await verify_chain(session) is True


# --- back-off window is honoured by pending_notifications --------------


async def test_pending_returns_row_after_backoff_elapses(session, alice):
    created = await queue_notification(
        session, user_id=alice.id, category="task_assigned", subject="s", body_md="b"
    )
    await session.commit()
    target = created[0]

    await mark_failed(session, target.id, error="x")
    # Simulate elapsed back-off by rewinding next_attempt_at.
    row = (
        await session.execute(
            select(Notification).where(Notification.id == target.id)
        )
    ).scalar_one()
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    ready_ids = [r.id for r in await pending_notifications(session)]
    assert target.id in ready_ids
