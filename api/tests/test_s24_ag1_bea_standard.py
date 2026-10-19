"""S24-AG1 lane BE-A — standard documents (B4), their file rules (B5 on this route), audit (B11) and the
compensating cleanup when the row cannot be committed (S10)."""

from __future__ import annotations

import hashlib
import re
import uuid
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import current_user
from app.db import get_session
from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.agreements import StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.deletion import DeletionJob
from app.models.user import User
from app.routers.agreements_workspace import TEST_IDENTITY_DETAIL
from app.routers.agreements_workspace import router as workspace_router
from app.services import agreement_audit as aa
from app.services import agreement_standard
from app.services.agreement_files import (
    MAX_BYTES,
    MSG_EMPTY,
    MSG_NOT_DOCX,
    MSG_NOT_PDF,
    MSG_TOO_LARGE,
    MSG_TYPE,
    check_bytes,
)
from app.services.deletion_cleanup import process_deletion_jobs
from app.services.test_fixtures import ISSUED
from tests.test_s24_ag1_bea_routes import (  # noqa: F401  (fixtures)
    ADMIN,
    E2E,
    E2E_ID,
    LEGAL,
    NOBODY,
    SALES,
    clock,
    engine,
)

PDF = b"%PDF-1.7\n" + b"standard nda body " * 64
DOCX = b"PK\x03\x04" + b"word body " * 64
HOSTILE_NAME = "Standard NDA <img src=x onerror=alert(1)>.pdf.pdf"


@pytest_asyncio.fixture
async def people(session, clock):  # noqa: F811
    writer = User(id=uuid.uuid4(), email=LEGAL.email, name="Wendy Writer", groups=["Legal"])
    admin = User(id=uuid.uuid4(), email=ADMIN.email, name="Ada Admin", groups=["SystemAdmin"])
    e2e = User(id=E2E_ID, email=E2E.email, name="E2E Runner", groups=["SystemAdmin", "officeapp-e2e"])
    session.add_all([writer, admin, e2e])
    await session.commit()
    return {"writer": writer, "admin": admin, "e2e": e2e}


@pytest.fixture
def storage():
    return StubS3()


@asynccontextmanager
async def api_for(session, user, storage):
    app = FastAPI()
    app.include_router(workspace_router)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[get_evidence_s3] = lambda: storage

    async def _db():
        yield session

    app.dependency_overrides[get_session] = _db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://bea") as api:
        yield api


async def upload(session, user, storage, kind="NDA", name="Standard NDA.pdf", body=PDF):
    async with api_for(session, user, storage) as api:
        return await api.post(f"/agreements/standard/{kind}", files={"file": (name, body, "application/pdf")})


async def call(session, user, storage, path):
    async with api_for(session, user, storage) as api:
        return await api.get(path)


async def count(session, model) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)))


async def test_nothing_uploaded_yet(session, people, storage):
    assert (await call(session, SALES, storage, "/agreements/standard")).json() == {"NDA": None, "MSA": None}
    response = await call(session, SALES, storage, "/agreements/standard/MSA/download")
    assert response.status_code == 404
    assert response.json()["detail"] == "No standard MSA has been uploaded yet."
    assert await count(session, AuditEvent) == 0


