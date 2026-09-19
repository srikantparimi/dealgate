"""Round-trip every model through an in-memory async session."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Agreement,
    Client,
    IntegrationEvent,
    LegalEntity,
    Opportunity,
    Task,
    User,
)


async def test_user_round_trip(session):
    u = User(email="finance@smartek21.com", name="Fin One", groups=["Finance"])
    session.add(u)
    await session.commit()

    got = (await session.execute(select(User).where(User.email == "finance@smartek21.com"))).scalar_one()
    assert got.groups == ["Finance"]
    assert isinstance(got.id, uuid.UUID)


async def test_user_email_unique(session):
    session.add(User(email="dup@smartek21.com", name="A", groups=[]))
    await session.commit()
    session.add(User(email="dup@smartek21.com", name="B", groups=[]))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_client_legal_entity_agreement_chain(session):
    c = Client(name="Acme")
    session.add(c)
    await session.flush()
    le = LegalEntity(client_id=c.id, name="Acme Inc.", country="US")
    session.add(le)
    await session.flush()
    a = Agreement(
        legal_entity_id=le.id,
        kind="MSA",
        effective_date=date(2026, 1, 1),
    )
    session.add(a)
    await session.commit()
    assert a.id is not None


async def test_opportunity_hubspot_id_unique(session):
    """S10-01: uniqueness is enforced by a **partial** index — NULLs may
    repeat (SOW-upload opportunities have no HubSpot side), non-NULLs
    must not."""

    session.add(Opportunity(hubspot_deal_id="H-1"))
    await session.commit()
    session.add(Opportunity(hubspot_deal_id="H-1"))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_opportunity_allows_multiple_null_hubspot_ids(session):
    """S10-01: two SOW-upload opportunities (hubspot_deal_id=NULL) coexist."""

    session.add(Opportunity(hubspot_deal_id=None, source="sow_upload"))
    session.add(Opportunity(hubspot_deal_id=None, source="sow_upload"))
    await session.commit()


async def test_task_defaults(session):
    t = Task(subject="Draft SOW")
    session.add(t)
    await session.commit()
    # S2-E3 flipped the default from 'Open' to 'assigned' as part of the
    # lifecycle state machine (see app.services.tasks.TASK_TRANSITIONS).
    assert t.status == "assigned"
    assert t.escalation_level == 0
    assert t.wake_at is None
    assert t.completed_at is None
    assert t.completed_by is None
    assert t.category is None


async def test_integration_event_source_event_id_unique(session):
    session.add(
        IntegrationEvent(source="hubspot", source_event_id="evt-1", payload={"k": "v"})
    )
    await session.commit()
    session.add(
        IntegrationEvent(source="hubspot", source_event_id="evt-1", payload={"k": "v"})
    )
    with pytest.raises(IntegrityError):
        await session.commit()
