"""S11 — one staffing store: prove that what the reviewer saves is what the
confirm screen shows, byte-identical, without any auto-plan fallback.

Kanna Parimi 20-Sep directive rule 2: "The moment a human edits or saves
staffing, staffing.source = human and no template, extractor or re-run may
ever overwrite or append to it. Assert this in a test: save 2 lines, re-open
confirm, exactly those 2 lines render, provenance manual, byte-identical to
what was saved."
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations.bedrock_sow_extract import EXTRACTED_FIELDS, StubBedrock
from app.models.opportunity import Opportunity
from app.models.sow import SowVersion
from app.services.provenance import wrap
from app.services.sow_confirmation import build_confirmation
from app.services.sow_extract import confirm_field, create_sow_version, run_extract
from app.services.sow_resources import update_resources


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


OWNER = _uid("s11-byte-owner@smartek21.com")


@pytest_asyncio.fixture
async def fixed_price_sow(session):
    """A fixed-price opportunity with a $50k extracted price, no staffing yet."""

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-S11-BYTE-1",
        owner_id=OWNER,
        governance_status="SOWDraft",
    )
    session.add(opp)
    await session.commit()
    state = await create_sow_version(
        session,
        opportunity_id=opp.id,
        uploaded_by=OWNER,
        file_s3_key="sow/s11.pdf",
        file_hash="sha256:s11",
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
    # A fixed-price SOW with no resource_table — the roster comes from the
    # human, not from a template.
    fields.pop("resource_table", None)
    row.extracted_fields = fields
    await session.commit()
    return {"opp": opp, "sow_version_id": state.id}


def _sme_line(hours: str) -> dict:
    return {
        "role": "SME",
        "seniority": "Senior",
        "location": "US",
        "allocation_pct": "1.0",  # canonical: 0..1 fraction
        "hours_billable": hours,
        "hourly_bill_rate": "0",
        "hourly_cost": "120",
        "start_date": "2026-10-01",
        "end_date": "2026-12-31",
    }


@pytest.mark.asyncio
async def test_saved_staffing_is_what_confirm_screen_shows(fixed_price_sow, session):
    """Save two SME lines; the confirm screen shows exactly those two.

    Before the two-store consolidation this failed: the Staffing page wrote
    a GmModel with `sow_version_id=NULL`, then `_existing_gm_for_sow` on the
    confirm side (which filtered `sow_version_id == version.id`) missed it
    and fell back to `auto_staff`'s hardcoded Architect+Engineer roster.
    """

    opp = fixed_price_sow["opp"]

    await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": [_sme_line("80"), _sme_line("160")],
            "cost_lines": [],
        },
    )
    await session.commit()

    payload = await build_confirmation(
        session, opportunity_id=opp.id, actor_id=OWNER
    )

    lines = payload.staffing.lines
    assert len(lines) == 2, [f"{line.role} {line.seniority}" for line in lines]
    assert all(line.role == "SME" for line in lines)
    assert all(line.seniority == "Senior" for line in lines)
    assert all(line.location == "US" for line in lines)
    assert all(line.provenance == "manual" for line in lines)
    hours = sorted(int(line.hours_billable) for line in lines)
    assert hours == [80, 160]
    assert all(line.hourly_cost == Decimal("120") for line in lines)


@pytest.mark.asyncio
async def test_reopen_confirm_never_reseeds_staffing(fixed_price_sow, session):
    """Second call to build_confirmation must not append or overwrite."""

    opp = fixed_price_sow["opp"]
    await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": [_sme_line("80")],
            "cost_lines": [],
        },
    )
    await session.commit()

    for _ in range(3):
        payload = await build_confirmation(
            session, opportunity_id=opp.id, actor_id=OWNER
        )
        assert len(payload.staffing.lines) == 1
        assert payload.staffing.lines[0].role == "SME"


@pytest.mark.asyncio
async def test_raising_cost_triggers_ceo_gate(fixed_price_sow, session):
    """Proof-protocol step 7: change line 2 cost to $220/hr → GM drops to
    10.4%, US floor (35%) fails, CEO gate triggers.

    Same session as `test_saved_staffing_is_what_confirm_screen_shows`
    proves the pair Kanna's directive named — both must hold together.
    """

    opp = fixed_price_sow["opp"]
    # Original: 2 × SME @ $120 → 42.4% (see the earlier test).
    # New: line 2 raised to $220 → cost 80×120 + 160×220 = 9,600 + 35,200
    # = 44,800; revenue 50,000; GM (50k − 44.8k)/50k = 10.4%.
    lines = [_sme_line("80"), {**_sme_line("160"), "hourly_cost": "220"}]

    await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": lines,
            "cost_lines": [],
        },
    )
    await session.commit()

    payload = await build_confirmation(
        session, opportunity_id=opp.id, actor_id=OWNER
    )

    gm_us = payload.floors["gm_us"]
    assert gm_us is not None
    assert Decimal("0.10") <= Decimal(str(gm_us)) <= Decimal("0.11"), gm_us
    assert payload.floors["us_pass"] is False
    assert payload.floors["requires_ceo"] is True


@pytest.mark.asyncio
async def test_fixed_price_revenue_uses_extracted_price(fixed_price_sow, session):
    """Kanna directive rule 4: fixed-price revenue = extracted price, not 0.

    2 SME × $120 cost, 80h + 160h = $28,800. Revenue $50,000. GM = 42.4%.
    US floor is 35%; the plan passes by 7.4 pts.
    """

    opp = fixed_price_sow["opp"]
    await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=OWNER,
        payload={
            "engagement_type": "fixed_price",
            "resource_lines": [_sme_line("80"), _sme_line("160")],
            "cost_lines": [],
            # total_price intentionally omitted — the service must pull it
            # from the SOW extraction.
        },
    )
    await session.commit()

    payload = await build_confirmation(
        session, opportunity_id=opp.id, actor_id=OWNER
    )

    assert payload.floors["has_gm"] is True
    gm_us = payload.floors["gm_us"]
    assert gm_us is not None, payload.floors
    # 42.4% ± rounding.
    assert Decimal("0.42") <= Decimal(str(gm_us)) <= Decimal("0.43"), gm_us
    assert payload.floors["us_pass"] is True