async def test_upload_creates_the_next_version_and_never_touches_attached_copies(session, people, storage):
    response = await upload(session, LEGAL, storage, name=HOSTILE_NAME)
    assert response.status_code == 201, response.text
    first = response.json()
    assert {k: first[k] for k in ("kind", "version", "file_name", "file_size", "uploaded_by", "attached_clients")} == {
        "kind": "NDA", "version": 1, "file_name": HOSTILE_NAME, "file_size": len(PDF),
        "uploaded_by": "Wendy Writer", "attached_clients": 0}
    assert first["sha256"] == hashlib.sha256(PDF).hexdigest() and first["uploaded_at"].endswith("Z")
    (key, stored), = storage.objects.items()
    assert stored == PDF
    assert re.fullmatch(r"agreements/standard/NDA/\d{8}T\d{6}Z-[0-9a-f]{8}-Standard NDA _img src_x onerror_alert_1_\.pdf",
                        key), key
    v1 = (await session.scalars(select(StandardAgreement))).one()
    assert (v1.version_no, v1.file_key, v1.uploaded_by) == (1, key, people["writer"].id)
    # One client holds v1 (as an attach would leave it).
    holder = Client(name="Holder Co", hubspot_company_id="c-holder")
    session.add(holder)
    await session.flush()
    session.add(Agreement(client_id=holder.id, kind="NDA", source="standard", standard_agreement_id=v1.id,
                          file_key=v1.file_key, filename=v1.filename, file_size=v1.file_size,
                          uploaded_by=people["admin"].id))
    await session.commit()
    assert (await call(session, SALES, storage, "/agreements/standard")).json()["NDA"]["attached_clients"] == 1

    second = await upload(session, ADMIN, storage, name="nda-v2.docx", body=DOCX)
    assert second.status_code == 201, second.text
    assert (second.json()["version"], second.json()["uploaded_by"], second.json()["attached_clients"]) == (
        2, "Ada Admin", 0)
    current = (await call(session, SALES, storage, "/agreements/standard")).json()
    assert current["NDA"]["version"] == 2 and current["NDA"]["file_name"] == "nda-v2.docx"
    assert current["NDA"]["attached_clients"] == 0 and current["MSA"] is None
    row = (await session.scalars(select(Agreement).where(Agreement.client_id == holder.id))).one()
    assert row.standard_agreement_id == v1.id and row.file_key == v1.file_key  # the attached copy is unchanged
    assert len(storage.objects) == 2

    audits = (await session.scalars(select(AuditEvent).where(AuditEvent.action == aa.STANDARD_UPLOADED)
                                    .order_by(AuditEvent.ts))).all()
    assert [(a.entity, a.after["version_no"], a.actor_id) for a in audits] == [
        ("standard_agreement", 1, people["writer"].id), ("standard_agreement", 2, people["admin"].id)]
    feed = (await call(session, SALES, storage, "/agreements/activity")).json()
    assert [item["text"] for item in feed["items"]] == [
        "Uploaded standard NDA version 2 (nda-v2.docx)", f"Uploaded standard NDA version 1 ({HOSTILE_NAME})"]


@pytest.mark.parametrize(("name", "body", "status", "message"), [
    ("contract.pdf", b"just some text", 415, MSG_NOT_PDF),
    ("contract.docx", PDF, 415, MSG_NOT_DOCX),
    ("contract.txt", b"%PDF-1.4 text", 415, MSG_TYPE),
    ("contract", PDF, 415, MSG_TYPE),
    ("contract.pdf", b"", 422, MSG_EMPTY),
    ("contract.pdf", b"%PDF-" + b"x" * MAX_BYTES, 413, MSG_TOO_LARGE),
])
async def test_file_rules_refuse_before_anything_is_stored(session, people, storage, name, body, status, message):
    response = await upload(session, LEGAL, storage, name=name, body=body)
    assert response.status_code == status, response.text
    assert response.json()["detail"] == message
    assert storage.objects == {}
    assert await count(session, StandardAgreement) == 0 and await count(session, AuditEvent) == 0


@pytest.mark.parametrize(("user", "status"), [(SALES, 403), (NOBODY, 403), (LEGAL, 201), (ADMIN, 201)])
async def test_only_legal_and_systemadmin_upload(session, people, storage, user, status):
    assert (await upload(session, user, storage)).status_code == status


