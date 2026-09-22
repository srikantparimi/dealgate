"""End-to-end confirmation flow tests (Sprint 9 wave 1).

Covers: extract → classify → auto-staff → auto-GM → confirmation payload
shape, needs_you ≤ 3 for a well-formed fixture, idempotent submit.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.integrations.bedrock_sow_extract import StubBedrock
from app.models.opportunity import Opportunity
from app.services.provenance import wrap
from app.services.sow_confirmation import (
    build_confirmation,
    serialize_confirmation,
    submit_confirmation,
)
from app.services.sow_extract import create_sow_version, run_extract, confirm_field
from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


OWNER = _uid("owner@smartek21.com")


@pytest_asyncio.fixture
async def seeded_sow(session):
    """Well-formed SOW fixture: uploaded, extracted, every field confirmed."""

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-CONF-1",
        owner_id=OWNER,
        governance_status="SOWDraft",
    )
    session.add(opp)
    await session.commit()
    state = await create_sow_version(
        session,
        opportunity_id=opp.id,
        uploaded_by=OWNER,
        file_s3_key="sow/x.pdf",
        file_hash="sha256:x",
    )
    await run_extract(session, sow_version_id=state.id, bedrock=StubBedrock())
    # Confirm every field so the version passes submit gates.
    for name in EXTRACTED_FIELDS:
        await confirm_field(
            session,
            actor_id=OWNER,
            sow_version_id=state.id,
            field_name=name,
            value=f"c-{name}",
        )
    # Add a staff_aug resource table so auto-staffing produces lines.
    from app.models.sow import SowVersion
    from sqlalchemy import select as _select

    row = (
        await session.execute(_select(SowVersion).where(SowVersion.id == state.id))
    ).scalar_one()
    fields = dict(row.extracted_fields or {})
    fields["resource_table"] = wrap(
        [
            {
                "role": "Engineer",
                "seniority": "Senior",
                "location": "US",
                "hours": 400,
                "hourly_rate": 200,
            },
            {
                "role": "PM",
                "seniority": "Senior",
                "location": "US",
                "hours": 200,
                "hourly_rate": 220,
            },
        ],
        provenance="extracted",
        page_ref=4,
    )
    row.extracted_fields = fields
    await session.commit()
    return {"opp": opp, "sow_version_id": state.id}


@pytest.mark.asyncio
async def test_build_confirmation_derives_full_package(seeded_sow, session):
    payload = await build_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    assert payload.engagement.primary.type in {
        "staff_aug",
        "single_resource",
        "fixed_price",
        "tm",
    }
    # staff_aug rule should fire with 2 rows in the resource table.
    assert payload.engagement.primary.type == "staff_aug"
    assert payload.engagement.auto_confirm is True
    assert len(payload.staffing.lines) == 2
    assert payload.gm_model is not None
    assert len(payload.gm_model.resource_lines) == 2
    # A well-formed SOW should have ≤ 3 needs_you slots.
    assert len(payload.needs_you) <= 3


@pytest.mark.asyncio
async def test_build_confirmation_serialises_cleanly(seeded_sow, session):
    payload = await build_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    dumped = serialize_confirmation(payload)
    assert dumped["engagement"]["primary"]["type"] == payload.engagement.primary.type
    assert "approvers" in dumped
    assert set(dumped["approvers"].keys()) == {"delivery", "hr", "finance", "legal"}
    assert "needs_you" in dumped
    assert "ceo_gate" in dumped


@pytest.mark.asyncio
async def test_build_confirmation_is_idempotent(seeded_sow, session):
    first = await build_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    second = await build_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    # Same GM model row on the second call — no duplicate insert.
    assert first.gm_model is not None and second.gm_model is not None
    assert first.gm_model.id == second.gm_model.id


@pytest.mark.asyncio
async def test_submit_confirmation_transitions_governance(seeded_sow, session):
    payload = await submit_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    assert payload.gm_model is not None
    from sqlalchemy import select
    from app.models.opportunity import Opportunity as Opp

    opp = (
        await session.execute(select(Opp).where(Opp.id == seeded_sow["opp"].id))
    ).scalar_one()
    assert opp.governance_status == "SOWDraft.confirmed"
    from app.models.sow import SowVersion
    version = await session.get(SowVersion, seeded_sow["sow_version_id"])
    assert version.confirmed_at is not None
    assert version.confirmed_by == OWNER


@pytest.mark.asyncio
async def test_submit_confirmation_is_idempotent(seeded_sow, session):
    payload_a = await submit_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    payload_b = await submit_confirmation(
        session, opportunity_id=seeded_sow["opp"].id, actor_id=OWNER
    )
    assert payload_a.gm_model is not None and payload_b.gm_model is not None
    assert payload_a.gm_model.id == payload_b.gm_model.id


@pytest.mark.asyncio
async def test_missing_scope_cannot_stamp_confirmation(seeded_sow, session):
    from fastapi import HTTPException
    from app.models.sow import SowVersion
    row = await session.get(SowVersion, seeded_sow['sow_version_id'])
    row.extracted_fields = {**row.extracted_fields, 'scope_summary': wrap(None, provenance='manual', status='confirmed')}
    await session.commit()
    with pytest.raises(HTTPException) as exc:
        await submit_confirmation(session, opportunity_id=seeded_sow['opp'].id, actor_id=OWNER)
    assert exc.value.status_code == 422
    assert row.confirmed_at is None


# --- what actually blocks submit (S10-11) --------------------------------


def test_fixed_fee_blocks_on_cost_not_bill_rate():
    """Reported: a fixed-price SOW demanded a bill rate on all three staffing
    lines, which is a number nobody has on a contract where nobody bills by
    the hour. Three of the five blockers were meaningless."""

    from decimal import Decimal

    from app.services.auto_staffing import AutoStaffingResult, StaffingLine
    from app.services.engagement_classifier import Candidate, ClassifierResult
    from app.services.sow_confirmation import _needs_you_for

    class _V:
        extracted_fields = {
            name: {"value": "x", "provenance": "extracted", "page_ref": 1}
            for name in (
                "scope_summary", "price", "term_start", "term_end",
                "deliverables", "signatories",
            )
        }

    def _line(bill: str, cost: str | None) -> StaffingLine:
        return StaffingLine(
            role="Consultant", seniority="Senior", location="US",
            allocation_pct=Decimal("1"), hours_billable=Decimal("160"),
            hourly_bill_rate=Decimal(bill), provenance="manual",
            hourly_cost=Decimal(cost) if cost else None,
        )

    fixed = ClassifierResult(
        primary=Candidate(type="fixed_price", confidence=1.0),
        rule_matched="rule.fixed_price_deliverables",
    )
    floors = {"has_gm": True, "gm_model_id": "gm-1"}

    # Cost present, bill rate zero → nothing blocks. This is the normal shape
    # of a fixed-fee plan.
    ok = _needs_you_for(
        _V(), fixed, AutoStaffingResult(lines=[_line("0", "95")]), floors
    )
    assert [g.field for g in ok] == []

    # Cost missing → that is the real blocker, because the margin on a fixed
    # fee is the fee against cost.
    missing = _needs_you_for(
        _V(), fixed, AutoStaffingResult(lines=[_line("225", None)]), floors
    )
    assert [g.field for g in missing] == ["staffing[0].hourly_cost"]

    # T&M is the other way round: revenue IS bill rate x hours.
    tm = ClassifierResult(
        primary=Candidate(type="tm", confidence=1.0), rule_matched="rule.tm"
    )
    tm_gaps = _needs_you_for(
        _V(), tm, AutoStaffingResult(lines=[_line("0", "95")]), floors
    )
    assert [g.field for g in tm_gaps] == ["staffing[0].hourly_bill_rate"]


def test_floors_do_not_pass_without_a_computed_margin():
    """Reported: the sheet read "Revenue 0.00, GM Unavailable" and still
    showed "Passes both floors". Nothing green should sit next to a number
    nobody computed."""

    from app.services.sow_confirmation import _compute_floors

    none_model = _compute_floors(None)
    assert none_model["us_pass"] is False
    assert none_model["india_pass"] is False
    assert none_model["has_gm"] is False
    assert none_model["requires_ceo"] is True
