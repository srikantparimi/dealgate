"""S21-01 ownership boundaries precede enabling all-stage deletion."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models.approval import ApprovalPackage
from app.models.gm_model import GmModel
from app.models.notification import Notification
from app.models.sow import Sow, SowVersion
from app.services.deletion import assess_sow, delete_sow
from tests.test_deletion_by_state import _seed


@pytest.mark.asyncio
async def test_deleting_draft_preserves_sibling_sow_package_and_parent_notification(session):
    owner, deal, target = await _seed(session, with_package=False)
    sibling = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
    session.add(sibling)
    await session.flush()
    version = SowVersion(id=uuid.uuid4(), sow_id=sibling.id, file_s3_key="sibling/owned.pdf",
                         file_hash=uuid.uuid4().hex, extract_status="complete")
    session.add(version)
    await session.flush()
    gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                 engagement_type="fixed_price", version=1)
    session.add(gm)
    await session.flush()
    package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
        gm_model_id=gm.id, package_hash=uuid.uuid4().hex, status="pending_delivery_hr",
        submitted_by=owner.id, submitted_at=datetime.now(UTC))
    notification = Notification(id=uuid.uuid4(), user_id=owner.id, channel="inapp", category="deal_updated",
        subject="Parent deal activity", body_md="Independent deal comment", related_entity="opportunity",
        related_entity_id=str(deal.id))
    session.add_all([package, notification])
    await session.commit()
    assessment = await assess_sow(session, target.id)
    assert assessment.counts["approval_packages"] == 0
    await delete_sow(session, actor_id=owner.id, sow_id=target.id)
    await session.commit()
    assert await session.scalar(select(ApprovalPackage.id).where(ApprovalPackage.id == package.id)) == package.id
    assert await session.scalar(select(Notification.id).where(Notification.id == notification.id)) == notification.id
    assert await session.scalar(select(Sow.id).where(Sow.id == sibling.id)) == sibling.id
