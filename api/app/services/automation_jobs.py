"""Source outbox and atomic refresh using the existing publication/draft services."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, literal, or_, select

from app.audit import append_audit
from app.auth import AuthUser
from app.models.automation import AutomationJob, AutomationRule, AutomationRuleVersion
from app.models.forecast import ForecastPlan
from app.models.people_sourcing import SourcingDraft, SourcingDraftVersion
from app.models.project import Project
from app.models.user import User
from app.services.automation import _authorized, _current, _root
from app.services.forecast_plans import runtime
from app.services.people_demand import PublishDemandInput, _source_rows, demand_sources, publish_plan_demand
from app.services.people_project_demand import PublishProjectDemandInput, publish_project_demand
from app.services.people_sourcing import DraftInput, _current_rules, _root as sourcing_root, prepare_draft
from app.services.test_fixtures import is_test_user


async def enqueue_refresh(session, *, actor, event_key, exclude_source_key=None, coalesce_pending=False):
    """Join the emitter transaction; no committed job without its source change."""
    return await _enqueue_for_root(session, root=await _root(session, actor), event_key=event_key,
        exclude_source_key=exclude_source_key, coalesce_pending=coalesce_pending)


async def enqueue_project_created(session, *, project):
    """Select the rule from captured source provenance, not the releasing user's roles."""
    scope = (project.baseline_snapshot_json or {}).get("source_scope")
    if not isinstance(scope, dict):
        return 0
    tenant, environment = runtime()
    if (scope.get("tenant_id"), scope.get("environment")) != (tenant, environment):
        return 0
    root = await session.scalar(select(AutomationRule).where(AutomationRule.tenant_id == tenant,
        AutomationRule.environment == environment, AutomationRule.domain == "sourcing_refresh",
        AutomationRule.test_fixture == (scope.get("fixture_grant_id") is not None)))
    return await _enqueue_for_root(session, root=root, event_key=f"project:{project.id}")


async def _enqueue_for_root(session, *, root, event_key, exclude_source_key=None, coalesce_pending=False):
    if not event_key or len(event_key) > 128:
        raise ValueError("A bounded source event identity is required")
    rule = await _current(session, root)
    if rule is None or not rule.enabled:
        return 0
    user = await session.get(User, rule.created_by, populate_existing=True)
    if user is None or "SystemAdmin" not in user.groups:
        return 0
    authority = AuthUser(id=user.id, email=user.email, name=user.name, groups=tuple(user.groups))
    if is_test_user(authority) != root.test_fixture:
        return 0
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    population = await demand_sources(session, actor=authority)
    # Only the worker holding this rule's root lock can safely reuse future work.
    pending = set((await session.execute(select(AutomationJob.source_key, AutomationJob.source_version)
        .where(AutomationJob.rule_version_id == rule.id, AutomationJob.status == "pending"))).all()) \
        if coalesce_pending else set()
    count = 0
    for source in population["items"]:
        key = source["source_id"]
        if key == exclude_source_key:
            continue
        if (key, source["source_version_id"]) in pending:
            continue
        job_id = uuid.uuid5(rule.id, f"{event_key}:{key}:{source['source_version_id']}")
        await session.execute(insert(AutomationJob).values(id=job_id, rule_version_id=rule.id,
            plan_version_id=uuid.UUID(source["source_version_id"]) if source["source_kind"] == "plan" else None,
            project_id=uuid.UUID(key) if source["source_kind"] == "project" else None,
            source_key=key, source_version=source["source_version_id"], event_key=event_key,
            status="pending", attempts=0).on_conflict_do_nothing())
        count += 1
    return count


