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


async def test_one_invalid_record_rolls_back_entire_page_and_cursor(factory):
    hub = StubHubSpotClient(deals={"a": deal("a"), "b": deal("b", hubspot_owner_id=42)})
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    async with factory() as session:
        assert (await session.scalars(select(Opportunity))).all() == []
        row = await session.get(SyncStatus, "hubspot_backfill")
        assert row.cursor is None and row.scan_phase == "failed"


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
    assert result.errors and not result.scan_completed
    async with factory() as session:
        row = (await session.scalars(select(Opportunity))).one()
        assert row.archived_at is None
