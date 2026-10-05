"""Unknown source facts must not be manufactured by schema expansion."""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.services.hubspot_properties import HubspotPropertyMapping


@pytest.mark.asyncio
async def test_legacy_rows_keep_owner_and_bu_unobserved(session):
    account = Client(name="Synthetic source observation")
    deal = Opportunity(source="manual", governance_status="Intake")
    session.add_all([account, deal])
    await session.commit()
    for row in (account, deal):
        assert row.hubspot_owner_id is None
        assert row.hubspot_owner_observed_at is None
        assert row.business_unit_value is None
        assert row.business_unit_mapping_version is None
        assert row.business_unit_observed_at is None
    assert deal.local_assignee_id is None


@pytest.mark.asyncio
async def test_observed_empty_owner_is_distinct_from_unobserved(session):
    observed = datetime.now(UTC)
    account = Client(name="Synthetic explicit empty owner", hubspot_owner_observed_at=observed)
    deal = Opportunity(source="manual", governance_status="Intake", hubspot_owner_id="external-no-local-user",
        hubspot_owner_observed_at=observed, business_unit_value="unknown-source-option",
        business_unit_mapping_version=7, business_unit_observed_at=observed)
    session.add_all([account, deal])
    await session.commit()
    assert account.hubspot_owner_id is None and account.hubspot_owner_observed_at == observed
    assert deal.owner_id is None and deal.local_assignee_id is None
    assert deal.hubspot_owner_id == "external-no-local-user"
    assert deal.business_unit_value == "unknown-source-option"


@pytest.mark.asyncio
async def test_mapping_can_record_unavailable_without_dummy_property_identity(session):
    mapping = HubspotPropertyMapping(key="business_unit", availability_state="unavailable",
        availability_reason="Forbidden metadata read", checked_at=datetime.now(UTC),
        evidence={"object_type": "deals", "status": 403})
    session.add(mapping)
    await session.commit()
    assert mapping.mapping_version == 1
    assert mapping.internal_name is None
    assert mapping.last_success_at is None
    assert mapping.selected_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [{"mapping_version": 0}, {"availability_state": "ready"}])
async def test_mapping_rejects_invalid_availability_or_revision(session, values):
    session.add(HubspotPropertyMapping(key=str(uuid.uuid4()), **values))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [Client, Opportunity])
async def test_source_mapping_revision_must_be_positive(session, model):
    values = {"name": "Synthetic invalid mapping"} if model is Client else {"source": "manual", "governance_status": "Intake"}
    session.add(model(**values, business_unit_mapping_version=0))
    with pytest.raises(IntegrityError):
        await session.commit()
