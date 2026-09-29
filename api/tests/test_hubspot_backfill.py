"""S18 §2 · HubSpot backfill worker.

Acceptance:
- Full paged fetch upserts every deal end-to-end.
- Second run reports zero created / zero updated — idempotent by construction.
- Deals missing from HubSpot get archived (never hard-deleted).
- Owner-less deals count as owners_unassigned.
- Company-less deals count as companies_created (the "Unknown Company" sentinel).
- Amount and close_date land on the opportunity row.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import HubSpotClient, StubHubSpotClient
from app.models.opportunity import Opportunity
from app.services.hubspot_backfill import run_backfill


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SALES_LEADER_EMAIL", "sales-leader@smartek21.com")
    monkeypatch.setenv("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _deal(deal_id: str, *, stage: str = "qualifiedtobuy", owner: str | None = "42",
          amount: str | None = "12500.00", close: str | None = "2026-12-15") -> dict:
    props: dict = {"dealname": f"Deal {deal_id}", "dealstage": stage, "pipeline": "default"}
    if owner is not None:
        props["hubspot_owner_id"] = owner
    if amount is not None:
        props["amount"] = amount
    if close is not None:
        props["closedate"] = close
    return {"id": deal_id, "properties": props}


def _owner(owner_id: str = "42", email: str = "rep@smartek21.com") -> dict:
    return {"id": owner_id, "email": email, "firstName": "Rep", "lastName": "One"}


async def test_backfill_upserts_every_deal(factory):
    stub = StubHubSpotClient(
        deals={"555": _deal("555"), "556": _deal("556", stage="closedwon")},
        owners={"42": _owner()},
    )
    counts = await run_backfill(stub, session_factory=factory, page_size=1)
    assert counts.deals_seen == 2
    assert counts.deals_created == 2
    assert counts.deals_updated == 0
    assert counts.deals_archived == 0
    assert counts.errors == 0
    async with factory() as s:
        rows = (await s.execute(select(Opportunity))).scalars().all()
    assert {r.hubspot_deal_id for r in rows} == {"555", "556"}
    assert all(r.source == "hubspot" for r in rows)
    # amount + close_date cached on the row for Pipeline reads
    r555 = next(r for r in rows if r.hubspot_deal_id == "555")
    assert str(r555.amount) == "12500.00"
    assert r555.close_date is not None


async def test_backfill_is_idempotent(factory):
    stub = StubHubSpotClient(deals={"555": _deal("555")}, owners={"42": _owner()})
    first = await run_backfill(stub, session_factory=factory)
    assert first.deals_created == 1

    second = await run_backfill(stub, session_factory=factory)
    assert second.deals_created == 0
    assert second.deals_updated == 0
    assert second.deals_unchanged == 1


async def test_backfill_archives_deals_missing_from_hubspot(factory):
    stub = StubHubSpotClient(
        deals={"555": _deal("555"), "556": _deal("556")}, owners={"42": _owner()}
    )
    await run_backfill(stub, session_factory=factory)

    # Deal 556 disappears from HubSpot.
    stub.deals.pop("556")
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.deals_archived == 1

    async with factory() as s:
        rows = (await s.execute(select(Opportunity))).scalars().all()
    archived = next(r for r in rows if r.hubspot_deal_id == "556")
    assert archived.archived_at is not None
    assert archived.archived_reason == "hubspot_deleted"


async def test_backfill_counts_owner_unassigned_and_amount_zero(factory):
    # F2 (no owner) and F6 (amount 0) edge cases.
    stub = StubHubSpotClient(
        deals={"777": _deal("777", owner=None, amount="0")},
        owners={},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.owners_unassigned == 1
    assert counts.deals_created == 1
    from decimal import Decimal

    async with factory() as s:
        rows = (await s.execute(select(Opportunity))).scalars().all()
    assert rows[0].amount == Decimal("0")


async def test_backfill_handles_deal_with_no_company(factory):
    # F1: deal with no company → Unknown Company sentinel client.
    stub = StubHubSpotClient(deals={"888": _deal("888")}, owners={"42": _owner()})
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.deals_created == 1
    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.client_id is not None  # never null — always the sentinel


async def test_backfill_skips_archive_sweep_when_a_deal_errored(factory, monkeypatch):
    """S18 §2 · F8 backend half: partial failure never archives stale rows."""

    # Seed a live deal so a "stale" row exists.
    stub = StubHubSpotClient(deals={"555": _deal("555")}, owners={"42": _owner()})
    await run_backfill(stub, session_factory=factory)

    # Next run: the previous deal has "disappeared" (would normally be
    # archived) but a new deal errors during processing. Injecting the
    # error at `_process_deal` — the boundary the run loop catches — is
    # the cleanest way to exercise the error path without polluting the
    # domain logic with test-only failure modes.
    stub.deals.clear()
    stub.deals["666"] = _deal("666")

    from app.services import hubspot_backfill as hb

    async def _boom(*_a, **_k):
        raise RuntimeError("simulated deal-processing failure")

    monkeypatch.setattr(hb, "_process_deal", _boom)

    counts = await run_backfill(stub, session_factory=factory)

    assert counts.errors >= 1
    assert counts.deals_archived == 0, "archive sweep must be skipped on error"

    # The original deal is still live locally.
    async with factory() as s:
        opp = (await s.execute(select(Opportunity).where(Opportunity.hubspot_deal_id == "555"))).scalar_one()
    assert opp.archived_at is None


async def test_backfill_skips_archive_when_pagination_fails(factory):
    """A HubSpot outage in list_deals_page must not archive anything."""

    stub = StubHubSpotClient(deals={"555": _deal("555")}, owners={"42": _owner()})
    await run_backfill(stub, session_factory=factory)

    class BrokenStub(StubHubSpotClient):
        async def list_deals_page(self, *, after=None, limit=100):
            raise RuntimeError("simulated outage")

    broken = BrokenStub(deals={}, owners={})
    counts = await run_backfill(broken, session_factory=factory)
    assert counts.errors == 1
    assert counts.deals_archived == 0

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.archived_at is None


async def test_hubspot_client_retries_on_429(monkeypatch):
    """F7: HubSpotClient honors 429 with backoff, then returns 200."""

    import httpx
    from app.integrations import hubspot as hub_mod

    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "pat-test")
    monkeypatch.setattr(hub_mod, "_RATE_LIMIT_BASE_DELAY", 0.01)

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0.01"})
        return httpx.Response(200, json={"results": [], "paging": {}})

    original_client = httpx.AsyncClient

    def patched_client(*a, **kw):
        kw.setdefault("transport", httpx.MockTransport(handler))
        return original_client(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    hub = HubSpotClient(access_token="pat-test")
    result = await hub.list_deals_page()
    assert result == {"results": [], "paging": {}}
    assert len(calls) == 2, f"expected one retry, got {len(calls)} calls"


async def test_hubspot_client_gives_up_after_max_retries(monkeypatch):
    """After the retry budget the client re-raises so the caller counts it."""

    import httpx
    from app.integrations import hubspot as hub_mod

    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "pat-test")
    monkeypatch.setattr(hub_mod, "_RATE_LIMIT_BASE_DELAY", 0.001)
    monkeypatch.setattr(hub_mod, "_RATE_LIMIT_MAX_RETRIES", 2)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0.001"})

    original_client = httpx.AsyncClient

    def patched_client(*a, **kw):
        kw.setdefault("transport", httpx.MockTransport(handler))
        return original_client(*a, **kw)

    monkeypatch.setattr(httpx, "AsyncClient", patched_client)

    hub = HubSpotClient(access_token="pat-test")
    with pytest.raises(httpx.HTTPStatusError):
        await hub.list_deals_page()


async def test_backfill_uses_unassigned_sentinel_when_no_sales_leader(factory, monkeypatch):
    """F2 checklist: an owner-less deal on a task-def without SALES_LEADER_EMAIL
    lands on the shared 'Unassigned' sentinel, not an error."""

    from sqlalchemy import select as sql_select

    from app.models.user import User
    from app.services.hubspot_intake import UNASSIGNED_USER_EMAIL

    monkeypatch.delenv("SALES_LEADER_EMAIL", raising=False)
    stub = StubHubSpotClient(deals={"777": _deal("777", owner=None)}, owners={})

    counts = await run_backfill(stub, session_factory=factory)
    assert counts.errors == 0
    assert counts.deals_created == 1
    assert counts.owners_unassigned == 1

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
        owner = (
            await s.execute(sql_select(User).where(User.id == opp.owner_id))
        ).scalar_one()
    assert owner.email == UNASSIGNED_USER_EMAIL


async def test_backfill_tolerates_404_owner_lookup(factory):
    """Regression for the first §2a staging run: real HubSpot returns 404
    for deactivated owners (e.g. 76287123); we must fall through to the
    Sales-leader fallback, not error the deal."""

    import httpx

    class ClientWith404Owner(StubHubSpotClient):
        async def get_deal_owner(self, owner_id: str):
            req = httpx.Request("GET", f"https://api.hubapi.com/crm/v3/owners/{owner_id}")
            resp = httpx.Response(404, request=req)
            raise httpx.HTTPStatusError("404 Not Found", request=req, response=resp)

    stub = ClientWith404Owner(
        deals={"555": _deal("555", owner="76287123")},
        owners={},
    )
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.errors == 0
    assert counts.deals_created == 1
    # Owner defaults to Sales Leader (SALES_LEADER_EMAIL); this deal is
    # neither `owners_matched` nor `owners_unassigned` because the id was
    # present on the deal — it just resolved via the fallback.
    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.owner_id is not None


async def test_backfill_re_unarchives_deal_that_returns(factory):
    stub = StubHubSpotClient(deals={"555": _deal("555")}, owners={"42": _owner()})
    await run_backfill(stub, session_factory=factory)

    # Simulate HubSpot deletion then restoration.
    stub.deals.pop("555")
    await run_backfill(stub, session_factory=factory)
    stub.deals["555"] = _deal("555", stage="contractsent")
    counts = await run_backfill(stub, session_factory=factory)
    assert counts.deals_archived == 0
    assert counts.deals_updated == 1

    async with factory() as s:
        opp = (await s.execute(select(Opportunity))).scalar_one()
    assert opp.archived_at is None
    assert opp.sales_stage == "contractsent"
