"""Acceptance tests for S7 story B — Teams/Slack retired as delivery channels.

Given/When/Then:

- Given a PATCH to enable a disabled channel (``teams`` / ``slack``),
  when the API receives it, then respond 422 "channel disabled".
- Given a legacy ``notification_setting`` row with ``teams=true`` in the
  DB, when ``queue_notification`` runs, then the teams row lands as
  ``suppressed`` with ``last_error="channel disabled"`` — no crash, no
  attempt to deliver.
- Given a GET on ``/notifications/settings``, when the response is
  materialised, then the ``channels`` list omits ``teams`` and ``slack``
  and the matrix has no rows for those channels.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio

from app.db import get_session
from app.main import app as main_app
from app.models.notification import NotificationSetting
from app.models.user import User
from app.services.notifications import (
    ACTIVE_CHANNELS,
    NOTIFICATION_CHANNELS,
    STATUS_PENDING,
    STATUS_SUPPRESSED,
    queue_notification,
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
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")


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


# --- PATCH rejects disabled channel --------------------------------------


@pytest.mark.parametrize("channel", ["teams", "slack"])
async def test_patch_notification_setting_rejects_disabled_channel(
    app_with_session, session, alice, channel
):
    async with _client(app_with_session) as c:
        r = await c.patch(
            "/notifications/settings",
            headers={"X-Test-User": "alice@smartek21.com"},
            json={"category": "task_assigned", "channel": channel, "enabled": True},
        )
    assert r.status_code == 422
    assert r.json()["detail"] == "channel disabled"


# --- legacy row still queues cleanly --------------------------------------


async def test_legacy_teams_setting_row_queues_as_suppressed(session, alice):
    """A row from before S7 with ``teams=true`` must not resurrect the channel.

    The queue writes the ``teams`` row anyway (schema + audit compat) but
    forces ``status=suppressed`` and ``last_error="channel disabled"``.
    """

    # Seed the legacy row directly — the API would 422 today, but the DB
    # cannot: existing installs may have Teams rows from before the story.
    session.add(
        NotificationSetting(
            user_id=alice.id,
            category="task_assigned",
            channel="teams",
            enabled=True,
        )
    )
    await session.commit()

    rows = await queue_notification(
        session,
        user_id=alice.id,
        category="task_assigned",
        subject="s",
        body_md="b",
    )
    await session.commit()

    by_channel = {r.channel: r for r in rows}
    assert set(by_channel) == set(NOTIFICATION_CHANNELS)

    teams = by_channel["teams"]
    assert teams.status == STATUS_SUPPRESSED
    assert teams.last_error == "channel disabled"
    assert teams.next_attempt_at is None

    slack = by_channel["slack"]
    assert slack.status == STATUS_SUPPRESSED
    assert slack.last_error == "channel disabled"

    # Active channels still queue pending.
    for ch in ACTIVE_CHANNELS:
        assert by_channel[ch].status == STATUS_PENDING


# --- settings matrix omits disabled channels ------------------------------


async def test_get_notification_settings_matrix_omits_teams_and_slack(
    app_with_session, session, alice
):
    async with _client(app_with_session) as c:
        r = await c.get(
            "/notifications/settings",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()

    assert "teams" not in body["channels"]
    assert "slack" not in body["channels"]
    assert set(body["channels"]) == set(ACTIVE_CHANNELS)

    channels_in_matrix = {row["channel"] for row in body["items"]}
    assert "teams" not in channels_in_matrix
    assert "slack" not in channels_in_matrix
    assert channels_in_matrix == set(ACTIVE_CHANNELS)


async def test_matrix_ignores_legacy_teams_row(app_with_session, session, alice):
    """Even if a Teams row exists in the DB it must not appear in the API."""

    session.add(
        NotificationSetting(
            user_id=alice.id,
            category="task_assigned",
            channel="teams",
            enabled=True,
        )
    )
    await session.commit()

    async with _client(app_with_session) as c:
        r = await c.get(
            "/notifications/settings",
            headers={"X-Test-User": "alice@smartek21.com"},
        )
    assert r.status_code == 200
    channels_in_matrix = {row["channel"] for row in r.json()["items"]}
    assert channels_in_matrix == set(ACTIVE_CHANNELS)
