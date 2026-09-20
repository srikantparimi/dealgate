"""Resources are editable at any point; the signature decides the cost (S10-08).

Before signature a plan is a proposal — edit it freely, tell nobody. After
signature the margin was part of a decision, so the edit is dated and the
approvers are told with both numbers. A margin that moves silently after
Finance approved it is exactly what this product exists to prevent.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.signed_sow import SignedSowUpload
from app.models.user import User
from app.services.sow_resources import (
    SowResourceError,
    current_resources,
    is_signed,
    update_resources,
)


def _line(location="US", hours="160", cost="95", util="1", bill="0"):
    return {
        "role": "Consultant",
        "seniority": "Senior",
        "location": location,
        "person_name": None,
        "allocation_pct": util,
        "start_date": "2026-08-25",
        "end_date": "2026-09-30",
        "hours_billable": hours,
        "hourly_bill_rate": bill,
        "hourly_cost": cost,
        "validated_by": None,
    }


def _payload(lines=None, total="50000.00"):
    return {
        "engagement_type": "fixed_price",
        "resource_lines": lines or [_line()],
        "cost_lines": [],
        "total_price": total,
    }


async def _seed(session, *, signed: bool = False):
    user = User(
        id=uuid.uuid4(), email="delivery@smartek21.com", name="D", groups=["Delivery"]
    )
    client = Client(id=uuid.uuid4(), name="Contoso Data Services, LLC")
    session.add_all([user, client])
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(), client_id=client.id, owner_id=user.id,
        governance_status="Intake",
    )
    session.add(opp)
    await session.flush()

    if signed:
        pkg = ApprovalPackage(
            id=uuid.uuid4(), opportunity_id=opp.id, sow_version_id=uuid.uuid4(),
            gm_model_id=uuid.uuid4(), policy_version_id=uuid.uuid4(),
            package_hash="x" * 64, status="released", submitted_by=user.id,
        )
        session.add(pkg)
        await session.flush()
        session.add(
            SignedSowUpload(
                id=uuid.uuid4(), package_id=pkg.id, file_s3_key="signed/x.pdf",
                file_hash="h", uploaded_by=user.id,
            )
        )
    await session.commit()
    return opp, user


async def test_unsigned_sow_can_be_edited_freely_and_quietly(session):
    opp, user = await _seed(session, signed=False)
    assert await is_signed(session, opp.id) is False

    # No effective date, no reason — neither is required before signature.
    first = await update_resources(
        session, opportunity_id=opp.id, actor_id=user.id, payload=_payload()
    )
    assert first.requires_notice is False
    assert first.notified == []

    # And again. A proposal can move as often as it needs to.
    second = await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=user.id,
        payload=_payload([_line(hours="200")]),
    )
    assert second.requires_notice is False
    assert second.previous_gm_model_id == first.gm_model_id

    await session.commit()
    assert not list((await session.execute(select(Notification))).scalars())


async def test_signed_sow_demands_a_date_and_a_reason(session):
    opp, user = await _seed(session, signed=True)
    assert await is_signed(session, opp.id) is True

    with pytest.raises(SowResourceError) as no_date:
        await update_resources(
            session, opportunity_id=opp.id, actor_id=user.id, payload=_payload()
        )
    assert "effective date" in no_date.value.message
    assert no_date.value.status_code == 422

    with pytest.raises(SowResourceError) as no_reason:
        await update_resources(
            session, opportunity_id=opp.id, actor_id=user.id, payload=_payload(),
            effective_from=date(2026, 10, 1),
        )
    assert "reason" in no_reason.value.message


async def test_signed_sow_change_notifies_with_both_margins(session):
    opp, user = await _seed(session, signed=True)

    result = await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=user.id,
        payload=_payload(),
        effective_from=date(2026, 10, 1),
        reason="Consultant rolled off; replaced by a senior engineer",
    )
    await session.commit()

    assert result.requires_notice is True
    assert result.effective_from == date(2026, 10, 1)

    rows = list((await session.execute(select(Notification))).scalars())
    assert rows, "approvers must be told when a signed SOW's margin moves"

    # `approval_pending` rows also land here — the change-voids-approval hook
    # fires whenever a GM moves, which is correct and separate. What this
    # test pins is the resource-change notice itself.
    changes = [r for r in rows if r.category == "resource_change"]
    assert changes, "expected a resource_change notification"
    body = changes[0].body_md
    # Both numbers, not just "the staffing changed" — otherwise the reader has
    # to go and find out whether it mattered.
    assert "Blended margin:" in body
    assert "→" in body
    assert "rolled off" in body


async def test_editing_is_always_allowed_after_signature(session):
    """The signature adds a cost to changing, not a prohibition. People leave
    projects and scope moves; refusing the edit just drives it off-system."""

    opp, _user = await _seed(session, signed=True)
    state = await current_resources(session, opp.id)
    assert state["is_signed"] is True
    assert state["editable"] is True
    assert state["requires_notice_on_change"] is True


async def test_utilization_is_surfaced_as_a_percentage(session):
    """The grid asks for "50"; the library stores 0.5. A reader should see
    the percentage they typed."""

    opp, user = await _seed(session)
    await update_resources(
        session,
        opportunity_id=opp.id,
        actor_id=user.id,
        payload=_payload([_line(util="0.5")]),
    )
    await session.commit()

    state = await current_resources(session, opp.id)
    assert state["resources"][0]["utilization_pct"].startswith("50")


async def test_part_time_resource_costs_half(session):
    """50% utilization: billed and paid for half, for the same hours."""

    opp, user = await _seed(session)
    full = await update_resources(
        session, opportunity_id=opp.id, actor_id=user.id,
        payload=_payload([_line(util="1")]),
    )
    half = await update_resources(
        session, opportunity_id=opp.id, actor_id=user.id,
        payload=_payload([_line(util="0.5")]),
    )
    await session.commit()

    # Same fee, half the cost → a materially better margin.
    full_gm = Decimal(str(full.after_margin["gm_blended"]))
    half_gm = Decimal(str(half.after_margin["gm_blended"]))
    assert half_gm > full_gm
