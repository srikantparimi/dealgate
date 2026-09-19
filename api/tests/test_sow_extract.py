"""Acceptance tests for S3-E5 SOW upload + AI extraction + human confirm.

Covers every Given/When/Then in docs/backlog/s3-e5-sow-upload-extract.md:

- upload → version created status=pending; ``sow.uploaded`` audit fires;
- extract with stub Bedrock → fields populated with page refs;
- extract with disabled Bedrock → status=manual_required (never silent);
- confirm every field then submit → ``sow.confirmed``; opportunity moves
  to ``SOWDraft.confirmed``;
- submit without confirming all → 422 with the specific field list;
- re-upload → new sow_version, old kept for audit;
- file > 25 MB via ``file_size`` hint → 413;
- PATCH by non-owner → 403.

Also asserts the audit chain remains verifiable after every state change.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.integrations.bedrock_sow_extract import (
    EXTRACTED_FIELDS,
    StubBedrock,
    get_bedrock_sow,
)
from app.integrations.s3_sow import StubS3, get_sow_s3
from app.main import app as main_app
from app.models.audit import AuditEvent
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion


OWNER_EMAIL = "owner@smartek21.com"
OTHER_EMAIL = "someone@smartek21.com"
ADMIN_EMAIL = "admin@smartek21.com"


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

    stub_s3 = StubS3()
    stub_bedrock = StubBedrock()

    main_app.dependency_overrides[get_session] = _override
    main_app.dependency_overrides[get_sow_s3] = lambda: stub_s3
    main_app.dependency_overrides[get_bedrock_sow] = lambda: stub_bedrock
    main_app.state.stub_s3 = stub_s3
    main_app.state.stub_bedrock = stub_bedrock
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)
        main_app.dependency_overrides.pop(get_sow_s3, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)
        main_app.state.stub_s3 = None
        main_app.state.stub_bedrock = None


@pytest_asyncio.fixture
async def seeded(session):
    """Seed an opportunity owned by ``owner@smartek21.com``."""

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id="H-SOW-1",
        owner_id=_uid(OWNER_EMAIL),
        governance_status="SOWDraft",
    )
    session.add(opp)
    await session.commit()
    return {"opp": opp}


async def _audit_for_version(session, version_id: uuid.UUID) -> list[AuditEvent]:
    return (
        await session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity == "sow_version",
                AuditEvent.entity_id == str(version_id),
            )
            .order_by(AuditEvent.ts.asc(), AuditEvent.id.asc())
        )
    ).scalars().all()


# --- upload url -----------------------------------------------------------


async def test_upload_url_owner_returns_signed_url(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/{seeded['opp'].id}/upload-url",
            headers={"X-Test-User": OWNER_EMAIL},
            json={"filename": "sample_sow.pdf", "content_type": "application/pdf"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("https://")
    assert body["method"] == "PUT"
    assert body["s3_key"].startswith(f"sow/{seeded['opp'].id}/")
    assert body["max_bytes"] == 25 * 1024 * 1024


async def test_upload_url_non_owner_forbidden(app_with_session, seeded, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/{seeded['opp'].id}/upload-url",
            headers={"X-Test-User": OTHER_EMAIL},
            json={"filename": "sow.pdf", "content_type": "application/pdf"},
        )
    assert r.status_code == 403


async def test_upload_url_rejects_bad_content_type(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/{seeded['opp'].id}/upload-url",
            headers={"X-Test-User": OWNER_EMAIL},
            json={"filename": "sow.png", "content_type": "image/png"},
        )
    assert r.status_code == 422


# --- create version + extract --------------------------------------------


async def _create_version(
    app, opp_id: uuid.UUID, *, actor: str, size: int | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "file_s3_key": f"sow/{opp_id}/test.pdf",
        "file_hash": "sha256:abc",
    }
    if size is not None:
        payload["file_size"] = size
    async with _client(app) as c:
        r = await c.post(
            f"/sow/{opp_id}/versions",
            headers={"X-Test-User": actor},
            json=payload,
        )
    return {"status": r.status_code, "body": r.json() if r.text else None}


async def test_create_version_stub_bedrock_populates_fields(
    app_with_session, seeded, session, monkeypatch
):
    """AC: upload → version created + audit; extract fills every field with
    a page_ref."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    res = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    assert res["status"] == 201, res
    body = res["body"]
    assert body["extract_status"] == "complete"
    assert body["extract_model"] is not None
    assert body["extract_prompt_version"] is not None
    fields = body["extracted_fields"]
    assert isinstance(fields, dict)
    for name in EXTRACTED_FIELDS:
        assert name in fields, f"missing field {name}"
        entry = fields[name]
        assert "page_ref" in entry and isinstance(entry["page_ref"], int)
        assert entry["status"] == "unconfirmed"
    assert body["engagement_type_suggested"] == "fixed_price"
    assert body["download_url"].startswith("https://")

    # Audit chain: sow.uploaded THEN sow.extracted.
    rows = await _audit_for_version(session, uuid.UUID(body["id"]))
    actions = [row.action for row in rows]
    assert actions[0] == "sow.uploaded"
    assert "sow.extracted" in actions
    assert await verify_chain(session) is True


