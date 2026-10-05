"""Source observations use CRM identity and explicit property presence."""

import pytest
import pytest_asyncio
from datetime import UTC, datetime
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.integrations.hubspot import HubSpotClient, StubHubSpotClient
from app.models.client import Client
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_intake import _resolve_client, _upsert_opportunity, handle_event
from app.services.hubspot_properties import HubspotPropertyMapping
from app.services.hubspot_backfill import run_backfill


@pytest_asyncio.fixture
async def records(session):
    owner = User(email="local@example.test", name="Local assignee", groups=[])
    company = Client(name="Adapter fixture", hubspot_company_id="company-1")
    session.add_all([owner, company])
    await session.flush()
    return owner, company


def deal(properties=None, version="2026-10-02T01:00:00Z"):
    return {"id": "deal-1", "properties": {
        "dealname": "Source deal", "hs_lastmodifieddate": version,
        **(properties or {}),
    }}


async def write(session, records, payload):
    return (await _upsert_opportunity(session, "deal-1", payload, *records, "adapter-test"))[0]


async def mapping(session, object_type="deal", state="configured"):
    row = HubspotPropertyMapping(key="business_unit", internal_name="custom_bu",
        object_type=object_type, label="Business Unit", field_type="enumeration",
        options=[{"value": "delivery", "label": "Delivery"}],
        availability_state=state, mapping_version=7)
    session.add(row)
    await session.flush()
    return row


async def test_external_owner_is_independent_of_local_login(session, records):
    row = await write(session, records, deal({"hubspot_owner_id": "external-no-login"}))
    assert row.hubspot_owner_id == "external-no-login"
    assert row.hubspot_owner_observed_at is not None
    assert row.owner_id == records[0].id
    assert row.local_assignee_id is None
    assert len(list((await session.scalars(select(User))).all())) == 1


async def test_unfetched_owner_is_not_an_observed_empty(session, records):
    row = await write(session, records, deal())
    assert row.hubspot_owner_id is None and row.hubspot_owner_observed_at is None
    await write(session, records, deal({"hubspot_owner_id": "external"}))
    observed = row.hubspot_owner_observed_at
    await write(session, records, deal(version="2026-10-02T02:00:00Z"))
    assert row.hubspot_owner_id == "external"
    assert row.hubspot_owner_observed_at.replace(tzinfo=UTC) == observed.replace(tzinfo=UTC)


@pytest.mark.parametrize("blank", [None, ""])
async def test_explicit_blank_clears_observed_owner_currency_activity(session, records, blank):
    row = await write(session, records, deal({"hubspot_owner_id": "external",
        "deal_currency_code": "EUR", "notes_last_updated": "2026-10-01T00:00:00Z"}))
    await write(session, records, deal({"hubspot_owner_id": blank,
        "deal_currency_code": blank, "notes_last_updated": blank}, "2026-10-02T02:00:00Z"))
    assert row.hubspot_owner_id is None and row.hubspot_owner_observed_at is not None
    assert row.currency is None and row.hubspot_last_activity_at is None


async def test_modified_time_is_not_activity_and_missing_fields_are_preserved(session, records):
    row = await write(session, records, deal({"amount": "50", "closedate": "2026-11-01",
        "deal_currency_code": "EUR"}))
    assert row.hubspot_last_activity_at is None
    await write(session, records, {"id": "deal-1", "properties": {
        "hs_lastmodifieddate": "2026-10-02T02:00:00Z"}})
    assert row.name == "Source deal" and row.amount == Decimal("50")
    assert row.close_date.isoformat() == "2026-11-01" and row.currency == "EUR"


@pytest.mark.parametrize("older", ["2026-10-01T00:00:00Z", None])
async def test_stale_or_unversioned_fetch_cannot_overwrite_versioned_record(session, records, older):
    row = await write(session, records, deal({"hubspot_owner_id": "new", "amount": "100"}))
    version = row.hubspot_last_modified_at
    await write(session, records, deal({"hubspot_owner_id": "old", "amount": "1",
        "dealname": "Stale name"}, older))
    assert row.hubspot_owner_id == "new" and row.name == "Source deal"
    assert row.amount == Decimal("100")
    assert row.hubspot_last_modified_at.replace(tzinfo=UTC) == version.replace(tzinfo=UTC)


class ObservingProvider(StubHubSpotClient):
    def __init__(self, payload, company=None):
        super().__init__(deals={"deal-1": payload}, companies={"company-1": company} if company else {})
        self.requested = []

    async def get_deal(self, deal_id, *, additional_properties=()):
        self.requested.append(("deal", additional_properties))
        return self.deals[deal_id]

    async def get_company(self, company_id, *, additional_properties=()):
        self.requested.append(("company", additional_properties))
        return self.companies[company_id]


