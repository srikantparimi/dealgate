"""Real persistence for permissioned, optimistic sourcing policy revisions."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.auth import AuthUser
from app.models.people_sourcing import SourcingRuleVersion
from app.models.user import User
from app.services.people_sourcing import RulesInput, get_rules, save_rules


async def setup(session, monkeypatch, groups=("HR",)):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "sourcing-test")
    monkeypatch.setenv("DEALGATE_ENV", "local")
    actor = AuthUser(uuid.uuid4(), f"{uuid.uuid4()}@example.test", "Synthetic HR", groups)
    session.add(User(id=actor.id, email=actor.email, name=actor.name, groups=list(groups)))
    await session.commit()
    return actor


def body(**changes):
    return RulesInput(**(dict(expected_version_id=None, request_key="first", reason="Reviewed synthetic hiring lead times",
        rules=[{"skill": "python", "location": "US", "lead_days": 45}]) | changes))


async def test_rules_start_unconfigured_and_replay_has_no_duplicate_history(session, monkeypatch):
    actor = await setup(session, monkeypatch)
    assert (await get_rules(session, actor=actor))["state"] == "unconfigured"
    first = await save_rules(session, actor=actor, body=body())
    assert await save_rules(session, actor=actor, body=body()) == first
    assert first["revision"] == 1 and first["rules"][0]["lead_days"] == 45
    assert await session.scalar(select(func.count()).select_from(SourcingRuleVersion)) == 1


async def test_cas_and_actor_replay_refused_without_erasing_prior_rules(session, monkeypatch):
    actor = await setup(session, monkeypatch)
    first = await save_rules(session, actor=actor, body=body())
    with pytest.raises(HTTPException) as stale:
        await save_rules(session, actor=actor, body=body(request_key="stale"))
    assert stale.value.status_code == 409
    await session.rollback()
    other = await setup(session, monkeypatch)
    with pytest.raises(HTTPException) as replay:
        await save_rules(session, actor=other, body=body())
    assert replay.value.status_code == 409
    await session.rollback()
    second = await save_rules(session, actor=actor, body=body(expected_version_id=first["id"], request_key="second",
        rules=[{"skill": "*", "location": "India", "lead_days": 30}]))
    assert second["revision"] == 2
    assert (await session.get(SourcingRuleVersion, uuid.UUID(first["id"]))).rules[0]["lead_days"] == 45


@pytest.mark.parametrize("groups", [("Sales",), ("Delivery",), ("Finance",), ("Legal",)])
async def test_only_hr_or_admin_changes_sourcing_rules(session, monkeypatch, groups):
    actor = await setup(session, monkeypatch, groups)
    with pytest.raises(HTTPException) as denied:
        await save_rules(session, actor=actor, body=body())
    assert denied.value.status_code == 403
    assert await session.scalar(select(func.count()).select_from(SourcingRuleVersion)) == 0


async def test_rule_scope_separates_tenants_and_server_issued_test_identity(session, monkeypatch):
    actor = await setup(session, monkeypatch)
    await save_rules(session, actor=actor, body=body())
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    assert (await get_rules(session, actor=actor))["state"] == "unconfigured"
    monkeypatch.setenv("DEALGATE_TENANT_ID", "sourcing-test")
    test_actor = await setup(session, monkeypatch, ("HR", "officeapp-e2e"))
    assert (await get_rules(session, actor=test_actor))["state"] == "unconfigured"
