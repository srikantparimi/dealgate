"""Source-to-sourcing history through actual plan, publication and supply services."""
import uuid
from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.people_sourcing import SourcingDraftVersion
from app.services.forecast_plans import save_plan
from app.services.people_sourcing import DraftInput, RulesInput, list_drafts, prepare_draft, save_rules
from tests.test_s21_people_company_x import (
    engine, isolated_scope, owner_and_account, import_roster, plan_request, publish,
)  # noqa: F401


async def fixture(session):
    actor, account = await owner_and_account(session)
    await import_roster(session, actor, [])
    request = plan_request(account)
    source = await save_plan(session, actor=actor, body=request)
    publication = await publish(session, actor, source)
    hr = replace(actor, groups=("HR",))
    rules = await save_rules(session, actor=hr, body=RulesInput(expected_version_id=None,
        request_key="rules-first", reason="Synthetic reviewed regional lead times",
        rules=[{"skill": "python", "location": "US", "lead_days": 45},
               {"skill": "python", "location": "India", "lead_days": 30}]))
    body = DraftInput(publication_id=publication["publication_id"], expected_demand_version_id=publication["version_id"],
        expected_rule_version_id=rules["id"], expected_draft_version_id=None, request_key="draft-first",
        reason="Prepare synthetic seven-person sourcing proposal")
    return actor, hr, request, source, publication, body


async def test_company_x_sourcing_keeps_full_headcount_and_independent_regional_dates(session):
    _, hr, _, _, _, body = await fixture(session)
    first = await prepare_draft(session, actor=hr, body=body)
    assert first["revision"] == 1 and first["snapshot"]["complete"] is True
    november = [row for row in first["snapshot"]["rows"] if row["start"] == "2026-11-01"]
    assert {row["location"]: (row["quantity"], row["incremental_gap_quantity"], row["sourcing_by"])
        for row in november} == {"US": (2, 2, "2026-09-17"), "India": (5, 5, "2026-10-02")}
    assert Decimal(first["snapshot"]["probability"]) == Decimal("0.70")
    assert await prepare_draft(session, actor=hr, body=body) == first
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1
    history = await list_drafts(session, actor=hr, publication_id=body.publication_id)
    assert history["state"] == "current" and history["current_version_id"] == first["id"]
    assert not any(key in str(first["snapshot"]) for key in ("cost_rate", "person_id", "salary", "matches"))
    assert first["snapshot"]["source_url"].startswith("/people/demand#demand-")
    assert all(row["source_url"].startswith("/people/demand#demand-") for row in first["snapshot"]["rows"])


async def test_probability_revision_requires_republication_then_appends_seven_person_history(session):
    actor, hr, request, source, publication, body = await fixture(session)
    first = await prepare_draft(session, actor=hr, body=body)
    revised = await save_plan(session, actor=actor, plan_id=source.plan_id,
        body=request.model_copy(update={"expected_version_id": source.id, "probability": "0.40"}))
    history = await list_drafts(session, actor=hr, publication_id=body.publication_id)
    assert history["state"] == "stale"
    next_body = body.model_copy(update={"request_key": "second", "expected_draft_version_id": uuid.UUID(first["id"])})
    with pytest.raises(HTTPException) as stale:
        await prepare_draft(session, actor=hr, body=next_body)
    assert stale.value.status_code == 409
    await session.rollback()
    await session.refresh(revised)
    current = await publish(session, actor, revised, previous=publication)
    second = await prepare_draft(session, actor=hr, body=next_body.model_copy(update={
        "expected_demand_version_id": uuid.UUID(current["version_id"])}))
    assert second["revision"] == 2 and Decimal(second["snapshot"]["probability"]) == Decimal("0.40")
    assert sum(row["quantity"] for row in second["snapshot"]["rows"] if row["start"] == "2026-11-01") == 7
    original = await session.get(SourcingDraftVersion, uuid.UUID(first["id"]))
    assert Decimal(original.snapshot["probability"]) == Decimal("0.70")


async def test_stale_draft_version_does_not_duplicate_history(session):
    _, hr, _, _, _, body = await fixture(session)
    await prepare_draft(session, actor=hr, body=body)
    with pytest.raises(HTTPException) as stale:
        await prepare_draft(session, actor=hr, body=body.model_copy(update={"request_key": "stale"}))
    assert stale.value.status_code == 409
    await session.rollback()
    assert await session.scalar(select(func.count()).select_from(SourcingDraftVersion)) == 1


async def test_foreign_runtime_and_test_identity_cannot_read_draft(session, monkeypatch):
    _, hr, _, _, _, body = await fixture(session)
    await prepare_draft(session, actor=hr, body=body)
    monkeypatch.setenv("DEALGATE_TENANT_ID", "foreign")
    with pytest.raises(HTTPException) as foreign:
        await list_drafts(session, actor=hr, publication_id=body.publication_id)
    assert foreign.value.status_code == 404
    monkeypatch.setenv("DEALGATE_TENANT_ID", "independent-company-x-demand")
    with pytest.raises(HTTPException) as test_identity:
        await list_drafts(session, actor=replace(hr, groups=("HR", "officeapp-e2e")), publication_id=body.publication_id)
    assert test_identity.value.status_code == 404
