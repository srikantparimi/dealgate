"""Seed owned source records, then exercise real editor HTTP/browser/PG revisions.

This is editor integration proof, not extraction, signing or staging acceptance.
"""
import asyncio
import json
import os
import signal
import socket
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from app.models.client import Client
from app.models.gm_model import GmModel
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/s21_lead"
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", 8210)) != 0, "Owned API port must be free"
    run = uuid.uuid4().hex
    env = {**os.environ, "DEALGATE_ENV": "local", "DEALGATE_TENANT_ID": f"editor-{run}",
        "DEALGATE_TEST_GROUPS": "SystemAdmin,Delivery,Finance", "PYTHONPATH": f"{ROOT / 'api'}:{ROOT}"}
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    fixtures = {}
    api = None
    try:
        async with factory() as session:
            email = "s21-browser@example.test"
            owner_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{email}")
            if await session.get(User, owner_id) is None:
                session.add(User(id=owner_id, email=email, name="Editor proof", groups=["SystemAdmin", "Delivery", "Finance"]))
            client = Client(id=uuid.uuid4(), name=f"Editor integration {run[:8]}")
            session.add(client)
            await session.flush()
            for profile in ("fixed_assignment", "recurring_msp", "hybrid", "custom_formula"):
                deal = Opportunity(id=uuid.uuid4(), client_id=client.id, owner_id=owner_id,
                    source="manual", name=f"Editor {profile} {run[:8]}")
                session.add(deal)
                await session.flush()
                sow = Sow(id=uuid.uuid4(), opportunity_id=deal.id)
                session.add(sow)
                await session.flush()
                version = SowVersion(id=uuid.uuid4(), sow_id=sow.id, uploaded_by=owner_id,
                    file_s3_key=f"local-editor-fixture/{run}/{profile}", file_hash=uuid.uuid4().hex,
                    extract_status="complete")
                session.add(version)
                await session.flush()
                fixtures[profile] = {"deal": str(deal.id), "sow": str(sow.id), "version": str(version.id)}
            await session.commit()
        evidence = ROOT / "docs/s21/evidence/baseline"
        with (evidence / "editor-browser-api.log").open("w") as log:
            api = await asyncio.create_subprocess_exec(sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8210",
                cwd=ROOT / "api", env=env, stdout=log, stderr=asyncio.subprocess.STDOUT, start_new_session=True)
            async with httpx.AsyncClient() as http:
                for _ in range(60):
                    assert api.returncode is None
                    try:
                        response = await http.get("http://127.0.0.1:8210/me", headers={"X-Test-User": email})
                        if response.status_code == 200:
                            break
                    except httpx.RequestError:
                        pass
                    await asyncio.sleep(1)
                else:
                    raise AssertionError("Editor API readiness timeout")
            browser = await asyncio.create_subprocess_exec("npm", "exec", "playwright", "test", "--",
                "--config=playwright.s21-local.config.ts", "s21-editor-defects.spec.ts", "--reporter=line",
                cwd=ROOT / "tests/e2e", env={**env, "S21_EDITOR_FIXTURES": json.dumps(fixtures)})
            assert await browser.wait() == 0, "Editor browser workflow failed"
        async with factory() as session:
            for profile, fixture in fixtures.items():
                models = (await session.scalars(select(GmModel).where(GmModel.opportunity_id == uuid.UUID(fixture["deal"]))
                    .order_by(GmModel.version))).all()
                assert len(models) == 2
                assert models[0].id != models[-1].id
                if profile == "custom_formula":
                    assert models[0].commercial_inputs["profile"] == "custom_formula"
                    assert models[0].commercial_snapshot["schedule"]["status"] == "unsupported"
                    assert models[-1].commercial_inputs["profile"] == "fixed_assignment"
                print(json.dumps({"profile": profile, "immutable_versions": len(models),
                    "latest_model": str(models[-1].id), "snapshot_status": models[-1].commercial_snapshot["schedule"]["status"]}), flush=True)
        print(json.dumps({"run": run, "editor_browser_api_postgres": "passed", "staging_verified": False}), flush=True)
    finally:
        if api is not None and api.returncode is None:
            os.killpg(api.pid, signal.SIGTERM)
            await asyncio.wait_for(api.wait(), 15)
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
