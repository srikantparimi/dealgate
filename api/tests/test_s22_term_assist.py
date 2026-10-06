"""S22 click-through fix · duration-aware term assist.

Owner finding: a SOW stating "seven weeks" (or a milestone plan ending
at Week 7) left Term start/end blank with no help. The assist derives
the stated duration deterministically and computes the end date from a
human-supplied kickoff — a labeled suggestion, never a guess.
"""

from __future__ import annotations

from datetime import date

from app.services.term_assist import derived_end, stated_duration


def fields(**kw):
    return {name: {"value": value, "status": "confirmed"} for name, value in kw.items()}


def test_milestone_week_labels_yield_the_plan_span():
    extracted = fields(
        milestones=(
            "Week 1 — Kickoff & Discovery: Stakeholder mapping, Weeks 2–5 — "
            "Parallel Workstream Execution, Week 6 — Synthesis, Week 7 — "
            "Roadmap & Executive Readout: Prioritization and findings "
            "presentation to leadership"
        ),
    )
    duration = stated_duration(extracted)
    assert duration == {
        "weeks": 7,
        "source_field": "milestones",
        "quote": duration["quote"],
    }
    assert "Week 7" in duration["quote"]


def test_explicit_weeks_statement_wins_over_milestone_labels():
    extracted = fields(
        scope_summary="A seven (7) week ServiceNow assessment",
        milestones="Week 1 kickoff ... Week 6 readout",
    )
    duration = stated_duration(extracted)
    assert duration["weeks"] == 7
    assert duration["source_field"] == "scope_summary"


def test_worded_duration_and_months_are_understood():
    assert stated_duration(fields(scope_summary="runs for twelve weeks"))["weeks"] == 12
    months = stated_duration(fields(billing_basis="a 6-month managed service"))
    assert months["months"] == 6


def test_no_stated_duration_stays_unknown():
    assert stated_duration(fields(scope_summary="an assessment of the platform")) is None
    assert stated_duration(None) is None


def test_derived_end_is_inclusive_week_arithmetic():
    # 7 weeks from a 2026-10-01 kickoff runs through 2026-11-18.
    assert derived_end(date(2026, 10, 1), {"weeks": 7}) == date(2026, 11, 18)
    # 6 months from Jan 15 ends Jul 14.
    assert derived_end(date(2026, 1, 15), {"months": 6}) == date(2026, 7, 14)
    # Month-end clamping: 6 months from Aug 31 → end of Feb.
    assert derived_end(date(2026, 8, 31), {"months": 6}) == date(2027, 2, 27)


import uuid
from datetime import UTC, datetime

import pytest


async def _seed_version(session):
    from app.models.client import Client
    from app.models.opportunity import Opportunity
    from app.models.sow import Sow, SowVersion
    from app.models.user import User

    owner = User(id=uuid.uuid4(), email=f"ta-{uuid.uuid4().hex[:6]}@smartek21.com",
                 name="Term Assist", groups=["Delivery"])
    client = Client(id=uuid.uuid4(), name="Assist Client")
    session.add_all([owner, client])
    await session.flush()
    opp = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id,
                      governance_status="Intake")
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    version = SowVersion(
        id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner.id,
        file_s3_key="ta/v1.docx", file_hash=uuid.uuid4().hex * 2,
        extract_status="complete",
        extracted_fields={
            "milestones": {"value": "Week 1 — Kickoff, Week 7 — Roadmap & Executive Readout",
                            "status": "confirmed"},
        },
        confirmed_by=owner.id, confirmed_at=datetime.now(UTC),
    )
    session.add(version)
    await session.commit()
    return version


@pytest.mark.asyncio
async def test_endpoint_gates_roles_and_derives_the_end(session, monkeypatch):
    import httpx

    from app.db import get_session
    from app.main import app as main_app

    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("S3_STUB", "1")
    version = await _seed_version(session)

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "officeapp-e2e")
            denied = await c.get(
                f"/sow/versions/{version.id}/term-assist",
                headers={"X-Test-User": "ta@smartek21.com"},
            )
            assert denied.status_code == 403
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
            ok = await c.get(
                f"/sow/versions/{version.id}/term-assist?start=2026-10-01",
                headers={"X-Test-User": "ta@smartek21.com"},
            )
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["available"] is True and body["weeks"] == 7
            assert body["suggested_end"] == "2026-11-18"
            assert "Week 7" in body["quote"]
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_staffing_draft_dates_win_over_stated_duration(session, monkeypatch):
    """Round 3: the user's own role dates become the one-click term
    suggestion — no retyping facts the draft already holds."""
    import httpx

    from app.db import get_session
    from app.main import app as main_app
    from app.models.commercial_draft import CommercialDraft
    from app.models.user import User
    from app.models.sow import Sow, SowVersion
    from sqlalchemy import select

    monkeypatch.setenv("DEALGATE_ENV", "local")
    version = await _seed_version(session)
    sow = await session.get(Sow, version.sow_id)
    actor = (await session.scalars(select(User))).first()
    session.add(CommercialDraft(
        opportunity_id=sow.opportunity_id,
        sow_version_id=version.id,
        inputs={
            "service_start": None,
            "service_end": None,
            "staffing": [
                {"start": "2026-10-01", "end": "2026-11-15"},
                {"start": "2026-10-15", "end": "2026-12-01"},
            ],
        },
        updated_by=actor.id,
    ))
    await session.commit()

    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        transport = httpx.ASGITransport(app=main_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Delivery")
            ok = await c.get(
                f"/sow/versions/{version.id}/term-assist",
                headers={"X-Test-User": "ta2@smartek21.com"},
            )
            body = ok.json()
            assert body["source"] == "staffing_draft"
            assert body["suggested_start"] == "2026-10-01"  # earliest role start
            assert body["suggested_end"] == "2026-12-01"  # latest role end
    finally:
        main_app.dependency_overrides.pop(get_session, None)
