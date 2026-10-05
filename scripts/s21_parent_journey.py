"""Real browser/API/PostgreSQL/worker/S3 parent retention proof in owned runtime."""

import asyncio
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from urllib.parse import urlparse

import boto3
import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.actual import FinancialActual, FinancialImportBatch
from app.models.approval import ApprovalPackage
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.deletion import DeletionJob
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.models.sow import Sow, SowVersion
from app.models.user import User
from app.services.deletion_cleanup import remove_object_versions

ROOT = Path(__file__).resolve().parents[1]


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/s21_lead"
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8210)) != 0, "Owned API port must be free; never replace another process"
    buckets = {"sow": os.environ["SOW_BUCKET"], "agreement": os.environ["AGREEMENTS_BUCKET"]}
    assert buckets == {"sow": "officeapp-dev-sows-669810405473", "agreement": "officeapp-dev-agreements-669810405473"}
    run = uuid.uuid4().hex
    tenant = f"parent-{run}"
    prefix = f"s21-isolated/parent/{run}"
    owned = [(buckets["sow"], f"{prefix}/sow.txt"), (buckets["agreement"], f"{prefix}/msa.txt")]
    neighbor = (buckets["sow"], f"{prefix}/sow.txt.sibling")
    env = {**os.environ, "DEALGATE_ENV": "local", "DEALGATE_TENANT_ID": tenant,
        "DEALGATE_TEST_GROUPS": "SystemAdmin,Finance", "AWS_PROFILE": "lm-arbiter-poc",
        "AWS_REGION": "us-east-2", "PYTHONPATH": f"{ROOT / 'api'}:{ROOT}"}
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    s3 = boto3.Session(profile_name="lm-arbiter-poc", region_name="us-east-2").client("s3")
    api = browser = None
    worker_log = api_log = None
    try:
        for bucket, key in owned:
            for version in (b"Synthetic source one", b"Synthetic source two"):
                s3.put_object(Bucket=bucket, Key=key, Body=version)
        s3.put_object(Bucket=neighbor[0], Key=neighbor[1], Body=b"Unrelated exact-key neighbor")
        async with factory() as session:
            email = "s21-browser@example.test"
            owner_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")
            owner = await session.get(User, owner_id)
            if owner is None:
                owner = User(id=owner_id, email=email, name="Browser finance", groups=["SystemAdmin", "Finance"])
                session.add(owner)
            client = Client(id=uuid.uuid4(), name=f"Parent deletion proof {run[:8]}")
            session.add(client)
            await session.flush()
            deal = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner.id, source="manual",
                name="Parent owned released deal", governance_status="Released")
            session.add(deal)
            await session.flush()
            sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
            session.add(sow)
            await session.flush()
            version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, file_s3_key=owned[0][1], file_hash=run,
                uploaded_by=owner.id, extract_status="complete")
            session.add(version)
            await session.flush()
            gm = GmModel(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                version=1, engagement_type="fixed_price")
            session.add(gm)
            await session.flush()
            package = ApprovalPackage(id=uuid.uuid4(), opportunity_id=deal.id, sow_version_id=version.id,
                gm_model_id=gm.id, package_hash=run, status="released", submitted_by=owner.id,
                submitted_at=datetime.now(UTC), released_at=datetime.now(UTC))
            session.add(package)
            await session.flush()
            project = Project(id=uuid.uuid4(), opportunity_id=deal.id, client_id=client.id,
                sow_version_id=version.id, gm_model_id=gm.id, package_id=package.id,
                title=f"Parent retained project {run}", baseline_snapshot_json={"revenue_us": "24680.12", "cost_us": "12340.06"},
                created_by=owner.id)
            batch = FinancialImportBatch(id=uuid.uuid4(), tenant_id=tenant, environment="local", source_system="parent-proof",
                request_key=run, request_hash=run * 2, uploaded_by=owner.id, status="committed", row_count=1)
            session.add_all([project, batch])
            await session.flush()
            fact = FinancialActual(id=uuid.uuid4(), tenant_id=tenant, environment="local", source_system="parent-proof",
                source_id=run, revision=1, batch_id=batch.id, account_id=client.id, original_account_id=client.id,
                gm_model_id=gm.id, original_gm_model_id=gm.id, period_month=date(2026, 9, 1),
                measure="recognized_revenue", amount=Decimal("24680.125"), currency="USD",
                source_date=date(2026, 9, 30), reason="Synthetic independent retention proof")
            session.add_all([fact, Agreement(client_id=client.id, kind="MSA", file_key=owned[1][1],
                filename="synthetic-msa.txt", file_size=20, uploaded_by=owner.id)])
            await session.commit()
            client_id, project_id, fact_id = client.id, project.id, fact.id
        print(json.dumps({"run": run, "tenant": tenant, "client_id": str(client_id)}), flush=True)
        evidence = ROOT / "docs/s21/evidence/baseline"
        api_log = (evidence / "parent-browser-api.log").open("w")
        worker_log = (evidence / "parent-browser-worker.log").open("w")
        api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8210"],
            cwd=ROOT / "api", env=env, stdout=api_log, stderr=subprocess.STDOUT, start_new_session=True)
        async with httpx.AsyncClient() as http:
            deadline = time.monotonic() + 60
            while True:
                assert api.poll() is None, "Owned API exited before readiness"
                try:
                    response = await http.get("http://127.0.0.1:8210/me", headers={"X-Test-User": email})
                    if response.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                assert time.monotonic() < deadline, "Owned API readiness timeout"
                await asyncio.sleep(1)
        browser = await asyncio.create_subprocess_exec("npm", "exec", "playwright", "test",
            "--", "--config=playwright.s21-local.config.ts", "s21-parent-deletion.spec.ts", "--reporter=line",
            cwd=ROOT / "tests/e2e", env={**env, "S21_PARENT_CLIENT": str(client_id),
                "S21_PARENT_PROJECT_TITLE": f"Parent retained project {run}"}, start_new_session=True)
        deadline = time.monotonic() + 210
        while browser.returncode is None:
            assert time.monotonic() < deadline, "Browser journey exceeded its bounded execution time"
            async with factory() as session:
                due = await session.scalar(select(DeletionJob.id).where(DeletionJob.tenant_id == tenant,
                    DeletionJob.environment == "local", DeletionJob.status.in_(("pending", "failed")),
                    or_(DeletionJob.next_attempt_at.is_(None), DeletionJob.next_attempt_at <= datetime.now(UTC))).limit(1))
            if due:
                worker = await asyncio.create_subprocess_exec(sys.executable, "-m", "worker.deletion_cleanup",
                    cwd=ROOT, env=env, stdout=worker_log, stderr=subprocess.STDOUT)
                assert await worker.wait() == 0, "Real cleanup worker failed"
            await asyncio.sleep(2)
        assert await browser.wait() == 0, "Connected parent deletion browser assertions failed"
        async with factory() as session:
            retained = await session.get(Project, project_id)
            actual = await session.get(FinancialActual, fact_id)
            assert retained.client_id is None and retained.opportunity_id is None and retained.source_deleted_at
            assert retained.baseline_snapshot_json == {"revenue_us": "24680.12", "cost_us": "12340.06"}
            assert actual.account_id is None and actual.gm_model_id is None and actual.original_account_id == client_id
            assert actual.amount == Decimal("24680.125")
            jobs = (await session.scalars(select(DeletionJob).where(DeletionJob.tenant_id == tenant))).all()
            assert len(jobs) == 3 and all(job.status == "done" and not job.objects for job in jobs)
            audit = (await session.scalars(select(AuditEvent).where(AuditEvent.entity_id == str(client_id),
                AuditEvent.action == "client.deleted"))).all()
            assert len(audit) == 1 and audit[0].actor_id == owner_id
            assert await session.get(Client, client_id) is None
        for bucket, key in owned:
            contents = s3.list_object_versions(Bucket=bucket, Prefix=key)
            assert all(row["Key"] != key for kind in ("Versions", "DeleteMarkers") for row in contents.get(kind, []))
        assert s3.get_object(Bucket=neighbor[0], Key=neighbor[1])["Body"].read() == b"Unrelated exact-key neighbor"
        print(json.dumps({"run": run, "browser_api_worker_storage": "passed", "retained_recognized_revenue": "24680.125",
            "project_retained": True, "client_deletion_audit_lines": 1, "cleanup_jobs_done": 3}), flush=True)
    finally:
        if browser and browser.returncode is None:
            os.killpg(browser.pid, signal.SIGTERM)
            await browser.wait()
        if api and api.poll() is None:
            os.killpg(api.pid, signal.SIGTERM)
            api.wait(timeout=15)
        for handle in (api_log, worker_log):
            if handle:
                handle.close()
        for bucket, key in [*owned, neighbor]:
            remove_object_versions(s3, bucket, key)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
