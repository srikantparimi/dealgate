"""S21F:T14.07 — a late signature callback cannot activate stale economics.

`verify`, `mark_declined` and `mark_expired` are callback surfaces: the
external signer (or an operator replaying one) can hit them long after
the package stopped being current. Each one must refuse when the
package is no longer `ready_to_sign` (voided, rejected, released), when
the package was superseded by a newer one, when the upload itself was
replaced by a re-upload, or when the pinned SOW version was superseded
by an amendment. Flipping any of those to `verified` would count a
stale contract as signed economics in the outlook and coverage reads.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.signed_sow import SignedSowUpload
from app.services.signed_sow import (
    SignedSowError,
    create_upload,
    mark_declined,
    mark_expired,
)
from tests.test_signed_sow import (  # noqa: F401
    SIGNED_HASH,
    _CannedBedrock,
    _local_env,
    _seed_ready_to_sign_package,
    _seed_user,
    verify,
)


async def _seeded_upload(session, owner):
    package, opp, pinned = await _seed_ready_to_sign_package(session, owner=owner)
    upload = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/current.pdf",
        file_hash=SIGNED_HASH,
    )
    return package, opp, pinned, upload


async def _unchanged(session, upload_id, expected_status="pending"):
    row = await session.get(SignedSowUpload, upload_id)
    await session.refresh(row)
    assert row.verify_status == expected_status
    assert row.verified_at is None
    return row


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["released", "voided", "rejected"])
async def test_verify_refuses_non_current_package_status(session, status):
    owner = await _seed_user(session, "late-owner@smartek21.com", ["Sales"])
    package, _, _, upload = await _seeded_upload(session, owner)
    package.status = status
    await session.commit()

    with pytest.raises(SignedSowError) as error:
        await verify(
            session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock()
        )
    assert error.value.status_code == 409
    await _unchanged(session, upload.id)


@pytest.mark.asyncio
async def test_verify_refuses_superseded_package(session):
    owner = await _seed_user(session, "late-sup@smartek21.com", ["Sales"])
    package, _, _, upload = await _seeded_upload(session, owner)
    package.superseded_by = uuid.uuid4()
    await session.commit()

    with pytest.raises(SignedSowError) as error:
        await verify(
            session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock()
        )
    assert error.value.status_code == 409
    await _unchanged(session, upload.id)


@pytest.mark.asyncio
async def test_verify_refuses_replaced_upload(session):
    owner = await _seed_user(session, "late-replaced@smartek21.com", ["Sales"])
    package, _, _, stale = await _seeded_upload(session, owner)
    # SQLite's CURRENT_TIMESTAMP has second granularity, so push the first
    # upload visibly into the past instead of racing the id tiebreak.
    from datetime import UTC, datetime, timedelta

    stale.uploaded_at = datetime.now(UTC) - timedelta(minutes=5)
    await session.commit()
    replacement = await create_upload(
        session,
        actor_id=owner.id,
        package_id=package.id,
        file_s3_key="sow/signed/replacement.pdf",
        file_hash=SIGNED_HASH,
    )

    with pytest.raises(SignedSowError) as error:
        await verify(
            session, actor_id=owner.id, upload_id=stale.id, bedrock=_CannedBedrock()
        )
    assert error.value.status_code == 409
    await _unchanged(session, stale.id)

    # The current upload still verifies normally.
    current = await verify(
        session, actor_id=owner.id, upload_id=replacement.id, bedrock=_CannedBedrock()
    )
    assert current.verify_status == "verified"


@pytest.mark.asyncio
async def test_verify_refuses_superseded_pinned_version(session):
    owner = await _seed_user(session, "late-amend@smartek21.com", ["Sales"])
    _, _, pinned, upload = await _seeded_upload(session, owner)
    pinned.superseded_by = uuid.uuid4()
    await session.commit()

    with pytest.raises(SignedSowError) as error:
        await verify(
            session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock()
        )
    assert error.value.status_code == 409
    await _unchanged(session, upload.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("callback", ["declined", "expired"])
async def test_late_signer_outcome_refused_on_released_package(session, callback):
    owner = await _seed_user(session, f"late-{callback}@smartek21.com", ["Sales"])
    package, _, _, upload = await _seeded_upload(session, owner)
    package.status = "released"
    await session.commit()

    with pytest.raises(SignedSowError) as error:
        if callback == "declined":
            await mark_declined(
                session, actor_id=owner.id, upload_id=upload.id, reason="too late"
            )
        else:
            await mark_expired(
                session, actor_id=owner.id, upload_id=upload.id, reason="too late"
            )
    assert error.value.status_code == 409
    await _unchanged(session, upload.id)


@pytest.mark.asyncio
async def test_current_callbacks_still_work(session):
    owner = await _seed_user(session, "late-ok@smartek21.com", ["Sales"])
    _, _, _, upload = await _seeded_upload(session, owner)
    verified = await verify(
        session, actor_id=owner.id, upload_id=upload.id, bedrock=_CannedBedrock()
    )
    assert verified.verify_status == "verified"

    owner2 = await _seed_user(session, "late-ok2@smartek21.com", ["Sales"])
    _, _, _, upload2 = await _seeded_upload(session, owner2)
    declined = await mark_declined(
        session, actor_id=owner2.id, upload_id=upload2.id, reason="client passed"
    )
    assert declined.verify_status == "declined"
