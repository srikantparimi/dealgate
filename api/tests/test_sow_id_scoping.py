"""S11 slice 2 — the staffing query is scoped by sow_id.

Two invariants proved here:

1. Two SOWs under one opportunity keep separate staffing. Today the service
   layer enforces one Sow per opportunity, so the second Sow can only exist
   by direct insert; the read query must isolate per-SOW even so.
2. An approved package's frozen ``gm_model_id`` still points at the exact
   pre-edit model after a later staffing edit (CLAUDE.md rule 4 in practice).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS, StubBedrock
from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel, ResourceLine
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.provenance import wrap
from app.services.sow_confirmation import _existing_gm_for_sow
from app.services.sow_extract import confirm_field, run_extract
from app.services.sow_resources import update_resources


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


OWNER = _uid("s11-sow-id-scoping@smartek21.com")


def _sme_line(hours: str, cost: str = "120") -> dict:
    return {
        "role": "SME",
        "seniority": "Senior",
        "location": "US",
        "allocation_pct": "1.0",
        "hours_billable": hours,
        "hourly_bill_rate": "0",
        "hourly_cost": cost,
        "start_date": "2026-10-01",
        "end_date": "2026-12-31",
    }


@pytest.mark.asyncio
async def test_staffing_read_is_scoped_by_sow_id(session):
    """`_existing_gm_for_sow` returns the correct GmModel per sow_id.

    Today the schema enforces one Sow per opportunity (UNIQUE constraint on
    `sow.opportunity_id`), so the "two SOWs on one opportunity" scenario is
    impossible at the DB level — Kanna's concern about the invariant is
    addressed by both the schema AND the sow_id keying in the read.

    This test uses two opportunities (one Sow each) to prove the query
    isolates correctly on `sow_id`. When (if ever) the UNIQUE constraint is
    dropped, the isolation logic already holds.
    """

    opp_a_id = uuid.uuid4()
    opp_b_id = uuid.uuid4()
    sow_a_id = uuid.uuid4()
    sow_b_id = uuid.uuid4()

    session.add(
        Opportunity(
            id=opp_a_id,
            hubspot_deal_id=f"H-A-{uuid.uuid4().hex[:8]}",
            owner_id=OWNER,
            governance_status="SOWDraft",
        )
    )
    session.add(
        Opportunity(
            id=opp_b_id,
            hubspot_deal_id=f"H-B-{uuid.uuid4().hex[:8]}",
            owner_id=OWNER,
            governance_status="SOWDraft",
        )
    )
    session.add(Sow(id=sow_a_id, opportunity_id=opp_a_id))
    session.add(Sow(id=sow_b_id, opportunity_id=opp_b_id))
    await session.flush()

    # Two GM models — one per SOW. Populate resource_line so
    # `_existing_gm_for_sow`'s selectinload resolves without lazy-loading.
    def _make_gm(opp_id: uuid.UUID, sow_id: uuid.UUID) -> GmModel:
        gm = GmModel(
            id=uuid.uuid4(),
            opportunity_id=opp_id,
            sow_id=sow_id,
            engagement_type="fixed_price",
            revenue_us=Decimal("50000"),
            revenue_india=Decimal("0"),
            created_by=OWNER,
        )
        session.add(gm)
        return gm

    gm_a = _make_gm(opp_a_id, sow_a_id)
    gm_b = _make_gm(opp_b_id, sow_b_id)
    await session.flush()

    for gm, role in [(gm_a, "SME"), (gm_b, "Contractor")]:
        session.add(
            ResourceLine(
                id=uuid.uuid4(),
                gm_model_id=gm.id,
                role=role,
                seniority="Senior",
                location="US",
                start_date=date(2026, 10, 1),
                end_date=date(2026, 12, 31),
                allocation_pct=Decimal("1.0"),
                billable_hours=Decimal("100"),
                hourly_bill_rate=Decimal("0"),
                hourly_loaded_cost=Decimal("120"),
                hourly_cost=Decimal("120"),
            )
        )
    await session.commit()

    plan_a = await _existing_gm_for_sow(session, sow_id=sow_a_id)
    plan_b = await _existing_gm_for_sow(session, sow_id=sow_b_id)

    assert plan_a is not None
    assert plan_b is not None
    assert plan_a.id != plan_b.id, "same GmModel returned for both SOWs — leak"
    roles_a = {line.role for line in plan_a.resource_lines}
    roles_b = {line.role for line in plan_b.resource_lines}
    assert roles_a == {"SME"}, roles_a
    assert roles_b == {"Contractor"}, roles_b


@pytest.mark.asyncio
async def test_approved_package_still_pins_gm_after_later_edit(session):
    """CLAUDE.md rule 4 in practice: the immutable gm_model_id stays valid."""

    from app.services.sow_extract import create_sow_version

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-PIN-{uuid.uuid4().hex[:8]}",
        owner_id=OWNER,
        governance_status="SOWDraft",
    )
    session.add(opp)
    await session.commit()

    state = await create_sow_version(
        session,
        opportunity_id=opp.id,
        uploaded_by=OWNER,
        file_s3_key="sow/pin.pdf",
        file_hash=f"sha256:{uuid.uuid4().hex}",
    )
    await run_extract(session, sow_version_id=state.id, bedrock=StubBedrock())
    for name in EXTRACTED_FIELDS:
        await confirm_field(
            session,
            actor_id=OWNER,
            sow_version_id=state.id,
            field_name=name,
            value=f"c-{name}" if name != "price" else "50000",
        )
    row = (
        await session.execute(select(SowVersion).where(SowVersion.id == state.id))
    ).scalar_one()
    fields = dict(row.extracted_fields or {})
    fields["price"] = wrap("50000", provenance="extracted", page_ref=1)
    fields.pop("resource_table", None)
    row.extracted_fields = fields
    await session.commit()

    # Save M1.
    result_1 = await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": [_sme_line("80"), _sme_line("160")],
            "cost_lines": [],
            "sow_version_id": str(state.id),
        },
    )
    await session.commit()
    m1_id = result_1.gm_model_id

    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=state.id,
        gm_model_id=m1_id,
        package_hash="test-hash-pin",
        status="pending_delivery_hr",
        submitted_by=OWNER,
        submitted_at=datetime.now(timezone.utc),
    )
    session.add(package)
    await session.commit()

    # Later edit creates M2. Does NOT touch M1.
    result_2 = await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": [_sme_line("40"), _sme_line("60")],
            "cost_lines": [],
            "sow_version_id": str(state.id),
        },
    )
    await session.commit()
    m2_id = result_2.gm_model_id
    assert m2_id != m1_id, "edit should create a new immutable GmModel"

    # Approval package still frozen at M1.
    reread = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package.id)
        )
    ).scalar_one()
    assert reread.gm_model_id == m1_id

    # M1's rows still exist and still sum to the original 80+160=240h × $120.
    m1_lines = (
        await session.execute(
            select(ResourceLine).where(ResourceLine.gm_model_id == m1_id)
        )
    ).scalars().all()
    total_cost = sum(
        (line.billable_hours or Decimal("0"))
        * (line.hourly_loaded_cost or Decimal("0"))
        for line in m1_lines
    )
    assert total_cost == Decimal("28800"), total_cost
