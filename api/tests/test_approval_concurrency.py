"""Real Postgres serialization of the two parallel first-stage reviews."""

import asyncio
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.task import Task
from app.services.approvals import submit_package, decide, load_package
from app.services.approval_routing import submission_plan
from tests.test_approval_routing import fixture


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("DEALGATE_POSTGRES_URL"), reason="requires disposable migrated Postgres"
)
async def test_parallel_reviews_advance_once():
    url = os.environ["DEALGATE_POSTGRES_URL"].replace("postgresql://", "postgresql+psycopg://")
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            owner, opp, _, _, people = await fixture(session)
            plan = await submission_plan(session, opportunity_id=opp.id, actor_id=owner.id)
            pkg = await submit_package(
                session, actor_id=owner.id, opportunity_id=opp.id, routing=plan
            )
            package_id = pkg.id

        async def approve(fn):
            async with factory() as session:
                await decide(
                    session,
                    actor_id=people[fn].id,
                    package_id=package_id,
                    function=fn,
                    decision="approve",
                    reason="Concurrent review verified",
                )

        await asyncio.gather(approve("delivery"), approve("hr"))
        async with factory() as session:
            pkg = await load_package(session, package_id)
            assert pkg.status == "pending_finance_legal"
            assert len(pkg.approvals) == 2
            tasks = list(
                (
                    await session.scalars(
                        select(Task).where(Task.owner_id.in_([u.id for u in people.values()]))
                    )
                ).all()
            )
            assert len(tasks) == 4
            assert sum(t.status == "assigned" for t in tasks) == 2
    finally:
        await engine.dispose()
