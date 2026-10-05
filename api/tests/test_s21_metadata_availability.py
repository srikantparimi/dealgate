"""Metadata availability must distinguish failed discovery from proven absence."""

from copy import deepcopy

import pytest
from sqlalchemy import select

from app.audit import verify_chain
from app.models.audit import AuditEvent

from app.services.hubspot_properties import (
    HubspotPropertyMapping,
    discover_business_unit,
    get_business_unit_mapping,
)


def prop(name="business_unit"):
    return {"name": name, "label": "Business Unit", "type": "enumeration",
            "options": [{"value": "consulting", "label": "Consulting"}]}


class Provider:
    def __init__(self, deals=None, companies=None):
        self.deals = deals if deals is not None else {"results": []}
        self.companies = companies if companies is not None else {"results": []}
        self.paths = []

    async def _get(self, path):
        self.paths.append(path)
        response = self.deals if path.endswith("deals") else self.companies
        if isinstance(response, Exception):
            raise response
        return deepcopy(response)


@pytest.mark.parametrize("response", [None, {}, {"results": None}, {"results": {}},
    {"results": [None]}, {"results": [{"name": "business_unit", "type": 5}]},
    PermissionError("403"), TimeoutError("timeout")])
async def test_failed_metadata_is_unavailable_not_absent(session, response):
    provider = Provider()
    provider.deals = response
    result = await discover_business_unit(session, provider)
    row = await session.get(HubspotPropertyMapping, "business_unit")
    assert not result.found
    assert row.availability_state == "unavailable"
    assert row.checked_at is not None and row.last_success_at is None
    assert provider.paths == ["/crm/v3/properties/deals"]


async def test_valid_empty_metadata_persists_absent(session):
    result = await discover_business_unit(session, Provider())
    row = await session.get(HubspotPropertyMapping, "business_unit")
    assert result.availability_state == row.availability_state == "absent"
    assert row.last_success_at is not None
    assert await get_business_unit_mapping(session) is None


async def test_multiple_candidates_never_choose_first(session):
    result = await discover_business_unit(session, Provider({"results": [prop(), prop("bu")]}))
    row = await session.get(HubspotPropertyMapping, "business_unit")
    assert not result.found and row.availability_state == "ambiguous"
    assert row.internal_name is None
    assert len(row.evidence["candidates"]) == 2


@pytest.mark.parametrize("options", [None, {}, [None], [{}],
    [{"value": "x", "label": 1}], [{"value": "x", "label": "X", "hidden": "false"}],
    [{"value": "x", "label": "X", "displayOrder": True}],
    [{"value": "x", "label": "X"}, {"value": "x", "label": "Again"}]])
async def test_invalid_options_are_not_configured(session, options):
    definition = prop()
    definition["options"] = options
    result = await discover_business_unit(session, Provider({"results": [definition]}))
    assert not result.found
    assert result.availability_state == "unavailable"


async def test_last_good_identity_options_and_evidence_survive_error(session):
    first = await discover_business_unit(session, Provider({"results": [prop()]}))
    row = await session.get(HubspotPropertyMapping, "business_unit")
    success_at = row.last_success_at
    result = await discover_business_unit(session, Provider(PermissionError("secret provider payload")))
    assert not result.found and result.availability_state == "unavailable"
    assert row.internal_name == first.internal_name
    assert row.options == first.options
    assert row.last_success_at == success_at
    assert row.evidence["last_good"]["matched_property"]["name"] == "business_unit"
    assert "secret provider payload" not in str(row.evidence)
    assert await get_business_unit_mapping(session) is None


async def test_bound_mapping_removed_does_not_rebind(session):
    await discover_business_unit(session, Provider({"results": [prop()]}))
    result = await discover_business_unit(session, Provider({"results": [prop("bu")]}))
    row = await session.get(HubspotPropertyMapping, "business_unit")
    assert result.availability_state == "unavailable"
    assert row.internal_name == "business_unit" and row.mapping_version == 1


async def test_metadata_version_changes_once_and_not_for_option_order(session):
    definition = prop()
    definition["options"].append({"value": "delivery", "label": "Delivery"})
    provider = Provider({"results": [definition]})
    await discover_business_unit(session, provider)
    row = await session.get(HubspotPropertyMapping, "business_unit")
    assert row.mapping_version == 1
    provider.deals["results"][0]["options"].reverse()
    await discover_business_unit(session, provider)
    assert row.mapping_version == 1
    provider.deals["results"][0]["options"][0]["label"] = "Delivery services"
    await discover_business_unit(session, provider)
    assert row.mapping_version == 2
    await discover_business_unit(session, provider)
    assert row.mapping_version == 2


async def test_bound_company_refresh_does_not_depend_on_deal_access(session):
    await discover_business_unit(session, Provider(companies={"results": [prop()]}))
    provider = Provider(PermissionError("403"), {"results": [prop()]})
    result = await discover_business_unit(session, provider)
    assert result.found and result.object_type == "company"
    assert provider.paths == ["/crm/v3/properties/companies"]


async def test_material_metadata_transitions_have_atomic_audit(session):
    await discover_business_unit(session, Provider())
    provider = Provider({"results": [prop()]})
    await discover_business_unit(session, provider)
    await discover_business_unit(session, provider)
    provider.deals["results"][0]["options"][0]["label"] = "Consulting services"
    await discover_business_unit(session, provider)
    await discover_business_unit(session, Provider(PermissionError("403")))
    await discover_business_unit(session, Provider(PermissionError("403")))
    events = list((await session.scalars(select(AuditEvent).order_by(AuditEvent.ts))).all())
    assert len(events) == 4
    assert [event.after["availability_state"] for event in events] == [
        "absent", "configured", "configured", "unavailable"]
    assert events[0].before["availability_state"] == "unknown"
    assert events[2].before["mapping_version"] == 1
    assert events[2].after["mapping_version"] == 2
    assert events[2].before["options"][0]["label"] == "Consulting"
    assert events[2].after["options"][0]["label"] == "Consulting services"
    assert events[3].after["availability_reason"] == "metadata_fetch_or_schema_failed"
    assert all(event.actor_id is None for event in events)
    assert all(event.after["source"] == "hubspot_property_discovery" for event in events)
    assert await verify_chain(session)
    await session.rollback()
    assert await session.get(HubspotPropertyMapping, "business_unit") is None
    assert list((await session.scalars(select(AuditEvent))).all()) == []
