"""S21F:T14.04/T14.07 — amendment activation supersedes the original
contract in the same transaction and records explicit overlap or gap.

Releasing an amendment package (a later SOW version on an opportunity
that already has a released contract) must: supersede the original
package and its pinned version so every signed read switches to the
amendment's effective schedule; create the amendment's own Project row
whose baseline carries the amendment term; and write an
``amendment.activated`` audit naming the explicit overlap/gap between
the original term end and the amendment term start. A pinned version
that was itself superseded is stale economics and cannot release.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.gm_model import GmModel
from app.models.project import Project
from app.models.sow import SowVersion
from app.integrations.ses import StubSES
from app.services.signed_sow import SignedSowError, create_upload, release
from tests.test_signed_sow import (  # noqa: F401
    SIGNED_HASH,
    _CannedBedrock,
    _local_env,
    _prepare_release_ready,
    _approved_fields,
    _seed_delivery_acceptance,
    _seed_internal_signoff,
    _seed_user,
    verify,
)


async def _release_original(session, owner):
    package, opp, pinned, delivery_user = await _prepare_release_ready(
        session, owner=owner
    )
    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/original.pdf",
        file_hash=SIGNED_HASH,
    )
    await verify(session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock())
    await release(session, actor_id=owner.id, upload_id=upload.id, ses=StubSES())
    return package, opp, pinned, delivery_user


async def _seed_amendment(
    session, owner, opp, original_version, *, term_start, term_end
):
    fields = _approved_fields()
    fields["term_start"]["value"] = term_start
    fields["term_end"]["value"] = term_end
    v2 = SowVersion(
        id=uuid.uuid4(),
        sow_id=original_version.sow_id,
        uploaded_by=owner.id,
        file_s3_key=f"sow/amendment-{uuid.uuid4().hex[:8]}.pdf",
        file_hash=uuid.uuid4().hex * 2,
        extract_status="complete",
        extracted_fields=fields,
        confirmed_by=owner.id,
        confirmed_at=datetime.now(UTC),
        version_no=original_version.version_no + 1,
    )
    session.add(v2)
    await session.flush()
    gm = GmModel(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=v2.id,
        engagement_type="fixed_price",
        delivery_pattern="us_only",
        contingency_pct=Decimal("5.00"),
        warranty_days=30,
        revenue_us=Decimal("100000.00"),
        revenue_india=Decimal("0"),
        created_by=owner.id,
    )
    session.add(gm)
    await session.flush()
    package2 = ApprovalPackage(
        id=uuid.uuid4(),
        opportunity_id=opp.id,
        sow_version_id=v2.id,
        gm_model_id=gm.id,
        package_hash="c" * 64,
        status="ready_to_sign",
        submitted_by=owner.id,
    )
    session.add(package2)
    await session.commit()
    delivery = await _seed_user(
        session, f"amend-delivery-{uuid.uuid4().hex[:6]}@smartek21.com", ["Delivery"]
    )
    await _seed_internal_signoff(session, package2, delivery)
    await _seed_delivery_acceptance(session, package2, delivery)
    upload2 = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package2.id,
        file_s3_key="sow/signed/amendment.pdf",
        file_hash=SIGNED_HASH,
    )
    await verify(
        session,
        actor_id=owner.id,
        upload_id=upload2.id,
        bedrock=_CannedBedrock(
            overrides={"term_start": term_start, "term_end": term_end}
        ),
    )
    return v2, package2, upload2


async def _activation_audits(session):
    return (
        await session.scalars(
            select(AuditEvent).where(AuditEvent.action == "amendment.activated")
        )
    ).all()


@pytest.mark.asyncio
async def test_activation_supersedes_original_and_records_overlap(session):
    owner = await _seed_user(session, "amend-owner@smartek21.com", ["Sales"])
    package1, opp, v1, _ = await _release_original(session, owner)
    assert not await _activation_audits(session)

    # Original term is 2026-10-01 → 2027-03-31; the amendment restates the
    # engagement from 2027-01-01, overlapping the original's final 90 days.
    v2, package2, upload2 = await _seed_amendment(
        session, owner, opp, v1, term_start="2027-01-01", term_end="2027-12-31"
    )
    await release(session, actor_id=owner.id, upload_id=upload2.id, ses=StubSES())

    await session.refresh(v1)
    await session.refresh(package1)
    assert v1.superseded_by == v2.id
    assert package1.superseded_by == package2.id
    assert package1.status == "released"  # history retained, not rewritten

    audits = await _activation_audits(session)
    assert len(audits) == 1
    payload = audits[0].after
    assert payload["overlap_days"] == 90
    assert payload["gap_days"] == 0
    assert payload["original_term_end"] == "2027-03-31"
    assert payload["amendment_term_start"] == "2027-01-01"
    assert payload["superseded_package_id"] == str(package1.id)

    # The amendment's Project row carries the amendment term.
    project2 = await session.scalar(
        select(Project).where(Project.package_id == package2.id)
    )
    assert project2 is not None
    assert project2.baseline_snapshot_json["term_start"] == "2027-01-01"
    assert project2.baseline_snapshot_json["term_end"] == "2027-12-31"
    # The original project row survives untouched.
    assert await session.scalar(
        select(Project.id).where(Project.package_id == package1.id)
    )


@pytest.mark.asyncio
async def test_activation_records_explicit_gap(session):
    owner = await _seed_user(session, "gap-owner@smartek21.com", ["Sales"])
    package1, opp, v1, _ = await _release_original(session, owner)
    v2, package2, upload2 = await _seed_amendment(
        session, owner, opp, v1, term_start="2027-05-01", term_end="2027-12-31"
    )
    await release(session, actor_id=owner.id, upload_id=upload2.id, ses=StubSES())

    audits = await _activation_audits(session)
    assert len(audits) == 1
    payload = audits[0].after
    assert payload["overlap_days"] == 0
    assert payload["gap_days"] == 30  # April 2027 is uncovered, explicitly

    await session.refresh(v1)
    assert v1.superseded_by == v2.id


@pytest.mark.asyncio
async def test_release_refuses_stale_pinned_version(session):
    owner = await _seed_user(session, "stale-owner@smartek21.com", ["Sales"])
    package1, opp, v1, _ = await _release_original(session, owner)
    v2, package2, upload2 = await _seed_amendment(
        session, owner, opp, v1, term_start="2027-04-01", term_end="2027-12-31"
    )
    v2.superseded_by = uuid.uuid4()
    await session.commit()

    with pytest.raises(SignedSowError) as error:
        await release(session, actor_id=owner.id, upload_id=upload2.id, ses=StubSES())
    assert error.value.status_code == 409

    await session.refresh(package1)
    await session.refresh(v1)
    assert package1.superseded_by is None
    assert v1.superseded_by is None
    assert not await _activation_audits(session)
