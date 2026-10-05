"""Publish synthetic seven-person planning inputs for connected automation proof."""
import asyncio
import json
import os
import uuid
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.forecast_plans import save_plan
from tests.test_s21_people_company_x import plan_request, publish


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname == "127.0.0.1" and parsed.port == 55421 and parsed.path == "/s21_journey"
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            deal = await session.get(Opportunity, uuid.UUID(os.environ["S21_AUTOMATION_DEAL"]))
            assert deal and deal.hubspot_deal_id is None and deal.source == "sow_upload"
            owner = await session.get(User, deal.owner_id)
            assert "officeapp-e2e" in owner.groups and "SystemAdmin" in owner.groups
            actor = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=tuple(owner.groups))
            account = await session.get(Client, deal.client_id)
            request = plan_request(account)
            request.opportunity_id = deal.id
            version = await save_plan(session, actor=actor, body=request)
            publication = await publish(session, actor, version)
            print(json.dumps({"plan_id": str(version.plan_id), "version_id": str(version.id),
                "publication_id": publication["publication_id"], "title": request.title,
                "fixture_kind": "synthetic_planning_not_signature_proof"}))
    finally:
        await engine.dispose()


asyncio.run(main())
