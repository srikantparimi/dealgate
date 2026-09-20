"""SOWs in progress must be findable (S10-10).

The reported symptom was "once I refresh the screen after I upload a SOW it
should be draft status so I can work on it again, now it's all gone".

Nothing was lost. The opportunity, the SOW version and the extracted fields
were all safely stored — but the approvals board lists approval *packages*,
so a SOW that had not reached one appeared in no lane at all, and no endpoint
anywhere could list it. The only route back was browser history.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.sow_lifecycle import draft_sows

OWNER_EMAIL = "delivery@smartek21.com"


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery,SystemAdmin")


@pytest_asyncio.fixture
async def app_with_deps(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


async def _seed_upload(session, *, with_package: bool = False):
    from app.auth.deps import _fake_user_from_email

    actor = _fake_user_from_email(OWNER_EMAIL, ("Delivery",))
    user = User(id=actor.id, email=OWNER_EMAIL, name="D", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Contoso Data Services, LLC")
    session.add_all([user, client])
    await session.flush()

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=None,
        client_id=client.id,
        owner_id=user.id,
        governance_status="Intake",
        source="sow_upload",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=user.id,
        file_s3_key="sow/x.docx",
        file_hash=f"h-{uuid.uuid4().hex[:8]}",
        extract_status="complete",
        version_no=1,
        extracted_fields={
            "scope_summary": {
                "value": "Discovery assessment across three tracks",
                "provenance": "extracted",
                "page_ref": 6,
                "status": "unconfirmed",
            }
        },
    )
    session.add(version)
    await session.flush()

    if with_package:
        session.add(
            ApprovalPackage(
                id=uuid.uuid4(),
                opportunity_id=opp.id,
                sow_version_id=version.id,
                gm_model_id=uuid.uuid4(),
                policy_version_id=uuid.uuid4(),
                package_hash="x" * 64,
                status="pending_delivery_hr",
                submitted_by=user.id,
            )
        )
    await session.commit()
    return opp, version


async def test_an_uploaded_sow_is_findable_again(session):
    """The whole point: after a refresh there has to be a way back."""

    opp, version = await _seed_upload(session)
    rows = await draft_sows(session)

    assert [d.opportunity_id for d in rows] == [opp.id]
    d = rows[0]
    assert d.client_name == "Contoso Data Services, LLC"
    assert d.title.startswith("Discovery assessment")
    assert d.sow_version_id == version.id
    assert d.has_gm is False


async def test_a_submitted_sow_is_not_a_draft(session):
    """Once it has a package it belongs on the approvals board, not here —
    otherwise the same SOW appears in two places."""

    await _seed_upload(session, with_package=True)
    assert await draft_sows(session) == []


async def test_drafts_endpoint_says_where_to_resume(app_with_deps, session):
    opp, _v = await _seed_upload(session)

    async with _client(app_with_deps) as c:
        r = await c.get("/sows/drafts", headers={"X-Test-User": OWNER_EMAIL})

    assert r.status_code == 200, r.text
    drafts = r.json()["drafts"]
    assert len(drafts) == 1
    row = drafts[0]
    assert row["opportunity_id"] == str(opp.id)
    # No margin yet, so the way back is the staffing gate — not the confirm
    # screen, which would only show an empty GM again.
    assert row["resume_href"] == f"/sows/{opp.id}/staffing"
    assert row["has_gm"] is False


async def test_resume_points_at_confirmation_once_a_margin_exists(
    app_with_deps, session
):
    from app.models.gm_model import GmModel

    opp, version = await _seed_upload(session)
    session.add(
        GmModel(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            sow_version_id=version.id,
            engagement_type="fixed_price",
            revenue_us=0,
            revenue_india=0,
        )
    )
    await session.commit()

    async with _client(app_with_deps) as c:
        r = await c.get("/sows/drafts", headers={"X-Test-User": OWNER_EMAIL})

    row = r.json()["drafts"][0]
    assert row["has_gm"] is True
    assert row["resume_href"] == f"/sows/new?opportunityId={opp.id}"


async def test_hubspot_sourced_opportunities_are_not_listed(session):
    """Only SOW-first work. A HubSpot deal has its own board and lifecycle."""

    from app.auth.deps import _fake_user_from_email

    actor = _fake_user_from_email(OWNER_EMAIL, ("Delivery",))
    user = User(id=actor.id, email=OWNER_EMAIL, name="D", groups=["Delivery"])
    session.add(user)
    await session.flush()
    session.add(
        Opportunity(
            id=uuid.uuid4(),
            hubspot_deal_id="hs-1",
            owner_id=user.id,
            governance_status="Intake",
            source="hubspot",
        )
    )
    await session.commit()

    assert await draft_sows(session) == []
