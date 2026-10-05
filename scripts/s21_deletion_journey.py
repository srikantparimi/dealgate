"""Isolated PostgreSQL deletion, retained facts and exact versioned S3 cleanup."""

import asyncio
import json
import os
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlparse

import boto3
from app.models.actual import ActualPeriod
from app.models.approval import ApprovalPackage
from app.models.client import Client
from app.models.gm_model import GmModel, ResourceLine
from app.models.notification import Notification
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.deletion import request_sow_deletion
from app.services.deletion_cleanup import process_deletion_jobs, remove_object_versions
from app.services.notifications import queue_notification
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/s21_lead"
    bucket = os.environ["SOW_BUCKET"]
    assert bucket == "officeapp-dev-sows-669810405473"
    run = uuid.uuid4().hex
    os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID=f"deletion-{run}")
    key = f"s21-isolated/deletion/{run}/document.txt"
    sibling_key = key + ".sibling"
    s3 = boto3.Session(profile_name="lm-arbiter-poc", region_name="us-east-2").client("s3")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for body in (b"Synthetic deletion proof version one", b"Synthetic deletion proof version two"):
            s3.put_object(Bucket=bucket, Key=key, Body=body)
        s3.put_object(Bucket=bucket, Key=sibling_key, Body=b"Sibling must survive")
        async with factory() as session:
            owner = User(id=uuid.uuid4(), email=f"deletion-{run}@synthetic.invalid", name="Deletion fixture", groups=["Finance"])
            client = Client(id=uuid.uuid4(), name=f"Isolated deletion {run}")
            session.add_all([owner, client])
            await session.flush()
            deal = Opportunity(id=uuid.uuid4(), source="manual", owner_id=owner.id,
                client_id=client.id, governance_status="Released")
            session.add(deal)
            await session.flush()
            sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
            session.add(sow)
            await session.flush()
            version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, file_s3_key=key,
                file_hash=run, extract_status="complete")
            session.add(version)
            await session.flush()
            gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                version=1, engagement_type="fixed_price")
            session.add(gm)
            await session.flush()
            package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                gm_model_id=gm.id, package_hash=run, status="released", submitted_by=owner.id,
                submitted_at=datetime.now(UTC))
            line = ResourceLine(id=uuid.uuid4(), gm_model_id=gm.id, role="Engineer", seniority="Senior",
                location="US", start_date=date(2026, 10, 1), end_date=date(2026, 10, 31),
                allocation_pct=Decimal(1), billable_hours=Decimal(160), hourly_bill_rate=Decimal(100))
            session.add_all([package, line])
            await session.flush()
            actual = ActualPeriod(id=uuid.uuid4(), gm_model_id=gm.id, resource_line_id=line.id,
                period_month=date(2026, 10, 1), actual_hours=Decimal("16.25"),
                actual_cost=Decimal("812.50"), actual_revenue=Decimal("1625.00"), imported_by=owner.id)
            baseline = {"revenue_us": "16000", "cost_us": "8000"}
            project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=client.id,
                sow_version_id=version.id, gm_model_id=gm.id, package_id=package.id,
                title="Retained synthetic project", baseline_snapshot_json=baseline, created_by=owner.id)
            session.add_all([actual, project])
            await queue_notification(session, user_id=owner.id, category="approval_pending",
                subject="Deleted fixture source", body_md="Synthetic only", related_entity="sow",
                related_entity_id=str(sow.id), channels=("inapp",))
            await session.commit()
            job = await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
            await session.commit()
            await session.refresh(actual)
            await session.refresh(project)
            assert actual.gm_model_id is None and actual.resource_line_id is None
            assert actual.original_gm_model_id == gm.id and actual.original_resource_line_id == line.id
            assert actual.actual_revenue == Decimal("1625.00") and actual.actual_cost == Decimal("812.50")
            assert project.baseline_snapshot_json == baseline and project.source_deleted_at
            assert project.package_id is None and project.sow_version_id is None
            assert await session.scalar(select(Sow.id).where(Sow.id == sow.id)) is None
            assert await session.scalar(select(Notification.id).where(Notification.related_entity_id == str(sow.id))) is None
            assert await session.get(Opportunity, deal.id) is not None
            assert await session.get(Client, client.id) is not None
            try:
                await queue_notification(session, user_id=owner.id, category="approval_pending",
                    subject="Late callback", body_md="Must not persist", related_entity="sow",
                    related_entity_id=str(sow.id), channels=("inapp",))
            except HTTPException as exc:
                assert exc.status_code == 410
            else:
                raise AssertionError("Deleted source accepted a late notification")
            await session.rollback()
            assert await process_deletion_jobs(session, s3=s3) == 1
            await session.refresh(job)
            assert job.status == "done" and job.objects == []
            assert await process_deletion_jobs(session, s3=s3) == 0
            contents = s3.list_object_versions(Bucket=bucket, Prefix=key)
            assert all(row["Key"] != key for kind in ("Versions", "DeleteMarkers") for row in contents.get(kind, []))
            assert s3.get_object(Bucket=bucket, Key=sibling_key)["Body"].read() == b"Sibling must survive"
        print(json.dumps({"run": run, "postgres": "passed", "retained_actual_revenue": "1625.00",
            "retained_actual_cost": "812.50", "retained_project": True,
            "late_notification": 410, "versioned_storage_cleanup": "passed", "prefix_sibling_preserved": True}))
    finally:
        for owned_key in (key, sibling_key):
            remove_object_versions(s3, bucket, owned_key)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
