"""S24-AG1 lane BE-B — B7 the one-time attach: dry run, the resumable job, undo (SQLite, foreign keys on).

The job runs inline here (the launcher dependency is replaced), so each committed chunk is observable.
Postgres-only behaviour (two concurrent starts, row locks) is in test_s24_ag1_beb_batch_pg.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import verify_chain
from app.auth import AuthUser
from app.models.agreements import AgreementBatch, AgreementMark, AgreementsSettings
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.user import User
from app.services import agreement_audit, agreement_batches
from tests.test_s24_ag1_beb_client import (  # noqa: F401  (engine, env: fixtures)
    ADMIN,
    BUCKET,
    LEGAL,
    NOW,
    PDF,
    TODAY,
    audit_rows,
    client_for,
    engine,
    env,
    seed,
    upload,
)

BOTH = ["NDA", "MSA"]


def factory_for(session) -> async_sessionmaker:
    return async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)


def inline(factory, **kwargs):
    async def launch(batch_id, phase):
        runner = agreement_batches.run_batch if phase == "run" else agreement_batches.run_undo
        await runner(factory, batch_id, **kwargs)
    return launch


def real(key: str, confirm: str, kinds=BOTH, *, net_new: bool = True, **extra) -> dict:
    return {"kinds": kinds, "dry_run": False, "include_net_new_past_stage_1": net_new, "idempotency_key": key,
            "confirm": confirm, **extra}


class Killed(BaseException):
    """A dead process: not an error the job records, so the batch stays running."""


@pytest.fixture
async def seeded(session, env):  # noqa: F811
    return await seed(session)


async def count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)))


async def test_dry_run_lists_targets_and_exclusions_and_changes_nothing(session, seeded):
    before = (await count(session, Agreement), await count(session, AuditEvent), await count(session, AgreementBatch))
    async with client_for(session, ADMIN) as api:
        both = await api.post("/agreements/batches", json={"kinds": BOTH, "include_net_new_past_stage_1": True})
        existing_only = await api.post("/agreements/batches", json={"kinds": ["MSA"]})
        chosen = await api.post("/agreements/batches", json={
            "kinds": ["NDA"], "include_client_ids": [str(seeded.clients["dune"])],
            "exclude_client_ids": [str(seeded.clients["atlas"])]})
        unknown = await api.post("/agreements/batches", json={"kinds": ["NDA"], "include_client_ids": [str(uuid.uuid4())]})
        empty = await api.post("/agreements/batches", json={"kinds": []})
    assert both.status_code == 200, both.text
    body = both.json()
    assert [(t["name"], t["relationship"], t["included"], t["reason"]) for t in body["targets"]] == [
        ("Atlas Foods", "existing", True, ""),
        ("Beacon Logistics", "existing", True, ""),
        ("Cobalt Systems", "net_new", True, ""),
        ("Falcon Capital", "net_new", True, ""),  # on Hold counts as past stage 1
        ("Harbor Labs", "net_new", True, ""),
        ("Dune Farms", "existing", False, "stage_1_only"),
        ("S21 e2e 1234 Seeded run", "existing", False, "test_data"),
    ]
    assert (body["will_receive"], body["net_new_included"], body["already_hold"], body["net_new_untouched"]) == (
        5, 3, 0, 2)
    assert (body["kinds"], body["existing_included"], body["standard_missing"]) == (BOTH, 2, [])
    rows = existing_only.json()
    assert [(t["name"], t["included"]) for t in rows["targets"]] == [
        ("Atlas Foods", True), ("Beacon Logistics", True), ("Dune Farms", False), ("S21 e2e 1234 Seeded run", False)]
    assert (rows["will_receive"], rows["net_new_included"], rows["net_new_untouched"]) == (2, 0, 5)
    assert [(t["name"], t["included"]) for t in chosen.json()["targets"] if t["included"]] == [
        ("Beacon Logistics", True), ("Dune Farms", True)]
    assert (unknown.status_code, empty.status_code) == (422, 422)
    after = (await count(session, Agreement), await count(session, AuditEvent), await count(session, AgreementBatch))
    assert after == before
    assert await session.get(AgreementsSettings, 1) is None or (await session.get(AgreementsSettings, 1)).cutover_date is None


async def test_a_real_run_needs_the_key_the_exact_phrase_and_every_standard_copy(session, env):  # noqa: F811
    await seed(session, standards=("NDA",))
    async with client_for(session, ADMIN) as api:
        dry = (await api.post("/agreements/batches", json={"kinds": BOTH, "include_net_new_past_stage_1": True})).json()
        assert dry["will_receive"] == 5 and dry["standard_missing"] == ["MSA"]  # the dry run works without one
        no_std = await api.post("/agreements/batches", json=real("k1", "ATTACH 5"))
        wrong = await api.post("/agreements/batches", json=real("k1", "ATTACH 4", ["NDA"]))
        spaced = await api.post("/agreements/batches", json=real("k1", "attach 5", ["NDA"]))
        no_key = await api.post("/agreements/batches", json={**real("", "ATTACH 5", ["NDA"]), "idempotency_key": None})
        long_key = await api.post("/agreements/batches", json=real("k" * 81, "ATTACH 5", ["NDA"]))
    assert no_std.status_code == 422 and no_std.json()["detail"] == "No standard MSA has been uploaded yet. Upload it before attaching it."
    assert wrong.status_code == 422 and wrong.json()["detail"] == "Type ATTACH 5 to confirm."
    assert (spaced.status_code, no_key.status_code, long_key.status_code) == (422, 422, 422)
    assert await count(session, AgreementBatch) == 0 and await count(session, Agreement) == 0
    settings = await session.get(AgreementsSettings, 1)
    assert settings is None or settings.cutover_date is None


async def test_a_real_run_attaches_credits_the_admin_sets_the_cutover_once_and_keeps_net_new(session, seeded,
                                                                                           monkeypatch):
    factory = factory_for(session)
    async with client_for(session, ADMIN, launcher=inline(factory)) as api:
        started = await api.post("/agreements/batches", json=real("first", "ATTACH 5"))
        assert started.status_code == 202, started.text
        batch = started.json()
        cobalt = (await api.get(f"/clients/{seeded.clients['cobalt']}/agreements")).json()
        ember = (await api.get(f"/clients/{seeded.clients['ember']}/agreements")).json()
    assert (batch["id"], batch["status"], batch["created_by"]) == ("AG-0001", "done", "Ada Admin")
    assert (batch["target_count"], batch["done_count"], batch["attached_count"], batch["attached_clients"],
            batch["skipped_count"], batch["undo_would_remove"]) == (5, 5, 10, 5, 0, 10)
    rows = (await session.scalars(select(Agreement))).all()
    assert len(rows) == 10 and {r.source for r in rows} == {"standard"}
    assert {r.uploaded_by for r in rows} == {ADMIN.id}  # the admin who ran it
    assert len({r.batch_id for r in rows}) == 1 and rows[0].batch_id is not None
    settings = await session.get(AgreementsSettings, 1, populate_existing=True)
    assert (settings.cutover_date, settings.set_by) == (TODAY, ADMIN.id)
    stamped = dict((await session.execute(select(Client.name, Client.relationship))).all())
    assert stamped["Cobalt Systems"] == "net_new" and stamped["Atlas Foods"] == "existing"
    assert all(value is not None for value in stamped.values())  # every client, once
    # Net-new clients that received a copy stay net new and show the standard copy; nothing is flagged.
    assert (cobalt["relationship"], cobalt["provisional"], cobalt["nda"]["state"], cobalt["needs_attention"]) == (
        "net_new", False, "standard", False)
    assert cobalt["nda"]["batch_id"] == "AG-0001" and cobalt["nda"]["uploaded_by"] == "Ada Admin"
    assert (ember["relationship"], ember["nda"]["state"]) == ("net_new", "due_later")
    assert len(await audit_rows(session, agreement_audit.BATCH_STARTED)) == 1
    attached = await audit_rows(session, agreement_audit.BATCH_ATTACHED)
    assert sorted(a.after["client_name"] for a in attached) == [
        "Atlas Foods", "Beacon Logistics", "Cobalt Systems", "Falcon Capital", "Harbor Labs"]
    assert {a.actor_id for a in attached} == {ADMIN.id}
    (run,) = await audit_rows(session, agreement_audit.BATCH_RUN)
    assert agreement_audit.activity_text(run.action, run.after, run.before) == (
        "Attached standard NDA and MSA to 5 clients (batch AG-0001): 2 existing and 3 net new in the pipeline")
    assert len(await audit_rows(session, agreement_audit.RELATIONSHIP_STAMPED)) == 9
    assert len(await audit_rows(session, agreement_audit.CUTOVER_SET)) == 1
    assert await verify_chain(session)

    # A second batch the next day: the cutover and every relationship stay; holders are not offered again.
    monkeypatch.setenv("DEALGATE_NOW", (NOW + timedelta(days=1)).isoformat())
    async with client_for(session, ADMIN, launcher=inline(factory)) as api:
        dry = (await api.post("/agreements/batches", json={"kinds": BOTH, "include_net_new_past_stage_1": True})).json()
        assert dry["will_receive"] == 0 and dry["already_hold"] == 5
        second = await api.post("/agreements/batches", json=real(
            "second", "ATTACH 1", include_client_ids=[str(seeded.clients["dune"])]))
    assert second.status_code == 202 and second.json()["id"] == "AG-0002" and second.json()["status"] == "done"
    settings = await session.get(AgreementsSettings, 1, populate_existing=True)
    assert settings.cutover_date == TODAY
    assert len(await audit_rows(session, agreement_audit.RELATIONSHIP_STAMPED)) == 9
    assert len(await audit_rows(session, agreement_audit.CUTOVER_SET)) == 1


async def test_a_repeated_key_returns_the_original_and_a_second_batch_waits(session, seeded):
    async with client_for(session, ADMIN) as api:  # the job is never launched: the batch stays running
        first = await api.post("/agreements/batches", json=real("same", "ATTACH 2", net_new=False))
        again = await api.post("/agreements/batches", json=real("same", "ATTACH 2", net_new=False))
        other = await api.post("/agreements/batches", json=real("other", "ATTACH 2", net_new=False))
        undo = await api.post("/agreements/batches/AG-0001/undo")
        listed = (await api.get("/agreements/batches")).json()["items"]
        unknown = await api.get("/agreements/batches/AG-0999")
    assert (first.status_code, again.status_code) == (202, 202)
    assert first.json()["id"] == again.json()["id"] == "AG-0001" and again.json()["status"] == "running"
    assert other.status_code == 409 and other.json()["detail"] == "Batch AG-0001 is still running. Wait for it to finish."
    assert undo.status_code == 409
    assert [b["id"] for b in listed] == ["AG-0001"] and unknown.status_code == 404
    assert await count(session, AgreementBatch) == 1


async def test_chunks_commit_every_25_and_a_killed_job_resumes_without_duplicates(session, env, engine):  # noqa: F811
    await seed(session, extra_existing=30)
    admin = await session.get(User, ADMIN.id)
    batch_id, created = await agreement_batches.start(
        session, actor=admin, kinds=BOTH, include_net_new=False, idempotency_key="kill", confirm="ATTACH 32")
    assert created
    factory = factory_for(session)

    async def kill(_batch_id):
        raise Killed

    with pytest.raises(Killed):
        await agreement_batches.run_batch(factory, batch_id, on_chunk=kill)
    batch = await session.get(AgreementBatch, batch_id, populate_existing=True)
    assert (batch.status, batch.done_count, batch.attached_count, batch.running_guard) == ("running", 25, 50, True)
    # While the job is dead, a writer gives a later target its own copy: the resume skips it.
    targets = [uuid.UUID(v) for v in batch.target_client_ids]
    async with client_for(session, LEGAL) as api:
        assert (await api.post(f"/clients/{targets[-1]}/agreements/NDA/client-copy",
                               **upload("own.pdf", PDF))).status_code == 201
    commits: list[int] = []

    def on_commit(conn):  # noqa: ARG001
        commits.append(1)

    event.listen(engine.sync_engine, "commit", on_commit)
    try:
        resumed = await agreement_batches.resume_stale(factory, now=datetime.now(UTC) + timedelta(minutes=5))
    finally:
        event.remove(engine.sync_engine, "commit", on_commit)
    assert resumed == [{"batch": "AG-0001", "was": "running", "now": "done"}]
    assert len(commits) == 2  # the last chunk of 7 clients, then the finish
    batch = await session.get(AgreementBatch, batch_id, populate_existing=True)
    assert (batch.status, batch.done_count, batch.attached_count, batch.skipped_count, batch.running_guard) == (
        "done", 32, 63, 1, None)
    assert batch.attached_count + batch.skipped_count == 32 * 2
    pairs = (await session.execute(select(Agreement.client_id, Agreement.kind))).all()
    assert len(pairs) == len(set(pairs)) == 64
    assert len(await audit_rows(session, agreement_audit.BATCH_ATTACHED)) == 32
    assert await agreement_batches.resume_stale(factory, now=datetime.now(UTC) + timedelta(minutes=5)) == []


async def test_undo_removes_only_this_batch_standard_rows(session, seeded):
    factory = factory_for(session)
    c = seeded.clients
    async with client_for(session, ADMIN, launcher=inline(factory)) as api:
        assert (await api.post("/agreements/batches", json=real("run", "ATTACH 5"))).status_code == 202
        # Made since the batch: a client copy, a mark in place of a detached copy, and a manual attachment.
        assert (await api.post(f"/clients/{c['atlas']}/agreements/NDA/client-copy",
                               **upload("atlas.pdf", PDF))).status_code == 201
        assert (await api.delete(f"/clients/{c['beacon']}/agreements/MSA")).status_code == 200
        assert (await api.put(f"/clients/{c['beacon']}/agreements/MSA/mark",
                              json={"reason": "other", "marked_on": TODAY.isoformat()})).status_code == 200
        assert (await api.post(f"/clients/{c['ember']}/agreements/NDA/attach-standard")).status_code == 201
        before = (await api.get("/agreements/batches/AG-0001")).json()
        assert before["undo_would_remove"] == 8
        undo = await api.post("/agreements/batches/ag-0001/undo")
        again = await api.post("/agreements/batches/AG-0001/undo")
        after = (await api.get("/agreements/batches/AG-0001")).json()
    assert undo.status_code == 202, undo.text
    assert (undo.json()["status"], undo.json()["undone_count"], undo.json()["undone_by"]) == ("undone", 8, "Ada Admin")
    assert again.status_code == 409 and again.json()["detail"] == "Batch AG-0001 is already undone."
    assert after["undo_would_remove"] == 0 and after["undone_at"]
    left = {(r.client_id, r.kind): r for r in (await session.scalars(select(Agreement))).all()}
    assert set(left) == {(c["atlas"], "NDA"), (c["ember"], "NDA")}
    assert left[(c["atlas"], "NDA")].source == "client" and left[(c["ember"], "NDA")].batch_id is None
    assert await session.scalar(select(func.count()).select_from(AgreementMark).where(
        AgreementMark.client_id == c["beacon"], AgreementMark.removed_at.is_(None))) == 1
    settings = await session.get(AgreementsSettings, 1, populate_existing=True)
    assert settings.cutover_date == TODAY  # the cutover and every relationship stay
    assert await session.scalar(select(func.count()).select_from(Client).where(Client.relationship.is_(None))) == 0
    (undone,) = await audit_rows(session, agreement_audit.BATCH_UNDONE)
    assert agreement_audit.activity_text(undone.action, undone.after) == (
        "Undid batch AG-0001: removed 8 standard attachments")
    assert len(await audit_rows(session, agreement_audit.BATCH_DETACHED)) == 5
    assert await verify_chain(session)


async def test_a_failed_job_releases_the_guard_and_can_be_undone(session, seeded, monkeypatch):
    factory = factory_for(session)

    async def broken(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(agreement_batches, "_run_chunk", broken)
    async with client_for(session, ADMIN, launcher=inline(factory)) as api:
        failed = (await api.post("/agreements/batches", json=real("boom", "ATTACH 5"))).json()
        monkeypatch.undo()
        retry = await api.post("/agreements/batches", json=real("retry", "ATTACH 5"))
        undo = await api.post("/agreements/batches/AG-0001/undo")
    assert (failed["status"], failed["error"]) == (
        "failed", "The batch stopped after 0 of 5 clients. Run it again to finish; clients that already hold a copy "
        "are skipped.")
    assert retry.status_code == 202 and retry.json()["status"] == "done"
    assert undo.status_code == 202 and undo.json()["status"] == "undone" and undo.json()["undone_count"] == 0
    (row,) = await audit_rows(session, agreement_audit.BATCH_FAILED)
    assert row.after["label"] == "AG-0001" and row.after["phase"] == "run"
    assert isinstance(row.after["attached_clients"], int) and row.after["kinds"]
    # The stop reads in the Activity feed as how far the run got (review finding: a partial run was silent).
    assert agreement_audit.activity_action(row.action, row.after) == "batch_run"
    assert agreement_audit.activity_text(row.action, row.after).startswith("Batch AG-0001 stopped ")


def test_a_stopped_batch_or_undo_reads_as_how_far_it_got():
    failed, text, action = agreement_audit.BATCH_FAILED, agreement_audit.activity_text, agreement_audit.activity_action
    run = {"label": "AG-0003", "phase": "run", "kinds": ["NDA", "MSA"], "attached_clients": 25}
    assert text(failed, run) == "Batch AG-0003 stopped after attaching standard NDA and MSA to 25 clients"
    assert action(failed, run) == "batch_run"
    assert text(failed, {**run, "attached_clients": 0}) == "Batch AG-0003 stopped before attaching anything"
    assert text(failed, {"label": "AG-0003", "phase": "run"}) == "Batch AG-0003 stopped before it finished"
    undo = {"label": "AG-0003", "phase": "undo", "undone_count": 1}
    assert text(failed, undo) == "Undo of batch AG-0003 stopped after removing 1 standard attachment"
    assert action(failed, undo) == "batch_undone"
    assert text(failed, {**undo, "undone_count": 0}) == "Undo of batch AG-0003 stopped before it finished"


async def test_a_test_identity_cannot_run_or_undo_a_real_batch_outside_local(session, seeded, monkeypatch):
    bot = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000e2"), "bot@example.test", "E2E Bot",
                   ("SystemAdmin", "officeapp-e2e"))
    session.add(User(id=bot.id, email=bot.email, name=bot.name, groups=list(bot.groups)))
    await session.commit()
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "ag1-staging-like")
    async with client_for(session, bot) as api:
        dry = await api.post("/agreements/batches", json={"kinds": BOTH, "include_net_new_past_stage_1": True})
        started = await api.post("/agreements/batches", json=real("bot", "ATTACH 0"))
        undo = await api.post("/agreements/batches/AG-0001/undo")
    assert dry.status_code == 200 and dry.json()["targets"] == []  # a test identity sees only its fixtures
    assert (started.status_code, undo.status_code) == (403, 403)
    assert await count(session, AgreementBatch) == 0


async def test_the_cleanup_worker_resume_step_never_raises(capsys):
    from worker.deletion_cleanup import resume_agreement_batches

    def broken_factory():
        raise RuntimeError("no database")

    await resume_agreement_batches(broken_factory)
    assert '"worker": "agreement_batches", "error": "RuntimeError"' in capsys.readouterr().out


async def test_the_cli_continues_a_batch_by_label_and_prints_its_status(session, seeded, monkeypatch, capsys):
    import app.db
    from worker import agreement_batches as cli

    monkeypatch.setattr(app.db, "session_factory", factory_for(session))
    async with client_for(session, ADMIN) as api:  # not launched: the batch waits as a dead job would
        assert (await api.post("/agreements/batches", json=real("cli", "ATTACH 5"))).status_code == 202
    assert await cli._run(["run", "ag-0001"]) == 0
    assert await cli._run(["status", "AG-0001"]) == 0
    assert await cli._run(["run", "AG-0002"]) == 1  # nothing running under that label
    out = capsys.readouterr().out
    assert '"resumed": [{"batch": "AG-0001", "was": "running", "now": "done"}]' in out
    assert '"status": "done"' in out and '"attached_count": 10' in out
