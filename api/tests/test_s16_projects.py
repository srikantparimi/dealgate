from datetime import UTC, datetime

import pytest

from app.auth import AuthUser
from tests.test_signed_sow import _seed_ready_to_sign_package, _seed_user
from tests.test_agreements import app_with_session, _client  # noqa: F401


@pytest.mark.asyncio
async def test_projects_excludes_unsigned_and_uses_frozen_model(session):
    from app.services.projects import list_projects

    owner = await _seed_user(session, "s16-owner@example.test", ["Sales"])
    package, opp, version = await _seed_ready_to_sign_package(session, owner=owner)
    actor = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=("Sales",))
    assert await list_projects(session, actor=actor) == []
    package.status, package.released_at = "released", datetime.now(UTC)
    await session.flush()
    rows = await list_projects(session, actor=actor)
    assert len(rows) == 1
    assert rows[0]["gm_model_id"] == str(package.gm_model_id)
    assert rows[0]["forecast"]["us"] is None
    stranger = await _seed_user(session, "s16-other@example.test", ["Sales"])
    assert (
        await list_projects(
            session,
            actor=AuthUser(
                id=stranger.id, email=stranger.email, name=stranger.name, groups=("Sales",)
            ),
        )
        == []
    )


@pytest.mark.asyncio
async def test_projects_role_gate(app_with_session, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DEALGATE_ENV", "local")
    async with _client(app_with_session) as client:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Marketing")
        assert (
            await client.get("/projects", headers={"X-Test-User": "reader@example.test"})
        ).status_code == 403
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
        assert (
            await client.get("/projects", headers={"X-Test-User": "reader@example.test"})
        ).status_code == 200
