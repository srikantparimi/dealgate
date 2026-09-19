"""S9 wave 1 — MSA rate-schedule import: stub extractor returns a canned
schedule, draft has per-row confidence + source='msa', not auto-published.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.integrations.bedrock_sow_extract import StubBedrock
from app.main import app as main_app
from app.models.client import Client
from app.models.client_rate_card import ClientRateCard
from app.services.msa_import import (
    DraftClientRateCard,
    MsaRateExtractor,
    import_rate_schedule,
)


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _http(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


@pytest_asyncio.fixture
async def acme(session):
    c = Client(id=uuid.uuid4(), name="Acme Corp")
    session.add(c)
    await session.commit()
    return c


# --- extractor -------------------------------------------------------------


async def test_import_returns_draft_with_stub_rows(session, acme):
    extractor = MsaRateExtractor(bedrock=StubBedrock())
    draft = await import_rate_schedule(
        session,
        actor_id=None,
        client_id=acme.id,
        msa_file_key="msa/acme/msa.pdf",
        extractor=extractor,
    )
    assert isinstance(draft, DraftClientRateCard)
    assert draft.manual_required is False
    assert len(draft.rows) == 3
    # Every row carries a page_ref and a confidence.
    for row in draft.rows:
        assert row.page_ref >= 1
        assert 0 <= row.confidence <= 1
    # Deterministic source_document_id derived from the file key.
    assert draft.source_document_id == uuid.uuid5(
        uuid.NAMESPACE_URL, "dealgate:msa:msa/acme/msa.pdf"
    )


async def test_import_never_publishes(session, acme):
    """Draft is not persisted — human must confirm via POST /rate-card."""

    extractor = MsaRateExtractor(bedrock=StubBedrock())
    await import_rate_schedule(
        session,
        actor_id=None,
        client_id=acme.id,
        msa_file_key="msa/acme/msa.pdf",
        extractor=extractor,
    )
    cards = (await session.execute(select(ClientRateCard))).scalars().all()
    assert cards == []


async def test_import_manual_required_when_bedrock_unavailable(session, acme):
    extractor = MsaRateExtractor(bedrock=StubBedrock(unavailable=True))
    draft = await import_rate_schedule(
        session,
        actor_id=None,
        client_id=acme.id,
        msa_file_key="msa/acme/msa.pdf",
        extractor=extractor,
    )
    assert draft.manual_required is True
    assert draft.rows == []
    assert draft.warnings and "bedrock" in draft.warnings[0].lower()


# --- router import + publish round trip -----------------------------------


async def test_router_import_returns_draft(app_with_session, acme, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    # Patch the extractor by monkeypatching the module-level default.
    from app.routers import client_rate_cards as router_mod

    orig_import = router_mod.import_rate_schedule

    async def _stub_import(*args, **kwargs):
        kwargs["extractor"] = MsaRateExtractor(bedrock=StubBedrock())
        return await orig_import(*args, **kwargs)

    monkeypatch.setattr(router_mod, "import_rate_schedule", _stub_import)

    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{acme.id}/rate-card/import",
            headers={"X-Test-User": "f@smartek21.com"},
            json={"msa_file_key": "msa/acme/msa.pdf"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft"]["manual_required"] is False
    assert len(body["draft"]["rows"]) == 3
    assert len(body["publish_rows"]) == 3


async def test_publish_msa_source_records_document_id(app_with_session, acme, monkeypatch, session):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    doc_id = uuid.uuid4()
    async with _http(app_with_session) as c:
        r = await c.post(
            f"/clients/{acme.id}/rate-card",
            headers={"X-Test-User": "f@smartek21.com"},
            json={
                "effective_from": "2026-09-01",
                "source": "msa",
                "source_document_id": str(doc_id),
                "rows": [
                    {
                        "role": "Engineer",
                        "seniority": "Mid",
                        "location": "US",
                        "bill_rate": "175.00",
                        "currency": "USD",
                        "unit": "hourly",
                    }
                ],
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["card"]["source"] == "msa"
    assert body["card"]["source_document_id"] == str(doc_id)

    cards = (await session.execute(select(ClientRateCard))).scalars().all()
    assert len(cards) == 1
    assert cards[0].source == "msa"
    assert cards[0].source_document_id == doc_id
