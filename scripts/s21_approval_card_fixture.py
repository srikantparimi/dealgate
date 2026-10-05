"""Declared mixed review fixture for T40, never approval-transition proof."""
import asyncio
import json
import os
import uuid
from datetime import UTC, date, datetime
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.approval import ApprovalPackage
from app.models.approval_routing import ApprovalAssignment
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.provenance import wrap
from app.services.test_fixtures import account_scope, allowed_for_package


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert (parsed.hostname, parsed.port, parsed.path) == ("127.0.0.1", 55421, "/s21_journey")
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            deals = [await session.get(Opportunity, uuid.UUID(os.environ[key]))
                     for key in ("S21_CARD_DEAL", "S21_CARD_HIDDEN_DEAL")]
            reviewers = [uuid.UUID(value) for value in json.loads(os.environ["S21_CARD_REVIEWERS"])]
            assert len(set(reviewers)) == 5
            for deal in deals:
                assert deal and deal.source == "sow_upload" and deal.hubspot_deal_id is None
                assert not await session.scalar(select(Sow.id).where(Sow.opportunity_id == deal.id))
                scope = await account_scope(session, deal.client_id, opportunity_id=deal.id)
                assert scope and deal.owner_id in scope
            owner_scope = await account_scope(session, deals[0].client_id, opportunity_id=deals[0].id)
            assert set(reviewers) <= owner_scope
            packages = []
            for index, status in enumerate(("pending_delivery_hr", "pending_finance_legal", "ready_to_sign", None, "pending_delivery_hr")):
                deal = deals[1] if index == 4 else deals[0]
                sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
                session.add(sow)
                await session.flush()
                version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=deal.owner_id,
                    file_s3_key="", file_hash=uuid.uuid4().hex * 2, extract_status="complete",
                    extracted_fields={"sow_title": wrap(f"T40 synthetic SOW {index}", provenance="manual", status="confirmed")})
                session.add(version)
                await session.flush()
                if status is None:
                    continue
                gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                    version=index + 1, engagement_type="fixed_price")
                session.add(gm)
                await session.flush()
                package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                    gm_model_id=gm.id, package_hash=uuid.uuid4().hex * 2, status=status,
                    submitted_by=deal.owner_id, submitted_at=datetime.now(UTC))
                session.add(package)
                await session.flush()
                if index < 2:
                    for function, reviewer in zip(("delivery", "hr", "sales", "finance", "legal"), reviewers, strict=True):
                        session.add(ApprovalAssignment(package_id=package.id, function=function,
                            approver_id=reviewer, due_date=date(2026, 10, 9)))
                assert await allowed_for_package(session, deal.owner_id, package)
                packages.append(str(package.id))
            await session.commit()
            print(json.dumps({"included": packages[:2], "approved": packages[2], "hidden": packages[3],
                "fixture_kind": "seeded_mixed_review_not_approval_transition_proof"}))
    finally:
        await engine.dispose()


asyncio.run(main())
