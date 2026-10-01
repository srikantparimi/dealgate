"""T35 · pagination-vs-totals (A5) — S20 W2 Session 3b Rev-2.

Contract: the ``total`` field in the list envelope is computed over
the FULL authorized filter set BEFORE pagination is applied. Chip
counts / summary bar / group counts / export all read from the full
matching set — never from the page.

The review's L03 finding was a page-scoped aggregate leaking into the
count ("50 rows, no next-page control, 106 matches claimed"). This
test seeds > 100 rows and asserts that:
1. ``total`` on a page-size=25 request equals the full seeded count.
2. ``total`` is stable across pages 1..6 of the same filter set.
3. Stage-chip counts on the same request sum to the same total.
4. ``stage_counts`` include ``open_value_by_currency`` per chip
   (S3b Rev-2 chip-value addition, review L06: "count + value per chip").
5. page_size 25/50/100 all respected — the UI selector matches the
   server allowlist.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.client import Client
from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_pipeline import list_opportunities


async def _seed(session, *, n_deals: int) -> int:
    owner = User(email="rep@dealgate.local", name="Rep One", groups=[])
    session.add(owner)
    client = Client(name="Scale Corp", hubspot_company_id="COMP_S")
    session.add(client)
    session.add(HubspotPipeline(id="710688094", label="Sales", display_order=0))
    session.add_all(
        [
            HubspotStage(
                id="STAGE_A",
                pipeline_id="710688094",
                label="1-Discovery",
                display_order=0,
                is_closed=False,
                probability=Decimal("0.10"),
            ),
            HubspotStage(
                id="STAGE_B",
                pipeline_id="710688094",
                label="2-Proposal",
                display_order=1,
                is_closed=False,
                probability=Decimal("0.30"),
            ),
        ]
    )
    await session.flush()

    for i in range(n_deals):
        stage_id = "STAGE_A" if i % 2 == 0 else "STAGE_B"
        stage_label = "1-Discovery" if stage_id == "STAGE_A" else "2-Proposal"
        session.add(
            Opportunity(
                source="hubspot",
                hubspot_deal_id=f"scale_{i:04d}",
                name=f"Scale deal {i}",
                owner_id=owner.id,
                client_id=client.id,
                sales_stage=stage_label,
                stage_label=stage_label,
                hubspot_pipeline_id="710688094",
                hubspot_stage_id=stage_id,
                stage_order=0 if stage_id == "STAGE_A" else 1,
                amount=Decimal("1000") * (i + 1),
                currency="USD" if i % 3 else "EUR",
                close_date=date.today() + timedelta(days=30),
                governance_status="Intake",
            )
        )
    await session.commit()
    return n_deals


@pytest.mark.asyncio
async def test_page_1_total_is_global_not_paged(session):
    n = await _seed(session, n_deals=137)
    page1 = await list_opportunities(session, page=1, page_size=25)
    assert page1.total == n, (
        f"total {page1.total} must equal full seeded count {n} — is the count "
        f"derived from the page only? (L03 regression)"
    )
    assert len(page1.items) == 25, "page 1 must return exactly page_size rows"


@pytest.mark.asyncio
async def test_total_stable_across_pages(session):
    n = await _seed(session, n_deals=137)
    totals: list[int] = []
    for page in range(1, 7):
        result = await list_opportunities(session, page=page, page_size=25)
        totals.append(result.total)
    assert len(set(totals)) == 1, (
        f"total drifted across pages: {totals} — pagination must not alter the total"
    )
    assert totals[0] == n


@pytest.mark.asyncio
async def test_stage_chips_reconcile_to_filtered_total_not_page(session):
    n = await _seed(session, n_deals=137)
    result = await list_opportunities(session, page=1, page_size=25)
    stage_sum = sum(c.count for c in result.stage_counts) + result.unknown_bucket
    assert stage_sum == result.total, (
        f"chip counts ({stage_sum}) must reconcile to total ({result.total}) — "
        f"L06 regression (chip aggregation must not be page-scoped)"
    )
    assert stage_sum == n


@pytest.mark.asyncio
async def test_stage_counts_carry_open_value_per_currency(session):
    """S3b Rev-2 · chip value contract (review L06 says 'count + value per chip').

    The aggregation groups by (pipeline_id, stage_id, currency). Python
    collates back to per-chip with a currency → sum(amount) dict. Both
    stages carry USD and EUR sub-totals because the seed alternates.
    """
    await _seed(session, n_deals=137)
    result = await list_opportunities(session, page=1, page_size=25)

    active_chips = [c for c in result.stage_counts if c.count > 0]
    assert active_chips, "expected non-zero chips on 137 seeded rows"

    for chip in active_chips:
        assert chip.open_value_by_currency, (
            f"chip {chip.stage_label} has count>0 but empty value map"
        )
        for ccy, amount in chip.open_value_by_currency.items():
            assert ccy in {"USD", "EUR"}, f"unexpected currency {ccy}"
            assert amount > Decimal("0"), (
                f"chip {chip.stage_label} · {ccy} value must be > 0 when count > 0"
            )


@pytest.mark.asyncio
async def test_page_size_25_50_100_all_respected(session):
    n = await _seed(session, n_deals=137)
    for size in (25, 50, 100):
        result = await list_opportunities(session, page=1, page_size=size)
        assert len(result.items) == size, (
            f"page_size={size} returned {len(result.items)} rows"
        )
        assert result.page_size == size
        assert result.total == n