async def test_a_test_identity_cannot_upload_a_standard_outside_local_and_test(session, people, storage, monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    response = await upload(session, E2E, storage)
    assert response.status_code == 403 and response.json()["detail"] == TEST_IDENTITY_DETAIL
    assert storage.objects == {} and await count(session, StandardAgreement) == 0
    monkeypatch.setenv("DEALGATE_ENV", "local")
    assert (await upload(session, E2E, storage)).status_code == 201


async def test_download_is_a_short_link_and_is_audited(session, people, storage):
    assert (await upload(session, LEGAL, storage)).status_code == 201
    response = await call(session, SALES, storage, "/agreements/standard/NDA/download")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in_seconds"] == 300 and body["file_name"] == "Standard NDA.pdf"
    assert body["url"].startswith("https://stub-agreements.local/get/agreements/standard/NDA/")
    sales_row = (await session.scalars(select(User).where(User.email == SALES.email))).one()
    download = (await session.scalars(select(AuditEvent).where(AuditEvent.action == aa.DOWNLOADED))).one()
    assert download.actor_id == sales_row.id and download.entity == "standard_agreement"
    assert download.after["standard"] is True and download.after["version_no"] == 1
    feed = (await call(session, LEGAL, storage, "/agreements/activity")).json()
    assert feed["items"][0]["text"] == "Downloaded the standard NDA" and feed["items"][0]["by"] == "Sam Sales"
    assert (await call(session, SALES, storage, "/agreements/standard/MSA/download")).status_code == 404


async def test_attached_counts_follow_what_the_caller_can_see(session, people, storage):
    assert (await upload(session, LEGAL, storage)).status_code == 201
    v1 = (await session.scalars(select(StandardAgreement))).one()
    visible = Client(name="Visible Co", hubspot_company_id="c-visible")
    fixture = Client(name="S21 e2e fixture holder")
    archived = Client(name="Gone Co", hubspot_company_id="c-gone", archived_at=v1.uploaded_at)
    session.add_all([visible, fixture, archived])
    await session.flush()
    for client in (visible, fixture, archived):
        session.add(Agreement(client_id=client.id, kind="NDA", source="standard", standard_agreement_id=v1.id,
                              file_key=v1.file_key, filename=v1.filename, file_size=v1.file_size,
                              uploaded_by=people["admin"].id))
    await aa.record(session, actor_id=people["e2e"].id, action=ISSUED, entity="client", entity_id=fixture.id,
                    after={"participant_ids": [str(E2E_ID)]})
    await session.commit()
    assert (await call(session, SALES, storage, "/agreements/standard")).json()["NDA"]["attached_clients"] == 1


@pytest.mark.parametrize(("failure", "expected"), [
    (RuntimeError("audit store down"), RuntimeError),
    (IntegrityError("INSERT", {}, Exception("duplicate version")), HTTPException),
])
async def test_a_row_that_cannot_be_committed_queues_its_object_for_cleanup(
        session, people, storage, monkeypatch, failure, expected):
    monkeypatch.setenv("AGREEMENTS_BUCKET", storage.bucket)
    original_record = aa.record

    async def broken_record(*args, **kwargs):
        raise failure

    monkeypatch.setattr(aa, "record", broken_record)
    checked = check_bytes("Standard MSA.pdf", PDF)
    writer_id = people["writer"].id  # the rollback inside expires every loaded row
    with pytest.raises(expected) as raised:
        await agreement_standard.upload_standard(session, storage, actor=people["writer"], kind="MSA",
                                                 checked=checked)
    if expected is HTTPException:
        assert raised.value.status_code == 409
    (key,) = storage.objects  # the object was stored first ...
    assert await count(session, StandardAgreement) == 0  # ... and the row never landed
    job = (await session.scalars(select(DeletionJob))).one()
    assert (job.subject_type, job.status, job.objects, job.actor_id) == (
        "agreement_upload", "pending", [{"bucket": storage.bucket, "key": key}], writer_id)

    class VersionedBucket:  # what the cleanup worker sees in S3
        def __init__(self):
            self.deleted: list[dict] = []

        def get_paginator(self, name):
            assert name == "list_object_versions"
            return self

        def paginate(self, **kwargs):
            remaining = [] if self.deleted else [{"Key": key, "VersionId": "v1"}]
            return [{"Versions": remaining, "DeleteMarkers": []}]

        def delete_objects(self, *, Bucket, Delete):  # noqa: N803 (boto3's names)
            assert Bucket == storage.bucket
            self.deleted.extend(Delete["Objects"])
            return {}

    monkeypatch.setattr(aa, "record", original_record)
    bucket = VersionedBucket()
    assert await process_deletion_jobs(session, s3=bucket) == 1
    assert bucket.deleted == [{"Key": key, "VersionId": "v1"}]
    assert (await session.get(DeletionJob, job.id)).status == "done"
