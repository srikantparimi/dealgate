"""FC-10/T24: persisted opt-in automation, immutable revisions and scoped access."""
import uuid

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.automation import AutomationRuleVersion
from app.services.automation import RuleInput, get_rule, rule_history, save_rule
from tests.test_s21_sourcing_rules import setup


def body(**changes):
    return RuleInput(**(dict(expected_version_id=None, request_key="first",
        reason="Enable synthetic sourcing refresh", enabled=True) | changes))


async def test_unconfigured_is_disabled_and_replay_is_exact(session, monkeypatch):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    initial = await get_rule(session, actor=actor)
    assert initial["state"] == "unconfigured" and initial["enabled"] is False
    first = await save_rule(session, actor=actor, body=body())
    assert first["enabled"] is True and first["domain"] == "sourcing_refresh"
    assert await save_rule(session, actor=actor, body=body()) == first
    assert await session.scalar(select(func.count()).select_from(AutomationRuleVersion)) == 1


async def test_disable_is_new_revision_with_preserved_history(session, monkeypatch):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    first = await save_rule(session, actor=actor, body=body())
    second = await save_rule(session, actor=actor, body=body(expected_version_id=first["id"],
        request_key="disable", reason="Stop future processing", enabled=False))
    assert second["revision"] == 2 and second["enabled"] is False
    assert (await session.get(AutomationRuleVersion, uuid.UUID(first["id"]))).enabled is True
    history = await rule_history(session, actor=actor)
    assert [row["revision"] for row in history["items"]] == [2, 1]
    assert history["current_version_id"] == second["id"]


@pytest.mark.parametrize("change", [{"request_key": "stale"}, {"enabled": False}])
async def test_stale_revision_or_changed_replay_refused(session, monkeypatch, change):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    await save_rule(session, actor=actor, body=body())
    with pytest.raises(HTTPException) as error:
        await save_rule(session, actor=actor, body=body(**change))
    assert error.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(AutomationRuleVersion)) == 1


async def test_replay_is_actor_bound(session, monkeypatch):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    await save_rule(session, actor=actor, body=body())
    other = await setup(session, monkeypatch, ("SystemAdmin",))
    with pytest.raises(HTTPException) as error:
        await save_rule(session, actor=other, body=body())
    assert error.value.status_code == 409


@pytest.mark.parametrize("groups", [("HR",), ("Delivery",), ("Finance",), ("Sales",), ()])
async def test_only_admin_can_configure_or_read_automation(session, monkeypatch, groups):
    actor = await setup(session, monkeypatch, groups)
    for operation in (lambda: save_rule(session, actor=actor, body=body()),
        lambda: get_rule(session, actor=actor), lambda: rule_history(session, actor=actor)):
        with pytest.raises(HTTPException) as error:
            await operation()
        assert error.value.status_code == 403
    assert await session.scalar(select(func.count()).select_from(AutomationRuleVersion)) == 0


@pytest.mark.parametrize("scope,value", [("DEALGATE_TENANT_ID", "other"), ("DEALGATE_ENV", "staging")])
async def test_runtime_scope_cannot_read_other_rule(session, monkeypatch, scope, value):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    await save_rule(session, actor=actor, body=body())
    monkeypatch.setenv(scope, value)
    assert (await get_rule(session, actor=actor))["enabled"] is False
    assert (await rule_history(session, actor=actor))["items"] == []


async def test_fixture_scope_is_separate(session, monkeypatch):
    actor = await setup(session, monkeypatch, ("SystemAdmin",))
    await save_rule(session, actor=actor, body=body())
    synthetic = await setup(session, monkeypatch, ("SystemAdmin", "officeapp-e2e"))
    assert (await get_rule(session, actor=synthetic))["state"] == "unconfigured"


@pytest.mark.parametrize("changes", [{"enabled": "false"}, {"reason": " "},
    {"request_key": " padded "}, {"domain": "approve"}, {"source_scope": "unknown"}])
def test_contract_rejects_coercion_unreviewed_domains_and_blank_justification(changes):
    with pytest.raises(ValidationError):
        body(**changes)
