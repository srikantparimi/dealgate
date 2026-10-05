"""FC-07/10: real source changes refresh proposals, never headcount probabilities."""
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.automation import AutomationJob
from app.models.people_demand import DemandPublicationVersion
from app.models.people_sourcing import SourcingDraftVersion
from app.models.user import User
from app.services.automation import RuleInput, save_rule
from app.services.automation_jobs import enqueue_refresh, process_jobs
from app.services.forecast_plans import AssumptionsInput, revise_assumptions, save_plan
from app.services.people_sourcing import list_drafts
from tests.test_s21_sourcing_drafts import fixture
from tests.test_s21_people_company_x import engine, isolated_scope  # noqa: F401
from tests.test_s21_people_company_x import import_roster, publish, roster


async def enabled(session):
    actor, _, request, source, publication, _ = await fixture(session)
    actor = replace(actor, groups=("SystemAdmin",))
    user = await session.get(User, actor.id)
    user.groups = ["SystemAdmin"]
    await session.commit()
    rule = await save_rule(session, actor=actor, body=RuleInput(expected_version_id=None,
        request_key="enable", reason="Reviewed source refresh authority", enabled=True))
    return actor, request, source, publication, rule


async def test_enable_refreshes_existing_source_once_with_literal_sourcing_dates(session):
    actor, _, _, publication, _ = await enabled(session)
    assert await session.scalar(select(func.count()).select_from(AutomationJob)) == 1
    assert await process_jobs(session) == 1
    draft = (await list_drafts(session, actor=actor, publication_id=uuid.UUID(publication["publication_id"])))
    assert draft["state"] == "current"
    snapshot = draft["items"][0]["snapshot"]
    november = [row for row in snapshot["rows"] if row["start"] == "2026-11-01"]
    assert {row["location"]: (row["quantity"], row["sourcing_by"]) for row in november} == {
        "US": (2, "2026-09-17"), "India": (5, "2026-10-02")}
    assert await process_jobs(session) == 0
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1
    job = await session.scalar(select(AutomationJob))
    assert job.status == "done" and job.attempts == 1 and job.completed_at is not None


async def test_probability_edit_republishes_and_refreshes_without_manual_prepare(session):
    actor, request, source, publication, _ = await enabled(session)
    await process_jobs(session)
    await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id, "probability": "0.40"}))
    assert await process_jobs(session) == 1
    history = await list_drafts(session, actor=actor, publication_id=uuid.UUID(publication["publication_id"]))
    assert history["state"] == "current"
    assert [Decimal(row["snapshot"]["probability"]) for row in history["items"]] == [Decimal("0.40"), Decimal("0.70")]
    for item in history["items"]:
        assert sum(row["quantity"] for row in item["snapshot"]["rows"] if row["start"] == "2026-11-01") == 7


async def test_disabled_rule_stops_pending_work(session):
    actor, _, _, _, rule = await enabled(session)
    await save_rule(session, actor=actor, body=RuleInput(expected_version_id=rule["id"],
        request_key="disable", reason="Stop before worker runs", enabled=False))
    assert await process_jobs(session) == 1
    assert (await session.scalar(select(AutomationJob))).status == "disabled"
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 0


async def test_revoked_admin_does_not_run_with_cached_authority(session):
    actor, _, _, _, _ = await enabled(session)
    (await session.get(User, actor.id)).groups = ["Sales"]
    await session.commit()
    assert await process_jobs(session) == 1
    assert (await session.scalar(select(AutomationJob))).status == "forbidden"
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 0


async def test_unconfigured_source_changes_do_not_create_jobs(session):
    await fixture(session)
    assert await session.scalar(select(func.count()).select_from(AutomationJob)) == 0


async def test_duplicate_event_id_does_not_duplicate_jobs_and_enqueue_does_not_commit(session):
    actor, _, _, _, _ = await enabled(session)
    await enqueue_refresh(session, actor=actor, event_key="reviewed-test-event")
    await enqueue_refresh(session, actor=actor, event_key="reviewed-test-event")
    assert await session.scalar(select(func.count()).select_from(AutomationJob)) == 2
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(AutomationJob)) == 1


async def test_foreign_worker_cannot_claim_jobs(session, monkeypatch):
    await enabled(session)
    monkeypatch.setenv("DEALGATE_TENANT_ID", "other")
    assert await process_jobs(session) == 0
    assert (await session.scalar(select(AutomationJob))).status == "pending"


