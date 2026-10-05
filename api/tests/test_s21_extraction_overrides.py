"""Same-document replay preserves human decisions, never signed source mutation."""

import copy
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS, ExtractedFields, ManualRequired, get_bedrock_sow
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.routers.sow import router
from app.services.sow_extract import SowError, confirm_field, run_extract


DOCUMENT = (Path(__file__).resolve().parents[2] / "fixtures/sample_sows/08_assessment_fixed_fee.docx").read_bytes()


class Provider:
    def __init__(self, *, price="100.00", failure=False):
        self.price, self.failure, self.calls = price, failure, 0

    def extract(self, document):
        self.calls += 1
        assert document.blocks
        if self.failure:
            return ManualRequired(reason="provider unavailable")
        fields = {name: {"value": f"candidate-{name}", "page_ref": 1, "status": "unconfirmed"}
                  for name in EXTRACTED_FIELDS}
        fields["price"]["value"] = self.price
        fields["currency"]["value"] = "USD"
        fields["engagement_type_suggested"]["value"] = "assessment"
        return ExtractedFields(fields=fields, model="boundary-provider", prompt_version="test-schema-v1")


@pytest_asyncio.fixture
async def source(session):
    owner = User(id=uuid.uuid4(), email="replay-owner@example.test", name="Replay Owner", groups=["Sales"])
    session.add(owner)
    await session.flush()
    deal = Opportunity(id=uuid.uuid4(), owner_id=owner.id, name="Synthetic replay source", governance_status="SOWDraft")
    session.add(deal)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
        file_s3_key="synthetic/replay.docx", file_hash=hashlib.sha256(DOCUMENT).hexdigest(), extract_status="pending")
    session.add(version)
    await session.flush()
    await run_extract(session, sow_version_id=version.id, bedrock=Provider(), file_bytes=DOCUMENT)
    await confirm_field(session, actor_id=owner.id, sow_version_id=version.id, field_name="price", value="250.00")
    await confirm_field(session, actor_id=owner.id, sow_version_id=version.id, field_name="currency", value="USD")
    await session.commit()
    return owner, deal, version


@pytest.mark.parametrize("failure", [False, True])
async def test_replay_preserves_actual_confirmations_and_audit(session, source, failure):
    _, _, version = source
    protected = {name: copy.deepcopy(version.extracted_fields[name]) for name in ("price", "currency")}
    assert protected["price"]["provenance"] == "manual"
    assert protected["currency"]["provenance"] == "extracted"
    provider = Provider(price="999.00", failure=failure)
    state = await run_extract(session, sow_version_id=version.id, bedrock=provider, file_bytes=DOCUMENT)
    await session.commit()
    await session.refresh(version)
    assert provider.calls == 1
    assert {name: version.extracted_fields[name] for name in protected} == protected
    assert state.extract_status == version.extract_status == "manual_required"
    assert version.extract_error
    if not failure:
        conflicts = version.extracted_fields["metadata"]["reextract_conflicts"]
        assert conflicts["price"]["value"] == "999.00"
        assert conflicts["price"]["status"] == "unconfirmed"
    audits = list((await session.scalars(select(AuditEvent).where(AuditEvent.entity_id == str(version.id)))).all())
    assert sum(row.action == "sow.field_confirmed" for row in audits) == 2
    assert any(row.action == "sow.extract_failed" and row.after["extract_status"] == "manual_required" for row in audits)


async def test_unchanged_candidate_preserves_envelopes_without_false_conflict(session, source):
    _, _, version = source
    protected = copy.deepcopy(version.extracted_fields["price"])
    state = await run_extract(session, sow_version_id=version.id, bedrock=Provider(price="250.00"), file_bytes=DOCUMENT)
    assert state.extract_status == "complete"
    assert state.extracted_fields["price"] == protected
    assert not state.extracted_fields["metadata"].get("reextract_conflicts")


async def test_manual_default_is_not_human_confirmation(session, source):
    _, _, version = source
    fields = copy.deepcopy(version.extracted_fields)
    fields["notice_date"] = {"value": "legacy default", "provenance": "manual", "status": "unconfirmed"}
    version.extracted_fields = fields
    await session.flush()
    state = await run_extract(session, sow_version_id=version.id, bedrock=Provider(price="250.00"), file_bytes=DOCUMENT)
    assert state.extracted_fields["notice_date"]["value"] == "candidate-notice_date"
    assert state.extracted_fields["notice_date"]["status"] == "unconfirmed"


async def test_changed_source_bytes_refused_before_provider_without_mutation(session, source):
    _, _, version = source
    before = copy.deepcopy(version.extracted_fields)
    provider = Provider()
    with pytest.raises(SowError):
        await run_extract(session, sow_version_id=version.id, bedrock=provider, file_bytes=DOCUMENT + b"changed")
    assert provider.calls == 0 and version.extracted_fields == before


@pytest.mark.parametrize("state", ["confirmed", "executed", "superseded", "discarded",
    "pending_delivery_hr", "ready_to_sign", "released", "rejected", "voided"])
async def test_immutable_versions_refused_before_provider(session, source, state):
    owner, deal, version = source
    if state == "confirmed":
        version.confirmed_by, version.confirmed_at = owner.id, datetime.now(UTC)
    elif state in ("executed", "superseded"):
        version.execution_state = state
    elif state == "discarded":
        version.discarded_at = datetime.now(UTC)
    else:
        gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_id=version.sow_id,
            sow_version_id=version.id, version=1, engagement_type="assessment", currency="USD")
        session.add(gm)
        await session.flush()
        session.add(ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
            gm_model_id=gm.id, package_hash="a" * 64, status=state, submitted_by=owner.id))
    await session.flush()
    before = copy.deepcopy(version.extracted_fields)
    provider = Provider()
    with pytest.raises(SowError):
        await run_extract(session, sow_version_id=version.id, bedrock=provider, file_bytes=DOCUMENT)
    assert provider.calls == 0 and version.extracted_fields == before


@pytest.mark.parametrize("mismatch", [False, True])
async def test_reextract_http_uses_storage_bytes_and_returns_conflict(session, source, mismatch):
    owner, _, version = source
    app = FastAPI()
    app.include_router(router)
    provider = Provider(price="250.00")
    storage = StubS3()
    storage.download_bytes = lambda key: DOCUMENT + (b"changed" if mismatch else b"")
    app.dependency_overrides[current_user] = lambda: AuthUser(owner.id, owner.email, owner.name, ("Sales",))

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[get_sow_s3] = lambda: storage
    app.dependency_overrides[get_bedrock_sow] = lambda: provider
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/sow/versions/{version.id}/reextract")
    assert response.status_code == (409 if mismatch else 200), response.text
    assert provider.calls == (0 if mismatch else 1)
