"""Agreements API — role gating, CRUD, state transitions, audit chain, and
the S3 evidence pre-signed URL flow (via `StubS3`).

Covers the acceptance tests in `docs/backlog/s2-e3-agreements-crud.md`:

- Legal POST /agreements → audited `agreement.created`.
- PATCH from `sent` → `executed` with `expiry` set persists + audits.
- 422 on illegal transitions with no audit row written.
- 403 on non-Legal mutation attempts.
- Non-Legal governance roles can read.
- Upload URL round-trip returns a signed URL and writes an audit row.
- Executed transition rejected when `expiry` is missing.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client, LegalEntity


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    stub = StubS3()

    def _stub_s3():
        return stub

    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_evidence_s3] = _stub_s3
    main_app.state.stub_s3 = stub
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_evidence_s3, None)
        main_app.state.stub_s3 = None


@pytest_asyncio.fixture
async def seeded(session):
    client = Client(id=uuid.uuid4(), name="Acme, Inc.")
    entity = LegalEntity(
        id=uuid.uuid4(),
        client_id=client.id,
        name="Acme US LLC",
        country="US",
    )
    other_entity = LegalEntity(
        id=uuid.uuid4(),
        client_id=client.id,
        name="Acme IN Pvt Ltd",
        country="IN",
    )
    session.add_all([client, entity, other_entity])
    await session.commit()
    return {"client": client, "entity": entity, "other_entity": other_entity}


async def _audit_for(session, agreement_id: uuid.UUID) -> list[AuditEvent]:
    return (
        await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity == "agreement",
                AuditEvent.entity_id == str(agreement_id),
            )
            .order_by(AuditEvent.ts.asc(), AuditEvent.id.asc())
        )
    ).scalars().all()


# --- permissions -----------------------------------------------------------


async def test_post_forbidden_for_non_legal(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/agreements",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={
                "legal_entity_id": str(seeded["entity"].id),
                "type": "NDA",
                "state": "requested",
                "owner_email": "legal@smartek21.com",
                "next_action": "Draft NDA",
                "due_date": str(date.today() + timedelta(days=7)),
            },
        )
    assert r.status_code == 403


async def test_patch_forbidden_for_non_legal(app_with_session, seeded, session, monkeypatch):
    # Seed an agreement directly so we can attempt to patch it.
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="drafting",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/agreements/{agreement.id}",
            headers={"X-Test-User": "sales@smartek21.com"},
            json={"state": "sent"},
        )
    assert r.status_code == 403


async def test_get_allowed_for_non_legal_governance_role(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="MSA",
        state="drafting",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/agreements",
            headers={"X-Test-User": "finance@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert any(row["id"] == str(agreement.id) for row in body["items"])
    # No cost fields — response shape does not carry any.
    for row in body["items"]:
        assert "cost" not in row
        assert "delivery_cost" not in row
        assert "gm" not in row


async def test_upload_url_forbidden_for_non_legal(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="drafting",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/agreements/{agreement.id}/evidence-upload-url",
            headers={"X-Test-User": "finance@smartek21.com"},
            json={"filename": "nda.pdf", "content_type": "application/pdf"},
        )
    assert r.status_code == 403


# --- POST /agreements ------------------------------------------------------


async def test_post_creates_and_audits(app_with_session, seeded, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/agreements",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={
                "legal_entity_id": str(seeded["entity"].id),
                "type": "NDA",
                "state": "requested",
                "owner_email": "legal@smartek21.com",
                "next_action": "Draft NDA",
                "due_date": str(date.today() + timedelta(days=7)),
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "NDA"
    assert body["state"] == "requested"
    assert body["owner_email"] == "legal@smartek21.com"

    rows = await _audit_for(session, uuid.UUID(body["id"]))
    assert len(rows) == 1
    assert rows[0].action == "agreement.created"
    assert rows[0].actor_id == _uid("legal@smartek21.com")
    assert rows[0].after["state"] == "requested"
    assert await verify_chain(session) is True


async def test_post_unknown_state_returns_422(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/agreements",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={
                "legal_entity_id": str(seeded["entity"].id),
                "type": "NDA",
                "state": "bogus",
            },
        )
    assert r.status_code == 422


async def test_post_unknown_type_returns_422(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/agreements",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={
                "legal_entity_id": str(seeded["entity"].id),
                "type": "SLA",
                "state": "requested",
            },
        )
    assert r.status_code == 422


async def test_post_missing_legal_entity_returns_404(app_with_session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/agreements",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={
                "legal_entity_id": str(uuid.uuid4()),
                "type": "NDA",
                "state": "requested",
            },
        )
    assert r.status_code == 404


# --- PATCH /agreements/{id} -----------------------------------------------


async def test_patch_state_transition_audits(
    app_with_session, seeded, session, monkeypatch
):
    # Tracking moves directly from requested to sent, without review.
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="requested",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    expiry = str(date.today() + timedelta(days=365))
    evidence_key = f"agreements/{agreement.id}/signed.pdf"
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/agreements/{agreement.id}",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={
                "state": "sent",
                "expiry": expiry,
                "evidence_s3_key": evidence_key,
                "notice_days": 60,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "sent"
    assert body["expiry"] == expiry
    assert body["evidence_s3_key"] == evidence_key
    assert body["notice_days"] == 60

    rows = await _audit_for(session, agreement.id)
    actions = [row.action for row in rows]
    assert actions == [
        "agreement.state_changed",  # expiry
        "agreement.state_changed",  # evidence_s3_key
        "agreement.state_changed",  # notice_days
        "agreement.state_changed",  # state
    ]
    # The last audit row carries the state diff.
    assert rows[-1].before == {"state": "requested"}
    assert rows[-1].after == {"state": "sent"}
    assert await verify_chain(session) is True


async def test_patch_illegal_transition_returns_422_no_audit(
    app_with_session, seeded, session, monkeypatch
):
    # `missing -> executed` is illegal.
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="missing",
        expiry=date.today() + timedelta(days=365),
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/agreements/{agreement.id}",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={"state": "executed"},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "signed evidence" in detail

    rows = await _audit_for(session, agreement.id)
    # No audit row for the illegal move.
    assert not any(row.action == "agreement.state_changed" and row.after.get("state") for row in rows)


async def test_patch_executed_without_expiry_returns_422(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="sent",  # legal path to executed, just missing expiry
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/agreements/{agreement.id}",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={"state": "executed"},
        )
    assert r.status_code == 422
    assert "signed evidence" in r.json()["detail"]


# --- GET /agreements filters ----------------------------------------------


async def test_list_filters_by_legal_entity_and_state(
    app_with_session, seeded, session, monkeypatch
):
    a1 = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="drafting",
    )
    a2 = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="MSA",
        state="executed",
        expiry=date.today() + timedelta(days=30),
    )
    a3 = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["other_entity"].id,
        kind="NDA",
        state="drafting",
    )
    session.add_all([a1, a2, a3])
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")

    async with _client(app_with_session) as c:
        r = await c.get(
            f"/agreements?legal_entity_id={seeded['entity'].id}",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert r.status_code == 200
    ids = {row["id"] for row in r.json()["items"]}
    assert ids == {str(a1.id), str(a2.id)}

    async with _client(app_with_session) as c:
        r = await c.get(
            "/agreements?state=executed",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert {row["id"] for row in r.json()["items"]} == {str(a2.id)}

    # Expiring-within filter: a2 expires in 30 days, so days=60 includes it,
    # days=10 excludes it.
    async with _client(app_with_session) as c:
        r = await c.get(
            "/agreements?expiring_within_days=60",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert {row["id"] for row in r.json()["items"]} == {str(a2.id)}

    async with _client(app_with_session) as c:
        r = await c.get(
            "/agreements?expiring_within_days=10",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert {row["id"] for row in r.json()["items"]} == set()


# --- Upload / download URL ------------------------------------------------


async def test_upload_url_returns_signed_url_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="sent",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/agreements/{agreement.id}/evidence-upload-url",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={"filename": "signed.pdf", "content_type": "application/pdf"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://")
    assert body["method"] == "PUT"
    assert body["expires_in"] == 300
    assert body["required_headers"]["Content-Type"] == "application/pdf"
    assert body["s3_key"].startswith(f"agreements/{agreement.id}/")

    rows = await _audit_for(session, agreement.id)
    assert any(r.action == "agreement.evidence_upload_url_issued" for r in rows)


async def test_upload_url_rejects_unsupported_content_type(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="sent",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/agreements/{agreement.id}/evidence-upload-url",
            headers={"X-Test-User": "legal@smartek21.com"},
            json={"filename": "signed.png", "content_type": "image/png"},
        )
    assert r.status_code == 422


async def test_download_url_requires_evidence(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="drafting",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/agreements/{agreement.id}/evidence-download-url",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert r.status_code == 404


async def test_download_url_returns_signed_url_and_audits(
    app_with_session, seeded, session, monkeypatch
):
    agreement = Agreement(
        id=uuid.uuid4(),
        legal_entity_id=seeded["entity"].id,
        kind="NDA",
        state="executed",
        expiry=date.today() + timedelta(days=365),
        evidence_s3_key=f"agreements/{uuid.uuid4()}/signed.pdf",
    )
    session.add(agreement)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/agreements/{agreement.id}/evidence-download-url",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith("https://")
    assert body["expires_in"] == 300

    rows = await _audit_for(session, agreement.id)
    assert any(r.action == "agreement.evidence_download_url_issued" for r in rows)