async def test_extract_manual_required_when_bedrock_disabled(
    app_with_session, seeded, session, monkeypatch
):
    """AC: Bedrock unavailable → status=manual_required (never silent)."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    # Flip the stub into unavailable mode.
    main_app.state.stub_bedrock.unavailable = True

    res = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    assert res["status"] == 201, res
    body = res["body"]
    assert body["extract_status"] == "manual_required"
    # No hallucinated values — every field is None / disputed. The
    # ``metadata`` key carries the extract-source tag (S7 story A) and is
    # not a field, so it is skipped.
    for name, entry in body["extracted_fields"].items():
        if name == "metadata":
            continue
        assert entry["value"] is None
        assert entry["status"] == "disputed"
    assert body["engagement_type_suggested"] is None

    rows = await _audit_for_version(session, uuid.UUID(body["id"]))
    assert any(row.action == "sow.extract_failed" for row in rows)
    assert await verify_chain(session) is True


async def test_reupload_creates_new_version_and_keeps_old(
    app_with_session, seeded, session, monkeypatch
):
    """AC: re-upload → new sow_version; previous stays for audit."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    first = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    second = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    assert first["status"] == 201 and second["status"] == 201
    assert first["body"]["id"] != second["body"]["id"]
    # Both rows live under the same ``sow`` parent (one per opportunity).
    assert first["body"]["sow_id"] == second["body"]["sow_id"]

    all_versions = (
        await session.execute(select(SowVersion).order_by(SowVersion.uploaded_at))
    ).scalars().all()
    assert len(all_versions) == 2
    # Only one Sow — the FK unique constraint holds.
    sows = (await session.execute(select(Sow))).scalars().all()
    assert len(sows) == 1


async def test_create_version_over_25mb_returns_413(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    res = await _create_version(
        app_with_session,
        seeded["opp"].id,
        actor=OWNER_EMAIL,
        size=26 * 1024 * 1024,
    )
    assert res["status"] == 413, res


async def test_create_version_non_owner_forbidden(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    res = await _create_version(app_with_session, seeded["opp"].id, actor=OTHER_EMAIL)
    assert res["status"] == 403


# --- get current + version ------------------------------------------------


async def test_get_current_returns_latest_or_null(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/sow/opportunity/{seeded['opp'].id}/current",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert r.status_code == 200
    assert r.json() is None

    await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)

    async with _client(app_with_session) as c:
        r2 = await c.get(
            f"/sow/opportunity/{seeded['opp'].id}/current",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert r2.status_code == 200
    body = r2.json()
    assert body is not None
    assert body["extract_status"] == "complete"


# --- confirm + submit -----------------------------------------------------


async def _confirm_all(app, version_id: uuid.UUID, actor: str) -> dict[str, Any]:
    latest: dict[str, Any] = {}
    async with _client(app) as c:
        for name in EXTRACTED_FIELDS:
            r = await c.patch(
                f"/sow/versions/{version_id}/fields/{name}",
                headers={"X-Test-User": actor},
                json={"value": f"confirmed-{name}"},
            )
            assert r.status_code == 200, (name, r.text)
            latest = r.json()
    return latest


async def test_confirm_field_by_non_owner_forbidden(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    created = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    version_id = created["body"]["id"]

    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/sow/versions/{version_id}/fields/price",
            headers={"X-Test-User": OTHER_EMAIL},
            json={"value": "300000.00"},
        )
    assert r.status_code == 403


async def test_confirm_unknown_field_returns_422(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    created = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    version_id = created["body"]["id"]
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/sow/versions/{version_id}/fields/nonsense",
            headers={"X-Test-User": OWNER_EMAIL},
            json={"value": "x"},
        )
    assert r.status_code == 422


async def test_submit_without_all_confirmed_returns_422_with_missing_list(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    created = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    version_id = created["body"]["id"]

    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/versions/{version_id}/submit",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["missing_fields"]
    # None should have been confirmed yet.
    assert set(detail["missing_fields"]) == set(EXTRACTED_FIELDS)


async def test_confirm_all_then_submit_moves_governance_status(
    app_with_session, seeded, session, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    created = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    version_id_str = created["body"]["id"]
    version_id = uuid.UUID(version_id_str)

    await _confirm_all(app_with_session, version_id, actor=OWNER_EMAIL)

    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/versions/{version_id}/submit",
            headers={"X-Test-User": OWNER_EMAIL},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["confirmed_by"] == str(_uid(OWNER_EMAIL))
    assert body["confirmed_at"] is not None
    assert body["engagement_type_confirmed"] == "confirmed-engagement_type_suggested"

    # Opportunity governance status flipped.
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == seeded["opp"].id)
        )
    ).scalar_one()
    assert opp.governance_status == "SOWDraft.confirmed"

    rows = await _audit_for_version(session, version_id)
    actions = [row.action for row in rows]
    assert actions[0] == "sow.uploaded"
    assert actions.count("sow.field_confirmed") == len(EXTRACTED_FIELDS)
    assert actions[-1] == "sow.confirmed"
    assert await verify_chain(session) is True


# --- read role gating -----------------------------------------------------


async def test_get_version_read_requires_governance_role(
    app_with_session, seeded, monkeypatch
):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    created = await _create_version(app_with_session, seeded["opp"].id, actor=OWNER_EMAIL)
    version_id = created["body"]["id"]

    # A user with no group at all should be 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/sow/versions/{version_id}",
            headers={"X-Test-User": "guest@smartek21.com"},
        )
    assert r.status_code == 403

    # Finance can read.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r2 = await c.get(
            f"/sow/versions/{version_id}",
            headers={"X-Test-User": "fin@smartek21.com"},
        )
    assert r2.status_code == 200


# --- systemadmin path -----------------------------------------------------


async def test_systemadmin_can_upload_and_submit(
    app_with_session, seeded, session, monkeypatch
):
    """Story: upload allowed for account owner *or* SystemAdmin."""

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    res = await _create_version(app_with_session, seeded["opp"].id, actor=ADMIN_EMAIL)
    assert res["status"] == 201
    version_id = uuid.UUID(res["body"]["id"])

    await _confirm_all(app_with_session, version_id, actor=ADMIN_EMAIL)
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/sow/versions/{version_id}/submit",
            headers={"X-Test-User": ADMIN_EMAIL},
        )
    assert r.status_code == 200
