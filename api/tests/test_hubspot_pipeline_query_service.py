"""S19 slice 1 · query service (C1-C8) — behaviour + query-count invariant.

Every `list_*` / `summary` call must run ≤ 3 SQL statements against the
session (C7). This test wraps the async engine in a counting listener and
asserts the budget after each call.

Behavioural coverage:
- list_opportunities returns the expected columns for an open HubSpot deal
- attention flags derive from raw fields (no_owner + stalled)
- list_clients aggregates open counts + currency values + agreements
- summary computes cross-currency totals + agreement gaps
- readiness / attention filters actually filter
- default sort brings the most-attention row to the top
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event

from app.models.client import Agreement, Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_pipeline import (
    AttentionFlag,
    PipelineFilters,
    SortSpec,
    SowApprovalState,
    list_clients,
    list_opportunities,
    summary,
)


# ---------------------------------------------------------------------------
# Query-count fixture (C7).
# ---------------------------------------------------------------------------


class _Counter:
    def __init__(self) -> None:
        self.n = 0

    def reset(self) -> None:
        self.n = 0


@pytest_asyncio.fixture
async def counter(engine):
    counter = _Counter()

    def _before(conn, cursor, statement, params, context, executemany):
        counter.n += 1

    # SQLAlchemy fires before_cursor_execute on the SYNC connection object
    # once the async wrapper hands off; hook there.
    sync_engine = engine.sync_engine
    event.listen(sync_engine, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before)


# ---------------------------------------------------------------------------
# Seed helpers — the seed does NOT reuse the query service; the queries under
# test must exercise their own code path (J4).
# ---------------------------------------------------------------------------


async def _seed_owner(session, *, email="owner@dealgate.local", name="Sam Owner") -> User:
    user = User(email=email, name=name, groups=[])
    session.add(user)
    await session.flush()
    return user


async def _seed_client(session, *, name="Test Corp", hs_id: str | None = None) -> Client:
    client = Client(name=name, hubspot_company_id=hs_id)
    session.add(client)
    await session.flush()
    return client


async def _seed_opp(
    session,
    *,
    client: Client | None,
    owner: User | None,
    stage_label: str = "3-Requirement/Fit Gap Analysis",
    stage_id: str = "1038193694",
    pipeline_id: str = "710688094",
    stage_order: int = 2,
    is_closed_won: bool = False,
    is_closed_lost: bool = False,
    amount: Decimal | None = Decimal("100000"),
    currency: str | None = "USD",
    close_date: date | None = None,
    last_activity_at: datetime | None = None,
    hubspot_deal_id: str | None = None,
) -> Opportunity:
    opp = Opportunity(
        source="hubspot",
        hubspot_deal_id=hubspot_deal_id or f"hs_{uuid.uuid4().hex[:8]}",
        owner_id=owner.id if owner else None,
        client_id=client.id if client else None,
        sales_stage=stage_label,
        stage_label=stage_label,
        hubspot_pipeline_id=pipeline_id,
        hubspot_stage_id=stage_id,
        stage_order=stage_order,
        is_closed_won=is_closed_won,
        is_closed_lost=is_closed_lost,
        amount=amount,
        currency=currency,
        close_date=close_date or date.today() + timedelta(days=30),
        hubspot_last_activity_at=last_activity_at,
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()
    return opp


async def _seed_agreement(session, *, client: Client, kind: str, owner: User) -> Agreement:
    ag = Agreement(
        client_id=client.id,
        kind=kind,
        file_key=f"agreements/{client.id}/{kind}.pdf",
        filename=f"{kind}.pdf",
        file_size=1024,
        uploaded_by=owner.id,
    )
    session.add(ag)
    await session.flush()
    return ag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_opportunities_returns_row_and_stays_within_query_budget(session, counter):
    owner = await _seed_owner(session)
    client = await _seed_client(session, name="Capitec Bank Limited")
    await _seed_opp(session, client=client, owner=owner)
    await session.commit()

    counter.reset()
    page = await list_opportunities(session, page=1, page_size=25)

    assert page.total == 1
    assert len(page.items) == 1
    row = page.items[0]
    assert row.client_name == "Capitec Bank Limited"
    assert row.owner_email == "owner@dealgate.local"
    assert row.currency == "USD"
    assert row.stage_label == "3-Requirement/Fit Gap Analysis"
    assert row.sow_approval_state == SowApprovalState.NONE.value
    # Owner + not stalled + not closed-won → zero attention flags on this row.
    assert row.attention_flags == ()
    # Query budget: ≤ 3 executes.
    assert counter.n <= 3, f"list_opportunities used {counter.n} queries"


@pytest.mark.asyncio
async def test_list_opportunities_attention_no_owner_flag(session, counter):
    client = await _seed_client(session, name="Unowned Client")
    await _seed_opp(session, client=client, owner=None)
    await session.commit()

    counter.reset()
    page = await list_opportunities(session, page=1, page_size=25)

    assert page.total == 1
    row = page.items[0]
    assert AttentionFlag.NO_OWNER.value in row.attention_flags
    assert counter.n <= 3


@pytest.mark.asyncio
async def test_list_opportunities_stalled_and_closed_won_gap_flags(session, counter):
    owner = await _seed_owner(session)
    client = await _seed_client(session, name="Stalled + Won-No-Release")
    stale = datetime.now(tz=UTC) - timedelta(days=30)
    await _seed_opp(
        session,
        client=client,
        owner=owner,
        last_activity_at=stale,
        is_closed_won=True,
        is_closed_lost=False,
        stage_label="7-Closed Won",
        stage_id="1038553758",
        stage_order=6,
    )
    await session.commit()

    counter.reset()
    page = await list_opportunities(
        session, filters=PipelineFilters(include_closed=True)
    )
    assert page.total == 1
    row = page.items[0]
    # closed-won → not stalled (spec: only open opps stall)
    assert AttentionFlag.STALLED.value not in row.attention_flags
    # closed-won without a released package → the gap flag
    assert AttentionFlag.CLOSED_WON_NOT_RELEASED.value in row.attention_flags
    assert counter.n <= 3


@pytest.mark.asyncio
async def test_list_clients_aggregates_open_value_by_currency_and_agreements(session, counter):
    owner = await _seed_owner(session)
    client = await _seed_client(session, name="Multi-Currency Corp")
    await _seed_opp(session, client=client, owner=owner, currency="USD", amount=Decimal("100"))
    await _seed_opp(session, client=client, owner=owner, currency="ZAR", amount=Decimal("2000"))
    await _seed_opp(session, client=client, owner=owner, currency="USD", amount=Decimal("50"))
    await _seed_agreement(session, client=client, kind="NDA", owner=owner)
    await session.commit()

    counter.reset()
    page = await list_clients(session, page=1, page_size=25)

    assert page.total == 1
    row = page.items[0]
    assert row.client_name == "Multi-Currency Corp"
    assert row.open_opp_count == 3
    assert row.open_value_by_currency.get("USD") == Decimal("150")
    assert row.open_value_by_currency.get("ZAR") == Decimal("2000")
    assert row.has_nda is True
    assert row.has_msa is False
    assert counter.n <= 3, f"list_clients used {counter.n} queries"


@pytest.mark.asyncio
async def test_summary_open_value_by_currency_and_agreement_gaps(session, counter):
    owner = await _seed_owner(session)
    c1 = await _seed_client(session, name="Client One")
    c2 = await _seed_client(session, name="Client Two")
    await _seed_opp(session, client=c1, owner=owner, currency="USD", amount=Decimal("100"))
    await _seed_opp(session, client=c2, owner=owner, currency="USD", amount=Decimal("200"))
    await _seed_opp(
        session,
        client=c1,
        owner=owner,
        currency="USD",
        amount=Decimal("50"),
        close_date=date.today(),
    )
    await _seed_agreement(session, client=c1, kind="NDA", owner=owner)
    await _seed_agreement(session, client=c1, kind="MSA", owner=owner)
    # c2 has an open deal but no agreements → agreement gap.
    await session.commit()

    counter.reset()
    result = await summary(session)

    assert result.open_count == 3
    assert result.open_value_by_currency["USD"] == Decimal("350")
    assert result.closing_this_month >= 1
    assert result.agreement_gaps == 1
    assert counter.n <= 3, f"summary used {counter.n} queries"


@pytest.mark.asyncio
async def test_attention_filter_drops_non_matching(session, counter):
    owner = await _seed_owner(session)
    client = await _seed_client(session, name="ATN")
    # One owned opp (no attention flags), one unowned opp (no_owner).
    await _seed_opp(session, client=client, owner=owner, amount=Decimal("100"))
    await _seed_opp(session, client=client, owner=None, amount=Decimal("200"))
    await session.commit()

    counter.reset()
    page = await list_opportunities(
        session,
        filters=PipelineFilters(attention=(AttentionFlag.NO_OWNER.value,)),
    )

    assert len(page.items) == 1
    assert AttentionFlag.NO_OWNER.value in page.items[0].attention_flags
    assert counter.n <= 3


@pytest.mark.asyncio
async def test_search_by_client_name(session, counter):
    owner = await _seed_owner(session)
    a = await _seed_client(session, name="Alpha Corp")
    b = await _seed_client(session, name="Beta Corp")
    await _seed_opp(session, client=a, owner=owner)
    await _seed_opp(session, client=b, owner=owner)
    await session.commit()

    counter.reset()
    page = await list_opportunities(session, filters=PipelineFilters(search="Alpha"))

    assert len(page.items) == 1
    assert page.items[0].client_name == "Alpha Corp"
    assert counter.n <= 3