@pytest.mark.parametrize("value", ["delivery", "unknown-provider-option", "", None])
async def test_configured_deal_bu_records_value_version_and_observation(session, value):
    await mapping(session)
    provider = ObservingProvider(deal({"custom_bu": value, "hubspot_owner_id": "nonlocal"}))
    await handle_event(session, {"eventId": "bu-event", "objectId": "deal-1"}, provider)
    row = await session.scalar(select(Opportunity))
    assert row.business_unit_value == (value or None)
    assert row.business_unit_mapping_version == 7 and row.business_unit_observed_at is not None
    assert provider.requested[0] == ("deal", ("custom_bu",))
    assert row.hubspot_owner_id == "nonlocal"


@pytest.mark.parametrize("state", ["unknown", "absent", "ambiguous", "unavailable"])
async def test_unconfigured_bu_not_requested_or_observed(session, state):
    await mapping(session, state=state)
    provider = ObservingProvider(deal({"custom_bu": "delivery"}))
    await handle_event(session, {"eventId": "bu-event", "objectId": "deal-1"}, provider)
    row = await session.scalar(select(Opportunity))
    assert row.business_unit_value is None and row.business_unit_observed_at is None
    assert provider.requested[0] == ("deal", ())


async def test_configured_bu_missing_from_response_is_not_observed_empty(session):
    await mapping(session)
    provider = ObservingProvider(deal())
    await handle_event(session, {"eventId": "bu-event", "objectId": "deal-1"}, provider)
    row = await session.scalar(select(Opportunity))
    assert row.business_unit_observed_at is None and row.business_unit_mapping_version is None


async def test_changed_mapping_during_fetch_cannot_stamp_wrong_version(session):
    selected = await mapping(session)

    class ChangingProvider(ObservingProvider):
        async def get_deal(self, deal_id, *, additional_properties=()):
            result = await super().get_deal(deal_id, additional_properties=additional_properties)
            selected.mapping_version = 8
            selected.internal_name = "replacement_bu"
            await session.flush()
            return result

    provider = ChangingProvider(deal({"custom_bu": "delivery"}))
    await handle_event(session, {"eventId": "bu-event", "objectId": "deal-1"}, provider)
    row = await session.scalar(select(Opportunity))
    assert row.business_unit_observed_at is None and row.business_unit_mapping_version is None
    assert provider.requested[0] == ("deal", ("custom_bu",))


async def test_company_owner_bu_and_stale_fence(session, records):
    await mapping(session, object_type="company")
    provider = ObservingProvider(deal(), {"id": "company-1", "properties": {
        "name": "New company", "hubspot_owner_id": "company-owner", "custom_bu": "delivery",
        "hs_lastmodifieddate": "2026-10-02T01:00:00Z"}})
    payload = deal({"associatedcompanyid": "company-1"})
    row = await _resolve_client(session, provider, "deal-1", payload, "company-test")
    assert row.hubspot_owner_id == "company-owner" and row.hubspot_owner_observed_at is not None
    assert row.business_unit_value == "delivery" and row.business_unit_mapping_version == 7
    assert provider.requested == [("company", ("custom_bu",))]
    provider.companies["company-1"]["properties"].update({"name": "Old company",
        "hubspot_owner_id": "old", "hs_lastmodifieddate": "2026-10-01T01:00:00Z"})
    await _resolve_client(session, provider, "deal-1", payload, "stale-company-test")
    assert row.name == "New company" and row.hubspot_owner_id == "company-owner"
    provider.companies["company-1"]["properties"].update({"name": "New company",
        "hubspot_owner_id": None, "custom_bu": "", "hs_lastmodifieddate": "2026-10-02T02:00:00Z"})
    await _resolve_client(session, provider, "deal-1", payload, "empty-company-test")
    assert row.hubspot_owner_id is None and row.business_unit_value is None
    assert row.hubspot_owner_observed_at is not None and row.business_unit_mapping_version == 7


async def test_transport_requests_selected_property_and_source_owner():
    class Transport(HubSpotClient):
        def __init__(self):
            self.calls = []

        async def _get(self, path, params=None):
            self.calls.append((path, params))
            return {"results": []}

    client = Transport()
    await client.get_deal("1", additional_properties=("custom_bu",))
    await client.list_deals_page(additional_properties=("custom_bu",))
    await client.get_company("2", additional_properties=("company_bu",))
    for _, params in client.calls:
        assert "hubspot_owner_id" in params["properties"].split(",")
        assert "hs_lastmodifieddate" in params["properties"].split(",")
    assert "custom_bu" in client.calls[0][1]["properties"].split(",")
    assert "custom_bu" in client.calls[1][1]["properties"].split(",")
    assert "company_bu" in client.calls[2][1]["properties"].split(",")


