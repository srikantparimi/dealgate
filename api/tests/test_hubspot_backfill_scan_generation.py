"""S20 W1 A3 · T33 — scan generation + resume without premature archive.

Contracts:

- ``run_backfill`` claims a new generation on ``sync_status`` at start.
- Archive-not-seen only runs when pagination succeeded AND every deal
  upsert succeeded. A pagination failure leaves ``scan_completed_at``
  unset, so no rows get archived under that generation.
- A subsequent, healthy run advances the generation, re-populates the
  seen set, and archives-not-seen only for rows created *before* the
  new run started.
- Opportunities inserted concurrently (via webhook) during a scan are
  NOT archived by that scan's sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import StubHubSpotClient
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.models.user import User
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_intake import handle_event


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SALES_LEADER_EMAIL", "sales-leader@smartek21.com")
    monkeypatch.setenv("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _deal(deal_id: str) -> dict[str, Any]:
    return {
        "id": deal_id,
        "properties": {
            "dealname": f"Deal {deal_id}",
            "dealstage": "qualifiedtobuy",
            "pipeline": "default",
            "hubspot_owner_id": "42",
            "amount": "12500.00",
            "closedate": "2026-12-15",
        },
    }


class _FailingListDealsClient(StubHubSpotClient):
    """Stub that raises during ``list_deals_page`` for pagination-failure tests."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pages_returned = 0

    async def list_deals_page(self, *, after: str | None = None, limit: int = 100):
        # Return one page then raise on the next.
        if self.pages_returned == 0:
            self.pages_returned += 1
            all_ids = sorted(self.deals.keys())
            payload = {"results": [self.deals[i] for i in all_ids[:1]]}
            if len(all_ids) > 1:
                payload["paging"] = {"next": {"after": all_ids[0]}}
            return payload
        raise RuntimeError("simulated hubspot 500 mid-scan")


async def test_backfill_claims_and_completes_generation_on_healthy_run(factory):
    stub = StubHubSpotClient(
        deals={"111": _deal("111"), "222": _deal("222")},
        owners={"42": {"id": "42", "email": "rep@x.com"}},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.scan_generation == 1
    assert counts.scan_completed is True

    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row is not None
    assert row.scan_generation == 1
    assert row.scan_completed_at is not None
    assert row.scan_started_at is not None


async def test_pagination_failure_leaves_no_archive_and_no_completion(factory):
    """A pagination failure mid-scan must archive nothing (T33)."""

    # First, pre-populate one opportunity that would be archive-eligible.
    stub_first = StubHubSpotClient(
        deals={"aaa": _deal("aaa")},
        owners={"42": {"id": "42", "email": "rep@x.com"}},
    )
    first = await run_backfill(stub_first, session_factory=factory)
    assert first.scan_completed is True

    async with factory() as s:
        opps_before = (
            await s.execute(select(Opportunity).where(Opportunity.hubspot_deal_id == "aaa"))
        ).scalars().all()
    assert len(opps_before) == 1
    assert opps_before[0].archived_at is None

    # Now: the portal returns a fresh set that doesn't include 'aaa', but
    # pagination fails mid-scan. archive_missing MUST NOT run.
    failing = _FailingListDealsClient(
        deals={"bbb": _deal("bbb"), "ccc": _deal("ccc")},
        owners={"42": {"id": "42", "email": "rep@x.com"}},
    )
    second = await run_backfill(failing, session_factory=factory, page_size=1)
    assert second.scan_completed is False
    assert second.deals_archived == 0
    assert second.errors >= 1

    async with factory() as s:
        row_a = (
            await s.execute(select(Opportunity).where(Opportunity.hubspot_deal_id == "aaa"))
        ).scalars().one()
    assert row_a.archived_at is None, "archive gate must be closed on a failed scan"

    # The failed run's watermark records the failure but does NOT stamp
    # scan_completed_at.
    async with factory() as s:
        row = await s.get(SyncStatus, "hubspot_backfill")
    assert row is not None
    assert row.scan_generation == 2
    assert row.scan_completed_at is None
    assert row.last_error is not None


async def test_second_healthy_run_archives_missing_under_new_generation(factory):
    stub = StubHubSpotClient(
        deals={"111": _deal("111"), "222": _deal("222")},
        owners={"42": {"id": "42", "email": "rep@x.com"}},
    )
    await run_backfill(stub, session_factory=factory)

    # 222 is removed from HubSpot; next healthy run should archive it.
    stub.deals = {"111": _deal("111")}
    second = await run_backfill(stub, session_factory=factory)
    assert second.scan_completed is True
    assert second.deals_archived == 1
    assert second.scan_generation == 2

    async with factory() as s:
        r222 = (
            await s.execute(select(Opportunity).where(Opportunity.hubspot_deal_id == "222"))
        ).scalars().one()
    assert r222.archived_at is not None
    assert r222.archived_reason == "hubspot_deleted"


async def test_opportunities_created_mid_scan_are_never_archived(factory):
    """A row inserted (via webhook) *after* run_started must survive the
    same run's archive sweep, even if the paginated response didn't
    include it (T33)."""

    # Baseline: one deal.
    stub = StubHubSpotClient(
        deals={"111": _deal("111")},
        owners={"42": {"id": "42", "email": "rep@x.com"}},
    )
    await run_backfill(stub, session_factory=factory)

    # Manually insert an opportunity that "looked" like a mid-scan
    # webhook — with created_at set to the future so the archive gate's
    # `row.created_at > run_started` filter kicks in.
    async with factory() as s:
        # Ensure at least one User exists (created by first backfill).
        user = (await s.execute(select(User))).scalars().first()
        assert user is not None
        future_row = Opportunity(
            hubspot_deal_id="mid-scan-999",
            source="hubspot",
            owner_id=user.id,
            hubspot_last_seen_at=datetime.now(UTC),
            governance_status="Intake",
            created_at=datetime(2999, 1, 1, tzinfo=UTC),
        )
        s.add(future_row)
        await s.commit()

    # Now, run backfill with a set that DOESN'T include mid-scan-999 —
    # the row was created after this new run started, so archive_missing
    # must skip it.
    stub.deals = {"111": _deal("111")}
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.scan_completed is True

    async with factory() as s:
        row = (
            await s.execute(
                select(Opportunity).where(Opportunity.hubspot_deal_id == "mid-scan-999")
            )
        ).scalars().one()
    assert row.archived_at is None
