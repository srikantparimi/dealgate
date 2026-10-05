"""Seed a released synthetic source for retained-demand UI proof, not signature proof."""
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.approval import ApprovalPackage
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.commercial_models import save_commercial_model
from app.services.project_lifecycle import create_or_link
from tests.test_s21_commercial_persistence import wire
from tests.test_s21_commercial_profiles import staffing


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port == 55421 and parsed.path == "/s21_journey"
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            deal = await session.get(Opportunity, uuid.UUID(os.environ["S21_RETAINED_DEAL"]))
            assert deal and deal.hubspot_deal_id is None and deal.source == "sow_upload"
            sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
            session.add(sow)
            await session.flush()
            version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=deal.owner_id,
                file_s3_key="", file_hash=uuid.uuid4().hex * 2, extract_status="manual_required",
                extracted_fields={"title": {"value": f"Synthetic retained staffing {sow.id}", "status": "confirmed"}})
            session.add(version)
            await session.flush()
            assignment = staffing(source_id=str(sow.id), source_version=str(version.id),
                policy_version="blueprint-defaults-v1")
            gm = await save_commercial_model(session, opportunity_id=deal.id, actor_id=deal.owner_id,
                sow_version_id=version.id, expected_gm_model_id=None, inputs=wire(version, staffing=(assignment,)),
                change_reason="Synthetic released baseline for retained-demand browser proof")
            package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                gm_model_id=gm.id, package_hash=uuid.uuid4().hex * 2, status="released",
                submitted_by=deal.owner_id, released_at=datetime.now(UTC))
            session.add(package)
            await session.flush()
            project, _ = await create_or_link(session, actor_id=deal.owner_id, package=package)
            await session.commit()
            print(json.dumps({"project_id": str(project.id), "sow_id": str(sow.id), "title": project.title,
                "fixture_kind": "seeded_release_not_signature_proof"}))
    finally:
        await engine.dispose()


asyncio.run(main())
