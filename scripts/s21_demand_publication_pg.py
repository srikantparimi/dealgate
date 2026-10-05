"""Owned scratch PostgreSQL proof for demand history, precision and locking."""
import asyncio
import json
import os
import uuid
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import app.db
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.models.client import Client
from app.models.forecast import ForecastPlan
from app.models.user import User
from app.services.commercial_models import COMPONENT
from app.services.forecast_plans import PlanInput, save_plan
from app.services.people_demand import PublishDemandInput, publish_plan_demand, demand_sources
from tests.test_s21_commercial_profiles import component, staffing

url = os.environ["DEALGATE_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path == "/s21_schema"
assert url.startswith("postgresql+psycopg://")
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID="s21-demand-pg-proof")
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
app.db.DATABASE_URL = url


async def proof():
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    user = AuthUser(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic Delivery", groups=("Delivery",))
    exact = "0.1234567890123456789012345678"
    try:
        async with factory() as session:
            session.add(User(id=user.id, email=user.email, name=user.name, groups=list(user.groups)))
            account = Client(id=uuid.uuid4(), name="Synthetic isolated demand proof")
            session.add(account)
            await session.commit()
            plan_input = PlanInput(account_id=account.id, title="Synthetic staffing plan", idempotency_key=uuid.uuid4(),
                inputs=COMPONENT.dump_python(component(staffing=(staffing(allocation=Decimal(exact)),)), mode="json"),
                probability="0.70", probability_source="Synthetic reviewed assumption", change_reason="PG proof")
            source = await save_plan(session, actor=user, body=plan_input)
            body = PublishDemandInput(plan_id=source.plan_id, expected_source_version_id=source.id,
                expected_publication_version_id=None, request_key=str(uuid.uuid4()), reason="PG publication proof")
            first = await publish_plan_demand(session, actor=user, body=body)
            assert await publish_plan_demand(session, actor=user, body=body) == first
            view = await demand_sources(session, actor=user)
            observed = next(item for item in view["items"] if item["plan_id"] == str(source.plan_id))
            assert observed["lines"][0]["allocation"] == exact
            assert observed["lines"][0]["quantity"] == 2
        async with factory() as writer, factory() as contender:
            await writer.execute(select(ForecastPlan.id).where(ForecastPlan.id == source.plan_id).with_for_update())
            second = body.model_copy(update={"expected_publication_version_id": uuid.UUID(first["version_id"]),
                "request_key": str(uuid.uuid4()), "reason": "First concurrent publication"})
            competing = second.model_copy(update={"request_key": str(uuid.uuid4()), "reason": "Stale concurrent publication"})
            async def compete():
                try:
                    await publish_plan_demand(contender, actor=user, body=competing)
                except HTTPException as error:
                    await contender.rollback()
                    assert error.status_code == 409
                    return "stale-refused"
                raise AssertionError("Stale concurrent publication was accepted")
            pending = asyncio.create_task(compete())
            waiting = 0
            for _ in range(100):
                async with engine.connect() as observer:
                    waiting = (await observer.execute(text("SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname=current_database() AND pid<>pg_backend_pid() "
                        "AND wait_event_type='Lock' AND query LIKE '%forecast_plan%'"))).scalar_one()
                if waiting:
                    break
                await asyncio.sleep(0.02)
            assert waiting, "Actual PostgreSQL source row-lock wait was not observed"
            result = await publish_plan_demand(writer, actor=user, body=second)
            assert result["revision"] == 2
            assert await asyncio.wait_for(pending, 10) == "stale-refused"
        async with factory() as session:
            count = (await session.execute(text("SELECT count(*) FROM demand_publication_version WHERE publication_id=:id"),
                {"id": uuid.UUID(first["publication_id"])})).scalar_one()
            audits = (await session.execute(text("SELECT count(*) FROM audit_event WHERE action='people.demand_published' "
                "AND entity_id=:id"), {"id": first["publication_id"]})).scalar_one()
            assert count == audits == 2
            await save_plan(session, actor=user, plan_id=source.plan_id,
                body=plan_input.model_copy(update={"expected_version_id": source.id, "probability": "0.5"}))
            view = await demand_sources(session, actor=user)
            observed = next(item for item in view["items"] if item["plan_id"] == str(source.plan_id))
            assert observed["state"] == "stale" and observed["lines"] == []
        return {"exact_allocation": exact, "pg_lock_wait": "observed", "stale_write": "409",
            "immutable_versions": count, "audits": audits, "stale_source": "explicit"}
    finally:
        await engine.dispose()


results = asyncio.run(proof())
try:
    command.downgrade(config, "20261002_0056_people_supply")
except RuntimeError as error:
    assert "demand" in str(error).lower()
else:
    raise AssertionError("Downgrade discarded demand history")
from sqlalchemy import create_engine
with create_engine(url).connect() as connection:
    assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261002_0057_people_demand"
print(json.dumps({"migration": "0057", "populated_downgrade": "refused", "head_preserved": True,
    "shared_database_touched": False, **results}))
