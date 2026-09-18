"""S4 E7 acceptance tests — CEO exception brief + approve/reject/return.

Covers the full vertical for Agent V's slice:

- brief is drafted with the deterministic inputs; rationale left null;
- rationale is owner-only (403 for anyone else);
- approve without a rationale returns 422;
- approve moves the package to ``ready_to_sign`` and audits;
- reject moves the package to ``rejected`` + governance back to
  ``SOWDraft``; account owner receives a notification row;
- non-CEO callers get 403;
- an active CEO delegate can decide; an expired delegate cannot.

Every test drives the HTTP surface through :mod:`httpx` so the router
+ auth wiring is exercised end-to-end, and asserts on the DB directly
so the audit chain + status transitions are visible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.db import get_session
from app.main import app as main_app
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.ceo_exception import CeoDelegate, CeoException
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.user import User


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.delenv("DEALGATE_TEST_GROUPS", raising=False)


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def _fake_user_id(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")


@pytest_asyncio.fixture
async def app_with_session(session):
    async def _override():
        yield session

    main_app.dependency_overrides[get_session] = _override
    try:
        yield main_app
    finally:
        main_app.dependency_overrides.pop(get_session, None)


# --- fixtures ---------------------------------------------------------------


OWNER_EMAIL = "owner@smartek21.com"
CEO_EMAIL = "ceo@smartek21.com"
FINANCE_EMAIL = "fin@smartek21.com"
DELEGATE_EMAIL = "dele@smartek21.com"
ADMIN_EMAIL = "admin@smartek21.com"


async def _seed_owner(session) -> User:
    owner = User(
        id=_fake_user_id(OWNER_EMAIL),
        email=OWNER_EMAIL,
        name="Owner",
        groups=["Sales"],
    )
    session.add(owner)
    await session.flush()
    return owner


async def _seed_package(session, *, owner_id: uuid.UUID) -> ApprovalPackage:
    """Fabricate a package in ``pending_ceo_exception``.

    We don't run Agent U's submission path here (that's their vertical);
    we just plant a row with plausible FK targets so the CEO surface has
    something to work on. The opportunity + SOW / GM parents are the
    minimum required to satisfy the FKs.
    """

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"deal-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        governance_status="Approvals",
    )
    session.add(opp)
    await session.flush()

    # Ephemeral SOW + gm_model rows so the FK constraints hold. The CEO
    # service never dereferences them beyond the package.status check.
    from app.models.gm_model import GmModel
    from app.models.sow import Sow, SowVersion

    sow_row = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow_row)
    await session.flush()
    sow_v = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow_row.id,
        file_s3_key="s3://test/sow.pdf",
        file_hash="deadbeef",
        extract_status="complete",
    )
    session.add(sow_v)

    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        engagement_type="staff_aug",
        currency="USD",
        revenue_us=Decimal("100000"),
        revenue_india=Decimal("50000"),
    )
    session.add(gm)
    await session.flush()

    pkg = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=sow_v.id,
        gm_model_id=gm.id,
        package_hash="0" * 64,
        status="pending_ceo_exception",
        submitted_by=owner_id,
    )
    session.add(pkg)
    await session.flush()
    await session.commit()
    return pkg


def _brief_inputs() -> dict:
    return {
        "client_name": "Acme Widgets",
        "client_context": "Global manufacturer, existing NDA + MSA.",
        "scope": "Replace bespoke quoting tool.",
        "team_summary": "2 US, 4 India, 12 weeks.",
        "revenue": {"us": Decimal("100000"), "india": Decimal("50000"), "blended": Decimal("150000")},
        "cost": {"us": Decimal("70000"), "india": Decimal("20000"), "blended": Decimal("90000")},
        "gm": {
            "us": {"value": Decimal("0.30"), "floor": Decimal("0.35"), "passes": False},
            "india": {"value": Decimal("0.60"), "floor": Decimal("0.50"), "passes": True},
            "blended": {"value": Decimal("0.40")},
        },
        "price_uplift": {"us": Decimal("5000"), "india": Decimal("0")},
        "gross_profit_shortfall_usd": Decimal("5000"),
        "alternatives": ["Reduce US hours by 20%", "Shift PM to India"],
        "finance_recommendation": "Approve with tighter conditions.",
        "delivery_recommendation": "Delivery neutral; team is stable.",
    }


# --- draft ------------------------------------------------------------------


async def test_draft_for_package_populates_brief_rationale_null(
    app_with_session, session
):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)

    row = await draft_for_package(
        session, pkg.id, brief_inputs=_brief_inputs()
    )
    assert row.rationale_text is None
    assert row.decision is None
    brief = row.brief_json
    # Numbers pass through the stub verbatim (as Decimal-strings).
    assert brief["client"]["name"] == "Acme Widgets"
    assert brief["revenue"]["us"] == "100000"
    assert brief["gm"]["us"]["passes"] is False
    assert brief["rationale"] is None
    assert brief["prompt_version"]

    audits = list(
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ceo_exception.drafted"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


async def test_draft_is_idempotent(app_with_session, session):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)

    first = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    second = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    assert first.id == second.id


# --- rationale --------------------------------------------------------------


async def test_set_rationale_owner_only(app_with_session, session, monkeypatch):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    # A non-owner Sales rep cannot write the rationale — 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/ceo-exceptions/{exc.id}/rationale",
            headers={"X-Test-User": "other@smartek21.com"},
            json={"rationale_text": "Because we need to close the year."},
        )
    assert r.status_code == 403, r.text

    # Owner succeeds.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.patch(
            f"/ceo-exceptions/{exc.id}/rationale",
            headers={"X-Test-User": OWNER_EMAIL},
            json={"rationale_text": "Because it closes the FY.", "tidy": True},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rationale_text"] == "Because it closes the FY."
    # Stub tidy is a whitespace passthrough — same string.
    assert body["rationale_tidied_text"] == "Because it closes the FY."


# --- decision ---------------------------------------------------------------


async def test_approve_requires_rationale(app_with_session, session, monkeypatch):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": CEO_EMAIL},
            json={"decision": "approve"},
        )
    assert r.status_code == 422, r.text
    assert "rationale" in r.json()["detail"]


async def test_approve_transitions_package_to_ready_to_sign(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import draft_for_package, set_rationale

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    await set_rationale(
        session,
        actor_id=owner.id,
        exception_id=exc.id,
        rationale_text="Strategic customer worth the exception.",
    )

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": CEO_EMAIL},
            json={
                "decision": "approve",
                "conditions_text": "Quarterly steering committee.",
                "valid_until": "2027-01-01",
            },
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["decision"] == "approve"
    assert body["conditions_text"] == "Quarterly steering committee."
    assert body["valid_until"] == "2027-01-01"

    # Package status flipped in the same transaction.
    refreshed_pkg = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == pkg.id)
        )
    ).scalar_one()
    assert refreshed_pkg.status == "ready_to_sign"
    assert refreshed_pkg.released_at is not None

    audits = list(
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ceo_exception.approved"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].after["package_status"] == "ready_to_sign"


async def test_reject_sends_owner_notification_and_reverts_status(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": CEO_EMAIL},
            json={"decision": "reject"},
        )
    assert r.status_code == 201, r.text

    refreshed_pkg = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == pkg.id)
        )
    ).scalar_one()
    assert refreshed_pkg.status == "rejected"
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == refreshed_pkg.opportunity_id)
        )
    ).scalar_one()
    assert opp.governance_status == "SOWDraft"

    # Owner got a notification row queued.
    notes = list(
        (
            await session.execute(
                select(Notification).where(Notification.user_id == owner.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) >= 1
    assert notes[0].related_entity == "approval_package"


async def test_return_for_changes_reverts_and_audits(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": CEO_EMAIL},
            json={"decision": "return_for_changes"},
        )
    assert r.status_code == 201, r.text

    audits = list(
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ceo_exception.returned"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


async def test_non_ceo_cannot_decide(app_with_session, session, monkeypatch):
    from app.services.ceo_exception import draft_for_package, set_rationale

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    await set_rationale(
        session, actor_id=owner.id, exception_id=exc.id,
        rationale_text="Compelling case.",
    )

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": FINANCE_EMAIL},
            json={"decision": "approve"},
        )
    assert r.status_code == 403, r.text


# --- delegate --------------------------------------------------------------


async def test_active_delegate_can_decide(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import (
        draft_for_package,
        grant_delegate,
        set_rationale,
    )

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    await set_rationale(
        session, actor_id=owner.id, exception_id=exc.id,
        rationale_text="Strategic bet.",
    )

    admin = User(
        id=_fake_user_id(ADMIN_EMAIL),
        email=ADMIN_EMAIL,
        name="Admin",
        groups=["SystemAdmin"],
    )
    session.add(admin)
    delegate = User(
        id=_fake_user_id(DELEGATE_EMAIL),
        email=DELEGATE_EMAIL,
        name="Delegate",
        groups=["Sales"],  # NB: not CEO, only the delegate row grants power.
    )
    session.add(delegate)
    await session.flush()

    today = datetime.now(UTC).date()
    await grant_delegate(
        session,
        actor_id=admin.id,
        delegate_id=delegate.id,
        effective_from=today - timedelta(days=1),
        expiry=today + timedelta(days=30),
    )

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": DELEGATE_EMAIL},
            json={"decision": "approve"},
        )
    assert r.status_code == 201, r.text
    refreshed_pkg = (
        await session.execute(
            select(ApprovalPackage).where(ApprovalPackage.id == pkg.id)
        )
    ).scalar_one()
    assert refreshed_pkg.status == "ready_to_sign"


async def test_expired_delegate_cannot_decide(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import draft_for_package, set_rationale

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())
    await set_rationale(
        session, actor_id=owner.id, exception_id=exc.id,
        rationale_text="Strategic bet.",
    )

    admin = User(
        id=_fake_user_id(ADMIN_EMAIL),
        email=ADMIN_EMAIL,
        name="Admin",
        groups=["SystemAdmin"],
    )
    delegate = User(
        id=_fake_user_id(DELEGATE_EMAIL),
        email=DELEGATE_EMAIL,
        name="Delegate",
        groups=["Sales"],
    )
    session.add(admin)
    session.add(delegate)
    await session.flush()

    # Grant a window that expired last month.
    today = datetime.now(UTC).date()
    old = CeoDelegate(
        id=uuid.uuid4(),
        delegate_id=delegate.id,
        effective_from=today - timedelta(days=90),
        expiry=today - timedelta(days=30),
        granted_by=admin.id,
    )
    session.add(old)
    await session.commit()

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/ceo-exceptions/{exc.id}/decisions",
            headers={"X-Test-User": DELEGATE_EMAIL},
            json={"decision": "approve"},
        )
    assert r.status_code == 403, r.text


# --- read + list ------------------------------------------------------------


async def test_read_brief_visible_to_governance_roles(
    app_with_session, session, monkeypatch
):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    exc = await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    async with _client(app_with_session) as c:
        r = await c.get(
            f"/ceo-exceptions/{exc.id}",
            headers={"X-Test-User": "legal@smartek21.com"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["brief_json"]["client"]["name"] == "Acme Widgets"


async def test_list_inbox_ceo_only(app_with_session, session, monkeypatch):
    from app.services.ceo_exception import draft_for_package

    owner = await _seed_owner(session)
    pkg = await _seed_package(session, owner_id=owner.id)
    await draft_for_package(session, pkg.id, brief_inputs=_brief_inputs())

    # CEO sees the inbox.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/ceo-exceptions?status=pending",
            headers={"X-Test-User": CEO_EMAIL},
        )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1

    # A pure Sales rep does not.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/ceo-exceptions?status=pending",
            headers={"X-Test-User": "sales@smartek21.com"},
        )
    assert r.status_code == 403


async def test_grant_delegate_admin_only(app_with_session, session, monkeypatch):
    admin = User(
        id=_fake_user_id(ADMIN_EMAIL),
        email=ADMIN_EMAIL,
        name="Admin",
        groups=["SystemAdmin"],
    )
    delegate = User(
        id=_fake_user_id(DELEGATE_EMAIL),
        email=DELEGATE_EMAIL,
        name="Delegate",
        groups=["Sales"],
    )
    session.add(admin)
    session.add(delegate)
    await session.commit()

    today = date.today()
    body = {
        "delegate_id": str(delegate.id),
        "effective_from": today.isoformat(),
        "expiry": (today + timedelta(days=14)).isoformat(),
    }

    # Non-admin -> 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "CEO")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/ceo-delegates",
            headers={"X-Test-User": CEO_EMAIL},
            json=body,
        )
    assert r.status_code == 403

    # Admin -> 201 + audit.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "SystemAdmin")
    async with _client(app_with_session) as c:
        r = await c.post(
            "/admin/ceo-delegates",
            headers={"X-Test-User": ADMIN_EMAIL},
            json=body,
        )
    assert r.status_code == 201, r.text

    audits = list(
        (
            await session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "ceo_delegate.granted"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
