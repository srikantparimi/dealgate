"""S21F:T24.04 — re-upload/retry/re-extract never duplicate forecast plans.

The connected journey is upload -> extraction -> (plan prepared once for the
opportunity). Each replay surface the owner can reach — same-byte re-upload,
failed-job retry upload, extraction replay, and an idempotent plan save retry
— must leave exactly one ForecastPlan, one ForecastPlanVersion and one
ForecastJob. A retry that silently carries different inputs under the same
idempotency key is a 409, never a second plan.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi import HTTPException
from pydantic import TypeAdapter
from sqlalchemy import select

from app.auth import AuthUser
from app.gm.commercial import PricingComponent
from app.models.forecast import ForecastJob, ForecastPlan, ForecastPlanVersion
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.sow_upload_job import SowUploadJob
from app.models.user import User
from app.services.forecast_plans import PlanInput, save_plan
from tests.test_s21_commercial_profiles import component
from tests.test_sow_upload_router import (  # noqa: F401
    OWNER_EMAIL,
    _client,
    _load_pdf,
    _seed_client,
    _StubBedrockWithClient,
    app_with_deps,
)

PDF_CONTENT_TYPE = "application/pdf"


class _DraftStubBedrock(_StubBedrockWithClient):
    """Same client signals, no signatories: the version stays a mutable
    draft, which is the state the Confirm page's re-extract retry targets."""

    def extract(self, doc):
        result = super().extract(doc)
        fields = dict(result.fields)
        fields.pop("signatories", None)
        return type(result)(
            fields=fields, model=result.model, prompt_version=result.prompt_version
        )


def _override_bedrock(client_name: str) -> None:
    from app.integrations.bedrock_sow_extract import get_bedrock_sow
    from app.main import app as main_app

    main_app.dependency_overrides[get_bedrock_sow] = lambda: _DraftStubBedrock(
        client_name
    )


@pytest.fixture(autouse=True)
def _plan_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "s21-plan-singularity")
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")


def _plan_body(account_id, opportunity_id, idempotency_key, title="Plan from SOW"):
    return PlanInput(
        account_id=account_id,
        opportunity_id=opportunity_id,
        title=title,
        idempotency_key=idempotency_key,
        inputs=TypeAdapter(PricingComponent).dump_python(
            component(policy_version="blueprint-defaults-v1"), mode="json"
        ),
        probability="0.70",
        probability_source="Reviewed sales assumption",
        assumptions=["Derived once from the extracted SOW"],
        change_reason="Plan prepared from the confirmed extraction",
    )


async def _plan_counts(session):
    plans = (await session.scalars(select(ForecastPlan))).all()
    versions = (await session.scalars(select(ForecastPlanVersion))).all()
    jobs = (await session.scalars(select(ForecastJob))).all()
    return plans, versions, jobs


