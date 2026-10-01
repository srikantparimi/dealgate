"""S20 W3 D6 · deletion is state-aware.

- A draft SOW (no approval_package) → `delete_sow` succeeds (hard
  delete, rows go, audit line stays).
- A SOW that reached approval (any package_status, incl. rejected) →
  `delete_sow` refuses with a 409; `archive_sow` is the allowed
  action. `sow.archived_at` is set; rows survive.
- `assess_sow` reports the state so the UI can render the right label
  before the click.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.approval import ApprovalPackage
from app.models.client import Client, LegalEntity
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.deletion import (
    DeletionError,
    archive_sow,
    assess_sow,
    delete_sow,
)


async def _seed(session, *, with_package: bool):
    owner = User(id=uuid.uuid4(), email="del-owner@example.com", name="Del Owner", groups=["Sales"])
    session.add(owner)
    client = Client(id=uuid.uuid4(), name="DelClient")
    session.add(client)
    session.add(LegalEntity(id=uuid.uuid4(), client_id=client.id, name="DelClient"))
    opp = Opportunity(
        id=uuid.uuid4(),
        source="test",
        owner_id=owner.id,
        client_id=client.id,
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
        file_s3_key="del/one.pdf",
        file_hash=uuid.uuid4().hex,
        extract_status="complete",
    )
    session.add(version)
    await session.flush()
    if with_package:
        gm = GmModel(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            sow_version_id=version.id,
            version=1,
            engagement_type="fixed_price",
        )
        session.add(gm)
        await session.flush()
        pkg = ApprovalPackage(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            sow_version_id=version.id,
            gm_model_id=gm.id,
            package_hash=uuid.uuid4().hex,
            status="pending_delivery_hr",
            submitted_by=owner.id,
            submitted_at=datetime.now(UTC),
        )
        session.add(pkg)
        await session.flush()
    return owner, opp, sow


@pytest.mark.asyncio
async def test_assess_reports_draft_when_no_package(session):
    _, _, sow = await _seed(session, with_package=False)
    result = await assess_sow(session, sow.id)
    assert result.state == "draft"


@pytest.mark.asyncio
async def test_assess_reports_governed_when_package_exists(session):
    _, _, sow = await _seed(session, with_package=True)
    result = await assess_sow(session, sow.id)
    assert result.state == "governed"


@pytest.mark.asyncio
async def test_delete_draft_hard_deletes_rows(session):
    owner, _, sow = await _seed(session, with_package=False)
    summary = await delete_sow(session, sow_id=sow.id, actor_id=owner.id)
    assert summary.sow_id == sow.id
    # Sow row is gone.
    from sqlalchemy import select

    row = (
        await session.execute(select(Sow).where(Sow.id == sow.id))
    ).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_delete_governed_is_refused_409(session):
    owner, _, sow = await _seed(session, with_package=True)
    with pytest.raises(DeletionError) as exc:
        await delete_sow(session, sow_id=sow.id, actor_id=owner.id)
    assert exc.value.status_code == 409
    assert "archive" in exc.value.message.lower()


@pytest.mark.asyncio
async def test_archive_governed_marks_archived_at_but_keeps_rows(session):
    owner, _, sow = await _seed(session, with_package=True)
    summary = await archive_sow(session, sow_id=sow.id, actor_id=owner.id)
    assert summary.sow_id == sow.id
    from sqlalchemy import select

    row = (
        await session.execute(select(Sow).where(Sow.id == sow.id))
    ).scalar_one()
    assert row.archived_at is not None
    assert row.archived_by == owner.id
    # Versions and approval package still exist.
    versions = list(
        (
            await session.execute(
                select(SowVersion).where(SowVersion.sow_id == sow.id)
            )
        ).scalars()
    )
    assert len(versions) == 1
    packages = list(
        (
            await session.execute(
                select(ApprovalPackage).where(
                    ApprovalPackage.sow_version_id == versions[0].id
                )
            )
        ).scalars()
    )
    assert len(packages) == 1


@pytest.mark.asyncio
async def test_archive_is_idempotent(session):
    owner, _, sow = await _seed(session, with_package=True)
    await archive_sow(session, sow_id=sow.id, actor_id=owner.id)
    # Second call should not raise and should return a summary.
    result = await archive_sow(session, sow_id=sow.id, actor_id=owner.id)
    assert result.sow_id == sow.id


# ---------------------------------------------------------------------------
# S21-1d · root-cause: non-mirror client cascades through governed SOWs.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_mirror_client_hard_deletes_with_governed_sow(session):
    """A client with no hubspot_company_id is scratch / e2e data; it
    must hard-delete even when its SOW has reached approval."""

    from app.services.deletion import delete_client

    owner, opp, sow = await _seed(session, with_package=True)
    client = await session.get(Client, opp.client_id)
    assert client is not None and client.hubspot_company_id is None, "fixture sanity"
    # Baseline: delete_sow refuses the governed row.
    with pytest.raises(DeletionError):
        await delete_sow(session, actor_id=owner.id, sow_id=sow.id)
    # delete_client cascades through anyway because the client is non-mirror.
    result = await delete_client(session, actor_id=owner.id, client_id=client.id)
    assert result.state == "draft"
    # Client + SOW are actually gone.
    assert await session.get(Client, client.id) is None
    assert await session.get(Sow, sow.id) is None


@pytest.mark.asyncio
async def test_mirror_client_still_refuses_governed_sow(session):
    """A client with a hubspot_company_id value remains governance-
    protected — the S20 W3 D6 refusal still fires. CLAUDE.md rule 4
    protects every mirror-sourced record."""

    from app.services.deletion import delete_client

    owner, opp, _sow = await _seed(session, with_package=True)
    client = await session.get(Client, opp.client_id)
    assert client is not None
    client.hubspot_company_id = "fake-hubspot-123"
    await session.commit()
    with pytest.raises(DeletionError):
        await delete_client(session, actor_id=owner.id, client_id=client.id)
    # Client survives.
    assert await session.get(Client, client.id) is not None
