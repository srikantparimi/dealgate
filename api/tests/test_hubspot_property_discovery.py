"""S20 W1 D10 · Business Unit property discovery acceptance.

Covers T09 / T26 style shape:
- Discovers a deal property matching internal name `business_unit`.
- Falls back to a company property when deal properties don't match.
- Records a blocked state with evidence when nothing matches.
- Re-runs are idempotent.
- The read-side returns the mapping row.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import StubHubSpotClient
from app.services.hubspot_properties import (
    HubspotPropertyMapping,
    discover_business_unit,
    get_business_unit_mapping,
)


class _PropsStub(StubHubSpotClient):
    def __init__(
        self,
        *,
        deal_props: list[dict[str, Any]] | None = None,
        company_props: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self._deal = deal_props or []
        self._company = company_props or []
        self.paths: list[str] = []

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:  # noqa: SLF001
        self.paths.append(path)
        if path == "/crm/v3/properties/deals":
            return {"results": list(self._deal)}
        if path == "/crm/v3/properties/companies":
            return {"results": list(self._company)}
        raise KeyError(path)


def _enum_prop(
    name: str, *, label: str, options: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "enumeration",
        "fieldType": "select",
        "options": options
        or [
            {"value": "financial_services", "label": "Financial Services", "displayOrder": 0},
            {"value": "healthcare", "label": "Healthcare", "displayOrder": 1},
        ],
    }


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def test_discovers_deal_business_unit_by_internal_name(factory):
    stub = _PropsStub(
        deal_props=[
            {"name": "dealname", "label": "Deal Name", "type": "string"},
            _enum_prop("business_unit", label="Business Unit"),
        ]
    )
    async with factory() as s:
        result = await discover_business_unit(s, stub)
        await s.commit()

    assert result.found is True
    assert result.internal_name == "business_unit"
    assert result.object_type == "deal"
    assert result.label == "Business Unit"
    assert result.field_type == "enumeration"
    assert result.options is not None
    assert {o["value"] for o in result.options} == {"financial_services", "healthcare"}
    # Fell out at the FIRST match — company path wasn't consulted.
    assert stub.paths == ["/crm/v3/properties/deals"]


async def test_falls_back_to_company_property(factory):
    stub = _PropsStub(
        deal_props=[
            {"name": "dealname", "label": "Deal Name", "type": "string"},
        ],
        company_props=[
            _enum_prop("bu", label="BU"),
        ],
    )
    async with factory() as s:
        result = await discover_business_unit(s, stub)
        await s.commit()

    assert result.found is True
    assert result.internal_name == "bu"
    assert result.object_type == "company"
    assert stub.paths == [
        "/crm/v3/properties/deals",
        "/crm/v3/properties/companies",
    ]


async def test_ignores_non_enumeration_matches(factory):
    stub = _PropsStub(
        deal_props=[
            # Correct name but wrong type — not the property we want.
            {"name": "business_unit_notes", "label": "Business Unit Notes", "type": "string"},
        ]
    )
    async with factory() as s:
        result = await discover_business_unit(s, stub)
        await s.commit()

    assert result.found is False
    # Evidence names what was searched so the settings page can render it.
    assert "business_unit_notes" in result.evidence["searched_deal_property_names"]


async def test_returns_blocked_with_evidence_when_missing(factory):
    stub = _PropsStub(
        deal_props=[{"name": "dealname", "label": "Deal Name", "type": "string"}],
        company_props=[{"name": "name", "label": "Name", "type": "string"}],
    )
    async with factory() as s:
        result = await discover_business_unit(s, stub)
        await s.commit()

    assert result.found is False
    assert result.internal_name is None
    # Evidence includes the searched names for the D10 blocked reason.
    assert result.evidence["searched_deal_property_names"] == ["dealname"]
    assert result.evidence["searched_company_property_names"] == ["name"]

    # No mapping row persisted when nothing matched.
    async with factory() as s:
        row = await get_business_unit_mapping(s)
    assert row is None


async def test_discovery_is_idempotent(factory):
    stub = _PropsStub(deal_props=[_enum_prop("business_unit", label="Business Unit")])
    async with factory() as s:
        first = await discover_business_unit(s, stub)
        await s.commit()
    async with factory() as s:
        second = await discover_business_unit(s, stub)
        await s.commit()
    assert first.found and second.found
    assert first.internal_name == second.internal_name

    async with factory() as s:
        rows = (await s.execute(select(HubspotPropertyMapping))).scalars().all()
    assert len(rows) == 1
    assert rows[0].key == "business_unit"


async def test_option_change_updates_mapping_in_place(factory):
    stub = _PropsStub(deal_props=[_enum_prop("business_unit", label="Business Unit")])
    async with factory() as s:
        await discover_business_unit(s, stub)
        await s.commit()

    stub._deal = [
        _enum_prop(
            "business_unit",
            label="Business Unit",
            options=[
                {"value": "financial_services", "label": "Financial Services", "displayOrder": 0},
                {"value": "healthcare", "label": "Healthcare", "displayOrder": 1},
                {"value": "gov", "label": "Government", "displayOrder": 2},
            ],
        )
    ]
    async with factory() as s:
        result = await discover_business_unit(s, stub)
        await s.commit()
    assert {o["value"] for o in result.options} == {
        "financial_services",
        "healthcare",
        "gov",
    }
    async with factory() as s:
        row = await get_business_unit_mapping(s)
    assert row is not None
    assert {o["value"] for o in row.options} == {
        "financial_services",
        "healthcare",
        "gov",
    }