async def _upload(app, payload, filename="sow.pdf"):
    async with _client(app) as c:
        response = await c.post(
            "/sows/upload",
            headers={"X-Test-User": OWNER_EMAIL},
            files={"file": (filename, payload, PDF_CONTENT_TYPE)},
        )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_reupload_retry_and_reextract_leave_exactly_one_plan(
    app_with_deps, session  # noqa: F811
):
    client = await _seed_client(session, "Singular Plan Client")
    _override_bedrock("Singular Plan Client")
    payload = _load_pdf("05_tm_capped.pdf")

    first = await _upload(app_with_deps, payload)
    assert first["status"] == "done"
    opportunity_id = uuid.UUID(first["opportunity_id"])

    owner = await session.scalar(select(User).where(User.email == OWNER_EMAIL))
    planner = AuthUser(
        id=owner.id, email=owner.email, name=owner.name, groups=("Delivery",)
    )
    journey_key = uuid.uuid4()
    body = _plan_body(client.id, opportunity_id, journey_key)
    created = await save_plan(session, actor=planner, body=body)

    plans, versions, jobs = await _plan_counts(session)
    assert [p.opportunity_id for p in plans] == [opportunity_id]
    assert len(versions) == 1 and len(jobs) == 1

    # 1. Same-byte re-upload returns the original job and prepares nothing new.
    duplicate = await _upload(app_with_deps, payload)
    assert duplicate["duplicate"] is True
    assert duplicate["job_id"] == first["job_id"]

    # 2. A failed upload job retried with the same bytes reuses every row.
    job = await session.scalar(select(SowUploadJob))
    job.status = "failed"
    job.error = "simulated transient failure"
    await session.commit()
    retried = await _upload(app_with_deps, payload)
    assert retried["duplicate"] is False and retried["status"] == "done"

    # 3. Extraction replay on the same mutable version touches no plan rows.
    # The offline stub returns empty bytes; replay verifies byte identity
    # against the stored hash, so serve the real document back.
    app_with_deps.state.stub_s3.download_bytes = lambda key: payload
    version_id = await session.scalar(select(SowVersion.id))
    async with _client(app_with_deps) as c:
        reextract = await c.post(
            f"/sow/versions/{version_id}/reextract",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert reextract.status_code == 200, reextract.text

    # 4. The plan save retried under the journey's idempotency key replays.
    replay = await save_plan(session, actor=planner, body=body)
    assert replay.id == created.id

    plans, versions, jobs = await _plan_counts(session)
    assert len(plans) == 1 and len(versions) == 1 and len(jobs) == 1
    assert plans[0].id == created.plan_id
    assert len((await session.scalars(select(Opportunity))).all()) == 1
    assert len((await session.scalars(select(Sow))).all()) == 1
    assert len((await session.scalars(select(SowVersion))).all()) == 1
    assert len((await session.scalars(select(SowUploadJob))).all()) == 1


@pytest.mark.asyncio
async def test_same_key_with_changed_inputs_is_rejected_not_duplicated(
    app_with_deps, session  # noqa: F811
):
    client = await _seed_client(session, "Conflicting Retry Client")
    _override_bedrock("Conflicting Retry Client")
    result = await _upload(app_with_deps, _load_pdf("05_tm_capped.pdf"))
    assert result["status"] == "done"
    opportunity_id = uuid.UUID(result["opportunity_id"])

    owner = await session.scalar(select(User).where(User.email == OWNER_EMAIL))
    planner = AuthUser(
        id=owner.id, email=owner.email, name=owner.name, groups=("Delivery",)
    )
    journey_key = uuid.uuid4()
    await save_plan(
        session, actor=planner, body=_plan_body(client.id, opportunity_id, journey_key)
    )

    drifted = _plan_body(
        client.id, opportunity_id, journey_key, title="Silently changed retry"
    )
    with pytest.raises(HTTPException) as error:
        await save_plan(session, actor=planner, body=drifted)
    assert error.value.status_code == 409
    await session.rollback()

    plans, versions, jobs = await _plan_counts(session)
    assert len(plans) == 1 and len(versions) == 1 and len(jobs) == 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DEALGATE_POSTGRES_URL"),
    reason="requires disposable migrated Postgres",
)
async def test_concurrent_same_key_saves_create_one_plan():
    """Two writers racing the same journey idempotency key on real Postgres:
    the account lock serializes them, the loser replays the winner's version,
    and the unique request constraint holds exactly one plan."""

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from tests.test_approval_routing import fixture

    url = os.environ["DEALGATE_POSTGRES_URL"].replace(
        "postgresql://", "postgresql+psycopg://"
    )
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            owner, opp, _, _, _ = await fixture(session)
            account_id, opportunity_id = opp.client_id, opp.id
            planner = AuthUser(
                id=owner.id, email=owner.email, name=owner.name, groups=("Delivery",)
            )
        body = _plan_body(account_id, opportunity_id, uuid.uuid4())

        async def save():
            async with factory() as racing:
                return await save_plan(racing, actor=planner, body=body)

        first, second = await asyncio.gather(save(), save())
        assert first.id == second.id

        async with factory() as session:
            plans = (
                await session.scalars(
                    select(ForecastPlan).where(
                        ForecastPlan.opportunity_id == opportunity_id
                    )
                )
            ).all()
            assert len(plans) == 1
            versions = (
                await session.scalars(
                    select(ForecastPlanVersion).where(
                        ForecastPlanVersion.plan_id == plans[0].id
                    )
                )
            ).all()
            assert len(versions) == 1
    finally:
        await engine.dispose()