async def test_stale_source_job_does_not_overwrite_newer_version(session):
    actor, request, source, _, _ = await enabled(session)
    await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id, "probability": "0.40"}))
    assert await process_jobs(session) == 2
    jobs = (await session.scalars(select(AutomationJob))).all()
    assert sorted(job.status for job in jobs) == ["done", "obsolete"]
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 2


async def test_assumptions_endpoint_path_emits_refresh(session):
    actor, _, source, publication, _ = await enabled(session)
    await process_jobs(session)
    await revise_assumptions(session, actor=actor, plan_id=source.plan_id, body=AssumptionsInput(
        expected_version_id=source.id, probability="0.25", probability_source="Reviewed new probability",
        assumptions=["Synthetic review"], lifecycle="tentative", change_reason="Updated sales assessment"))
    assert await process_jobs(session) == 1
    history = await list_drafts(session, actor=actor, publication_id=uuid.UUID(publication["publication_id"]))
    assert Decimal(history["items"][0]["snapshot"]["probability"]) == Decimal("0.25")


async def test_supply_change_refreshes_saved_incremental_gap(session):
    from app.models.people_planning import PeopleImportBatch
    actor, _, _, publication, _ = await enabled(session)
    await process_jobs(session)
    previous = await session.scalar(select(PeopleImportBatch))
    await import_roster(session, actor, roster(us=1, india=4), previous={"id": str(previous.id)})
    assert await process_jobs(session) == 1
    history = await list_drafts(session, actor=actor, publication_id=uuid.UUID(publication["publication_id"]))
    snapshot = history["items"][0]["snapshot"]
    assert snapshot["complete"] is True
    assert sum(row["incremental_gap_quantity"] for row in snapshot["rows"] if row["start"] == "2026-11-01") == 2
    assert history["items"][0]["revision"] == 2


async def test_fault_after_real_draft_write_rolls_back_all_effects_and_records_backoff(session, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from app.services import automation_jobs
    actor, request, source, _, _ = await enabled(session)
    await process_jobs(session)
    await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id, "probability": "0.40"}))
    original = automation_jobs.prepare_draft

    async def fail_after_write(*args, **kwargs):
        assert kwargs["commit"] is False
        await original(*args, **kwargs)
        raise RuntimeError("Injected crash boundary after real draft flush")

    monkeypatch.setattr(automation_jobs, "prepare_draft", fail_after_write)
    assert await process_jobs(session) == 1
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 1
    failed = await session.scalar(select(AutomationJob).where(AutomationJob.status == "failed"))
    assert failed.attempts == 1 and failed.next_attempt_at is not None
    assert await process_jobs(session) == 0
    monkeypatch.setattr(automation_jobs, "prepare_draft", original)
    failed.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()
    assert await process_jobs(session) == 1
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 2
    assert await session.scalar(select(func.count()).select_from(DemandPublicationVersion)) == 2


async def test_changed_source_is_published_first_and_pending_global_refresh_is_not_duplicated(session):
    actor, _, request, source, publication, _ = await fixture(session)
    other = await save_plan(session, actor=actor, body=request.model_copy(update={
        "idempotency_key": uuid.uuid4(), "title": "Second reviewed planning source"}))
    await publish(session, actor, other)
    (await session.get(User, actor.id)).groups = ["SystemAdmin"]
    await session.commit()
    actor = replace(actor, groups=("SystemAdmin",))
    await save_rule(session, actor=actor, body=RuleInput(expected_version_id=None,
        request_key="enable", reason="Refresh both planning sources", enabled=True))
    assert await process_jobs(session) == 2
    revised = await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id, "probability": "0.40"}))
    assert await process_jobs(session, limit=1) == 1
    latest = await session.scalar(select(DemandPublicationVersion).where(
        DemandPublicationVersion.publication_id == uuid.UUID(publication["publication_id"]))
        .order_by(DemandPublicationVersion.version.desc()).limit(1))
    assert latest.source_version == str(revised.id)
    assert await session.scalar(select(func.count()).select_from(AutomationJob).where(AutomationJob.status == "pending")) == 1
    assert await process_jobs(session) == 1
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 4
    assert set((await session.scalars(select(AutomationJob.status))).all()) == {"done"}
