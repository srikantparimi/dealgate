"""Publish a synthetic plan/project pair for explicit staffing mapping UI proof."""
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.gm.demand_source import line_key
from app.models.project import Project
from app.models.user import User
from app.services.forecast_plans import save_plan
from app.services.people_demand import publish_plan_demand
from app.services.people_project_demand import publish_project_demand
from tests.test_s21_demand_publication import publication
from tests.test_s21_forecast_plans import body
from tests.test_s21_project_demand import request


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port == 55421 and parsed.path == "/s21_journey"
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            project = await session.get(Project, uuid.UUID(os.environ["S21_COVERAGE_PROJECT"]))
            scope = project.baseline_snapshot_json["source_scope"]
            assert scope["fixture_grant_id"] and scope["tenant_id"] == "s21-lead"
            if os.environ.get("S21_ARCHIVE_PROJECT") == "1":
                project.archived_at = datetime.now(UTC)
                await session.commit()
                print(json.dumps({"project_id": str(project.id), "fixture_kind": "archive_fault_injection"}))
                return
            owner = await session.get(User, uuid.UUID(scope["owner_id"]))
            user = AuthUser(id=owner.id, name=owner.name, email=owner.email,
                groups=("SystemAdmin", "Finance", "HR", "officeapp-e2e"))
            plan = body(project.client_id)
            plan.title = f"Synthetic staffing replacement {project.id}"
            plan.inputs = project.baseline_snapshot_json["commercial_inputs"]
            version = await save_plan(session, actor=user, body=plan)
            enrichments = {line_key("build", "team-1"): {
                "skills": ["python"], "level": "senior", "evidence": ["Synthetic coverage review"]}}
            a = await publish_plan_demand(session, actor=user, body=publication(version, enrichments=enrichments))
            b = await publish_project_demand(session, actor=user, body=request(project, enrichments=enrichments))
            print(json.dumps({"plan_id": str(version.plan_id), "plan_title": plan.title,
                "account_id": str(project.client_id), "project_id": str(project.id), "project_title": project.title,
                "plan_publication_id": a["publication_id"], "project_publication_id": b["publication_id"],
                "fixture_kind": "seeded_release_not_signature_proof"}))
    finally:
        await engine.dispose()


asyncio.run(main())
