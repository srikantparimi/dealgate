"""Owned PostgreSQL sourcing history, source freshness and real row-lock proof."""
import asyncio
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import app.db
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.forecast import ForecastPlan
from app.models.people_sourcing import SourcingRuleSet
from app.services.people_sourcing import RulesInput, get_rules, save_rules, prepare_draft, list_drafts
from tests.test_s21_sourcing_drafts import fixture


url = os.environ["DEALGATE_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path == "/s21_schema"
assert url.startswith("postgresql+psycopg://")
os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID=f"sourcing-pg-{uuid.uuid4()}")
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
app.db.DATABASE_URL = url


async def wait_for_lock(engine, table):
    for _ in range(100):
        async with engine.connect() as observer:
            waiting = await observer.scalar(text("SELECT count(*) FROM pg_stat_activity "
                "WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock' "
                "AND query LIKE :query"), {"query": f"%{table}%"})
        if waiting:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"Actual PostgreSQL lock wait was not observed for {table}")


async def proof():
    engine = create_async_engine(url.replace("+psycopg", "+asyncpg"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            actor, hr, request, source, publication, body = await fixture(session)
            first = await prepare_draft(session, actor=hr, body=body)
            assert await prepare_draft(session, actor=hr, body=body) == first
            november = [row for row in first["snapshot"]["rows"] if row["start"] == "2026-11-01"]
            assert {row["location"]: (row["quantity"], row["sourcing_by"]) for row in november} == {
                "US": (2, "2026-09-17"), "India": (5, "2026-10-02")}
            rules = await get_rules(session, actor=hr)
        async with factory() as writer, factory() as contender:
            root_row = await writer.scalar(select(SourcingRuleSet).where(
                SourcingRuleSet.tenant_id == os.environ["DEALGATE_TENANT_ID"]).with_for_update())
            assert root_row
            revision = RulesInput(expected_version_id=rules["id"], request_key="rules-second",
                reason="Synthetic concurrent policy revision", rules=rules["rules"])

            async def competing_rule():
                try:
                    await save_rules(contender, actor=hr, body=revision.model_copy(update={"request_key": "rules-competing"}))
                except HTTPException as error:
                    await contender.rollback()
                    assert error.status_code == 409
                    return
                raise AssertionError("Stale rule revision accepted")

            pending = asyncio.create_task(competing_rule())
            await wait_for_lock(engine, "sourcing_rule_set")
            rules = await save_rules(writer, actor=hr, body=revision)
            await asyncio.wait_for(pending, 10)
        async with factory() as writer, factory() as contender:
            await writer.execute(select(ForecastPlan.id).where(ForecastPlan.id == source.plan_id).with_for_update())
            revision = body.model_copy(update={"expected_draft_version_id": uuid.UUID(first["id"]),
                "expected_rule_version_id": uuid.UUID(rules["id"]), "request_key": "draft-second"})

            async def competing_draft():
                try:
                    await prepare_draft(contender, actor=hr, body=revision.model_copy(update={"request_key": "draft-competing"}))
                except HTTPException as error:
                    await contender.rollback()
                    assert error.status_code == 409
                    return
                raise AssertionError("Stale draft revision accepted")

            pending = asyncio.create_task(competing_draft())
            await wait_for_lock(engine, "forecast_plan")
            second = await prepare_draft(writer, actor=hr, body=revision)
            assert second["revision"] == 2
            await asyncio.wait_for(pending, 10)
        async with factory() as session:
            history = await list_drafts(session, actor=hr, publication_id=body.publication_id)
            assert history["state"] == "current" and len(history["items"]) == 2
            count = await session.scalar(text("SELECT count(*) FROM audit_event WHERE entity='sourcing_draft' "
                "AND entity_id=:id"), {"id": first["draft_id"]})
            assert count == 2
        return {"rule_lock_wait": "observed", "draft_lock_wait": "observed", "stale_writes": "409",
            "draft_versions": 2, "draft_audits": count, "headcount": 7, "dates": ["2026-09-17", "2026-10-02"]}
    finally:
        await engine.dispose()


command.downgrade(config, "20261002_0057_people_demand")
command.upgrade(config, "head")
results = asyncio.run(proof())
try:
    command.downgrade(config, "20261002_0057_people_demand")
except RuntimeError as error:
    assert "sourcing history" in str(error)
else:
    raise AssertionError("Downgrade discarded sourcing history")
print(json.dumps({"migration": "0058", "empty_roundtrip": "passed", "populated_downgrade": "refused", **results}))
