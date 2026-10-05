"""Real PostgreSQL retained-source race, with a database barrier, not mocks."""

import asyncio
import json
import os
import uuid
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser
from app.models.actual import FinancialActual, FinancialImportBatch
from app.models.client import Client
from app.models.user import User
from app.services.actuals_import import FinancialImportInput, import_financial


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert parsed.hostname in {"localhost", "127.0.0.1"} and parsed.path == "/s21_lead"
    run = uuid.uuid4().hex
    os.environ.update(DEALGATE_ENV="local", DEALGATE_TENANT_ID=f"race-{run}")
    application = f"s21-financial-race-{run}"
    engine = create_async_engine(url, connect_args={"options": f"-c application_name={application}"})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            users = [User(id=uuid.uuid4(), email=f"finance-{i}-{run}@synthetic.invalid", name="Finance race fixture", groups=["Finance"]) for i in range(2)]
            account = Client(id=uuid.uuid4(), name=f"Isolated financial race {run}")
            session.add_all([*users, account])
            await session.commit()
            actors = [AuthUser(u.id, u.email, u.name, ("Finance",)) for u in users]
            original = FinancialImportInput.model_validate({"source_system": run, "idempotency_key": str(uuid.uuid4()),
                "rows": [{"account_id": str(account.id), "source_id": "recognized", "revision": 1,
                    "period_month": "2026-10-01", "measure": "recognized_revenue",
                    "amount": "123456789012345678901234567890.123456789", "currency": "USD",
                    "source_date": "2026-10-01", "reason": "Exact synthetic financial source"}]})
            await import_financial(session, actor=actors[0], body=original)
            fact = await session.scalar(select(FinancialActual).where(FinancialActual.source_system == run))
            assert fact.amount == Decimal("123456789012345678901234567890.123456789")
            await session.execute(delete(Client).where(Client.id == account.id))
            await session.commit()

        async def correct(actor):
            body = original.model_dump(mode="json")
            body["idempotency_key"] = str(uuid.uuid4())
            body["rows"][0].update(revision=2, expected_previous_revision=1, amount="11000.99")
            async with factory() as session:
                try:
                    await import_financial(session, actor=actor, body=FinancialImportInput.model_validate(body))
                    return 201
                except HTTPException as exc:
                    return exc.status_code

        async with engine.connect() as gate:
            await gate.execute(text("SELECT pg_advisory_xact_lock(42424242)"))
            attempts = [asyncio.create_task(correct(actor)) for actor in actors]
            try:
                async with asyncio.timeout(15):
                    while True:
                        await gate.execute(text("SELECT pg_stat_clear_snapshot()"))
                        waiting = await gate.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE application_name=:name AND wait_event_type='Lock'"), {"name": application})
                        if waiting == 2:
                            break
                        await asyncio.sleep(0.05)
            finally:
                await gate.commit()
            results = await asyncio.gather(*attempts, return_exceptions=True)
        assert sorted(str(result) for result in results) == ["201", "409"], repr(results)
        async with factory() as session:
            facts = list((await session.scalars(select(FinancialActual).where(FinancialActual.source_system == run).order_by(FinancialActual.revision))).all())
            batches = list((await session.scalars(select(FinancialImportBatch).where(FinancialImportBatch.source_system == run))).all())
            assert [f.revision for f in facts] == [1, 2] and all(f.account_id is None for f in facts)
            assert sorted(b.status for b in batches) == ["committed", "committed", "failed"]
        print(json.dumps({"run": run, "postgres_race": "passed", "responses": results,
                          "retained_versions": 2, "durable_batches": 3, "exact_numeric": True}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
