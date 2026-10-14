"""Provider faults must not turn a partial page or live-list absence into truth."""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.integrations.hubspot import StubHubSpotClient
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.services.hubspot_backfill import run_backfill


@pytest_asyncio.fixture
async def engine(savepoint_engine):
    # S23-PL1: per-deal SAVEPOINTs must roll back with their page, as on PostgreSQL.
    return savepoint_engine


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def deal(identity, **props):
    return {"id": identity, "properties": {"dealname": f"Synthetic {identity}",
        "hs_lastmodifieddate": "2026-10-02T00:00:00Z", **props}}


class PageFailure(StubHubSpotClient):
    fail_next = True
    async def list_deals_page(self, *, after=None, limit=100, **kwargs):
        if after and self.fail_next:
            self.fail_next = False
            raise RuntimeError("injected page failure")
        return await super().list_deals_page(after=after, limit=limit, **kwargs)


async def test_resume_reuses_committed_generation_and_cursor(factory):
    hub = PageFailure(deals={"a": deal("a"), "b": deal("b")})
    first = await run_backfill(hub, session_factory=factory, page_size=1)
    assert first.errors and not first.scan_completed
    async with factory() as session:
        row = await session.get(SyncStatus, "hubspot_backfill")
        assert row.cursor == "a" and row.scan_phase == "failed"
    second = await run_backfill(hub, session_factory=factory, page_size=1)
    assert second.scan_generation == first.scan_generation
    assert second.scan_completed and second.errors == 0
    assert second.deals_seen == 1
    async with factory() as session:
        rows = (await session.scalars(select(Opportunity))).all()
        assert {row.hubspot_deal_id for row in rows} == {"a", "b"}
        assert {row.hubspot_seen_generation for row in rows} == {first.scan_generation}


async def test_one_invalid_record_is_listed_and_the_page_still_commits(factory):
    # S23-PL1 item 4 replaces "one invalid record rolls back the page": the bad
    # record is caught, listed with its HubSpot id and not written; the rest of
    # the page and the cursor commit together.
    hub = StubHubSpotClient(deals={"a": deal("a"), "b": deal("b", hubspot_owner_id=42)})
    result = await run_backfill(hub, session_factory=factory)
    assert result.fatal_error is None and result.scan_completed
    assert result.record_errors == [{"hubspot_id": "b", "reason": "deal: invalid owner identity"}]
    async with factory() as session:
        rows = (await session.scalars(select(Opportunity))).all()
        assert [row.hubspot_deal_id for row in rows] == ["a"]
        row = await session.get(SyncStatus, "hubspot_backfill")
        assert row.cursor is None and row.scan_phase == "completed"


async def test_repeated_cursor_is_refused_without_third_fetch(factory):
    class Repeated(StubHubSpotClient):
        calls = 0
        async def list_deals_page(self, **kwargs):
            self.calls += 1
            if self.calls > 2:
                raise AssertionError("Repeated cursor was fetched again")
            return {"results": [deal("a")], "paging": {"next": {"after": "repeat"}}}
    hub = Repeated()
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    assert hub.calls == 2


@pytest.mark.parametrize("page", [{}, {"results": "not-a-list"},
    {"results": [], "paging": {"next": {}}},
    {"results": [deal("a"), deal("a")]}])
async def test_malformed_page_is_failed_not_successful_empty_scan(factory, page):
    class Malformed(StubHubSpotClient):
        async def list_deals_page(self, **kwargs):
            return page
    result = await run_backfill(Malformed(), session_factory=factory)
    assert result.errors and not result.scan_completed
    async with factory() as session:
        assert (await session.scalars(select(Opportunity))).all() == []


async def test_live_list_omission_requires_authoritative_deletion_evidence(factory):
    class Omitted(StubHubSpotClient):
        omit = False
        async def list_deals_page(self, **kwargs):
            return {"results": []} if self.omit else await super().list_deals_page(**kwargs)
    hub = Omitted(deals={"a": deal("a")})
    await run_backfill(hub, session_factory=factory)
    hub.omit = True
    result = await run_backfill(hub, session_factory=factory)
    assert result.deals_archived == 0
    # S23-PL1 item 4: the absence is listed, never archived, and the scan ends.
    assert result.record_errors == [
        {"hubspot_id": "a", "reason": "deal: missing from HubSpot but deletion not confirmed"}]
    assert result.scan_completed
    async with factory() as session:
        row = (await session.scalars(select(Opportunity))).one()
        assert row.archived_at is None


async def test_an_empty_live_list_stops_asking_hubspot_after_five_absences(factory):
    class Emptied(StubHubSpotClient):
        omit = False
        archive_checks = 0
        async def list_deals_page(self, **kwargs):
            return {"results": []} if self.omit else await super().list_deals_page(**kwargs)
        async def get_archived_deal(self, deal_id):
            self.archive_checks += 1
            return None
    hub = Emptied(deals={f"d{i}": deal(f"d{i}") for i in range(9)})
    await run_backfill(hub, session_factory=factory)
    hub.omit = True
    result = await run_backfill(hub, session_factory=factory)
    assert hub.archive_checks == 5 and result.deals_archived == 0
    assert result.record_errors[-1] == {"hubspot_id": "", "reason": "deal: 4 more deals missing from HubSpot were not checked"}
    async with factory() as session:
        assert all(row.archived_at is None for row in (await session.scalars(select(Opportunity))).all())
