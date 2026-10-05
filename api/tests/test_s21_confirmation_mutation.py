"""Confirmation shares replay's immutable source and fresh-JSON boundary."""

import copy
import uuid
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel
from app.models.sow import SowVersion
from app.routers.sow import router
from app.services.sow_extract import SowError, confirm_field
from tests.test_s21_extraction_overrides import source  # noqa: F401


@pytest.mark.parametrize("state", ["confirmed", "executed", "pending_delivery_hr", "released", "voided"])
async def test_confirmation_refuses_immutable_source(session, source, state):
    owner, deal, version = source
    if state == "confirmed":
        version.confirmed_at = datetime.now(UTC)
        version.confirmed_by = owner.id
    elif state == "executed":
        version.execution_state = "executed"
    else:
        gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_id=version.sow_id,
            sow_version_id=version.id, version=1, engagement_type="assessment", currency="USD")
        session.add(gm)
        await session.flush()
        session.add(ApprovalPackage(opportunity_id=deal.id, sow_version_id=version.id,
            gm_model_id=gm.id, package_hash="c" * 64, status=state, submitted_by=owner.id))
    await session.flush()
    before = copy.deepcopy(version.extracted_fields)
    with pytest.raises(SowError):
        await confirm_field(session, actor_id=owner.id, sow_version_id=version.id, field_name="price", value="1.00")
    assert version.extracted_fields == before


async def test_cached_second_session_preserves_first_session_field_confirmation(session, engine, source):
    owner, _, version = source
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as second:
        cached = await second.get(SowVersion, version.id)
        await second.commit()
        await confirm_field(session, actor_id=owner.id, sow_version_id=version.id,
                            field_name="term_start", value="2026-11-01")
        await session.commit()
        assert cached.extracted_fields["term_start"]["status"] == "unconfirmed"
        await confirm_field(second, actor_id=owner.id, sow_version_id=version.id,
                            field_name="term_end", value="2027-04-30")
        await second.commit()
    await session.refresh(version)
    for field, value in (("term_start", "2026-11-01"), ("term_end", "2027-04-30")):
        assert version.extracted_fields[field]["value"] == value
        assert version.extracted_fields[field]["status"] == "confirmed"


async def test_http_confirmation_mutation_conflict_is_409(session, source):
    owner, _, version = source
    version.confirmed_at, version.confirmed_by = datetime.now(UTC), owner.id
    await session.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: AuthUser(owner.id, owner.email, owner.name, ("Sales",))

    async def database():
        yield session

    app.dependency_overrides[get_session] = database
    app.dependency_overrides[get_sow_s3] = lambda: StubS3()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(f"/sow/versions/{version.id}/fields/price", json={"value": "1.00"})
    assert response.status_code == 409, response.text
