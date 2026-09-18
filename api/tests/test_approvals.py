"""S4 E7 — approval packages: sequential + parallel review + change-voids.

Every Given/When/Then from ``docs/backlog/s4-e7-approval-packages.md``, one
test per case. Tests round-trip through the FastAPI router where possible
so role gates + audit + notification wiring are exercised end-to-end.

No math in this file (CLAUDE.md rule 2): the floor pass/fail case leans
on the pure GM library exactly like the delivery-model tests do.
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
from app.models.approval import Approval, ApprovalPackage
from app.models.audit import AuditEvent
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.approvals import (
    ApprovalError,
    decide,
    package_hash,
    submit_package,
    void_on_change,
)
from app.services.delivery_model import (
    CostLinePayload,
    GmModelPayload,
    ResourceLinePayload,
    create_gm_model_version,
)


# ---- fixtures / helpers --------------------------------------------------


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


async def _seed_owner(session, email: str = "owner@smartek21.com") -> User:
    return await _seed_user(session, email, ["Sales"])


async def _seed_opp_with_sow(
    session, owner: User, *, legacy: bool = False, confirmed: bool = True
) -> tuple[Opportunity, SowVersion]:
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-AP-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        governance_status="SOWDraft.confirmed" if confirmed else "SOWDraft",
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
        extracted_fields={
            "scope_summary": {"value": "Build a thing", "page_ref": 1, "status": "confirmed"},
            "price": {"value": "145000", "page_ref": 1, "status": "confirmed"},
        },
        confirmed_by=owner.id if confirmed else None,
        confirmed_at=datetime.now(UTC) if confirmed else None,
    )
    if legacy:
        version.legacy = True  # type: ignore[attr-defined]
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return opp, version


def _passing_payload(sow_version_id: uuid.UUID) -> GmModelPayload:
    """US 50% + India 60% margin — comfortably above the 35% / 50% floors.

    Uses the ``tm`` template so validation only needs ``hourly_cost`` per
    resource — the sheet reads as ``complete`` and ``requires_ceo`` is
    False iff every component passes.
    """

    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    return GmModelPayload(
        engagement_type="tm",
        sow_version_id=sow_version_id,
        delivery_pattern="hybrid",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        resource_lines=[
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="US",
                person_name="Alice",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("1000"),
                hourly_bill_rate=Decimal("200"),
                hourly_cost=Decimal("100"),
                validated_by=uuid.uuid4(),
            ),
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="India",
                person_name="Bob",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("800"),
                hourly_bill_rate=Decimal("100"),
                hourly_cost=Decimal("40"),
                validated_by=uuid.uuid4(),
            ),
        ],
        cost_lines=[],
    )


def _failing_payload(sow_version_id: uuid.UUID) -> GmModelPayload:
    """US 10% margin — well under the 35% floor → CEO exception route."""

    start = date(2026, 3, 1)
    end = date(2026, 8, 31)
    return GmModelPayload(
        engagement_type="tm",
        sow_version_id=sow_version_id,
        delivery_pattern="us_only",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        resource_lines=[
            ResourceLinePayload(
                role="Engineer",
                seniority="senior",
                location="US",
                person_name="Alice",
                allocation_pct=Decimal("1"),
                start_date=start,
                end_date=end,
                hours_billable=Decimal("1000"),
                hourly_bill_rate=Decimal("100"),
                hourly_cost=Decimal("90"),
                validated_by=uuid.uuid4(),
            ),
        ],
        cost_lines=[],
    )


async def _seed_full_deal(
    session,
    *,
    passing: bool = True,
    owner_email: str = "owner@smartek21.com",
) -> tuple[Opportunity, SowVersion, User]:
    owner = await _seed_owner(session, owner_email)
    opp, version = await _seed_opp_with_sow(session, owner)
    payload = _passing_payload(version.id) if passing else _failing_payload(version.id)
    await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=payload,
    )
    return opp, version, owner


async def _count_audits(session, action: str) -> int:
    rows = (
        await session.execute(select(AuditEvent).where(AuditEvent.action == action))
    ).scalars().all()
    return len(list(rows))


# ---- Given/When/Then ----------------------------------------------------


async def test_submit_creates_pending_delivery_hr_with_audit(session):
    opp, _version, owner = await _seed_full_deal(session)

    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)

    assert pkg.status == "pending_delivery_hr"
    assert pkg.package_hash and len(pkg.package_hash) == 64
    assert pkg.submitted_by == owner.id
    assert await _count_audits(session, "package.submitted") == 1


async def test_delivery_then_hr_advances_to_finance_legal(session):
    opp, _v, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)

    delivery = await _seed_user(session, "d@smartek21.com", ["Delivery"])
    hr = await _seed_user(session, "h@smartek21.com", ["HR"])

    after_delivery = await decide(
        session,
        actor_id=delivery.id,
        package_id=pkg.id,
        function="delivery",
        decision="approve",
    )
    assert after_delivery.status == "pending_delivery_hr"

    after_hr = await decide(
        session,
        actor_id=hr.id,
        package_id=pkg.id,
        function="hr",
        decision="approve",
    )
    assert after_hr.status == "pending_finance_legal"
    assert await _count_audits(session, "approval.delivery.approve") == 1
    assert await _count_audits(session, "approval.hr.approve") == 1
    assert await _count_audits(session, "package.delivery_hr_passed") == 1


async def test_finance_then_legal_moves_to_ready_to_sign_when_floors_pass(session):
    opp, _v, owner = await _seed_full_deal(session, passing=True)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    d = await _seed_user(session, "d@smartek21.com", ["Delivery"])
    h = await _seed_user(session, "h@smartek21.com", ["HR"])
    f = await _seed_user(session, "f@smartek21.com", ["Finance"])
    lg = await _seed_user(session, "l@smartek21.com", ["Legal"])
    await decide(session, actor_id=d.id, package_id=pkg.id, function="delivery", decision="approve")
    await decide(session, actor_id=h.id, package_id=pkg.id, function="hr", decision="approve")

    still_pending = await decide(
        session, actor_id=f.id, package_id=pkg.id, function="finance", decision="approve"
    )
    assert still_pending.status == "pending_finance_legal"

    final = await decide(
        session, actor_id=lg.id, package_id=pkg.id, function="legal", decision="approve"
    )
    assert final.status == "ready_to_sign"
    assert final.released_at is not None
    assert await _count_audits(session, "package.ready_to_sign") == 1


async def test_below_floor_model_routes_to_ceo_exception(session):
    opp, _v, owner = await _seed_full_deal(session, passing=False)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    d = await _seed_user(session, "d@smartek21.com", ["Delivery"])
    h = await _seed_user(session, "h@smartek21.com", ["HR"])
    f = await _seed_user(session, "f@smartek21.com", ["Finance"])
    lg = await _seed_user(session, "l@smartek21.com", ["Legal"])
    await decide(session, actor_id=d.id, package_id=pkg.id, function="delivery", decision="approve")
    await decide(session, actor_id=h.id, package_id=pkg.id, function="hr", decision="approve")
    await decide(session, actor_id=f.id, package_id=pkg.id, function="finance", decision="approve")
    final = await decide(
        session, actor_id=lg.id, package_id=pkg.id, function="legal", decision="approve"
    )
    assert final.status == "pending_ceo_exception"
    assert await _count_audits(session, "package.escalated_to_ceo") == 1


async def test_new_sow_version_voids_active_package(session):
    opp, _v, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert pkg.status == "pending_delivery_hr"

    # Creating a fresh sow_version through the service fires the hook.
    from app.services.sow_extract import create_sow_version

    new_version = await create_sow_version(
        session,
        opportunity_id=opp.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{uuid.uuid4()}.pdf",
        file_hash="cafef00d" * 8,
    )
    await session.commit()

    fresh = (
        await session.execute(select(ApprovalPackage).where(ApprovalPackage.id == pkg.id))
    ).scalar_one()
    assert fresh.status == "voided"
    assert fresh.voided_reason and str(new_version.id) in fresh.voided_reason
    assert await _count_audits(session, "package.voided") == 1

    # Submitter got notified.
    notes = (
        await session.execute(
            select(Notification).where(Notification.related_entity_id == str(pkg.id))
        )
    ).scalars().all()
    assert len(list(notes)) >= 1


async def test_new_gm_model_voids_active_package(session):
    opp, version, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert pkg.status == "pending_delivery_hr"

    # A fresh gm_model version triggers the hook.
    await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=_passing_payload(version.id),
    )

    fresh = (
        await session.execute(select(ApprovalPackage).where(ApprovalPackage.id == pkg.id))
    ).scalar_one()
    assert fresh.status == "voided"
    assert fresh.voided_reason and "gm_model" in fresh.voided_reason


async def test_submitter_cannot_approve_own_package(session):
    opp, _v, owner = await _seed_full_deal(session)
    # Owner also happens to hold the Delivery role — should still 403.
    owner.groups = ["Sales", "Delivery"]
    await session.commit()
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    with pytest.raises(ApprovalError) as exc:
        await decide(
            session,
            actor_id=owner.id,
            package_id=pkg.id,
            function="delivery",
            decision="approve",
        )
    assert exc.value.status_code == 403
    assert "separation of duties" in exc.value.detail


async def test_duplicate_approval_for_same_function_conflicts(session):
    opp, _v, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    d1 = await _seed_user(session, "d1@smartek21.com", ["Delivery"])
    d2 = await _seed_user(session, "d2@smartek21.com", ["Delivery"])
    await decide(session, actor_id=d1.id, package_id=pkg.id, function="delivery", decision="approve")
    with pytest.raises(ApprovalError) as exc:
        await decide(
            session, actor_id=d2.id, package_id=pkg.id, function="delivery", decision="approve"
        )
    assert exc.value.status_code == 409


async def test_dual_role_user_can_approve_only_one_function_per_package(session):
    opp, _v, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    both = await _seed_user(session, "both@smartek21.com", ["Finance", "Delivery", "HR"])
    await decide(
        session, actor_id=both.id, package_id=pkg.id, function="delivery", decision="approve"
    )
    with pytest.raises(ApprovalError) as exc:
        await decide(
            session, actor_id=both.id, package_id=pkg.id, function="hr", decision="approve"
        )
    assert exc.value.status_code == 409


async def test_reject_returns_owner_to_sowdraft_and_notifies(session):
    opp, _v, owner = await _seed_full_deal(session)
    pkg = await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    d = await _seed_user(session, "d@smartek21.com", ["Delivery"])
    result = await decide(
        session,
        actor_id=d.id,
        package_id=pkg.id,
        function="delivery",
        decision="reject",
        reason="staffing shortfall",
    )
    assert result.status == "rejected"
    opp_refreshed = (
        await session.execute(select(Opportunity).where(Opportunity.id == opp.id))
    ).scalar_one()
    assert opp_refreshed.governance_status == "SOWDraft"
    notes = (
        await session.execute(
            select(Notification).where(Notification.related_entity_id == str(pkg.id))
        )
    ).scalars().all()
    assert len(list(notes)) >= 1


async def test_legacy_sow_version_blocked_with_rollout_message(session):
    owner = await _seed_owner(session)
    opp, _version = await _seed_opp_with_sow(session, owner, legacy=True)
    # Any gm_model — legacy guard fires before the gm_model lookup.
    payload = _passing_payload(_version.id)
    await create_gm_model_version(
        session, opportunity_id=opp.id, actor_id=owner.id, payload=payload
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert exc.value.status_code == 403
    assert "backfill fake approvals" in exc.value.detail


async def test_duplicate_package_hash_resubmit_conflicts(session):
    opp, _v, owner = await _seed_full_deal(session)
    await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    with pytest.raises(ApprovalError) as exc:
        await submit_package(session, actor_id=owner.id, opportunity_id=opp.id)
    assert exc.value.status_code == 409


# ---- HTTP layer / permissions ------------------------------------------


async def test_http_submit_requires_owner_or_admin(app_with_session, session):
    owner = await _seed_owner(session)
    opp, _v, _o = await _seed_full_deal(session, owner_email="owner2@smartek21.com")

    # A non-owner Sales user (using the local auth stub) is rejected 403.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/approvals/packages/{opp.id}",
            headers={"X-Test-User": "someone-else@smartek21.com"},
        )
        assert r.status_code == 403

    # The account owner (owner_email set in _seed_full_deal) succeeds.
    async with _client(app_with_session) as c:
        r = await c.post(
            f"/approvals/packages/{opp.id}",
            headers={"X-Test-User": "owner2@smartek21.com"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "pending_delivery_hr"
        assert "floors" in body


async def test_http_decide_requires_matching_role(app_with_session, session, monkeypatch):
    opp, _v, _owner = await _seed_full_deal(session, owner_email="owner3@smartek21.com")

    async with _client(app_with_session) as c:
        r = await c.post(
            f"/approvals/packages/{opp.id}",
            headers={"X-Test-User": "owner3@smartek21.com"},
        )
        assert r.status_code == 201, r.text
        pkg_id = r.json()["id"]

    # Wrong role: an HR user cannot approve as delivery.
    async with _client(app_with_session) as c:
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", "HR")
        r = await c.post(
            f"/approvals/packages/{pkg_id}/decisions/delivery",
            headers={"X-Test-User": "h@smartek21.com"},
            json={"decision": "approve"},
        )
        assert r.status_code == 403


async def test_http_list_gates_read_role(app_with_session, session, monkeypatch):
    await _seed_full_deal(session)
    # Sales-only user gets 403.
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Sales")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/approvals/packages", headers={"X-Test-User": "salesguy@smartek21.com"}
        )
        assert r.status_code == 403

    # Finance user succeeds (empty list, still 200).
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Finance")
    async with _client(app_with_session) as c:
        r = await c.get(
            "/approvals/packages", headers={"X-Test-User": "financeguy@smartek21.com"}
        )
        assert r.status_code == 200
        assert "items" in r.json()
