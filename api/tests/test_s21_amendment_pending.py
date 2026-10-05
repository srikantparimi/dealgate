"""S21F:T14.02 — a pending amendment never kills the signed original.

`void_on_change` fires whenever a new SOW version or GM model lands. An
amendment draft on a signed/released contract is exactly that event, so
the hook must leave a released package — or one whose signed upload has
verified — untouched. Only a package that is still in flight (submitted,
pending reviews, ready_to_sign without a verified signature) is voided
by a source change. `manual_void` remains the explicit escape hatch for
signed contracts.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.audit import AuditEvent
from app.models.signed_sow import SignedSowUpload
from app.services.approval_routing import submission_plan
from app.services.approvals import submit_package, void_on_change
from app.services.approvals_hooks import on_sow_version_created
from tests.test_approval_routing import fixture
from tests.test_sow_lifecycle import _local_env, app_with_deps  # noqa: F401


async def _submitted_package(session):
    owner, opp, sow, gm, people = await fixture(session)
    plan = await submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
    package = await submit_package(
        session, actor_id=owner.id, opportunity_id=opp.id, routing=plan
    )
    return owner, opp, package


async def _void_audits(session, package_id):
    rows = (
        await session.scalars(
            select(AuditEvent).where(
                AuditEvent.action == "package.voided",
                AuditEvent.entity_id == str(package_id),
            )
        )
    ).all()
    return rows


@pytest.mark.asyncio
async def test_new_sow_version_does_not_void_released_package(session):
    owner, opp, package = await _submitted_package(session)
    package.status = "released"
    await session.flush()

    await on_sow_version_created(
        session,
        opportunity_id=opp.id,
        new_sow_version_id=uuid.uuid4(),
        actor_id=owner.id,
    )

    await session.refresh(package)
    assert package.status == "released"
    assert package.voided_at is None
    assert not await _void_audits(session, package.id)


@pytest.mark.asyncio
async def test_verified_signature_blocks_void_on_change(session):
    owner, opp, package = await _submitted_package(session)
    package.status = "ready_to_sign"
    session.add(
        SignedSowUpload(
            id=uuid.uuid4(),
            package_id=package.id,
            file_s3_key="signed/test.pdf",
            file_hash="a" * 64,
            uploaded_by=owner.id,
            verify_status="verified",
        )
    )
    await session.flush()

    result = await void_on_change(
        session,
        opportunity_id=opp.id,
        reason="sow_version changed (amendment draft)",
        actor_id=owner.id,
    )

    assert result is None
    await session.refresh(package)
    assert package.status == "ready_to_sign"
    assert not await _void_audits(session, package.id)


@pytest.mark.asyncio
async def test_unsigned_in_flight_package_is_still_voided(session):
    owner, opp, package = await _submitted_package(session)

    result = await void_on_change(
        session,
        opportunity_id=opp.id,
        reason="sow_version changed (ordinary revision)",
        actor_id=owner.id,
    )

    assert result is not None and result.id == package.id
    await session.refresh(package)
    assert package.status == "voided"
    assert len(await _void_audits(session, package.id)) == 1


@pytest.mark.asyncio
async def test_revision_of_signed_version_defers_supersession(app_with_deps, session):  # noqa: F811
    """An amendment draft on a signed original must not supersede it at
    upload: the original's schedule keeps counting until the amendment
    actually activates at its own release (S21-16, T14.02/T14.04)."""

    from app.models.gm_model import GmModel
    from app.models.approval import ApprovalPackage as Package
    from tests.test_sow_lifecycle import FIXTURES, _client, _seed, OWNER_EMAIL as LIFECYCLE_OWNER

    opp, sow, v1 = await _seed(session)
    gm = GmModel(
        id=uuid.uuid4(), opportunity_id=opp.id, sow_version_id=v1.id,
        engagement_type="fixed_price", created_by=v1.uploaded_by,
    )
    session.add(gm)
    await session.flush()
    session.add(
        Package(
            id=uuid.uuid4(), opportunity_id=opp.id, sow_version_id=v1.id,
            gm_model_id=gm.id, package_hash="d" * 64, status="released",
            submitted_by=v1.uploaded_by,
        )
    )
    await session.commit()

    docx = (FIXTURES / "08_assessment_fixed_fee.docx").read_bytes()
    async with _client(app_with_deps) as c:
        response = await c.post(
            f"/sows/{opp.id}/versions",
            headers={"X-Test-User": LIFECYCLE_OWNER},
            files={
                "file": (
                    "amendment.docx",
                    docx,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["supersedes"] is None
    assert body["amendment_draft_of"] == str(v1.id)

    await session.refresh(v1)
    assert v1.superseded_by is None
    assert v1.execution_state != "superseded"


@pytest.mark.asyncio
async def test_revision_of_unsigned_version_still_supersedes(app_with_deps, session):  # noqa: F811
    from tests.test_sow_lifecycle import FIXTURES, _client, _seed, OWNER_EMAIL as LIFECYCLE_OWNER

    opp, sow, v1 = await _seed(session)
    docx = (FIXTURES / "08_assessment_fixed_fee.docx").read_bytes()
    async with _client(app_with_deps) as c:
        response = await c.post(
            f"/sows/{opp.id}/versions",
            headers={"X-Test-User": LIFECYCLE_OWNER},
            files={
                "file": (
                    "revised.docx",
                    docx,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    assert response.status_code == 201, response.text
    assert response.json()["supersedes"] == str(v1.id)
    await session.refresh(v1)
    assert v1.superseded_by is not None
