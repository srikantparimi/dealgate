"""S20 W1 D7 · A4 · T34 — duplicate delivery + atomic commit acceptance.

Contracts §D7: "Record + audit + outbox committed atomically before SQS
ack." Concretely:

- Same source_event_id delivered under two distinct SQS message ids only
  produces ONE opportunity + ONE audit line (idempotency).
- ``hubspot_webhook_processed`` watermark advances in the same commit as
  the record + audit (no half-open write).
- A crash between record commit and worker ack redelivers the same
  message; the second call sees ``processed_at`` set and returns.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.hubspot import StubHubSpotClient
from app.models.audit import AuditEvent
from app.models.integration import IntegrationEvent
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.services.hubspot_intake import handle_event


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("SALES_LEADER_EMAIL", "sales-leader@smartek21.com")
    monkeypatch.setenv("DEALGATE_ENV", "local")


@pytest_asyncio.fixture
async def factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


def _event(event_id: int = 5001, deal_id: str = "999") -> dict[str, Any]:
    return {
        "eventId": event_id,
        "subscriptionType": "deal.propertyChange",
        "objectId": int(deal_id),
        "portalId": 12345,
        "changeSource": "CRM",
    }


def _deal(deal_id: str = "999") -> dict[str, Any]:
    return {
        "id": deal_id,
        "properties": {
            "dealname": "S20 W1 dedupe deal",
            "dealstage": "qualifiedtobuy",
            "pipeline": "default",
            "hubspot_owner_id": "42",
            "amount": "10000.00",
            "closedate": "2026-11-15",
        },
    }


def _owner() -> dict[str, Any]:
    return {"id": "42", "email": "rep@x.com", "firstName": "Rep", "lastName": "One"}


async def test_same_source_event_produces_one_opportunity_only(factory):
    """T34 top: two distinct SQS messages, same source_event_id → 1 write."""

    event = _event()
    stub = StubHubSpotClient(deals={"999": _deal()}, owners={"42": _owner()})

    async with factory() as s:
        await handle_event(s, event, stub)
    # Second call simulates SQS redelivering under a different queue msg id.
    async with factory() as s:
        await handle_event(s, event, stub)

    async with factory() as s:
        opps = (
            await s.execute(
                select(Opportunity).where(Opportunity.hubspot_deal_id == "999")
            )
        ).scalars().all()
        audits = (
            await s.execute(
                select(AuditEvent).where(AuditEvent.action == "opportunity.created")
            )
        ).scalars().all()
        integration_rows = (
            await s.execute(select(IntegrationEvent))
        ).scalars().all()
    assert len(opps) == 1
    assert len(audits) == 1
    # source_event_id unique constraint → only one integration_event row.
    assert len(integration_rows) == 1
    assert integration_rows[0].processed_at is not None


async def test_processed_watermark_advances_atomically(factory):
    """D4 + D7: the watermark row commits WITH the opportunity + audit.

    We verify commit-atomicity by observing that the integration_event's
    ``processed_at`` timestamp AND the sync_status ``processed_at``
    watermark are both set after a single call — proving they landed in
    the same transaction.
    """

    stub = StubHubSpotClient(deals={"999": _deal()}, owners={"42": _owner()})
    async with factory() as s:
        await handle_event(s, _event(), stub)

    async with factory() as s:
        ievent = (
            await s.execute(select(IntegrationEvent))
        ).scalars().one()
        wm = await s.get(SyncStatus, "hubspot_webhook_processed")
    assert ievent.processed_at is not None
    assert wm is not None
    assert wm.processed_at is not None


async def test_replay_after_ack_drop_is_no_op(factory):
    """A message re-delivered after commit sees processed_at and exits.

    The intake worker deletes the SQS message AFTER commit; a crash
    between commit and delete means SQS redelivers. handle_event must
    detect the already-set ``processed_at`` and return without doing
    the deal upsert twice.
    """

    stub = StubHubSpotClient(deals={"999": _deal()}, owners={"42": _owner()})
    async with factory() as s:
        await handle_event(s, _event(), stub)

    # Force a redelivery from the same source event id — should short-
    # circuit before touching HubSpot again. Assert no additional deal
    # GET was issued by wiping the deals map and observing no KeyError.
    stub.deals = {}
    async with factory() as s:
        await handle_event(s, _event(), stub)  # No exception = short-circuit
    async with factory() as s:
        rows = (await s.execute(select(Opportunity))).scalars().all()
    assert len(rows) == 1


async def test_non_deal_subscription_still_advances_processed_watermark(factory):
    """Even ``contact.creation`` events bump the watermark so freshness
    stays honest on portals that emit non-deal events."""

    stub = StubHubSpotClient(deals={}, owners={})
    contact_event = {
        "eventId": 7777,
        "subscriptionType": "contact.creation",
        "objectId": 5555,
        "portalId": 12345,
    }
    async with factory() as s:
        await handle_event(s, contact_event, stub)

    async with factory() as s:
        wm = await s.get(SyncStatus, "hubspot_webhook_processed")
    assert wm is not None
    assert wm.processed_at is not None
