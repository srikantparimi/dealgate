"""S21F:T14.06 — nonrenewal closes the renewal, files closeout/roll-off
actions, and leaves current delivery untouched through the end date.

The directive (S21-16): "Nonrenewal leaves current delivery active
through the end date and creates closeout/roll-off actions." Closing a
renewal with the explicit `not_renewing` outcome therefore files a
closeout task and a roll-off task on the account owner, due at term
end, without touching the released package, its project, or the SOW
version. A plain close (e.g. completed closeout) files nothing new.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.sow import Sow, SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.renewals import patch_renewal

TERM_END = date(2027, 3, 31)


async def _seed(session):
    owner = User(
        id=uuid.uuid4(),
        email=f"nonrenew-{uuid.uuid4().hex[:6]}@smartek21.com",
        name="Owner",
        groups=["Sales"],
    )
    client = Client(id=uuid.uuid4(), name="Nonrenewal Client")
    session.add_all([owner, client])
    await session.flush()
    opp = Opportunity(
        id=uuid.uuid4(),
        client_id=client.id,
        owner_id=owner.id,
        governance_status="Intake",
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
        file_s3_key="sow/nonrenewal.pdf",
        file_hash=uuid.uuid4().hex * 2,
        extract_status="complete",
    )
    session.add(version)
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        engagement_type="fixed_price",
        created_by=owner.id,
    )
    session.add(gm)
    await session.flush()
    package = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=version.id,
        gm_model_id=gm.id,
        package_hash="e" * 64,
        status="released",
        submitted_by=owner.id,
    )
    renewal = Renewal(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        term_end=TERM_END,
        trigger_date=date(2027, 1, 31),
        status="open",
    )
    session.add_all([package, renewal])
    await session.commit()
    return owner, opp, package, version, renewal


async def _tasks(session, owner_id):
    return (
        await session.scalars(select(Task).where(Task.owner_id == owner_id))
    ).all()


@pytest.mark.asyncio
async def test_not_renewing_files_closeout_and_roll_off(session):
    owner, opp, package, version, renewal = await _seed(session)

    updated = await patch_renewal(
        session,
        renewal=renewal,
        actor_id=owner.id,
        outcome_summary="Not renewing: client is insourcing",
        to_status="closed",
        outcome="not_renewing",
    )
    await session.commit()
    assert updated.status == "closed"

    tasks = await _tasks(session, owner.id)
    categories = {t.category for t in tasks}
    assert "closeout" in categories
    assert "roll_off" in categories
    for task in tasks:
        assert task.due_date == TERM_END
        assert task.status == "assigned"

    # Current delivery stays active through the end date: nothing signed
    # was touched by the nonrenewal decision.
    await session.refresh(package)
    await session.refresh(version)
    assert package.status == "released"
    assert package.superseded_by is None
    assert version.superseded_by is None


@pytest.mark.asyncio
async def test_plain_close_files_no_tasks(session):
    owner, _, _, _, renewal = await _seed(session)
    await patch_renewal(
        session,
        renewal=renewal,
        actor_id=owner.id,
        outcome_summary="Completed closeout",
        to_status="closed",
    )
    await session.commit()
    assert not await _tasks(session, owner.id)


@pytest.mark.asyncio
async def test_not_renewing_requires_the_close_transition(session):
    owner, _, _, _, renewal = await _seed(session)
    from app.services.renewals import RenewalError

    with pytest.raises(RenewalError) as error:
        await patch_renewal(
            session,
            renewal=renewal,
            actor_id=owner.id,
            outcome_summary="Not renewing",
            to_status="extended",
            outcome="not_renewing",
        )
    assert error.value.status_code == 422
    await session.rollback()
    assert not await _tasks(session, owner.id)
