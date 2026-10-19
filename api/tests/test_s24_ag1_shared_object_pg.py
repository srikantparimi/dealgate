"""S24-AG1 T4 (lane T-B): one standard object shared by many clients, on PostgreSQL.

A standard copy is ONE stored object; every client it is attached to has its own agreement row pointing at it
(directive B6/B7, contract DocState ``standard``). What these tests add to test_s24_ag1_beb_batch_pg.py:

* the object is never copied (no storage write for a batch or a manual attach) and every holder's row and
  history point at the same key and the same standard version;
* detaching one holder, then every holder, leaves the object in the bucket: no cleanup job is queued and the
  real cleanup worker entry point (``worker/deletion_cleanup.py``, which runs ``process_deletion_jobs``) never
  asks the bucket to delete it, while it does remove a deleted client's own copy; deleting the only client that
  holds a standard version queues nothing for that object;
* the cleanup worker re-checks every key it is given: a job that names a standard key (current or superseded),
  a client's current copy or a file kept only in a client's history removes none of them, and removes an
  unreferenced key;
* undoing one batch leaves every other user of the same object alone: rows of another batch and manual
  attachments (``batch_id`` NULL) keep their rows, and the object stays.

Each test runs on its own migrated scratch database (tests/s24_pg.py); every file is synthetic bytes. The
helpers below (bucket double, launcher, per-request API client, snapshot) are shared with the lane's T5 and
T13 files.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.agreements import (
    AgreementBatch,
    AgreementHubspotMap,
    AgreementMark,
    AgreementsSettings,
    StandardAgreement,
)
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers import agreements, agreements_workspace, client_agreements, clients, deletion
from app.routers.agreements import get_batch_launcher
from app.services import agreement_audit, agreement_batches
from app.services.deletion_storage import key_is_referenced
from app.services.parent_deletion import queue_storage_cleanup
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_beb_client import ADMIN, BUCKET, LEGAL, PDF, env, seed, upload  # noqa: F401  (env: fixture)

pytestmark = POSTGRES

BOTH = ("NDA", "MSA")
# A second SystemAdmin, so "the admin who ran it" is never confused with the standard copy's uploader (ADMIN).
RUNNER = AuthUser(uuid.UUID("00000000-0000-4000-8000-0000000000e5"), "bree@example.test", "Bree Batch",
                  ("SystemAdmin",))


# --- shared helpers (imported by test_s24_ag1_batch_t5_pg.py, test_s24_ag1_cost.py and test_s24_ag1_cost_pg.py) --


class VersionedStore(StubS3):
    """The agreements bucket: StubS3 for the routes, plus the boto3 surface the cleanup worker uses
    (``list_object_versions`` paging and ``delete_objects``). Every stored version, every write and every
    delete request is recorded, so a test can say an object was never even asked to be deleted."""

    def __init__(self, bucket: str = BUCKET) -> None:
        super().__init__(bucket=bucket)
        self.versions: dict[str, list[str]] = {}
        self.puts: list[str] = []
        self.delete_requests: list[str] = []

    def hold(self, key: str, body: bytes = PDF) -> None:
        """An object already in the bucket (for example a standard copy uploaded before the test)."""
        self.objects[key] = body
        self.versions.setdefault(key, []).append(f"v{len(self.versions.get(key, [])) + 1}")

    def put_object_at(self, key: str, content_type: str, body: bytes) -> str:
        stored = super().put_object_at(key, content_type, body)
        self.versions.setdefault(stored, []).append(f"v{len(self.versions.get(stored, [])) + 1}")
        self.puts.append(stored)
        return stored

    def get_paginator(self, name: str):
        assert name == "list_object_versions"
        return self

    def paginate(self, *, Bucket: str, Prefix: str):  # noqa: N803 — boto3 names
        assert Bucket == self.bucket
        return [{"Versions": [{"Key": key, "VersionId": version} for key, versions in sorted(self.versions.items())
                              if key.startswith(Prefix) for version in versions],
                 "DeleteMarkers": []}]

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]):  # noqa: N803
        assert Bucket == self.bucket
        for item in Delete["Objects"]:
            key = item["Key"]
            self.delete_requests.append(key)
            left = [v for v in self.versions.get(key, []) if v != item["VersionId"]]
            if left:
                self.versions[key] = left
            else:
                self.versions.pop(key, None)
                self.objects.pop(key, None)
        return {}


class Jobs:
    """The batch launcher (``get_batch_launcher``).

    ``inline``: the job runs inside the request, so the 202 already reads done. ``background``: an asyncio task,
    as the API runs it (``launch_in_background``). ``deferred``: only recorded; the test runs the job itself."""

    def __init__(self, factory, mode: str = "inline", **kwargs: Any) -> None:
        self.factory, self.mode, self.kwargs = factory, mode, kwargs
        self.calls: list[tuple[uuid.UUID, str]] = []
        self.tasks: list[asyncio.Task] = []

    async def __call__(self, batch_id: uuid.UUID, phase: str) -> None:
        self.calls.append((batch_id, phase))
        if self.mode == "deferred":
            return
        runner = agreement_batches.run_batch if phase == "run" else agreement_batches.run_undo
        job = runner(self.factory, batch_id, **self.kwargs)
        if self.mode == "inline":
            await job
        else:
            self.tasks.append(asyncio.get_running_loop().create_task(job))


@asynccontextmanager
async def api_for(factory, user: AuthUser, *, storage: StubS3 | None = None, launcher=None):
    """The production routers with one database session per request (as ``app.db.get_session`` does)."""
    app = FastAPI()
    for router in (clients.router, agreements_workspace.router, agreements.router, client_agreements.router,
                   deletion.router):
        app.include_router(router)
    app.dependency_overrides[current_user] = lambda: user

    async def _db():
        async with factory() as session:
            yield session

    bucket = storage if storage is not None else VersionedStore()
    jobs = launcher if launcher is not None else Jobs(factory, "deferred")
    app.dependency_overrides[get_session] = _db
    app.dependency_overrides[get_evidence_s3] = lambda: bucket
    app.dependency_overrides[get_batch_launcher] = lambda: jobs
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t-b") as api:
        yield api


def real(key: str, confirm: str | None, kinds=BOTH, *, net_new: bool = True, **extra: Any) -> dict[str, Any]:
    """A real (non-dry) POST /agreements/batches body."""
    return {"kinds": list(kinds), "dry_run": False, "include_net_new_past_stage_1": net_new,
            "idempotency_key": key, "confirm": confirm, **extra}


async def count(session, model, *where) -> int:
    return int(await session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


async def add_user(factory, user: AuthUser) -> None:
    async with factory() as session:
        session.add(User(id=user.id, email=user.email, name=user.name, groups=list(user.groups)))
        await session.commit()


async def snapshot(factory) -> dict[str, Any]:
    """Everything an agreement write could change: row counts of every table it touches, the audit tail, the
    settings row, every client's relationship, every agreement row, mark and batch. (A user's last_login is
    the sign-in time ensure_user keeps; it is not business state and is left out.)"""
    async with factory() as s:
        out: dict[str, Any] = {model.__tablename__: await count(s, model) for model in (
            Client, Opportunity, Agreement, AgreementFileVersion, AgreementMark, AgreementBatch, StandardAgreement,
            AgreementHubspotMap, DeletionJob, User, AuditEvent)}
        out["audit_tail"] = [tuple(r) for r in (await s.execute(
            select(AuditEvent.id, AuditEvent.action, AuditEvent.row_hash)
            .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc()).limit(5))).all()]
        settings = await s.get(AgreementsSettings, 1)
        out["settings"] = None if settings is None else (settings.cutover_date, settings.set_by, settings.set_at)
        out["relationships"] = sorted((str(r[0]), r[1], r[2], str(r[3]), str(r[4])) for r in (await s.execute(
            select(Client.id, Client.relationship, Client.relationship_basis, Client.relationship_set_by,
                   Client.relationship_set_at))).all())
        out["agreements"] = sorted((str(r[0]), str(r[1]), r[2], r[3], str(r[4]), r[5]) for r in (await s.execute(
            select(Agreement.id, Agreement.client_id, Agreement.kind, Agreement.source, Agreement.batch_id,
                   Agreement.version_no))).all())
        out["marks"] = sorted((str(r[0]), str(r[1]), r[2], str(r[3])) for r in (await s.execute(
            select(AgreementMark.id, AgreementMark.client_id, AgreementMark.kind, AgreementMark.removed_at))).all())
        out["batches"] = sorted(tuple(r) for r in (await s.execute(
            select(AgreementBatch.label, AgreementBatch.status, AgreementBatch.done_count,
                   AgreementBatch.attached_count, AgreementBatch.skipped_count, AgreementBatch.undone_count,
                   AgreementBatch.running_guard))).all())
    return out


async def run_cleanup_worker(factory, store: VersionedStore, monkeypatch, capsys) -> int:
    """worker/deletion_cleanup.py ``main()`` — the every-minute entry point — on this database and bucket.
    Returns how many cleanup jobs it handled."""
    import worker.deletion_cleanup as cleanup
    from app.integrations import s3_sow

    monkeypatch.setattr(cleanup, "session_factory", factory)
    monkeypatch.setattr(s3_sow, "_client", lambda: store)
    capsys.readouterr()
    await cleanup.main()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    (summary,) = [line for line in lines if line.get("worker") == "deletion_cleanup"]
    return int(summary["handled"])


# --- T4 ----------------------------------------------------------------------------------------------------


async def test_one_standard_object_serves_every_holder_and_outlives_a_detach_the_last_holder_and_a_client_deletion(
        env, monkeypatch, capsys):  # noqa: F811
    store = VersionedStore()
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            seeded = await seed(s)
            kiln = Client(name="Kiln Works Local")  # no HubSpot company and no deals: it can be deleted
            s.add(kiln)
            await s.commit()
        nda, msa = seeded.standards["NDA"], seeded.standards["MSA"]
        for standard in (nda, msa):
            store.hold(standard.file_key)  # uploaded before the test
        c = seeded.clients
        holders = [c[k] for k in ("atlas", "beacon", "cobalt", "falcon", "harbor")]

        # One stored object, many holders: the batch and a manual attach point at it; nothing is copied.
        async with api_for(factory, ADMIN, storage=store, launcher=Jobs(factory)) as admin, \
                api_for(factory, LEGAL, storage=store) as legal:
            run = await admin.post("/agreements/batches", json=real("t4-shared", "ATTACH 5"))
            assert run.status_code == 202 and run.json()["status"] == "done", run.text
            assert (await legal.post(f"/clients/{kiln.id}/agreements/NDA/attach-standard")).status_code == 201
            own = await legal.post(f"/clients/{kiln.id}/agreements/MSA/client-copy", **upload("kiln-msa.pdf", PDF))
            assert own.status_code == 201, own.text
            panels = [(await legal.get(f"/clients/{cid}/agreements")).json() for cid in (*holders, kiln.id)]
        (kiln_msa_key,) = store.puts  # the only object written: Kiln's own MSA
        assert set(store.objects) == {nda.file_key, msa.file_key, kiln_msa_key}
        assert {(p["nda"]["state"], p["nda"]["source"], p["nda"]["standard_version"]) for p in panels} == {
            ("standard", "standard", 1)}
        async with factory() as s:
            rows = (await s.scalars(select(Agreement).where(Agreement.kind == "NDA"))).all()
            assert {r.client_id for r in rows} == {*holders, kiln.id}
            assert {(r.file_key, r.standard_agreement_id, r.source) for r in rows} == {
                (nda.file_key, nda.id, "standard")}
            history = (await s.scalars(select(AgreementFileVersion.file_key).join(
                Agreement, Agreement.id == AgreementFileVersion.agreement_id).where(Agreement.kind == "NDA"))).all()
            assert len(history) == 6 and set(history) == {nda.file_key}

        # Detaching one holder removes its row only: no cleanup job, the key is still referenced, the object stays.
        async with api_for(factory, LEGAL, storage=store) as legal:
            gone = await legal.delete(f"/clients/{c['atlas']}/agreements/NDA")
        assert gone.status_code == 200 and gone.json()["state"] == "existing_none", gone.text
        async with factory() as s:
            assert await count(s, DeletionJob) == 0
            assert await key_is_referenced(s, BUCKET, nda.file_key)
            assert await count(s, Agreement, Agreement.file_key == nda.file_key) == 5

        # Deleting a client that holds the standard copy queues only its own object; the cleanup worker removes
        # that one and is never asked to delete the standard key.
        async with api_for(factory, ADMIN, storage=store) as admin:
            deleted = await admin.delete(f"/clients/{kiln.id}")
        assert deleted.status_code == 202, deleted.text
        async with factory() as s:
            job = (await s.scalars(select(DeletionJob))).one()
            assert job.objects == [{"bucket": BUCKET, "key": kiln_msa_key}]
            assert await s.get(Client, kiln.id) is None
        assert await run_cleanup_worker(factory, store, monkeypatch, capsys) == 1
        assert store.delete_requests == [kiln_msa_key]
        assert set(store.objects) == {nda.file_key, msa.file_key}

        # Detaching every remaining holder still keeps it: the standard_agreement row points at the object.
        async with api_for(factory, LEGAL, storage=store) as legal:
            for client_id in holders[1:]:
                response = await legal.delete(f"/clients/{client_id}/agreements/NDA")
                assert response.status_code == 200, response.text
        async with factory() as s:
            assert await count(s, Agreement, Agreement.file_key == nda.file_key) == 0
            assert await count(s, AgreementFileVersion, AgreementFileVersion.file_key == nda.file_key) == 0
            assert await key_is_referenced(s, BUCKET, nda.file_key)
            assert await count(s, DeletionJob) == 1  # still only the client deletion's job
        assert await run_cleanup_worker(factory, store, monkeypatch, capsys) == 0
        assert nda.file_key in store.objects and nda.file_key not in store.delete_requests

        # The worker re-checks every key it is handed. A job that names the (now superseded) standard v1, the
        # current standard, a client's current copy and a file kept only in that client's history removes none of
        # them; an unreferenced key in the same job goes.
        async with api_for(factory, LEGAL, storage=store) as legal:
            v2 = await legal.post("/agreements/standard/NDA", **upload("standard-nda-v2.pdf", PDF))
            assert v2.status_code == 201 and v2.json()["version"] == 2, v2.text
            for name in ("cobalt-msa-v2.pdf", "cobalt-msa-v3.pdf"):
                copy = await legal.post(f"/clients/{c['cobalt']}/agreements/MSA/client-copy", **upload(name, PDF))
                assert copy.status_code == 201, copy.text
        nda_v2_key, history_key, current_key = store.puts[-3:]
        junk = "agreements/standard/NDA/never-referenced.pdf"
        store.hold(junk)
        async with factory() as s:
            assert await count(s, Agreement, Agreement.file_key == history_key) == 0  # only in the history now
            assert await count(s, AgreementFileVersion, AgreementFileVersion.file_key == history_key) == 1
            await queue_storage_cleanup(s, actor_id=ADMIN.id, account_id=None, title="cleanup naming shared keys",
                                        keys=[nda.file_key, nda_v2_key, msa.file_key, history_key, current_key, junk])
            await s.commit()
        assert await run_cleanup_worker(factory, store, monkeypatch, capsys) == 1
        assert store.delete_requests == [kiln_msa_key, junk]
        assert {nda.file_key, nda_v2_key, msa.file_key, history_key, current_key} <= set(store.objects)
        async with factory() as s:
            done = (await s.scalars(select(DeletionJob).where(DeletionJob.subject_type == "agreement_upload"))).one()
            assert (done.status, done.objects) == ("done", [])
            assert await count(s, StandardAgreement, StandardAgreement.file_key == nda.file_key) == 1

        # Deleting the ONLY client that holds a standard version queues nothing for that object either: once the
        # client's rows are gone, its standard_agreement row still points at it.
        async with factory() as s:
            lone = Client(name="Lark Local Works")  # no HubSpot company and no deals: it can be deleted
            s.add(lone)
            await s.commit()
        async with api_for(factory, LEGAL, storage=store) as legal:
            attached = await legal.post(f"/clients/{lone.id}/agreements/NDA/attach-standard")
        assert attached.status_code == 201 and attached.json()["standard_version"] == 2, attached.text
        async with factory() as s:
            assert await count(s, Agreement, Agreement.file_key == nda_v2_key) == 1  # its only holder
        async with api_for(factory, ADMIN, storage=store) as admin:
            deleted = await admin.delete(f"/clients/{lone.id}")
        assert deleted.status_code == 202, deleted.text
        async with factory() as s:
            job = (await s.scalars(select(DeletionJob).where(DeletionJob.subject_id == lone.id))).one()
            assert (job.objects, job.summary["counts"]["agreements"]) == ([], 1)
            assert await count(s, Agreement, Agreement.file_key == nda_v2_key) == 0
            assert await key_is_referenced(s, BUCKET, nda_v2_key)
        asked_before = list(store.delete_requests)
        await run_cleanup_worker(factory, store, monkeypatch, capsys)
        assert store.delete_requests == asked_before and nda_v2_key in store.objects


async def test_undo_leaves_the_other_holders_of_the_shared_object_alone(env, monkeypatch, capsys):  # noqa: F811
    store = VersionedStore()
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            seeded = await seed(s)
        nda = seeded.standards["NDA"]
        store.hold(nda.file_key)
        c = seeded.clients
        async with api_for(factory, ADMIN, storage=store, launcher=Jobs(factory)) as admin, \
                api_for(factory, LEGAL, storage=store) as legal:
            # AG-0001: the existing clients' NDA (Atlas, Beacon).
            first = await admin.post("/agreements/batches", json=real("t4-first", "ATTACH 2", ["NDA"], net_new=False))
            assert first.status_code == 202 and first.json()["status"] == "done", first.text
            # A manual attachment of the same object (batch_id NULL) to a net-new client past stage 1.
            assert (await legal.post(f"/clients/{c['cobalt']}/agreements/NDA/attach-standard")).status_code == 201
            # AG-0002: the net-new clients past stage 1 that still lack it (Falcon, Harbor).
            second = await admin.post("/agreements/batches", json=real("t4-second", "ATTACH 2", ["NDA"]))
            assert second.status_code == 202 and second.json()["status"] == "done", second.text
            assert (await admin.get("/agreements/batches/AG-0001")).json()["undo_would_remove"] == 2
            undo = await admin.post("/agreements/batches/AG-0001/undo")
            assert undo.status_code == 202, undo.text
            assert (undo.json()["status"], undo.json()["undone_count"]) == ("undone", 2)
            other = (await admin.get("/agreements/batches/AG-0002")).json()
        assert (other["status"], other["undone_count"], other["undo_would_remove"]) == ("done", 0, 2)
        async with factory() as s:
            labels = dict((await s.execute(select(AgreementBatch.label, AgreementBatch.id))).all())
            rows = {r.client_id: r for r in (await s.scalars(select(Agreement).where(Agreement.kind == "NDA"))).all()}
            assert set(rows) == {c["cobalt"], c["falcon"], c["harbor"]}
            assert rows[c["cobalt"]].batch_id is None
            assert rows[c["falcon"]].batch_id == rows[c["harbor"]].batch_id == labels["AG-0002"]
            assert {(r.file_key, r.standard_agreement_id, r.source) for r in rows.values()} == {
                (nda.file_key, nda.id, "standard")}
            assert await count(s, AgreementFileVersion) == 3  # the removed rows' history went with them, no more
            detached = (await s.scalars(select(AuditEvent).where(
                AuditEvent.action == agreement_audit.BATCH_DETACHED))).all()
            assert sorted(e.after["client_name"] for e in detached) == ["Atlas Foods", "Beacon Logistics"]
            assert await count(s, DeletionJob) == 0
            assert await key_is_referenced(s, BUCKET, nda.file_key)
        assert await run_cleanup_worker(factory, store, monkeypatch, capsys) == 0
        assert store.delete_requests == [] and nda.file_key in store.objects

        # Undoing the other batch as well still leaves the manual attachment, and the object.
        async with api_for(factory, ADMIN, storage=store, launcher=Jobs(factory)) as admin:
            again = await admin.post("/agreements/batches/AG-0002/undo")
        assert again.status_code == 202 and again.json()["undone_count"] == 2, again.text
        async with factory() as s:
            (left,) = (await s.scalars(select(Agreement))).all()
            assert (left.client_id, left.batch_id, left.file_key) == (c["cobalt"], None, nda.file_key)
            assert await count(s, DeletionJob) == 0
        assert await run_cleanup_worker(factory, store, monkeypatch, capsys) == 0
        assert store.delete_requests == [] and set(store.objects) == {nda.file_key}
