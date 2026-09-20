"""S9 wave 1 — resolve_bill_rate: SOW override wins, client card next,
fallback returns a warning.

Order per docs/directives/sow-first.md:
    client card  ->  SOW-stated override  ->  segment default  ->  company default

For the split, "SOW-stated" wins over "client card" for revenue (finance
policy) — the client card still records what the MSA said; the SOW
override is scoped to this SOW.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest_asyncio

from app.models.client import Client
from app.services.client_rate_cards import (
    ClientRateCardRowInput,
    publish_client_rate_card,
    resolve_bill_rate,
)


@pytest_asyncio.fixture
async def acme(session):
    c = Client(id=uuid.uuid4(), name="Acme Corp")
    session.add(c)
    await session.commit()
    return c


async def test_sow_override_wins(session, acme):
    await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=acme.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    r = await resolve_bill_rate(
        session,
        client_id=acme.id,
        role="Engineer",
        seniority="Mid",
        location="US",
        sow_stated=Decimal("200.00"),
    )
    assert r.rate == Decimal("200.00")
    assert r.source == "sow_override"
    assert r.warning is None


async def test_client_card_used_when_no_sow_override(session, acme):
    await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=acme.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    r = await resolve_bill_rate(
        session,
        client_id=acme.id,
        role="Engineer",
        seniority="Mid",
        location="US",
    )
    assert r.rate == Decimal("175.0000")
    assert r.source == "client_card"
    assert r.warning is None


async def test_missing_row_falls_back_with_warning(session, acme):
    await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=acme.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    r = await resolve_bill_rate(
        session,
        client_id=acme.id,
        role="Architect",
        seniority="Principal",
        location="India",
    )
    assert r.rate is None
    assert r.source == "company_default"
    assert r.warning is not None
    assert "Architect" in r.warning


async def test_no_card_at_all_falls_back(session, acme):
    r = await resolve_bill_rate(
        session,
        client_id=acme.id,
        role="Engineer",
        seniority="Mid",
        location="US",
    )
    assert r.rate is None
    assert r.source == "company_default"
    assert r.warning is not None
    assert "no rate card" in r.warning


async def test_no_client_id_at_all(session):
    r = await resolve_bill_rate(
        session,
        client_id=None,
        role="Engineer",
        seniority="Mid",
        location="US",
    )
    assert r.rate is None
    assert r.source == "company_default"
    assert "no client on this line" in r.warning


async def test_case_insensitive_match(session, acme):
    await publish_client_rate_card(
        session,
        actor_id=None,
        client_id=acme.id,
        rows=[
            ClientRateCardRowInput(
                role="Engineer",
                seniority="Mid",
                location="US",
                bill_rate=Decimal("175.00"),
            )
        ],
        effective_from=date(2026, 1, 1),
    )
    r = await resolve_bill_rate(
        session,
        client_id=acme.id,
        role="  engineer  ",
        seniority="mid",
        location="US",
    )
    assert r.source == "client_card"
    assert r.rate == Decimal("175.0000")


async def test_bad_location_raises(session, acme):
    import pytest

    with pytest.raises(ValueError):
        await resolve_bill_rate(
            session,
            client_id=acme.id,
            role="Engineer",
            seniority="Mid",
            location="Canada",
        )
