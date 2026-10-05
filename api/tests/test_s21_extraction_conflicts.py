"""Explicit source-bound review, not silent confirmation of replay candidates."""
# Pytest injects the imported fixtures into the matching argument names.
# ruff: noqa: F811
import copy
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.sow import SowVersion
from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS
from app.routers.sow import router
from app.services.sow_extract import SowSubmissionIncomplete, confirm_field, run_extract, submit_sow
from tests.test_s21_extraction_overrides import DOCUMENT, Provider, source  # noqa: F401
from tests.test_sow_confirmation import OWNER, seeded_sow  # noqa: F401


@asynccontextmanager
async def client_for(session, owner, *, foreign=False):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: AuthUser(
        uuid.uuid4() if foreign else owner.id,
        "foreign-editor@example.test" if foreign else owner.email,
        "Foreign editor" if foreign else owner.name,
        ("Sales",),
    )

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def conflicting(session, version):
    await run_extract(session, sow_version_id=version.id, bedrock=Provider(price="999.00"), file_bytes=DOCUMENT)
    await session.commit()
    return f"/sow/versions/{version.id}/extraction-conflicts"


@pytest.mark.parametrize("decision,expected,provenance", [
    ("keep_confirmed", "250.00", "manual"), ("accept_candidate", "999.00", "extracted")])
async def test_review_retains_evidence_and_records_human_decision(session, source, decision, expected, provenance):
    owner, _, version = source
    path = await conflicting(session, version)
    original = copy.deepcopy(version.extracted_fields["price"])
    async with client_for(session, owner) as client:
        listing = await client.get(path)
        assert listing.status_code == 200, listing.text
        conflict = listing.json()["items"][0]
        assert conflict["field"] == "price"
        assert conflict["current"]["value"] == "250.00"
        assert conflict["candidate"]["value"] == "999.00"
        body = {"review_token": conflict["review_token"], "decision": decision, "reason": "Reviewed source clause"}
        response = await client.post(f"{path}/price", json=body)
        assert response.status_code == 200, response.text
        assert response.json() == {"items": []}
        assert (await client.post(f"{path}/price", json=body)).status_code == 409
    await session.refresh(version)
    field = version.extracted_fields["price"]
    assert (field["value"], field["provenance"], field["status"]) == (expected, provenance, "confirmed")
    assert field["page_ref"] == 1
    if decision == "keep_confirmed":
        assert field == original
    assert version.extract_status == "complete" and version.extract_error is None
    events = (await session.scalars(select(AuditEvent).where(AuditEvent.action == "sow.extraction_conflict_resolved"))).all()
    assert len(events) == 1 and events[0].actor_id == owner.id
    assert events[0].after["reason"] == body["reason"] and events[0].after["decision"] == decision


@pytest.mark.parametrize("change", ["candidate", "confirmed", "immutable"])
async def test_stale_or_immutable_review_cannot_replace_values(session, source, change):
    owner, _, version = source
    path = await conflicting(session, version)
    async with client_for(session, owner) as client:
        listing = await client.get(path)
        assert listing.status_code == 200
        token = listing.json()["items"][0]["review_token"]
        if change == "candidate":
            await run_extract(session, sow_version_id=version.id, bedrock=Provider(price="777.00"), file_bytes=DOCUMENT)
        elif change == "confirmed":
            await confirm_field(session, actor_id=owner.id, sow_version_id=version.id, field_name="price", value="500.00")
        else:
            version.confirmed_by, version.confirmed_at = owner.id, datetime.now(UTC)
        await session.commit()
        before = copy.deepcopy(version.extracted_fields)
        response = await client.post(f"{path}/price", json={"review_token": token,
            "decision": "accept_candidate", "reason": "Stale review must fail"})
        assert response.status_code == 409, response.text
        assert version.extracted_fields == before


async def test_foreign_editor_cannot_read_or_resolve_conflict(session, source):
    owner, _, version = source
    path = await conflicting(session, version)
    async with client_for(session, owner, foreign=True) as client:
        assert (await client.get(path)).status_code == 403
        response = await client.post(f"{path}/price", json={"review_token": "a" * 64,
            "decision": "keep_confirmed", "reason": "Unauthorized"})
        assert response.status_code == 403


async def test_manual_field_confirmation_does_not_silently_dismiss_replay_conflict(session, source):
    owner, _, version = source
    await conflicting(session, version)
    for name in EXTRACTED_FIELDS:
        await confirm_field(session, actor_id=owner.id, sow_version_id=version.id,
            field_name=name, value=version.extracted_fields[name]["value"])
    with pytest.raises(SowSubmissionIncomplete):
        await submit_sow(session, actor_id=owner.id, sow_version_id=version.id)
    assert version.confirmed_at is None


async def test_scope_completion_surfaces_and_refuses_conflicts(session, seeded_sow):
    from app.services.sow_confirmation import build_confirmation, scope_blockers, submit_confirmation

    version = await session.scalar(select(SowVersion))
    fields = copy.deepcopy(version.extracted_fields)
    fields["metadata"] = {"reextract_conflicts": {"price": {
        "value": "999.00", "status": "unconfirmed", "provenance": "extracted", "page_ref": 2}}}
    version.extracted_fields = fields
    await session.commit()
    payload = await build_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert "extraction_conflict:price" in {row.field for row in scope_blockers(payload)}
    with pytest.raises(HTTPException, match="extraction_conflict:price") as error:
        await submit_confirmation(session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER)
    assert error.value.status_code == 422 and version.confirmed_at is None


async def test_review_does_not_erase_newer_provider_failure(session, source):
    owner, _, version = source
    path = await conflicting(session, version)
    await run_extract(session, sow_version_id=version.id, bedrock=Provider(failure=True), file_bytes=DOCUMENT)
    await session.commit()
    async with client_for(session, owner) as client:
        listing = await client.get(path)
        assert listing.status_code == 200
        token = listing.json()["items"][0]["review_token"]
        response = await client.post(f"{path}/price", json={"review_token": token,
            "decision": "keep_confirmed", "reason": "Keep human-reviewed fee, retain provider error"})
        assert response.status_code == 200
    assert version.extract_status == "manual_required"
    assert version.extract_error == "provider unavailable"
