"""S24-AG1 lane BE-A on Postgres: the workspace, export, documents, activity and standard documents on a
fresh, migrated scratch database (tests/s24_pg.py). Postgres differs from SQLite where this lane relies on
it: the settings row exists (migration 0072) and is locked FOR UPDATE as the standard-version mutex, the
audit table is append-only (a trigger), foreign keys and partial unique indexes are real, JSON is JSONB, and
the statement budget is counted on the real driver. Skipped without DEALGATE_POSTGRES_URL.
"""

from __future__ import annotations

import csv
import io
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError

from app.integrations.s3_evidence import StubS3
from app.models.agreements import AgreementsSettings, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement
from app.models.deletion import DeletionJob
from app.services import agreement_audit as aa
from app.services import agreement_standard
from app.services.agreement_files import check_bytes
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_bea_routes import E2E, NOW, REAL_FEED, SALES, VIEWER, get, seed_world
from tests.test_s24_ag1_bea_standard import DOCX, PDF, call, upload

pytestmark = POSTGRES


@pytest.fixture
def pg_clock(monkeypatch):
    monkeypatch.setenv("DEALGATE_NOW", NOW.isoformat())
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "bea-tenant")


async def test_workspace_documents_activity_and_export_on_postgres(pg_clock):
    async with scratch_postgres() as (engine, factory):
        async with factory() as s:
            world = await seed_world(s)
        async with factory() as s:
            statements: list[str] = []

            def count(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
                if not statement.lstrip().upper().startswith(("SAVEPOINT", "RELEASE")):
                    statements.append(statement)

            event.listen(engine.sync_engine, "before_cursor_execute", count)
            try:
                body = (await get(s, SALES, "/agreements/workspace")).json()
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", count)
            assert len(statements) <= 8, len(statements)
            assert {c["key"]: c["value"] for c in body["cards"]} == {
                "clients": 7, "existing": 2, "net_new": 5, "needs_attention": 1, "standard_attached": 2,
                "client_copies": 4}
            for card in body["cards"]:
                drilled = (await get(s, SALES, "/agreements/workspace", **card["drill"])).json()
                assert drilled["total"] == card["value"], card["key"]
            assert body["cutover"]["latest_batch"]["undo_would_remove"] == 3
            documents = (await get(s, SALES, "/agreements/documents", page_size=100)).json()
            assert documents["total"] == body["document_count"] == 8
            feed = (await get(s, SALES, "/agreements/activity")).json()
            assert [row["text"] for row in feed["items"]] == REAL_FEED
            assert feed["total"] == body["activity_count"] == 7
            e2e = (await get(s, E2E, "/agreements/activity")).json()
            # The older client-level event with no client id is hidden from a test identity (bug #91), so 5, not 6.
            assert e2e["total"] == 5 and e2e["items"][0]["client_id"] == str(world["fixture"])
            assert not any("from a client" in row["text"] for row in e2e["items"])

            export = await get(s, VIEWER, "/agreements/export", relationship="net_new")
            rows = list(csv.reader(io.StringIO(export.content.decode("utf-8-sig"))))
            assert len(rows) == 6 and rows[0][0] == "Client"
            audit = (await s.scalars(select(AuditEvent).where(AuditEvent.action == aa.EXPORTED))).one()
            assert audit.after["rows"] == 5
            first = (await get(s, SALES, "/agreements/activity")).json()["items"][0]
            assert (first["action"], first["text"], first["by"]) == ("exported", "Exported 5 clients to CSV",
                                                                    "Viewer Vance")


async def test_standard_versions_download_and_cleanup_on_postgres(pg_clock, monkeypatch):
    storage = StubS3()
    monkeypatch.setenv("AGREEMENTS_BUCKET", storage.bucket)
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            await seed_world(s)  # the standard NDA and MSA v1 exist; the settings row is the migration's
            assert (await s.get(AgreementsSettings, 1)) is not None
        async with factory() as s:
            from tests.test_s24_ag1_bea_routes import LEGAL

            response = await upload(s, LEGAL, storage, kind="NDA", name="nda-v2.docx", body=DOCX)
            assert response.status_code == 201, response.text
            assert (response.json()["version"], response.json()["attached_clients"]) == (2, 0)
            current = (await call(s, SALES, storage, "/agreements/standard")).json()
            assert current["NDA"]["version"] == 2 and current["NDA"]["attached_clients"] == 0
            assert current["MSA"]["version"] == 1 and current["MSA"]["attached_clients"] == 1
            held = (await s.scalars(select(Agreement).where(Agreement.source == "standard",
                                                            Agreement.kind == "NDA"))).all()
            assert {row.standard_agreement_id for row in held} == {
                (await s.scalars(select(StandardAgreement.id).where(StandardAgreement.kind == "NDA",
                                                                    StandardAgreement.version_no == 1))).one()}
            downloads = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == aa.DOWNLOADED)
            before = await s.scalar(downloads)  # the seed holds the e2e identity's download
            link = await call(s, SALES, storage, "/agreements/standard/NDA/download")
            assert link.status_code == 200 and link.json()["file_name"] == "nda-v2.docx"
            assert await s.scalar(downloads) == before + 1

        async with factory() as s:
            writer = (await s.scalars(select(StandardAgreement.uploaded_by)
                                      .where(StandardAgreement.version_no == 2))).one()
            from app.models.user import User

            actor = await s.get(User, writer)
            original = aa.record

            async def duplicate(*args, **kwargs):
                raise IntegrityError("INSERT", {}, Exception("duplicate version"))

            monkeypatch.setattr(aa, "record", duplicate)
            try:
                with pytest.raises(HTTPException) as raised:
                    await agreement_standard.upload_standard(s, storage, actor=actor, kind="MSA",
                                                             checked=check_bytes("msa.pdf", PDF))
            finally:
                monkeypatch.setattr(aa, "record", original)
            assert raised.value.status_code == 409
            assert await s.scalar(select(func.count()).select_from(StandardAgreement)
                                  .where(StandardAgreement.kind == "MSA")) == 1
            job = (await s.scalars(select(DeletionJob))).one()
            assert job.status == "pending" and job.subject_type == "agreement_upload"
            assert [item["key"] for item in job.objects] == [
                key for key in storage.objects if key.startswith("agreements/standard/MSA/")]
            assert uuid.UUID(str(job.subject_id))
