"""S20 W3 T19 · stale-tab refusal for approval decisions.

`services.approvals.decide` accepts an optional
``expected_package_hash``. When supplied, the server 409s if it does
not match ``package.package_hash`` — the caller's tab is out of date
(most commonly because `void_on_change` fired between load and click).

The test uses the existing fixtures from `test_approvals.py` as a
reference — it seeds a full deal, submits a package, then attempts a
decision with a stale hash. The test asserts the ApprovalError shape,
not the router: the router is a thin pass-through and its 409 is a
consequence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio

from app.models.client import Client, LegalEntity
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.approvals import ApprovalError, decide, package_hash, submit_package
from app.services.approval_routing import submission_plan
from app.services.delivery_model import (
    CostLinePayload,
    GmModelPayload,
    ResourceLinePayload,
    create_gm_model_version,
)


@pytest.fixture(autouse=True)
def _local_env(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")


async def _seed_reviewers(session) -> dict[str, User]:
    def uid(email: str) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")

    reviewers: dict[str, User] = {}
    for role in ("Delivery", "HR", "Finance", "Legal"):
        email = f"{role.lower()}@example.com"
        u = User(id=uid(email), email=email, name=role, groups=[role])
        session.add(u)
        reviewers[role] = u
    await session.flush()
    return reviewers


async def _seed_full_deal(session) -> tuple[Opportunity, SowVersion, User, dict[str, User]]:
    def uid(email: str) -> uuid.UUID:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")

    owner = User(
        id=uid("owner@example.com"),
        email="owner@example.com",
        name="owner",
        groups=["Sales"],
    )
    session.add(owner)
    client = Client(id=uuid.uuid4(), name="Acme")
    session.add(client)
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name="Acme"))
    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=f"H-{uuid.uuid4().hex[:6]}",
        owner_id=owner.id,
        client_id=client.id,
        governance_status="SOWDraft.confirmed",
    )
    session.add(opp)
    await session.flush()
    sow = Sow(id=uuid.uuid4(), opportunity_id=opp.id)
    session.add(sow)
    await session.flush()
    v = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow.id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/{sow.id}.pdf",
        file_hash="a" * 64,
        extract_status="complete",
        extracted_fields={
            "scope_summary": {
                "value": "Build a thing",
                "page_ref": 1,
                "status": "confirmed",
            },
            "price": {"value": "150000", "page_ref": 1, "status": "confirmed"},
        },
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
    )
    session.add(v)
    await session.commit()

    # A passing GM model so submit_package doesn't refuse.
    await create_gm_model_version(
        session,
        opportunity_id=opp.id,
        actor_id=owner.id,
        payload=GmModelPayload(
            engagement_type="tm",
            sow_version_id=v.id,
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
                    start_date=date(2026, 3, 1),
                    end_date=date(2026, 8, 31),
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
                    start_date=date(2026, 3, 1),
                    end_date=date(2026, 8, 31),
                    hours_billable=Decimal("800"),
                    hourly_bill_rate=Decimal("100"),
                    hourly_cost=Decimal("40"),
                    validated_by=uuid.uuid4(),
                ),
            ],
            cost_lines=[],
        ),
    )
    reviewers = await _seed_reviewers(session)
    return opp, v, owner, reviewers


@pytest.mark.asyncio
async def test_stale_hash_is_refused_with_409(session):
    """T19: a decision with a stale ``expected_package_hash`` raises
    ApprovalError with status 409."""

    opp, _v, owner, reviewers = await _seed_full_deal(session)
    plan = await submission_plan(session, actor_id=owner.id, opportunity_id=opp.id)
    pkg = await submit_package(
        session, actor_id=owner.id, opportunity_id=opp.id, routing=plan
    )
    stale = "0" * 64
    with pytest.raises(ApprovalError) as exc_info:
        await decide(
            session,
            actor_id=reviewers["Delivery"].id,
            package_id=pkg.id,
            function="delivery",
            decision="approve",
            reason="fine by me",
            expected_package_hash=stale,
        )
    assert exc_info.value.status_code == 409
    assert "package_hash mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_matching_hash_is_accepted(session):
    """The same decision with the correct hash goes through."""

    opp, _v, owner, reviewers = await _seed_full_deal(session)
    plan = await submission_plan(session, actor_id=owner.id, opportunity_id=opp.id)
    pkg = await submit_package(
        session, actor_id=owner.id, opportunity_id=opp.id, routing=plan
    )
    correct = pkg.package_hash
    result = await decide(
        session,
        actor_id=reviewers["Delivery"].id,
        package_id=pkg.id,
        function="delivery",
        decision="approve",
        reason="fine by me",
        expected_package_hash=correct,
    )
    # The package still exists and its status advanced or stayed same.
    assert result.id == pkg.id


@pytest.mark.asyncio
async def test_omitted_hash_still_works(session):
    """Omitting the hash preserves the pre-S20 behaviour — the check
    is opt-in for compatibility. Clients that don't send the hash are
    still valid; only the stale-check is skipped."""

    opp, _v, owner, reviewers = await _seed_full_deal(session)
    plan = await submission_plan(session, actor_id=owner.id, opportunity_id=opp.id)
    pkg = await submit_package(
        session, actor_id=owner.id, opportunity_id=opp.id, routing=plan
    )
    result = await decide(
        session,
        actor_id=reviewers["Delivery"].id,
        package_id=pkg.id,
        function="delivery",
        decision="approve",
        reason="fine by me",
        # expected_package_hash omitted → no stale-check.
    )
    assert result.id == pkg.id
