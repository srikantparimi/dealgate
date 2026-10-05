"""CO-09: cleanup authority comes from issued provenance, never display names."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.test_fixtures import create_fixture


@pytest.mark.parametrize("value", ["nonsense", "-1", "NaN", "Infinity", "-Infinity", ""])
def test_cleanup_rejects_invalid_age(monkeypatch, value):
    from worker.e2e_cleanup import _min_age
    monkeypatch.setenv("E2E_MIN_AGE_HOURS", value)
    with pytest.raises(ValueError):
        _min_age()


def test_zero_age_requires_exact_run_and_owner(monkeypatch):
    from worker.e2e_cleanup import _min_age
    monkeypatch.setenv("E2E_MIN_AGE_HOURS", "0")
    with pytest.raises(ValueError):
        _min_age()
    with pytest.raises(ValueError):
        _min_age(run_id=uuid.uuid4())
    assert _min_age(run_id=uuid.uuid4(), owner_id=uuid.uuid4()) == timedelta(0)


@pytest.mark.asyncio
async def test_manifest_excludes_names_active_untagged_mirrors_and_foreign_grants(session, monkeypatch):
    from app.services.fixture_cleanup import cleanup_manifest
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "cleanup-test")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    actor = User(id=uuid.uuid4(), email="cleanup@example.test", name="Cleanup fixture owner",
        groups=["officeapp-e2e", "SystemAdmin"])
    session.add(actor)
    await session.flush()
    eligible = await create_fixture(session, actor_id=actor.id, label="Eligible", reviewer_ids=[])
    mirrored = await create_fixture(session, actor_id=actor.id, label="Mirrored", reviewer_ids=[])
    extra_deal = await create_fixture(session, actor_id=actor.id, label="Extra deal", reviewer_ids=[])
    mirror_client = await session.get(Client, mirrored["client_id"])
    mirror_client.hubspot_company_id = "must-preserve-source"
    session.add(Opportunity(client_id=extra_deal["client_id"], owner_id=actor.id,
        name="Not granted by fixture issuer", source="manual"))
    collisions = [Client(name=name) for name in ("Liberty", "S14b e2e real customer", "Peppermill Casino's, LLC", "Manual client")]
    session.add_all(collisions)
    await session.commit()
    assert await cleanup_manifest(session, now=datetime.now(UTC)) == []
    future = datetime.now(UTC) + timedelta(hours=25)
    manifest = await cleanup_manifest(session, now=future)
    assert [row["client_id"] for row in manifest] == [str(eligible["client_id"])]
    assert manifest[0]["run_id"] == str(eligible["run_id"])
    assert manifest[0]["owner_id"] == str(actor.id)
    assert manifest[0]["counts"]["opportunities"] == 1
    assert await session.get(Client, eligible["client_id"]) is not None
    for client in collisions:
        assert await session.get(Client, client.id) is not None
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert await cleanup_manifest(session, now=future) == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "cleanup-test")
    monkeypatch.setenv("DEALGATE_ENV", "dev")
    assert await cleanup_manifest(session, now=future) == []


@pytest.mark.asyncio
async def test_zero_age_does_not_override_active_run_and_revalidates_issuer(session, monkeypatch):
    from app.services.fixture_cleanup import cleanup_manifest
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "cleanup-test")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    actor = User(id=uuid.uuid4(), email="bounded@example.test", name="Bounded owner",
        groups=["officeapp-e2e", "SystemAdmin"])
    session.add(actor)
    await session.flush()
    fixture = await create_fixture(session, actor_id=actor.id, label="Bounded", reviewer_ids=[], hours=1)
    await session.commit()
    args = {"run_id": fixture["run_id"], "owner_id": actor.id, "min_age": timedelta(0)}
    assert await cleanup_manifest(session, now=datetime.now(UTC), **args) == []
    later = datetime.now(UTC) + timedelta(hours=2)
    assert len(await cleanup_manifest(session, now=later, **args)) == 1
    assert await cleanup_manifest(session, now=later, **{**args, "owner_id": uuid.uuid4()}) == []
    actor.groups = ["officeapp-e2e"]
    await session.flush()
    assert await cleanup_manifest(session, now=later, **args) == []