async def _refresh(session, job, root):
    rule = await _current(session, root)
    if rule is None or not rule.enabled:
        return "disabled", None
    if rule.id != job.rule_version_id:
        return "obsolete", None
    # Use persisted roles, not the groups captured when the event was emitted.
    user = await session.get(User, rule.created_by, populate_existing=True)
    if user is None or "SystemAdmin" not in user.groups:
        return "forbidden", None
    actor = AuthUser(id=user.id, email=user.email, name=user.name, groups=tuple(user.groups))
    if is_test_user(actor) != root.test_fixture:
        return "forbidden", None
    model = ForecastPlan if job.plan_version_id else Project
    await session.execute(select(model.id).where(model.id == uuid.UUID(job.source_key)).with_for_update())
    sources = await _source_rows(session, actor=actor, source_id=uuid.UUID(job.source_key))
    source = next((row for row in sources["items"] if row["source_id"] == job.source_key), None)
    if source is None:
        return "forbidden", None
    if source["source_version_id"] != job.source_version:
        return "obsolete", None
    if source["state"] != "current":
        values = dict(expected_source_version_id=job.source_version,
            expected_publication_version_id=source["publication_version_id"],
            request_key=f"automation:{job.id}:publish", reason="Source change refresh under configured automation")
        if job.plan_version_id:
            publication = await publish_plan_demand(session, actor=actor,
                body=PublishDemandInput(plan_id=job.source_key, **values), commit=False)
        else:
            publication = await publish_project_demand(session, actor=actor,
                body=PublishProjectDemandInput(project_id=job.source_key, **values), commit=False)
        # A changed global allocation invalidates other sources' saved proposals.
        await enqueue_refresh(session, actor=actor, event_key=f"publication:{publication['version_id']}",
            exclude_source_key=job.source_key, coalesce_pending=True)
        publication_id, demand_version_id = publication["publication_id"], publication["version_id"]
    else:
        publication_id, demand_version_id = source["publication_id"], source["publication_version_id"]
    rules = await _current_rules(session, await sourcing_root(session, actor))
    if rules is None:
        raise HTTPException(422, "Sourcing lead-time rules require review")
    draft = await session.scalar(select(SourcingDraft).where(SourcingDraft.publication_id == uuid.UUID(publication_id)))
    prior = await session.scalar(select(SourcingDraftVersion).where(SourcingDraftVersion.draft_id == draft.id)
        .order_by(SourcingDraftVersion.revision.desc()).limit(1)) if draft else None
    result = await prepare_draft(session, actor=actor, body=DraftInput(publication_id=publication_id,
        expected_demand_version_id=demand_version_id, expected_rule_version_id=rules.id,
        expected_draft_version_id=prior.id if prior else None, request_key=f"automation:{job.id}:draft",
        reason="Source change refresh under configured automation"), commit=False)
    return ("done" if result["snapshot"]["complete"] else "review"), uuid.UUID(result["id"])


async def process_jobs(session, *, limit=50):
    tenant, environment = runtime()
    processed = 0
    for _ in range(min(max(limit, 1), 100)):
        now = datetime.now(UTC)
        job = await session.scalar(select(AutomationJob).join(AutomationRuleVersion,
            AutomationJob.rule_version_id == AutomationRuleVersion.id).join(AutomationRule,
            AutomationRuleVersion.rule_id == AutomationRule.id).where(AutomationRule.tenant_id == tenant,
            AutomationRule.environment == environment, AutomationJob.status.in_(("pending", "failed")),
            AutomationJob.attempts < 5, or_(AutomationJob.next_attempt_at.is_(None),
                AutomationJob.next_attempt_at <= now)).order_by(case(
                    (AutomationJob.event_key == literal("plan:") + AutomationJob.source_version, 0),
                    (AutomationJob.event_key == literal("project:") + AutomationJob.source_key, 0),
                    else_=1), AutomationJob.created_at, AutomationJob.id)
            .limit(1).with_for_update(skip_locked=True, of=AutomationJob))
        if job is None:
            await session.commit()
            break
        version = await session.get(AutomationRuleVersion, job.rule_version_id)
        root = await session.scalar(select(AutomationRule).where(AutomationRule.id == version.rule_id)
            .with_for_update().execution_options(populate_existing=True))
        job.attempts += 1
        try:
            async with session.begin_nested():
                state, result_id = await _refresh(session, job, root)
            job.status, job.result_version_id = state, result_id
            job.completed_at, job.last_error, job.next_attempt_at = now, None, None
        except HTTPException as error:
            job.status = "forbidden" if error.status_code in (403, 404) else "review" if error.status_code == 422 else (
                "dead" if job.attempts >= 5 else "failed")
            job.last_error = f"Source refresh requires review (HTTP {error.status_code})"
            job.next_attempt_at = now + timedelta(seconds=min(300, 2 ** job.attempts)) if job.status == "failed" else None
            job.completed_at = None if job.status == "failed" else now
        except (ValueError, ArithmeticError, RuntimeError) as error:
            job.status = "dead" if job.attempts >= 5 else "failed"
            job.last_error = f"{type(error).__name__}: source refresh failed"
            job.next_attempt_at = now + timedelta(seconds=min(300, 2 ** job.attempts))
        await append_audit(session, actor_id=None, action="automation.refresh_processed", entity="automation_job",
            entity_id=str(job.id), before=None, after={"status": job.status, "attempts": job.attempts,
                "rule_version_id": str(job.rule_version_id)}, correlation_id=str(job.id))
        await session.commit()
        processed += 1
    return processed


class RetryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_attempts: int = Field(strict=True, ge=0)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def explicit_reason(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Explicit normalized reason required")
        return value


async def _retry_authority(session, root):
    rule = await _current(session, root)
    user = await session.get(User, rule.created_by, populate_existing=True) if rule else None
    if not rule or not rule.enabled or not user or "SystemAdmin" not in user.groups:
        return None
    actor = AuthUser(id=user.id, email=user.email, name=user.name, groups=tuple(user.groups))
    return rule.id if is_test_user(actor) == root.test_fixture else None


def _job_result(job, authority):
    return {"id": str(job.id), "status": job.status, "attempts": job.attempts,
        "rule_version_id": str(job.rule_version_id), "source_id": job.source_key,
        "source_version": job.source_version, "event_key": job.event_key,
        "next_attempt_at": job.next_attempt_at.isoformat() if job.next_attempt_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(), "last_error": job.last_error,
        "result_version_id": str(job.result_version_id) if job.result_version_id else None,
        "can_retry": job.rule_version_id == authority and job.status in ("failed", "review") and job.attempts < 5}


async def list_jobs(session, *, actor, page=1, size=25):
    _authorized(actor)
    root = await _root(session, actor)
    if root is None:
        return {"items": [], "last_success_at": None}
    condition = AutomationJob.rule_version_id.in_(select(AutomationRuleVersion.id)
        .where(AutomationRuleVersion.rule_id == root.id))
    rows = (await session.scalars(select(AutomationJob).where(condition)
        .order_by(AutomationJob.created_at.desc(), AutomationJob.id.desc()).offset((page - 1) * size).limit(size))).all()
    success = await session.scalar(select(func.max(AutomationJob.completed_at)).where(condition, AutomationJob.status == "done"))
    authority = await _retry_authority(session, root)
    return {"items": [_job_result(job, authority) for job in rows],
        "last_success_at": success.isoformat() if success else None}


async def retry_job(session, *, actor, job_id, body: RetryInput):
    _authorized(actor)
    root = await _root(session, actor)
    job = await session.scalar(select(AutomationJob).where(AutomationJob.id == job_id,
        AutomationJob.rule_version_id.in_(select(AutomationRuleVersion.id)
            .where(AutomationRuleVersion.rule_id == root.id))).with_for_update()
        .execution_options(populate_existing=True)) if root else None
    if job is None:
        raise HTTPException(404, "Automation job unavailable")
    await session.execute(select(AutomationRule.id).where(AutomationRule.id == root.id).with_for_update())
    authority = await _retry_authority(session, root)
    if not _job_result(job, authority)["can_retry"] or job.attempts != body.expected_attempts:
        raise HTTPException(409, "Job or automation authority changed; reload before retrying")
    previous = job.status
    job.status, job.next_attempt_at, job.completed_at = "pending", None, None
    await append_audit(session, actor_id=actor.id, action="automation.refresh_requeued", entity="automation_job",
        entity_id=str(job.id), before={"status": previous, "attempts": job.attempts},
        after={"status": "pending", "attempts": job.attempts, "reason": body.reason})
    result = _job_result(job, authority)
    await session.commit()
    return result
