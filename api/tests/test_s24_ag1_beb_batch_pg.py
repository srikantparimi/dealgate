"""S24-AG1 lane BE-B — B7 / T4 / T5 on PostgreSQL (a scratch database per test; never staging).

What SQLite cannot show: two real starts at the same moment (the settings row lock and the running_guard unique
index leave exactly one batch), a 67-client run that commits in chunks of 25 within the 60-second budget, a
killed job resumed by the worker step without duplicates, and the shared standard object surviving a detach
and a client deletion with foreign keys enforced.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select

from app.audit import verify_chain
from app.models.agreements import AgreementBatch, AgreementsSettings
from app.models.client import Agreement, Client
from app.models.deletion import DeletionJob
from app.models.user import User
from app.services import agreement_batches, agreements_service
from app.services.deletion_storage import key_is_referenced
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_beb_client import ADMIN, BUCKET, TODAY, env, seed  # noqa: F401  (env: fixture)

pytestmark = POSTGRES

BOTH = ["NDA", "MSA"]


class Killed(BaseException):
    pass


async def _admin(session) -> User:
    return await session.get(User, ADMIN.id)


async def test_two_starts_at_once_leave_exactly_one_batch(env):  # noqa: F811
    async with scratch_postgres() as (_engine, factory):
        async with factory() as session:
            await seed(session)

        async def start(key: str):
            async with factory() as session:
                try:
                    return await agreement_batches.start(
                        session, actor=await _admin(session), kinds=BOTH, include_net_new=True,
                        idempotency_key=key, confirm="ATTACH 5")
                except HTTPException as exc:
                    return exc.status_code

        results = await asyncio.gather(start("left"), start("right"))
        assert sorted(type(r).__name__ for r in results) == ["int", "tuple"]
        assert 409 in results
        same = await asyncio.gather(start("again"), start("again"))
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(AgreementBatch)) == 1
        assert all(r == 409 for r in same)  # the first batch still runs: a new key waits


async def test_a_67_client_batch_commits_in_chunks_resumes_after_a_kill_and_undoes(env):  # noqa: F811
    async with scratch_postgres() as (engine, factory):
        async with factory() as session:
            await seed(session, extra_existing=62)  # 2 + 62 existing, plus 3 net new past stage 1 = 67
            batch_id, created = await agreement_batches.start(
                session, actor=await _admin(session), kinds=BOTH, include_net_new=True,
                idempotency_key="sixty-seven", confirm="ATTACH 67")
        assert created
        commits: list[float] = []

        def on_commit(conn):  # noqa: ARG001
            commits.append(time.monotonic())

        async def kill(_batch_id):
            raise Killed

        event.listen(engine.sync_engine, "commit", on_commit)
        try:
            started = time.monotonic()
            with pytest.raises(Killed):
                await agreement_batches.run_batch(factory, batch_id, on_chunk=kill)
            async with factory() as session:
                batch = await session.get(AgreementBatch, batch_id)
                assert (batch.status, batch.done_count, batch.attached_count) == ("running", 25, 50)
            resumed = await agreement_batches.resume_stale(factory, now=datetime.now(UTC) + timedelta(minutes=5))
            elapsed = time.monotonic() - started
        finally:
            event.remove(engine.sync_engine, "commit", on_commit)
        print(f"T13 67-client batch: {elapsed:.2f}s across {len(commits)} commits")
        assert resumed == [{"batch": "AG-0001", "was": "running", "now": "done"}]
        assert len(commits) == 4  # 25 (killed after commit), then 25, 17 and the finish
        assert elapsed < 60
        async with factory() as session:
            batch = await session.get(AgreementBatch, batch_id)
            assert (batch.status, batch.done_count, batch.attached_count, batch.attached_clients,
                    batch.skipped_count) == ("done", 67, 134, 67, 0)
            pairs = (await session.execute(select(Agreement.client_id, Agreement.kind))).all()
            assert len(pairs) == len(set(pairs)) == 134
            assert {r for (r,) in (await session.execute(select(Agreement.uploaded_by)))} == {ADMIN.id}
            settings = await session.get(AgreementsSettings, 1)
            assert settings.cutover_date == TODAY
            assert await session.scalar(select(func.count()).select_from(Client).where(
                Client.relationship.is_(None))) == 0
            assert await verify_chain(session)
            undo_id, started_undo = await agreement_batches.start_undo(session, actor=await _admin(session),
                                                                         label="AG-0001")
        assert started_undo
        assert await agreement_batches.run_undo(factory, undo_id) == "undone"
        async with factory() as session:
            batch = await session.get(AgreementBatch, batch_id)
            assert (batch.status, batch.undone_count, batch.running_guard) == ("undone", 134, None)
            assert await session.scalar(select(func.count()).select_from(Agreement)) == 0
            assert (await session.get(AgreementsSettings, 1)).cutover_date == TODAY
            assert await verify_chain(session)


async def test_the_shared_standard_object_survives_a_detach_and_a_client_deletion(env):  # noqa: F811
    from app.services.parent_deletion import request_client_deletion

    async with scratch_postgres() as (_engine, factory):
        async with factory() as session:
            seeded = await seed(session)
            standard_key = seeded.standards["NDA"].file_key
            local = Client(name="Local only client")
            session.add(local)
            await session.commit()
            admin = await _admin(session)
            for client_id in (seeded.clients["atlas"], seeded.clients["beacon"], local.id):
                await agreements_service.attach_standard(session, actor=admin, client_id=client_id, kind="NDA")
            await agreements_service.set_mark(session, actor=admin, client_id=local.id, kind="MSA",
                                              reason="other", marked_on=TODAY, note=None)
            detached = await agreements_service.detach(session, actor=admin, client_id=seeded.clients["atlas"],
                                                       kind="NDA")
            assert detached.job is None
            job = await request_client_deletion(session, actor_id=admin.id, client_id=local.id)
            await session.commit()
            assert job.objects == [] and job.summary["counts"]["agreement_marks"] == 1
            assert await session.scalar(select(func.count()).select_from(DeletionJob)) == 1
            assert await key_is_referenced(session, BUCKET, standard_key)
            assert await session.scalar(select(func.count()).select_from(Agreement).where(
                Agreement.file_key == standard_key)) == 1  # Beacon still holds it
            assert await session.get(Client, local.id) is None
            assert uuid.UUID(str(seeded.clients["beacon"])) in {
                r for (r,) in await session.execute(select(Agreement.client_id))}
