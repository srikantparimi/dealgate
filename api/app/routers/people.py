"""HR-owned managed supply; demand summaries have separate permission contracts."""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.services import people_planning, people_demand, people_allocation, people_sourcing
from app.services import people_project_demand
from app.services import people_coverage
from app.services import automation
from app.services import automation_jobs
from app.services.user_provisioning import ensure_user

router = APIRouter(prefix="/people", tags=["people"])
_supply_user = require_role("HR", "SystemAdmin")
_demand_user = require_role(*sorted(people_demand.DEMAND_READ))
_publisher = require_role("Delivery", "SystemAdmin")
_automation_admin = require_role("SystemAdmin")


@router.post("/imports", status_code=201)
async def import_supply(body: people_planning.WorkforceImportInput,
    user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_planning.import_workforce(session, actor=user, body=body)


@router.get("/imports")
async def history(page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=200),
    user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    return await people_planning.import_history(session, actor=user, page=page, size=size)


@router.get("/availability")
async def supply(user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    return await people_planning.availability(session, actor=user)


@router.post("/demand/publications", status_code=201)
async def publish(body: people_demand.PublishDemandInput,
    user: AuthUser = Depends(_publisher), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_demand.publish_plan_demand(session, actor=user, body=body)


@router.get("/demand")
async def demand(user: AuthUser = Depends(_demand_user), session: AsyncSession = Depends(get_session)):
    return await people_demand.demand_sources(session, actor=user)


@router.post("/demand/project-publications", status_code=201)
async def publish_project(body: people_project_demand.PublishProjectDemandInput,
    user: AuthUser = Depends(_publisher), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_project_demand.publish_project_demand(session, actor=user, body=body)


@router.get("/demand/allocation")
async def allocation(account_id: uuid.UUID | None = None, user: AuthUser = Depends(_demand_user),
    session: AsyncSession = Depends(get_session)):
    return await people_allocation.demand_allocation(session, actor=user, account_id=account_id)


@router.post("/demand/coverage", status_code=201)
async def save_coverage(body: people_coverage.CoverageInput, user: AuthUser = Depends(_publisher),
    session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_coverage.save_coverage(session, actor=user, body=body)


@router.get("/demand/coverage")
async def coverage(plan_publication_id: uuid.UUID, root_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(_demand_user), session: AsyncSession = Depends(get_session)):
    return await people_coverage.list_coverage(session, actor=user, plan_publication_id=plan_publication_id,
        root_id=root_id, page=page, size=size)


@router.get("/sourcing/rules")
async def sourcing_rules(user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    return await people_sourcing.get_rules(session, actor=user)


@router.get("/sourcing/automation")
async def automation_rule(user: AuthUser = Depends(_automation_admin), session: AsyncSession = Depends(get_session)):
    return await automation.get_rule(session, actor=user)


@router.post("/sourcing/automation", status_code=201)
async def revise_automation_rule(body: automation.RuleInput, user: AuthUser = Depends(_automation_admin),
    session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await automation.save_rule(session, actor=user, body=body)


@router.get("/sourcing/automation/history")
async def automation_history(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(_automation_admin), session: AsyncSession = Depends(get_session)):
    return await automation.rule_history(session, actor=user, page=page, size=size)


@router.get("/sourcing/automation/jobs")
async def automation_status(page: int = Query(1, ge=1), size: int = Query(25, ge=1, le=100),
    user: AuthUser = Depends(_automation_admin), session: AsyncSession = Depends(get_session)):
    return await automation_jobs.list_jobs(session, actor=user, page=page, size=size)


@router.post("/sourcing/automation/jobs/{job_id}/retry")
async def retry_automation(job_id: uuid.UUID, body: automation_jobs.RetryInput,
    user: AuthUser = Depends(_automation_admin), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await automation_jobs.retry_job(session, actor=user, job_id=job_id, body=body)


@router.post("/sourcing/rules", status_code=201)
async def revise_sourcing_rules(body: people_sourcing.RulesInput,
    user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_sourcing.save_rules(session, actor=user, body=body)


@router.post("/sourcing/drafts", status_code=201)
async def prepare_sourcing_draft(body: people_sourcing.DraftInput,
    user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    await ensure_user(session, user)
    return await people_sourcing.prepare_draft(session, actor=user, body=body)


@router.get("/sourcing/drafts")
async def sourcing_drafts(publication_id: uuid.UUID, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(_supply_user), session: AsyncSession = Depends(get_session)):
    return await people_sourcing.list_drafts(session, actor=user, publication_id=publication_id, page=page, size=size)
