"""T04 · owner resolution across states (S20 · W5, implemented 2026-10-05).

Per review + D2:
- deal sales owner   → HubSpot owner id, resolved via owner mirror
                       (archived owners included).
- client account owner → HubSpot company owner property, else "not set";
                       NEVER derived from a deal.
- local assignee     → DealGate user for actions/tasks only.

Display rules:
- unresolved source reference → name/email None with source_owner_id set
  (the UI renders "Owner details unavailable").
- empty source                → everything None ("Unassigned").

These were xfail skeletons from S20; the owner mirror (W1/W2) landed but
the list surfaces were never wired to it — the released Pipeline showed
"Owner details unavailable" for every company. Implemented together with
that wiring fix.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_owners import HubspotOwner
from app.services.hubspot_pipeline import list_clients, list_opportunities


async def _seed_deal(
    session,
    *,
    hubspot_owner_id: str | None,
    client_owner_id: str | None = None,
    local_owner: User | None = None,
):
    client = Client(
        id=uuid.uuid4(),
        name=f"Owner res client {uuid.uuid4().hex[:6]}",
        hubspot_company_id=f"HS-OR-{uuid.uuid4().hex[:6]}",
    )
    if client_owner_id is not None:
        client.hubspot_owner_id = client_owner_id
    session.add(client)
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"HD-{uuid.uuid4().hex[:8]}",
        client_id=client.id,
        owner_id=local_owner.id if local_owner else None,
        hubspot_owner_id=hubspot_owner_id,
        governance_status="Intake",
        name="Owner resolution deal",
    )
    session.add(opp)
    await session.commit()
    return client, opp


def _mirror(owner_id: str, first: str, last: str, *, archived: bool = False):
    return HubspotOwner(
        id=owner_id,
        email=f"{first.lower()}.{last.lower()}@example.test",
        first_name=first,
        last_name=last,
        archived=archived,
    )


async def _only_row(session, opp_id):
    page = await list_opportunities(session, page_size=100)
    return next(r for r in page.items if r.opportunity_id == opp_id)


@pytest.mark.asyncio
async def test_active_owner_resolves_to_name(session):
    session.add(_mirror("901", "Sam", "Owner"))
    _, opp = await _seed_deal(session, hubspot_owner_id="901")
    row = await _only_row(session, opp.id)
    assert row.owner_name == "Sam Owner"
    assert row.owner_archived is False


@pytest.mark.asyncio
async def test_archived_owner_still_resolves(session):
    session.add(_mirror("902", "Alex", "Retired", archived=True))
    _, opp = await _seed_deal(session, hubspot_owner_id="902")
    row = await _only_row(session, opp.id)
    assert row.owner_name == "Alex Retired"
    assert row.owner_archived is True


@pytest.mark.asyncio
async def test_unresolved_owner_reads_owner_details_unavailable(session):
    _, opp = await _seed_deal(session, hubspot_owner_id="903-missing")
    row = await _only_row(session, opp.id)
    assert row.owner_name is None and row.owner_email is None
    assert row.source_owner_id == "903-missing"  # UI: "Owner details unavailable"


@pytest.mark.asyncio
async def test_null_source_owner_reads_unassigned(session):
    _, opp = await _seed_deal(session, hubspot_owner_id=None)
    row = await _only_row(session, opp.id)
    assert row.owner_name is None and row.owner_email is None
    assert row.source_owner_id is None and row.owner_id is None  # "Unassigned"


@pytest.mark.asyncio
async def test_company_account_owner_not_derived_from_deals(session):
    session.add_all([_mirror("904", "Carol", "Account"), _mirror("905", "Dana", "Deal")])
    client, opp = await _seed_deal(
        session, hubspot_owner_id="905", client_owner_id="904"
    )
    clients_page = await list_clients(session, page_size=100)
    crow = next(r for r in clients_page.items if r.client_id == client.id)
    assert crow.account_owner_name == "Carol Account"
    assert crow.account_owner_email == "carol.account@example.test"
    drow = await _only_row(session, opp.id)
    assert drow.owner_name == "Dana Deal"  # the two axes stay independent


@pytest.mark.asyncio
async def test_hubspot_owner_without_local_login_still_valid(session):
    # No DealGate User exists for this rep — only the mirror knows them.
    session.add(_mirror("906", "Remote", "Rep"))
    _, opp = await _seed_deal(session, hubspot_owner_id="906", local_owner=None)
    row = await _only_row(session, opp.id)
    assert row.owner_name == "Remote Rep"
    assert row.owner_id is None  # no local login, still valid CRM ownership
