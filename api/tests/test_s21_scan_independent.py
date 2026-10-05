"""Independent source-scan faults; private SQLite, not live/PG acceptance."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.integrations.hubspot import HubSpotClient, StubHubSpotClient
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.services.hubspot_backfill import run_backfill
from app.services.hubspot_intake import handle_event
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.sync_status import acquire_scan


@pytest.fixture(autouse=True)
def isolated_scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "qa-independent-scan")
    monkeypatch.setenv("SALES_LEADER_EMAIL", "scan-owner@example.test")


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


def deal(identity="a", modified="2026-10-02T01:00:00Z", **properties):
    return {"id": identity, "properties": {"dealname": "Independent scan source",
        "hs_lastmodifieddate": modified, **properties}}


async def persisted(factory):
    async with factory() as session:
        return await session.get(SyncStatus, "hubspot_backfill"), list((await session.scalars(select(Opportunity))).all())


class ArchivalProvider(StubHubSpotClient):
    omit = False
    evidence = None

    async def list_deals_page(self, **kwargs):
        return {"results": []} if self.omit else await super().list_deals_page(**kwargs)

    async def get_archived_deal(self, identity):
        return self.evidence


@pytest.mark.asyncio
async def test_nonadjacent_cursor_cycle_stops_before_fetching_a_committed_cursor_again(factory):
    class Cyclic(StubHubSpotClient):
        calls = []

        async def list_deals_page(self, *, after=None, **kwargs):
            self.calls.append(after)
            if len(self.calls) > 3:
                raise RuntimeError("Independent safety bound: fourth fetch would repeat cursor A")
            cursor = ["A", "B", "A"][len(self.calls) - 1]
            return {"results": [deal(str(len(self.calls)))], "paging": {"next": {"after": cursor}}}

    hub = Cyclic()
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    assert hub.calls == [None, "A", "B"]
    state, rows = await persisted(factory)
    assert state.cursor == "B" and {row.hubspot_deal_id for row in rows} == {"1", "2"}


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", [True, {"invalid": "identity"}, ["invalid"], "   ", None])
async def test_malformed_deal_identity_cannot_be_coerced_into_a_persisted_source(factory, identity):
    class Malformed(StubHubSpotClient):
        async def list_deals_page(self, **kwargs):
            return {"results": [deal(identity)]}

    result = await run_backfill(Malformed(), session_factory=factory)
    assert result.errors and not result.scan_completed
    state, rows = await persisted(factory)
    assert not rows and state.cursor is None and state.last_success_at is None


@pytest.mark.asyncio
async def test_archived_owner_fetch_failure_is_not_a_successful_complete_scan(factory):
    class OwnerFailure(StubHubSpotClient):
        async def _get(self, path, params=None):
            if path == "/crm/v3/owners" and (params or {}).get("archived") == "true":
                raise RuntimeError("Archived-owner endpoint unavailable")
            return await super()._get(path, params)

    result = await run_backfill(OwnerFailure(deals={"a": deal()}), session_factory=factory)
    assert result.errors and not result.scan_completed
    async with factory() as session:
        state = await session.get(SyncStatus, "hubspot_owner_mirror")
        assert state is None or (state.last_success_at is None and state.last_error)


@pytest.mark.asyncio
async def test_metadata_failure_persists_failed_freshness_without_advancing_prior_success(factory):
    class MetadataFailure(StubHubSpotClient):
        fail = False

        async def list_pipelines(self):
            if self.fail:
                raise RuntimeError("Pipeline metadata unavailable")
            return await super().list_pipelines()

    hub = MetadataFailure(deals={"a": deal()})
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    before, _ = await persisted(factory)
    hub.fail = True
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    after, _ = await persisted(factory)
    assert after.last_success_at == before.last_success_at
    assert after.last_error, "A failed refresh must not leave the persisted scan looking healthy"
    assert after.last_attempt_at > before.last_attempt_at


@pytest.mark.asyncio
@pytest.mark.parametrize("evidence,allowed", [
    (None, False), ({"id": "wrong", "archived": True}, False),
    ({"id": "a", "archived": "true"}, False), ({"id": "a", "archived": False}, False),
    ({"id": "a", "archived": True}, True),
])
async def test_archive_requires_exact_identity_and_explicit_boolean_evidence(factory, evidence, allowed):
    hub = ArchivalProvider(deals={"a": deal()})
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    hub.omit, hub.evidence = True, evidence
    result = await run_backfill(hub, session_factory=factory)
    state, rows = await persisted(factory)
    assert (rows[0].archived_at is not None) is allowed
    assert result.scan_completed is allowed and result.deals_archived == int(allowed)
    assert (state.scan_phase == "completed") is allowed


@pytest.mark.asyncio
async def test_transport_404_is_not_authoritative_archive_evidence():
    class NotFound(HubSpotClient):
        def __init__(self):
            pass

        async def _get(self, path, params=None):
            response = httpx.Response(404, request=httpx.Request("GET", "https://provider.invalid/deal"))
            raise httpx.HTTPStatusError("Not found", request=response.request, response=response)

    assert await NotFound().get_archived_deal("a") is None


async def change_mapping(factory):
    async with factory() as session:
        mapping = await session.get(HubspotPropertyMapping, "business_unit")
        mapping.availability_state = "configured"
        mapping.internal_name = "qa_business_unit"
        mapping.object_type = "deal"
        mapping.mapping_version += 1
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["page", "archive_evidence"])
async def test_mapping_change_during_provider_io_cannot_complete_old_context(factory, phase):
    class ChangedMapping(ArchivalProvider):
        race = False

        async def list_deals_page(self, **kwargs):
            result = await super().list_deals_page(**kwargs)
            if self.race and phase == "page":
                await change_mapping(factory)
            return result

        async def get_archived_deal(self, identity):
            if self.race and phase == "archive_evidence":
                await change_mapping(factory)
            return {"id": identity, "archived": True}

    hub = ChangedMapping(deals={"a": deal()})
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    hub.omit, hub.race = True, True
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    state, rows = await persisted(factory)
    assert rows[0].archived_at is None and state.scan_phase != "completed"


@pytest.mark.asyncio
async def test_new_lease_during_page_fetch_rejects_old_owner_without_poisoning_new_state(factory):
    class Takeover(StubHubSpotClient):
        replacement = None

        async def list_deals_page(self, **kwargs):
            async with factory() as session:
                state = await session.get(SyncStatus, "hubspot_backfill")
                state.scan_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
                context = dict(state.scan_context)
                await session.commit()
                self.replacement = await acquire_scan(session, source=state.source, context=context)
                await session.commit()
            return {"results": [deal()]}

    hub = Takeover()
    result = await run_backfill(hub, session_factory=factory)
    assert result.errors and not result.scan_completed
    state, rows = await persisted(factory)
    assert not rows and state.cursor is None and state.last_error is None
    assert state.scan_lease_token == hub.replacement.token and state.scan_phase == "scanning"


@pytest.mark.asyncio
@pytest.mark.parametrize("version,restore", [
    ("2026-10-02T00:00:00Z", False), ("2026-10-02T01:00:00Z", False),
    ("2026-10-02T02:00:00Z", True),
])
async def test_obsolete_source_response_cannot_resurrect_authoritatively_archived_deal(factory, version, restore):
    hub = ArchivalProvider(deals={"a": deal()})
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    hub.omit, hub.evidence = True, {"id": "a", "archived": True}
    assert (await run_backfill(hub, session_factory=factory)).deals_archived == 1
    hub.deals["a"] = {**deal(modified=version), "archived": False}
    async with factory() as session:
        await handle_event(session, {"eventId": str(uuid.uuid4()), "objectId": "a",
            "subscriptionType": "deal.propertyChange"}, hub)
    _, rows = await persisted(factory)
    assert (rows[0].archived_at is None) is restore


@pytest.mark.asyncio
async def test_partial_source_fields_preserve_known_values_but_explicit_null_clears(factory):
    hub = StubHubSpotClient(deals={"a": deal(hubspot_owner_id="external-owner", deal_currency_code="EUR", amount="17.25")})
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    hub.deals["a"] = {"id": "a", "properties": {"hs_lastmodifieddate": "2026-10-02T02:00:00Z"}}
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    _, rows = await persisted(factory)
    assert rows[0].name == "Independent scan source" and rows[0].hubspot_owner_id == "external-owner"
    assert rows[0].currency == "EUR" and rows[0].amount == Decimal("17.25")
    hub.deals["a"] = deal(modified="2026-10-02T03:00:00Z", hubspot_owner_id=None, deal_currency_code=None)
    assert (await run_backfill(hub, session_factory=factory)).scan_completed
    _, rows = await persisted(factory)
    assert rows[0].hubspot_owner_id is None and rows[0].hubspot_owner_observed_at is not None
    assert rows[0].currency is None
