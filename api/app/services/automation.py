"""Scoped automation settings; enabling does not grant source permissions."""
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import StrictBool
from sqlalchemy import select

from app.audit import append_audit
from app.models.automation import AutomationRule, AutomationRuleVersion
from app.services.forecast_plans import _digest, runtime
from app.services.people_sourcing import ReasonedInput
from app.services.test_fixtures import is_test_user


class RuleInput(ReasonedInput):
    expected_version_id: uuid.UUID | None
    enabled: StrictBool
    source_scope: Literal["authorized_sources"] = "authorized_sources"


def _authorized(actor):
    if "SystemAdmin" not in actor.groups:
        raise HTTPException(403, "Automation configuration requires SystemAdmin")


async def _root(session, actor, *, lock=False):
    tenant, environment = runtime()
    scope = dict(tenant_id=tenant, environment=environment,
        test_fixture=is_test_user(actor), domain="sourcing_refresh")
    if lock:
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        await session.execute(insert(AutomationRule).values(id=uuid.uuid4(), **scope).on_conflict_do_nothing())
    query = select(AutomationRule).filter_by(**scope)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return await session.scalar(query)


async def _current(session, root):
    return await session.scalar(select(AutomationRuleVersion).where(AutomationRuleVersion.rule_id == root.id)
        .order_by(AutomationRuleVersion.revision.desc()).limit(1)) if root else None


def _result(row):
    if row is None:
        return dict(state="unconfigured", domain="sourcing_refresh", enabled=False, id=None, revision=None,
            source_scope="authorized_sources")
    return dict(state="configured", domain="sourcing_refresh", enabled=row.enabled, id=str(row.id),
        rule_id=str(row.rule_id), revision=row.revision, source_scope=row.source_scope,
        reason=row.reason, created_by=str(row.created_by), created_at=row.created_at.isoformat())


async def get_rule(session, *, actor):
    _authorized(actor)
    return _result(await _current(session, await _root(session, actor)))


async def rule_history(session, *, actor, page=1, size=50):
    _authorized(actor)
    root = await _root(session, actor)
    if root is None:
        return dict(items=[], current_version_id=None)
    current = await _current(session, root)
    rows = (await session.scalars(select(AutomationRuleVersion).where(AutomationRuleVersion.rule_id == root.id)
        .order_by(AutomationRuleVersion.revision.desc()).offset((page - 1) * size).limit(size))).all()
    return dict(items=[_result(row) for row in rows], current_version_id=str(current.id) if current else None)


async def save_rule(session, *, actor, body: RuleInput):
    _authorized(actor)
    root = await _root(session, actor, lock=True)
    digest = _digest(body.model_dump(mode="json"))
    replay = await session.scalar(select(AutomationRuleVersion).where(
        AutomationRuleVersion.rule_id == root.id, AutomationRuleVersion.request_key == body.request_key))
    if replay:
        if replay.request_hash != digest or replay.created_by != actor.id:
            raise HTTPException(409, "Automation request key belongs to different inputs or actor")
        result = _result(replay)
        await session.commit()
        return result
    prior = await _current(session, root)
    if (prior.id if prior else None) != body.expected_version_id:
        raise HTTPException(409, "Automation rule changed; reload before saving")
    row = AutomationRuleVersion(id=uuid.uuid4(), rule_id=root.id, revision=prior.revision + 1 if prior else 1,
        enabled=body.enabled, source_scope=body.source_scope, request_key=body.request_key,
        request_hash=digest, reason=body.reason, created_by=actor.id)
    session.add(row)
    await session.flush()
    await append_audit(session, actor_id=actor.id, action="automation.rule_revised", entity="automation_rule",
        entity_id=str(root.id), before={"version_id": str(prior.id)} if prior else None,
        after={"version_id": str(row.id), "revision": row.revision, "enabled": row.enabled,
            "domain": root.domain, "reason": row.reason}, correlation_id=body.request_key)
    result = _result(row)
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"automation_rule:{row.id}")
    await session.commit()
    return result
