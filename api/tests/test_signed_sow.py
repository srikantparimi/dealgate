"""S5 E8 — signed SOW verify + diff + distribution.

Every Given/When/Then from ``docs/backlog/s5-signed-sow-distribution.md``,
one test per case. Round-trips through the FastAPI router where a
permission gate needs exercising; talks to the service directly for
happy-path state transitions.

Rule 4 (CLAUDE.md): ``signed_sow_upload`` rows are immutable versions.
Rule 5: every transition writes an ``audit_event`` in the same
transaction. Rule 2: price comparisons use :class:`Decimal`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.audit import verify_chain
from app.db import get_session
from app.integrations.bedrock_sow_extract import (
    EXTRACTED_FIELDS,
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
    get_bedrock_sow,
)
from app.integrations.ses import StubSES, get_ses_client
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.signed_sow import SignedSowUpload
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.signed_sow import (
    SignedSowError,
    create_upload,
    release,
    verify,
)


# ---- fixtures ------------------------------------------------------------


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _uid(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


def _client(app):
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


async def _seed_user(session, email: str, groups: list[str]) -> User:
    u = User(id=_uid(email), email=email, name=email.split("@")[0], groups=groups)
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


# ---- helpers -------------------------------------------------------------


APPROVED_PRICE = "250000.00"
APPROVED_TERM_START = "2026-10-01"
APPROVED_TERM_END = "2027-03-31"
APPROVED_SCOPE = "Modernise loan-origination platform onto AWS."


def _approved_fields() -> dict:
    """The pinned ``sow_version.extracted_fields`` block for the tests."""

    fields: dict = {}
    for name in EXTRACTED_FIELDS:
        fields[name] = {"value": None, "page_ref": 1, "status": "confirmed"}
    fields["price"]["value"] = APPROVED_PRICE
    fields["term_start"]["value"] = APPROVED_TERM_START
    fields["term_end"]["value"] = APPROVED_TERM_END
    fields["scope_summary"]["value"] = APPROVED_SCOPE
    return fields


class _CannedBedrock(BedrockSowExtract):
    """Bedrock stub tests parametrise per case.

    Not backed by :class:`app.integrations.bedrock_sow_extract.StubBedrock`
    directly because that stub always returns the same canned fields;
    here we need to vary price / scope per test.
    """

    def __init__(self, overrides: dict[str, object] | None = None) -> None:
        self.overrides = overrides or {}
        self.calls: list[int] = []

    def extract(self, file_bytes: bytes) -> ExtractedFields | ManualRequired:
        self.calls.append(len(file_bytes))
        fields: dict[str, dict[str, object]] = {}
        for name in EXTRACTED_FIELDS:
            fields[name] = {
                "value": self.overrides.get(name),
                "page_ref": 1,
                "status": "unconfirmed",
            }
        # Populate the four material fields with the "matching" defaults
        # so a test only has to override the fields it wants to mutate.
        for name, default in (
            ("price", APPROVED_PRICE),
            ("term_start", APPROVED_TERM_START),
            ("term_end", APPROVED_TERM_END),
            ("scope_summary", APPROVED_SCOPE),
        ):
            if name not in self.overrides:
                fields[name]["value"] = default
        return ExtractedFields(fields=fields)


async def _seed_ready_to_sign_package(
    session,
    *,
    owner: User,
) -> tuple[ApprovalPackage, Opportunity, SowVersion]:
    """Build a package that's already sitting in ``ready_to_sign``.

    Skips the full approval flow — we go straight to the state the
    signed-SOW story starts from. The GM model is not needed because
    :func:`app.services.signed_sow.release` only reads the pinned
    ``sow_version.extracted_fields``.
    """

    # A minimal gm_model row so the FK holds — the numbers are ignored.
    from app.models.gm_model import GmModel
    from tests.test_coverage_gate import _seed_client_with_agreements
    client, _ = await _seed_client_with_agreements(session, kinds_executed=("NDA", "MSA"))

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-SS-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client.id,
        governance_status="SOWDraft.confirmed",
    )
    session.add(opp)
    await session.flush()

    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="deadbeef" * 8,
        extract_status="complete",
        extracted_fields=_approved_fields(),
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(version)

    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        engagement_type="fixed_price",
        delivery_pattern="us_only",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        revenue_us=Decimal(APPROVED_PRICE),
        revenue_india=Decimal("0"),
        created_by=owner.id,
    )
    session.add(gm)
    await session.flush()

    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        gm_model_id=gm.id,
        package_hash="a" * 64,
        status="ready_to_sign",
        submitted_by=owner.id,
        released_at=None,
    )
    session.add(package)
    await session.commit()
    await session.refresh(package)
    await session.refresh(opp)
    await session.refresh(version)
    return package, opp, version


async def _count_audits(session, action: str) -> int:
    rows = (
        await session.execute(select(AuditEvent).where(AuditEvent.action == action))
    ).scalars().all()
    return len(list(rows))


# ---- verify --------------------------------------------------------------


async def test_verify_passes_on_exact_terms(session):
    owner = await _seed_user(session, "owner@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/exact.pdf",
        file_hash="sha256:exact",
    )

    bedrock = _CannedBedrock()
    result = await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=bedrock
    )

    assert result.verify_status == "verified"
    assert result.verified_at is not None
    diff = result.diff_json
    assert diff["match"] is True
    assert {f["field"] for f in diff["fields"]} == {
        "price",
        "term_start",
        "term_end",
        "scope_summary",
    }
    assert all(f["match"] for f in diff["fields"])
    assert await _count_audits(session, "signed_sow.verified") == 1
    assert await _count_audits(session, "signed_sow.blocked") == 0
    assert await verify_chain(session) is True


async def test_verify_blocks_on_price_mismatch(session):
    owner = await _seed_user(session, "owner2@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/bad-price.pdf",
        file_hash="sha256:badprice",
    )

    bedrock = _CannedBedrock(overrides={"price": "999999.00"})
    result = await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=bedrock
    )

    assert result.verify_status == "blocked"
    assert result.verified_at is None
    fields_by_name = {f["field"]: f for f in result.diff_json["fields"]}
    assert fields_by_name["price"]["match"] is False
    assert fields_by_name["price"]["extracted"] == "999999.00"
    assert fields_by_name["price"]["approved"] == APPROVED_PRICE
    # Dates + scope still match.
    assert fields_by_name["term_start"]["match"] is True
    assert fields_by_name["scope_summary"]["match"] is True
    assert await _count_audits(session, "signed_sow.blocked") == 1


async def test_verify_blocks_on_scope_similarity_below_threshold(session):
    owner = await _seed_user(session, "owner3@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/bad-scope.pdf",
        file_hash="sha256:badscope",
    )

    bedrock = _CannedBedrock(
        overrides={"scope_summary": "Completely different scope of work."}
    )
    result = await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=bedrock
    )
    assert result.verify_status == "blocked"
    scope = next(f for f in result.diff_json["fields"] if f["field"] == "scope_summary")
    assert scope["match"] is False
    assert scope["similarity"] < 0.9


# ---- release -------------------------------------------------------------


async def test_release_requires_verified(session):
    owner = await _seed_user(session, "owner4@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/pending.pdf",
        file_hash="sha256:pending",
    )
    # Not verified yet.
    ses = StubSES()
    with pytest.raises(SignedSowError) as exc:
        await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    assert exc.value.status_code == 409
    assert ses.sent == []


async def test_release_distributes_and_opens_renewal(session):
    owner = await _seed_user(session, "owner5@smartek21.com", ["Sales"])
    await _seed_user(session, "delivery@smartek21.com", ["Delivery"])
    await _seed_user(session, "finance@smartek21.com", ["Finance"])
    await _seed_user(session, "legal@smartek21.com", ["Legal"])
    package, opp, pinned = await _seed_ready_to_sign_package(session, owner=owner)

    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/ok.pdf",
        file_hash="sha256:ok",
    )
    await verify(
        session,
        actor_id=owner.id,
        upload_id=upload.id,
        bedrock=_CannedBedrock(),
    )

    ses = StubSES()
    released = await release(
        session, actor_id=owner.id, upload_id=upload.id, ses=ses
    )
    assert released.verify_status == "verified"
    assert released.released_at is not None

    # Distribution — one email per recipient (owner + one per group).
    recipients = {msg["to"] for msg in ses.sent}
    assert "owner5@smartek21.com" in recipients
    assert "delivery@smartek21.com" in recipients
    assert "finance@smartek21.com" in recipients
    assert "legal@smartek21.com" in recipients

    # Kickoff + billing_setup tasks on the owner.
    tasks = list(
        (
            await session.execute(
                select(Task).where(Task.owner_id == owner.id)
            )
        )
        .scalars()
        .all()
    )
    categories = {t.category for t in tasks}
    assert "kickoff" in categories
    assert "billing_setup" in categories

    # Renewal row opened with trigger_date = term_end - 60d.
    renewals = list(
        (
            await session.execute(
                select(Renewal).where(Renewal.opportunity_id == opp.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(renewals) == 1
    r = renewals[0]
    assert r.status == "open"
    assert r.term_end == date.fromisoformat(APPROVED_TERM_END)
    assert r.trigger_date == r.term_end - timedelta(days=60)

    # Package moved to released; audit + chain intact.
    fresh_package = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == package.id)
        )
    ).scalar_one()
    assert fresh_package.status == "released"
    assert await _count_audits(session, "package.released") == 1
    assert await _count_audits(session, "signed_sow.released") == 1
    assert await _count_audits(session, "renewal.opened") == 1
    assert await verify_chain(session) is True


async def test_release_guards_when_configured_recipients_missing(session):
    """No Delivery/Finance/Legal users seeded → owner still gets the email."""

    owner = await _seed_user(session, "owner-solo@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/solo.pdf",
        file_hash="sha256:solo",
    )
    await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock()
    )

    ses = StubSES()
    await release(session, actor_id=owner.id, upload_id=upload.id, ses=ses)
    recipients = {msg["to"] for msg in ses.sent}
    assert recipients == {"owner-solo@smartek21.com"}


# ---- re-upload voids previous verification -----------------------------


async def test_reupload_creates_new_row_and_audits_replaced(session):
    owner = await _seed_user(session, "owner6@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    first = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/first.pdf",
        file_hash="sha256:first",
    )
    await verify(
        session, actor_id=owner.id, upload_id=first.id, bedrock=_CannedBedrock()
    )
    assert first.verify_status == "verified"

    second = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/second.pdf",
        file_hash="sha256:second",
    )
    assert second.id != first.id
    assert second.verify_status == "pending"
    assert await _count_audits(session, "signed_sow.replaced") == 1

    # Two rows exist; the older one is still verified but replaced.
    rows = list(
        (
            await session.execute(
                select(SignedSowUpload)
                .where(SignedSowUpload.package_id == package.id)
                .order_by(SignedSowUpload.uploaded_at.asc())
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    assert rows[0].verify_status == "verified"
    assert rows[1].verify_status == "pending"


# ---- HTTP / permissions --------------------------------------------------


async def test_http_upload_requires_owner_or_admin(app_with_session, session):
    owner = await _seed_user(session, "http-owner@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    # A random Sales user is not the owner → 403.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/signed-sow/{package.id}",
            headers={"X-Test-User": "someone-else@smartek21.com"},
            json={"file_s3_key": "sow/x.pdf", "file_hash": "sha256:x"},
        )
        assert r.status_code == 403

    # Owner succeeds.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/signed-sow/{package.id}",
            headers={"X-Test-User": "http-owner@smartek21.com"},
            json={"file_s3_key": "sow/y.pdf", "file_hash": "sha256:y"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["verify_status"] == "pending"


async def test_http_verify_and_release_end_to_end(app_with_session, session):
    owner = await _seed_user(session, "http-owner2@smartek21.com", ["Sales"])
    await _seed_user(session, "delivery-h@smartek21.com", ["Delivery"])
    await _seed_user(session, "finance-h@smartek21.com", ["Finance"])
    await _seed_user(session, "legal-h@smartek21.com", ["Legal"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    ses_stub = StubSES()
    bedrock_stub = _CannedBedrock()
    main_app.dependency_overrides[get_ses_client] = lambda: ses_stub
    main_app.dependency_overrides[get_bedrock_sow] = lambda: bedrock_stub
    try:
        async with _client(app_with_session) as c:
            r = await c.post(
                f"/signed-sow/{package.id}",
                headers={"X-Test-User": "http-owner2@smartek21.com"},
                json={"file_s3_key": "sow/http.pdf", "file_hash": "sha256:http"},
            )
            assert r.status_code == 201, r.text

            r = await c.post(
                f"/signed-sow/{package.id}/verify",
                headers={"X-Test-User": "http-owner2@smartek21.com"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["verify_status"] == "verified"

            r = await c.post(
                f"/signed-sow/{package.id}/release",
                headers={"X-Test-User": "http-owner2@smartek21.com"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["released_at"] is not None
    finally:
        main_app.dependency_overrides.pop(get_ses_client, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)

    assert len(ses_stub.sent) >= 4
    # Verify notifications for task_assigned were queued.
    notes = list(
        (
            await session.execute(
                select(Notification).where(
                    Notification.category == "task_assigned"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) >= 2  # kickoff + billing_setup fan-out (per channel)


async def test_http_get_requires_governance_role(app_with_session, session, monkeypatch):
    owner = await _seed_user(session, "http-owner3@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)

    # Reader with no governance role → 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/signed-sow/{package.id}",
            headers={"X-Test-User": "randomer@smartek21.com"},
        )
        assert r.status_code == 403

    # Governance reader gets 200 + null (no upload yet).
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/signed-sow/{package.id}",
            headers={"X-Test-User": "finance-r@smartek21.com"},
        )
        assert r.status_code == 200
        assert r.json() is None
