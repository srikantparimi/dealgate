"""Persisted planning versions and authorized projections over real source snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select

from app.audit import append_audit
from app.gm.commercial import CALCULATION_VERSION, HybridPricing, calculate_component
from app.gm.forecast import ForecastLine, project_outlook, validate_converted_scope
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.forecast import ForecastConversion, ForecastJob, ForecastPlan, ForecastPlanVersion, ForecastSchedule
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.sow import SowVersion
from app.services.commercial_models import COMPONENT, OUTCOME, SCHEDULE, parse_component
from app.services.policy import active_policy

ORG_READ = {"Delivery", "Finance", "CEO", "SystemAdmin"}
PLAN_WRITE = {"Delivery", "Finance", "SystemAdmin"}


class PlanInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    opportunity_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    idempotency_key: uuid.UUID
    expected_version_id: uuid.UUID | None = None
    inputs: dict
    probability: str | None = None
    probability_source: str | None = Field(default=None, max_length=2000)
    assumptions: list[str] = Field(default_factory=list, max_length=100)
    lifecycle: Literal["needs_review", "tentative", "won_unsigned", "closed_lost", "dismissed", "expired"] = "needs_review"
    scenario_group: str | None = Field(default=None, max_length=255)
    selected: bool = True
    fx_rate: str | None = None
    fx_version: str | None = Field(default=None, max_length=128)
    fx_date: date | None = None
    change_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("probability", "fx_rate")
    @classmethod
    def decimal_string(cls, value):
        if value is not None:
            try:
                amount = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("Invalid Decimal string") from exc
            if not amount.is_finite() or amount < 0:
                raise ValueError("Expected a finite nonnegative Decimal string")
        return value


def runtime():
    tenant = os.environ.get("DEALGATE_TENANT_ID")
    environment = os.environ.get("DEALGATE_ENV", "local")
    if not tenant:
        raise HTTPException(409, "Forecast requires configured DEALGATE_TENANT_ID")
    return tenant, environment


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _bind(component, plan_id, version_id, policy_version):
    for assignment in component.staffing:
        if any(getattr(assignment, field) != getattr(component, field) for field in (
            "source_id", "source_version", "component_id", "profile_version", "policy_version", "currency", "timezone",
        )):
            raise HTTPException(422, "Staffing assignment source binding does not match its component")
    staffing = tuple(replace(assignment, source_id=f"forecast:{plan_id}",
                             source_version=str(version_id), policy_version=policy_version)
                     for assignment in component.staffing)
    pricing = component.pricing
    if isinstance(pricing, HybridPricing):
        if any(any(getattr(child, field) != getattr(component, field) for field in (
            "source_id", "source_version", "policy_version")) for child in pricing.components):
            raise HTTPException(422, "Hybrid child source/policy binding mismatch")
        pricing = replace(pricing, components=tuple(_bind(child, plan_id, version_id, policy_version) for child in pricing.components))
    return replace(component, source_id=f"forecast:{plan_id}", source_version=str(version_id),
                   policy_version=policy_version, pricing=pricing, staffing=staffing)


async def _account_allowed(session, actor, account_id):
    from app.services.test_fixtures import account_scope, user_allowed
    return user_allowed(actor, await account_scope(session, account_id))


async def save_plan(session, *, actor, body: PlanInput, plan_id=None):
    if not set(actor.groups) & PLAN_WRITE:
        raise HTTPException(403, "Delivery or Finance planning permission required")
    tenant, environment = runtime()
    if not body.title.strip() or not body.change_reason.strip():
        raise HTTPException(422, "Plan name and written change reason are required")
    probability = Decimal(body.probability) if body.probability is not None else None
    if probability is not None and not 0 <= probability <= 1:
        raise HTTPException(422, "Probability must be between zero and one")
    fx = Decimal(body.fx_rate) if body.fx_rate is not None else None
    if fx is not None and (fx <= 0 or not body.fx_version or not body.fx_date):
        raise HTTPException(422, "A positive FX rate requires a version and date")
    component = parse_component(body.inputs)
    account = await session.get(Client, body.account_id)
    if account is None or account.archived_at is not None:
        raise HTTPException(404, "Account unavailable")
    if not await _account_allowed(session, actor, account.id):
        raise HTTPException(403, "Account is outside the trusted planning scope")
    if body.opportunity_id:
        deal = await session.get(Opportunity, body.opportunity_id)
        if not deal or deal.client_id != body.account_id:
            raise HTTPException(422, "Linked CRM deal must belong to this account")
    request_key = f"{actor.id}:{body.idempotency_key}"
    request_hash = _digest(body.model_dump(mode="json"))
    if plan_id is None:
        # Account lock also serializes same-key creates without an uncommitted duplicate race.
        await session.execute(select(Client.id).where(Client.id == account.id).with_for_update())
        plan = await session.scalar(select(ForecastPlan).where(
            ForecastPlan.tenant_id == tenant, ForecastPlan.environment == environment,
            ForecastPlan.request_key == request_key))
        if plan:
            if plan.request_hash != request_hash:
                raise HTTPException(409, "Idempotency key already has different plan inputs")
            return await session.scalar(select(ForecastPlanVersion).where(
                ForecastPlanVersion.plan_id == plan.id).order_by(ForecastPlanVersion.version).limit(1))
        if body.expected_version_id is not None:
            raise HTTPException(409, "New plan cannot have a previous version")
        plan = ForecastPlan(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
                            account_id=account.id, opportunity_id=body.opportunity_id, owner_id=actor.id,
                            request_key=request_key, request_hash=request_hash)
        session.add(plan)
        await session.flush()
        prior = None
    else:
        plan = await session.scalar(select(ForecastPlan).where(
            ForecastPlan.id == plan_id, ForecastPlan.tenant_id == tenant,
            ForecastPlan.environment == environment).with_for_update())
        if plan is None:
            raise HTTPException(404, "Plan unavailable")
        if (plan.account_id, plan.opportunity_id) != (body.account_id, body.opportunity_id):
            raise HTTPException(409, "Account/deal identity cannot change through a commercial edit")
        prior = await session.scalar(select(ForecastPlanVersion).where(
            ForecastPlanVersion.plan_id == plan.id).order_by(ForecastPlanVersion.version.desc()).limit(1))
        if prior.id != body.expected_version_id:
            raise HTTPException(409, "Plan version changed; refresh before saving")
    policy = await active_policy(session)
    policy_id = str(policy.id) if policy.id else "blueprint-defaults-v1"
    version_id = uuid.uuid4()
    bound = _bind(component, plan.id, version_id, policy_id)
    row = ForecastPlanVersion(
        id=version_id, plan_id=plan.id, version=prior.version + 1 if prior else 1,
        title=body.title.strip(), scope_id=str(plan.id), lifecycle=body.lifecycle,
        probability=probability, probability_source=body.probability_source,
        assumptions=body.assumptions, component_inputs=COMPONENT.dump_python(bound, mode="json"),
        policy_snapshot={"version": policy_id, "us_floor": str(policy.us_floor), "india_floor": str(policy.india_floor)},
        scenario_group=body.scenario_group, selected=body.selected,
        fx_rate=fx, fx_version=body.fx_version, fx_date=body.fx_date,
        change_reason=body.change_reason.strip(), created_by=actor.id,
    )
    session.add(row)
    await session.flush()
    session.add(ForecastJob(id=uuid.uuid5(row.id, "forecast.schedule.v1"), plan_version_id=row.id,
                            tenant_id=tenant, environment=environment, status="pending", attempts=0))
    await append_audit(session, actor_id=actor.id, action="forecast.plan_version_created",
                       entity="forecast_plan", entity_id=str(plan.id), before={"version_id": str(prior.id)} if prior else None,
                       after={"version_id": str(row.id), "version": row.version, "lifecycle": row.lifecycle,
                              "scope_id": row.scope_id, "reason": row.change_reason}, correlation_id=str(body.idempotency_key))
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"plan:{row.id}")
    await session.commit()
    return row


async def process_plan_jobs(session, *, limit=50):
    tenant, environment = runtime()
    now = datetime.now(UTC)
    jobs = list((await session.scalars(select(ForecastJob).where(
        ForecastJob.tenant_id == tenant, ForecastJob.environment == environment,
        ForecastJob.status.in_(("pending", "failed")), ForecastJob.attempts < 5,
        or_(ForecastJob.next_attempt_at.is_(None), ForecastJob.next_attempt_at <= now),
    ).order_by(ForecastJob.created_at, ForecastJob.id).limit(min(max(limit, 1), 100)).with_for_update(skip_locked=True))).all())
    for job in jobs:
        version = await session.get(ForecastPlanVersion, job.plan_version_id)
        await session.execute(select(ForecastPlan.id).where(ForecastPlan.id == version.plan_id).with_for_update())
        latest = await session.scalar(select(func.max(ForecastPlanVersion.version)).where(ForecastPlanVersion.plan_id == version.plan_id))
        if version.version != latest:
            job.status, job.completed_at = "obsolete", now
            continue
        job.attempts += 1
        try:
            existing = await session.get(ForecastSchedule, version.id)
            if existing is None:
                schedule = calculate_component(parse_component(version.component_inputs))
                policy = version.policy_snapshot
                outcome = schedule.assess(us_floor=Decimal(policy["us_floor"]), india_floor=Decimal(policy["india_floor"]))
                session.add(ForecastSchedule(plan_version_id=version.id, calculation_version=CALCULATION_VERSION,
                    snapshot={"schedule": SCHEDULE.dump_python(schedule, mode="json"),
                              "outcome": OUTCOME.dump_python(outcome, mode="json")}))
            job.status, job.completed_at, job.last_error = "done", now, None
            await append_audit(session, actor_id=None, action="forecast.schedule_calculated", entity="forecast_plan",
                               entity_id=str(version.plan_id), before=None,
                               after={"version_id": str(version.id), "job_id": str(job.id), "calculation_version": CALCULATION_VERSION})
        except (ValueError, ArithmeticError) as exc:
            job.status = "dead" if job.attempts >= 5 else "failed"
            job.last_error = f"{type(exc).__name__}: calculation input requires repair"
            job.next_attempt_at = now + timedelta(seconds=min(300, 2 ** job.attempts))
    await session.commit()
    return len(jobs)


async def _plans(session, actor):
    tenant, environment = runtime()
    if not set(actor.groups) & (ORG_READ | {"Sales", "SalesLeader"}):
        raise HTTPException(403, "Financial outlook permission required")
    query = select(ForecastPlan).where(ForecastPlan.tenant_id == tenant, ForecastPlan.environment == environment)
    if not set(actor.groups) & ORG_READ:
        query = query.where(ForecastPlan.owner_id == actor.id)
    records = list((await session.scalars(query.order_by(ForecastPlan.id))).all())
    return [plan for plan in records if await _account_allowed(session, actor, plan.account_id)]


class AssumptionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version_id: uuid.UUID
    probability: str | None
    probability_source: str | None = Field(max_length=2000)
    assumptions: list[str] = Field(max_length=100)
    lifecycle: Literal["needs_review", "tentative", "won_unsigned", "closed_lost", "dismissed", "expired"]
    change_reason: str = Field(min_length=1, max_length=2000)

    @field_validator("probability")
    @classmethod
    def valid_probability(cls, value):
        if value is not None:
            try:
                number = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("Invalid probability") from exc
            if not number.is_finite() or not 0 <= number <= 1:
                raise ValueError("Probability must be between zero and one")
        return value

    @field_validator("change_reason")
    @classmethod
    def written_reason(cls, value):
        if not value.strip():
            raise ValueError("Written change reason is required")
        return value.strip()


class CommercialRevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version_id: uuid.UUID
    inputs: dict
    change_reason: str = Field(min_length=1, max_length=2000)


async def revise_commercial(session, *, actor, plan_id, body: CommercialRevisionInput):
    if not set(actor.groups) & PLAN_WRITE:
        raise HTTPException(403, "Delivery or Finance planning permission required")
    tenant, environment = runtime()
    plan = await session.scalar(select(ForecastPlan).where(
        ForecastPlan.id == plan_id, ForecastPlan.tenant_id == tenant,
        ForecastPlan.environment == environment).with_for_update())
    if plan is None:
        raise HTTPException(404, "Plan unavailable")
    if not await _account_allowed(session, actor, plan.account_id):
        raise HTTPException(403, "Account is outside the trusted planning scope")
    prior = await session.scalar(select(ForecastPlanVersion).where(
        ForecastPlanVersion.plan_id == plan.id).order_by(ForecastPlanVersion.version.desc()).limit(1))
    if prior is None or prior.id != body.expected_version_id:
        raise HTTPException(409, "Plan version changed; refresh before saving")
    return await save_plan(session, actor=actor, plan_id=plan.id, body=PlanInput(
        account_id=plan.account_id, opportunity_id=plan.opportunity_id,
        title=prior.title, idempotency_key=uuid.uuid4(), expected_version_id=prior.id,
        inputs=body.inputs, probability=str(prior.probability) if prior.probability is not None else None,
        probability_source=prior.probability_source, assumptions=prior.assumptions,
        lifecycle=prior.lifecycle, scenario_group=prior.scenario_group, selected=prior.selected,
        fx_rate=str(prior.fx_rate) if prior.fx_rate is not None else None,
        fx_version=prior.fx_version, fx_date=prior.fx_date, change_reason=body.change_reason,
    ))


def _assumption_revision_source(component, version_id):
    pricing = component.pricing
    if isinstance(pricing, HybridPricing):
        pricing = replace(pricing, components=tuple(
            _assumption_revision_source(child, version_id) for child in pricing.components))
    return replace(component, source_version=str(version_id), pricing=pricing,
                   staffing=tuple(replace(row, source_version=str(version_id)) for row in component.staffing))


async def revise_assumptions(session, *, actor, plan_id, body: AssumptionsInput):
    if not set(actor.groups) & PLAN_WRITE:
        raise HTTPException(403, "Delivery or Finance planning permission required")
    tenant, environment = runtime()
    plan = await session.scalar(select(ForecastPlan).where(
        ForecastPlan.id == plan_id, ForecastPlan.tenant_id == tenant,
        ForecastPlan.environment == environment).with_for_update())
    if plan is None:
        raise HTTPException(404, "Plan unavailable")
    account = await session.get(Client, plan.account_id)
    if account is None or account.archived_at is not None:
        raise HTTPException(404, "Account unavailable")
    if not await _account_allowed(session, actor, plan.account_id):
        raise HTTPException(403, "Account is outside the trusted planning scope")
    prior = await session.scalar(select(ForecastPlanVersion).where(
        ForecastPlanVersion.plan_id == plan.id).order_by(ForecastPlanVersion.version.desc()).limit(1))
    if prior is None or prior.id != body.expected_version_id:
        raise HTTPException(409, "Plan version changed; refresh before saving")
    if body.probability is not None and not (body.probability_source or "").strip():
        raise HTTPException(422, "Probability requires a written source")
    version_id = uuid.uuid4()
    # Assumption-only edits keep the frozen commercial policy and economic terms.
    component = parse_component(prior.component_inputs)
    bound = _assumption_revision_source(component, version_id)
    row = ForecastPlanVersion(
        id=version_id, plan_id=plan.id, version=prior.version + 1,
        title=prior.title, scope_id=prior.scope_id, lifecycle=body.lifecycle,
        probability=Decimal(body.probability) if body.probability is not None else None,
        probability_source=body.probability_source, assumptions=body.assumptions,
        component_inputs=COMPONENT.dump_python(bound, mode="json"),
        policy_snapshot=prior.policy_snapshot, scenario_group=prior.scenario_group,
        selected=prior.selected, fx_rate=prior.fx_rate, fx_version=prior.fx_version,
        fx_date=prior.fx_date, change_reason=body.change_reason, created_by=actor.id,
    )
    session.add(row)
    await session.flush()
    session.add(ForecastJob(id=uuid.uuid5(row.id, "forecast.schedule.v1"), plan_version_id=row.id,
                            tenant_id=tenant, environment=environment, status="pending", attempts=0))
    await append_audit(session, actor_id=actor.id, action="forecast.plan_assumptions_revised",
                       entity="forecast_plan", entity_id=str(plan.id),
                       before={"version_id": str(prior.id)},
                       after={"version_id": str(row.id), "version": row.version,
                              "lifecycle": row.lifecycle, "reason": row.change_reason})
    from app.services.automation_jobs import enqueue_refresh
    await enqueue_refresh(session, actor=actor, event_key=f"plan:{row.id}")
    await session.commit()
    return row


async def _plan_source_identity(session, actor, plan):
    if plan.opportunity_id is None:
        return {"opportunity_id": None, "source_status": "Local forecast only"}
    unavailable = {"opportunity_id": None, "source_status": "Linked deal unavailable"}
    deal = await session.get(Opportunity, plan.opportunity_id)
    if deal is None or deal.archived_at is not None or deal.client_id != plan.account_id:
        return unavailable
    from app.services.test_fixtures import account_scope, user_allowed
    if not user_allowed(actor, await account_scope(session, plan.account_id, opportunity_id=deal.id)):
        return unavailable
    if (deal.hubspot_deal_id or "").strip():
        status = "Linked HubSpot deal"
    elif deal.source in {"sow_upload", "manual", "bulk_import"}:
        status = "Linked local deal"
    else:
        status = "Linked deal; CRM identity unavailable"
    return {"opportunity_id": str(deal.id), "source_status": status}


async def list_plans(session, *, actor, account_id=None):
    result = []
    for plan in await _plans(session, actor):
        if account_id is not None and plan.account_id != account_id:
            continue
        version = await session.scalar(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == plan.id)
                                       .order_by(ForecastPlanVersion.version.desc()).limit(1))
        if version is None:
            continue
        account = await session.get(Client, plan.account_id)
        job = await session.scalar(select(ForecastJob).where(ForecastJob.plan_version_id == version.id))
        source_identity = await _plan_source_identity(session, actor, plan)
        result.append({"id": str(plan.id), "version_id": str(version.id), "version": version.version,
                       "account_id": str(plan.account_id), "account_name": account.name if account else None,
                       **source_identity,
                       "owner_id": str(plan.owner_id), "title": version.title, "lifecycle": version.lifecycle,
                       "probability": str(version.probability) if version.probability is not None else None,
                       "probability_source": version.probability_source, "assumptions": version.assumptions,
                       "can_edit_assumptions": bool(set(actor.groups) & PLAN_WRITE),
                       "source_evidence": version.component_inputs.get("source_evidence", []),
                       "commercial_inputs": version.component_inputs, "scope_id": version.scope_id,
                       "job": {"id": str(job.id), "status": job.status, "attempts": job.attempts,
                               "next_attempt_at": job.next_attempt_at, "last_error": job.last_error} if job else None})
    return sorted(result, key=lambda row: (row["title"].casefold(), row["id"]))


async def link_conversion(session, *, actor, plan_id, gm_model_id, expected_version_id, scope_fraction, reason):
    if not set(actor.groups) & PLAN_WRITE:
        raise HTTPException(403, "Delivery or Finance conversion permission required")
    tenant, environment = runtime()
    fraction = Decimal(scope_fraction)
    if not fraction.is_finite() or not 0 < fraction <= 1 or not reason.strip():
        raise HTTPException(422, "Conversion requires fraction in (0,1] and written scope evidence")
    plan = await session.scalar(select(ForecastPlan).where(
        ForecastPlan.id == plan_id, ForecastPlan.tenant_id == tenant,
        ForecastPlan.environment == environment).with_for_update())
    if plan is None or not await _account_allowed(session, actor, plan.account_id):
        raise HTTPException(404, "Plan unavailable")
    latest = await session.scalar(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == plan.id)
                                  .order_by(ForecastPlanVersion.version.desc()).limit(1))
    if latest.id != expected_version_id:
        raise HTTPException(409, "Plan version changed; refresh conversion preview")
    await session.execute(select(GmModel.id).where(GmModel.id == gm_model_id).with_for_update())
    gm = await session.get(GmModel, gm_model_id)
    deal = await session.get(Opportunity, gm.opportunity_id) if gm else None
    if not gm or not deal or deal.client_id != plan.account_id or not gm.commercial_snapshot:
        raise HTTPException(422, "Conversion needs a commercial SOW for the same account")
    snapshot = gm.commercial_snapshot
    if (snapshot.get("tenant_id"), snapshot.get("environment")) != (tenant, environment):
        raise HTTPException(404, "Signed source unavailable")
    signed = await session.scalar(select(ApprovalPackage).where(ApprovalPackage.gm_model_id == gm.id,
        ApprovalPackage.status.notin_(("voided", "rejected")),
        or_(ApprovalPackage.status == "released", ApprovalPackage.id.in_(select(SignedSowUpload.package_id).where(
            SignedSowUpload.verify_status == "verified")))).limit(1))
    if signed is None:
        raise HTTPException(409, "Unsigned work cannot replace potential revenue")
    existing = await session.scalar(select(ForecastConversion).where(ForecastConversion.gm_model_id == gm.id))
    if existing:
        if existing.plan_id == plan.id and existing.scope_fraction == fraction:
            return existing
        raise HTTPException(409, "Signed economic source already has a different conversion mapping")
    schedule = SCHEDULE.validate_python(snapshot["schedule"])
    if not schedule.rows:
        raise HTTPException(409, "Signed service scope is unresolved")
    coverage = [(row.month, row.location, fraction) for row in schedule.rows]
    prior_sources = (await session.execute(select(ForecastConversion, GmModel).join(
        GmModel, GmModel.id == ForecastConversion.gm_model_id).where(ForecastConversion.plan_id == plan.id))).all()
    for prior, prior_gm in prior_sources:
        prior_schedule = SCHEDULE.validate_python(prior_gm.commercial_snapshot["schedule"])
        coverage.extend((row.month, row.location, prior.scope_fraction) for row in prior_schedule.rows)
    try:
        validate_converted_scope(tuple(coverage))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    row = ForecastConversion(id=uuid.uuid4(), plan_id=plan.id, gm_model_id=gm.id,
                             scope_fraction=fraction, reason=reason.strip(), created_by=actor.id)
    session.add(row)
    await append_audit(session, actor_id=actor.id, action="forecast.scope_converted", entity="forecast_plan",
                       entity_id=str(plan.id), before=None, after={"version_id": str(latest.id),
                       "gm_model_id": str(gm.id), "scope_fraction": str(fraction), "reason": reason.strip()})
    await session.commit()
    return row


async def outlook(session, *, actor, as_of=None, scenario="expected", future_quarters=2, account_id=None):
    as_of = as_of or datetime.now(UTC)
    tenant, environment = runtime()
    timezone, currency = os.environ.get("DEALGATE_REPORTING_TIMEZONE"), os.environ.get("DEALGATE_REPORTING_CURRENCY")
    if not timezone or not currency:
        raise HTTPException(409, "Configure organization reporting timezone and currency before using Forecast")
    plans = await _plans(session, actor)
    plans = [plan for plan in plans if account_id is None or plan.account_id == account_id]
    lines, pending, watermark, labels, unresolved, sources = [], [], [], {}, [], {}
    if account_id is not None:
        selected = await session.get(Client, account_id)
        if selected is not None and selected.archived_at is None and await _account_allowed(session, actor, selected.id):
            portfolio_visible = bool(set(actor.groups) & ORG_READ) or bool(plans)
            if not portfolio_visible:
                portfolio_visible = await session.scalar(select(Opportunity.id).where(
                    Opportunity.client_id == selected.id, Opportunity.owner_id == actor.id,
                    Opportunity.archived_at.is_(None)).limit(1)) is not None
            if portfolio_visible:
                labels[str(selected.id)] = selected.name
    conversions = {}
    for plan in plans:
        account = await session.get(Client, plan.account_id)
        if account is None or account.archived_at:
            continue
        labels[str(account.id)] = account.name
        version = await session.scalar(select(ForecastPlanVersion).where(ForecastPlanVersion.plan_id == plan.id)
                                       .order_by(ForecastPlanVersion.version.desc()).limit(1))
        if version is None:
            continue
        watermark.append((str(plan.id), str(version.id)))
        source_identity = await _plan_source_identity(session, actor, plan)
        sources[str(plan.id)] = {"source_name": version.title, "assumptions": version.assumptions,
            "source_evidence": version.component_inputs.get("source_evidence", []),
            **source_identity,
            "source_url": f"/deals/{source_identity['opportunity_id']}" if source_identity["opportunity_id"] else None}
        for conversion in (await session.scalars(select(ForecastConversion).where(ForecastConversion.plan_id == plan.id))).all():
            if conversion.gm_model_id:
                conversions[conversion.gm_model_id] = (version.scope_id, conversion.scope_fraction)
                watermark.append((str(conversion.id), str(conversion.scope_fraction)))
        snapshot = await session.get(ForecastSchedule, version.id)
        sources[str(plan.id)]["calculation_version"] = snapshot.calculation_version if snapshot else None
        watermark.append((str(version.id), snapshot.calculation_version if snapshot else "pending"))
        if snapshot is None:
            pending.append(str(version.id))
            continue
        schedule = SCHEDULE.validate_python(snapshot.snapshot["schedule"])
        rows = schedule.rows
        if not rows:
            unresolved.append({"source_id": str(plan.id), "source_version": str(version.id),
                               "account_id": str(plan.account_id), "name": version.title,
                               "reasons": [gap.reason for gap in schedule.missing] or ["Service schedule unresolved"]})
            continue
        for index, row in enumerate(rows):
            lines.append(ForecastLine(
                row_id=f"{version.id}:{index}", account_id=str(plan.account_id), source_id=str(plan.id),
                source_version=str(version.id), scope_id=f"{version.scope_id}:{row.location}",
                month=row.month,
                lifecycle=version.lifecycle, currency=schedule.component.currency,
                revenue=row.revenue, cost=row.cost, revenue_uses_ratio=row.revenue_uses_ratio,
                probability=version.probability, probability_source=version.probability_source,
                assumptions=tuple(version.assumptions), scenario_group=version.scenario_group, selected=version.selected,
                fx_rate=version.fx_rate, fx_version=version.fx_version, fx_date=version.fx_date,
                missing=tuple(gap.reason for gap in schedule.missing),
            ))
    # Signed truth is read from the approval-bound model, never copied into a plan.
    # An activated amendment supersedes the original version/package; counting
    # both would book the original contract again as extension revenue (T20.08).
    signed_query = select(GmModel, Opportunity, ApprovalPackage).join(
        ApprovalPackage, ApprovalPackage.gm_model_id == GmModel.id).join(
        Opportunity, Opportunity.id == GmModel.opportunity_id).join(
        SowVersion, SowVersion.id == GmModel.sow_version_id).where(
        or_(ApprovalPackage.status == "released", ApprovalPackage.id.in_(
            select(SignedSowUpload.package_id).where(SignedSowUpload.verify_status == "verified"))),
        ApprovalPackage.status.notin_(("voided", "rejected")),
        ApprovalPackage.superseded_by.is_(None),
        SowVersion.superseded_by.is_(None),
        SowVersion.discarded_at.is_(None),
    )
    if not set(actor.groups) & ORG_READ:
        signed_query = signed_query.where(Opportunity.owner_id == actor.id)
    if account_id:
        signed_query = signed_query.where(Opportunity.client_id == account_id)
    seen = set()
    coverage_schedules = []
    for gm, deal, package in (await session.execute(signed_query)).all():
        if gm.id in seen or not gm.commercial_snapshot or deal.client_id is None:
            continue
        data = gm.commercial_snapshot
        if (data.get("tenant_id"), data.get("environment")) != (tenant, environment):
            continue
        seen.add(gm.id)
        from app.services.test_fixtures import allowed_for_package
        if not await allowed_for_package(session, actor.id, package):
            continue
        from app.services.financial_coverage import signed_model_evidence
        coverage_signed = await signed_model_evidence(session, gm)
        schedule = SCHEDULE.validate_python(data["schedule"])
        sources[str(gm.id)] = {"source_name": deal.name or "Signed SOW", "assumptions": [],
            "source_evidence": list(schedule.component.source_evidence),
            "opportunity_id": str(deal.id), "source_url": f"/sows/{deal.id}/staffing",
            "calculation_version": schedule.calculation_version}
        scope, fraction = conversions.get(gm.id, (str(gm.id), Decimal("1")))
        account = await session.get(Client, deal.client_id)
        labels[str(deal.client_id)] = account.name if account else "Account unavailable"
        watermark.append((str(gm.id), str(package.id)))
        for index, row in enumerate(schedule.rows):
            if coverage_signed:
                basis_missing = schedule.status == "unsupported" or any(gap.field not in {
                    "costs.amount", "costs_confirmed", "cost_basis"} for gap in schedule.missing)
                coverage_schedules.append({"row_id": f"{gm.id}:{index}",
                    "account_id": str(deal.client_id), "source_id": str(gm.id),
                    "source_version": str(gm.sow_version_id), "month": row.month.isoformat(),
                    "currency": gm.currency, "revenue": None if basis_missing else row.revenue,
                    "cost": None if basis_missing else row.cost})
            lines.append(ForecastLine(row_id=f"{gm.id}:{index}", account_id=str(deal.client_id),
                source_id=str(gm.id), source_version=str(gm.sow_version_id), scope_id=f"{scope}:{row.location}",
                month=row.month, lifecycle="signed", currency=gm.currency, revenue=row.revenue, cost=row.cost,
                revenue_uses_ratio=row.revenue_uses_ratio,
                scope_fraction=fraction, missing=tuple(gap.reason for gap in schedule.missing
                    if gap.field not in {"costs.amount", "costs_confirmed", "cost_basis"})))
    view = project_outlook(tuple(lines), as_of=as_of or datetime.now(UTC), timezone=timezone,
                           scenario=scenario, future_quarters=future_quarters, reporting_currency=currency)
    for row in view["rows"] + view["excluded"]:
        row.update(sources.get(row["source_id"], {}))
    empty = project_outlook((), as_of=as_of or datetime.now(UTC), timezone=timezone,
                            scenario=scenario, future_quarters=future_quarters, reporting_currency=currency)
    represented = {row["account_id"] for row in view["accounts"]}
    for identity in labels.keys() - represented:
        view["accounts"].append({"account_id": identity, **{key: empty[key] for key in
            ("current_month", "current_quarter", "future", "quarters")}})
    for account in view["accounts"]:
        account["name"] = labels.get(account["account_id"], "Account unavailable")
    view["accounts"].sort(key=lambda row: (row["name"].casefold(), row["account_id"]))
    if set(actor.groups) & {"Finance", "SystemAdmin"}:
        from app.gm.actuals import summarize_financial_actuals
        from app.services.actuals_import import financial_records
        records = await financial_records(session, actor=actor, account_id=account_id)
        view["financial_actuals"] = summarize_financial_actuals(
            records, as_of=as_of or datetime.now(UTC), timezone=timezone, currency=currency)
        from app.gm.coverage import reconcile_actual_coverage
        view["current_period_estimate"] = reconcile_actual_coverage(coverage_schedules, records,
            as_of=as_of or datetime.now(UTC), timezone=timezone, currency=currency)
        view["actuals_available"] = bool(view["financial_actuals"]["totals"])
        view["actuals_basis"] = "Separate financial measures; service schedule unchanged"
        watermark.extend((row["id"], str(row["revision"])) for row in records)
    view.update(pending_sources=pending, unresolved_sources=unresolved,
                source_watermark=_digest([tenant, environment, str(actor.id), sorted(actor.groups), sorted(watermark)]),
                scope_label="My portfolio" if not set(actor.groups) & ORG_READ else ("Selected total" if account_id else "Company total"),
                source_count=len(sources), stale=bool(pending),
                source_coverage="Tenant-bound commercial schedules and versioned plans",
                legacy_sources_included=False)
    return view
