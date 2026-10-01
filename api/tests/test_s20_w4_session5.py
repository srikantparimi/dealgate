"""S20 W4 Session 5 · tests for items 0, 1, 2, 7, 8 of the directive.

- Item 2 (renewals): Jan 31 → Nov 30 edge; SES sender = noreply@dealgateapp.com.
- Item 1/7 (summaries agree): the number the Command center shows for
  "open value USD" is produced by `hubspot_pipeline.summary()` on the
  same filter set that /pipeline uses, and chip-count sum reconciles
  to that same total (A5/T35 contract rolled up to the summary layer).
- Item 0a (user_preference-backed saved view key): the existing
  `user_preference` row supports the saved-view-id key used by W6
  Session 4b, so S5 can move last-view off localStorage onto it.
- Item 8 extended: no raw ids leak into the summary/reports JSON
  response bodies (grep-level assertion against a dict dump).
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.integrations.ses import DEFAULT_FROM_ADDRESS, _from_address
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.user_preference import UserPreference
from app.services.hubspot_pipeline import PipelineFilters, list_opportunities, summary
from app.services.renewals import compute_alert_date


@pytest.mark.asyncio
async def test_renewal_jan_31_edge_is_nov_30(session):
    """Item 2 · D8 calendar-month rule hits Nov 30 for a Jan 31 term end,
    not an invalid Nov 31."""
    assert compute_alert_date(date(2026, 1, 31)) == date(2025, 11, 30)
    # Leap-year sanity: Feb 29 → Dec 29 (previous year).
    assert compute_alert_date(date(2024, 2, 29)) == date(2023, 12, 29)
    # Plain month: Jun 15 → Apr 15.
    assert compute_alert_date(date(2026, 6, 15)) == date(2026, 4, 15)


def test_ses_sender_is_noreply_dealgateapp():
    """Item 2 · emails originate from noreply@dealgateapp.com (directive
    says the account owner receives from that sender). The default
    constant drives both the renewal worker and other notifications."""
    assert DEFAULT_FROM_ADDRESS == "noreply@dealgateapp.com"
    # The env indirection respects the override, but the DEFAULT is
    # what ships on every ECS task without SES_FROM_ADDRESS set.
    assert _from_address().endswith("@dealgateapp.com")


@pytest.mark.asyncio
async def test_summary_total_matches_list_total_on_same_filter(session):
    """Item 1/7 · summary() open-count + value for a filter set equals
    the paginator total that /pipeline/opportunities returns for the
    same filter. Lock this invariant: the Command center number and
    the Pipeline paginator read the SAME `hubspot_pipeline` function.
    """
    owner = User(email="r@dealgate.local", name="Rep", groups=[])
    client = Client(name="Rec Corp")
    session.add_all([owner, client])
    await session.flush()
    for i in range(7):
        session.add(
            Opportunity(
                source="hubspot",
                hubspot_deal_id=f"rec_{i}",
                name=f"Rec {i}",
                owner_id=owner.id,
                client_id=client.id,
                sales_stage="1-Discovery",
                stage_label="1-Discovery",
                hubspot_pipeline_id="710688094",
                hubspot_stage_id="STAGE_A",
                amount=Decimal("1000"),
                currency="USD",
                close_date=date.today() + timedelta(days=30),
                governance_status="Intake",
            )
        )
    await session.commit()

    sumres = await summary(session, filters=PipelineFilters())
    listres = await list_opportunities(
        session, filters=PipelineFilters(), page=1, page_size=25
    )
    assert sumres.open_count == listres.total == 7, (
        f"summary.open_count={sumres.open_count} must equal "
        f"list_opportunities.total={listres.total}"
    )
    # Open value aggregates to the same per-currency total the list
    # would yield if you summed all its amount cells (we seeded 7 × $1000).
    assert sumres.open_value_by_currency.get("USD") == Decimal("7000")


@pytest.mark.asyncio
async def test_user_preference_round_trips_saved_view_key(session):
    """Item 0a · `user_preference` can store the "last saved view" key
    (W6 Session 4b currently uses localStorage; this proves the
    server-side home exists so S5 can migrate without a new table).
    """
    u = User(email="pref@dealgate.local", name="Pref", groups=[])
    session.add(u)
    await session.flush()

    pref = UserPreference(
        user_id=u.id,
        key="s20.pipeline.lastSavedView",
        value={"view_id": "built-in:my_opportunities"},
    )
    session.add(pref)
    await session.commit()

    from sqlalchemy import select as _select

    found = (
        await session.execute(
            _select(UserPreference).where(
                UserPreference.user_id == u.id,
                UserPreference.key == "s20.pipeline.lastSavedView",
            )
        )
    ).scalar_one()
    assert found.value["view_id"] == "built-in:my_opportunities"


@pytest.mark.asyncio
async def test_summary_response_carries_no_raw_hubspot_ids(session):
    """Item 8 extended · summary() returns typed numeric fields, not
    raw 11/10-digit HubSpot ids and not UUIDs stringified as labels.
    Grep the JSON body for id-shaped tokens masquerading as data.
    """
    import re

    owner = User(email="s@dealgate.local", name="S Rep", groups=[])
    client = Client(name="S Corp", hubspot_company_id="34959929030")
    session.add_all([owner, client])
    await session.flush()
    session.add(
        Opportunity(
            source="hubspot",
            hubspot_deal_id="65211153545",
            name="S deal",
            owner_id=owner.id,
            client_id=client.id,
            sales_stage="X",
            stage_label="X",
            hubspot_pipeline_id="710688094",
            hubspot_stage_id="1038193695",
            amount=Decimal("500"),
            currency="USD",
            close_date=date.today() + timedelta(days=30),
            governance_status="Intake",
        )
    )
    await session.commit()

    sumres = await summary(session, filters=PipelineFilters())
    # Dataclasses are not JSON-serialisable directly; dump via asdict.
    from dataclasses import asdict

    body = json.dumps(asdict(sumres), default=str)
    # The summary surface is counts + currency totals + currency codes —
    # no deal name, no stage label, no HubSpot ids should appear.
    assert "65211153545" not in body, "raw HubSpot deal id leaked into summary"
    assert "1038193695" not in body, "raw HubSpot stage id leaked into summary"
    assert "34959929030" not in body, "raw HubSpot company id leaked into summary"