async def test_company_partial_response_preserves_unfetched_name(session, records):
    provider = ObservingProvider(deal(), {"id": "company-1", "properties": {
        "hubspot_owner_id": "company-owner", "hs_lastmodifieddate": "2026-10-02T01:00:00Z"}})
    row = await _resolve_client(session, provider, "deal-1",
        deal({"associatedcompanyid": "company-1"}), "partial-company")
    assert row.name == "Adapter fixture"
    events = list((await session.scalars(select(AuditEvent).where(
        AuditEvent.action == "client.source_observed"))).all())
    assert len(events) == 1
    assert events[0].after["hubspot_owner_id"] == "company-owner"
    assert events[0].after["hubspot_last_modified_at"] == "2026-10-02T01:00:00+00:00"


async def test_source_observations_and_audit_rollback_together(session, records):
    await session.commit()
    row = await write(session, records, deal({"hubspot_owner_id": "external"}))
    row_id = row.id
    event = await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(row_id)))
    assert event.after["hubspot_owner_id"] == "external"
    assert event.after["owner_observed"] is True
    await session.rollback()
    assert await session.get(Opportunity, row_id) is None
    assert await session.scalar(select(AuditEvent).where(AuditEvent.entity_id == str(row_id))) is None


async def test_backfill_requests_and_persists_configured_property(engine):
    class Provider(StubHubSpotClient):
        def __init__(self):
            super().__init__(deals={"deal-1": deal({"business_unit": "delivery"})})
            self.requested = []

        async def _get(self, path, params=None):
            if path == "/crm/v3/properties/deals":
                return {"results": [{"name": "business_unit", "label": "Business Unit",
                    "type": "enumeration", "options": [{"value": "delivery", "label": "Delivery"}]}]}
            if path == "/crm/v3/owners":
                return {"results": []}
            raise AssertionError(path)

        async def list_deals_page(self, *, after=None, limit=100, additional_properties=()):
            self.requested.append(additional_properties)
            return await super().list_deals_page(after=after, limit=limit,
                additional_properties=additional_properties)

    provider = Provider()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    counts = await run_backfill(provider, session_factory=factory)
    assert counts.errors == 0 and counts.deals_created == 1
    assert provider.requested == [("business_unit",)]
    async with factory() as session:
        row = await session.scalar(select(Opportunity))
        assert row.business_unit_value == "delivery"
        assert row.business_unit_mapping_version == 1 and row.business_unit_observed_at is not None


async def test_deal_fence_reloads_version_instead_of_trusting_identity_cache(session, records):
    row = await write(session, records, deal({"hubspot_owner_id": "initial"}))
    await session.flush()
    await session.execute(update(Opportunity).where(Opportunity.id == row.id).values(
        hubspot_last_modified_at=datetime(2026, 10, 2, 3, tzinfo=UTC),
        hubspot_owner_id="newest").execution_options(synchronize_session=False))
    await write(session, records, deal({"hubspot_owner_id": "stale"}, "2026-10-02T02:00:00Z"))
    await session.flush()
    await session.refresh(row)
    assert row.hubspot_owner_id == "newest"


async def test_company_fence_reloads_version_instead_of_trusting_identity_cache(session, records):
    provider = ObservingProvider(deal(), {"id": "company-1", "properties": {
        "name": "Company", "hubspot_owner_id": "initial",
        "hs_lastmodifieddate": "2026-10-02T01:00:00Z"}})
    payload = deal({"associatedcompanyid": "company-1"})
    row = await _resolve_client(session, provider, "deal-1", payload, "initial-company")
    await session.flush()
    await session.execute(update(Client).where(Client.id == row.id).values(
        hubspot_last_modified_at=datetime(2026, 10, 2, 3, tzinfo=UTC),
        hubspot_owner_id="newest").execution_options(synchronize_session=False))
    provider.companies["company-1"]["properties"].update({"hubspot_owner_id": "stale",
        "hs_lastmodifieddate": "2026-10-02T02:00:00Z"})
    await _resolve_client(session, provider, "deal-1", payload, "stale-company")
    await session.flush()
    await session.refresh(row)
    assert row.hubspot_owner_id == "newest"
