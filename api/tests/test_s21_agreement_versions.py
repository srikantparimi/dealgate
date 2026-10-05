"""DG05 replacement preserves root identity, prior bytes and audited versions."""
import hashlib

import pytest
from sqlalchemy import select

from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from tests.test_signed_sow import app_with_session, _client, _seed_user, _local_env


@pytest.mark.asyncio
async def test_replacement_is_versioned_and_stale_writes_do_not_store(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    legal = await _seed_user(session, "agreement-versions@example.test", ["Legal"])
    account = Client(name="Synthetic versioned documents")
    session.add(account)
    await session.commit()
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_evidence_s3, lambda: storage)
    headers = {"X-Test-User": legal.email}
    first, second = b"%PDF synthetic NDA revision one", b"%PDF synthetic NDA revision two"
    async with _client(app_with_session) as client:
        response = await client.post("/agreements", headers=headers,
            data={"client_id": str(account.id), "kind": "NDA"},
            files={"file": ("nda-v1.pdf", first, "application/pdf")})
        assert response.status_code == 201, response.text
        original = response.json()
        assert original["version_no"] == 1
        identity = original["id"]
        response = await client.post(f"/agreements/{identity}/replace", headers=headers,
            data={"expected_version": "1"}, files={"file": ("nda-v2.pdf", second, "application/pdf")})
        assert response.status_code == 200, response.text
        assert response.json()["id"] == identity
        assert response.json()["version_no"] == 2
        assert response.json()["filename"] == "nda-v2.pdf"
        history = await client.get(f"/agreements/{identity}/versions", headers=headers)
        assert history.status_code == 200, history.text
        rows = history.json()["items"]
        assert [row["version_no"] for row in rows] == [2, 1]
        assert [row["file_hash"] for row in rows] == [hashlib.sha256(second).hexdigest(), hashlib.sha256(first).hexdigest()]
        assert {row["uploaded_by"] for row in rows} == {str(legal.id)}
        assert len(storage.objects) == 2
        assert set(storage.objects.values()) == {first, second}
        previous = await client.get(f"/agreements/{identity}/versions/1/download", headers=headers)
        assert previous.status_code == 200, previous.text
        assert previous.json()["filename"] == "nda-v1.pdf"
        stored = dict(storage.objects)
        stale = await client.post(f"/agreements/{identity}/replace", headers=headers,
            data={"expected_version": "1"}, files={"file": ("stale.pdf", b"%PDF stale", "application/pdf")})
        assert stale.status_code == 409, stale.text
        assert storage.objects == stored
        listed = await client.get(f"/agreements?client_id={account.id}", headers=headers)
        assert [(row["id"], row["version_no"]) for row in listed.json()["items"]] == [(identity, 2)]
    audit = (await session.scalars(select(AuditEvent).where(AuditEvent.action == "agreement.replaced"))).one()
    assert audit.actor_id == legal.id
    assert audit.entity_id == identity
    assert audit.before["version_no"] == 1
    assert audit.after["version_no"] == 2
    assert audit.after["file_hash"] == hashlib.sha256(second).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["document", "client"])
async def test_delete_queues_every_revision_after_database_removal(app_with_session, session, monkeypatch, mode):
    from app.services.parent_deletion import request_client_deletion
    monkeypatch.setenv("DEALGATE_TEST_GROUPS", "Legal")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "agreement-delete-test")
    monkeypatch.setenv("AGREEMENTS_BUCKET", "stub-agreements")
    actor = await _seed_user(session, "agreement-delete@example.test", ["Legal"])
    account = Client(name="Synthetic agreement deletion")
    session.add(account)
    await session.commit()
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_evidence_s3, lambda: storage)
    def no_precommit_storage():
        raise AssertionError("Storage must be handled by the durable cleanup worker")
    monkeypatch.setattr("app.integrations.s3_sow._client", no_precommit_storage)
    headers = {"X-Test-User": actor.email}
    async with _client(app_with_session) as client:
        first = await client.post("/agreements", headers=headers,
            data={"client_id": str(account.id), "kind": "NDA"},
            files={"file": ("nda.pdf", b"%PDF one", "application/pdf")})
        assert first.status_code == 201, first.text
        identity = first.json()["id"]
        replacement = await client.post(f"/agreements/{identity}/replace", headers=headers,
            data={"expected_version": "1"}, files={"file": ("nda.pdf", b"%PDF two", "application/pdf")})
        assert replacement.status_code == 200, replacement.text
        keys = set(storage.objects)
        assert len(keys) == 2
        if mode == "document":
            response = await client.delete(f"/agreements/{identity}", headers=headers)
            assert response.status_code == 202, response.text
            assert response.json()["source_deleted"] is True
            assert response.json()["status"] == "pending"
            assert response.json()["job_id"]
        else:
            await request_client_deletion(session, actor_id=actor.id, client_id=account.id)
            await session.commit()
    assert (await session.scalars(select(Agreement))).all() == []
    assert (await session.scalars(select(AgreementFileVersion))).all() == []
    job = (await session.scalars(select(DeletionJob))).one()
    assert job.status == "pending"
    assert {item["key"] for item in job.objects} == keys
    assert {item["bucket"] for item in job.objects} == {"stub-agreements"}
    assert set(storage.objects) == keys


@pytest.mark.asyncio
async def test_trusted_cleanup_rejects_foreign_historical_uploader(session, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from app.services.fixture_cleanup import cleanup_manifest
    from tests.test_s21_parent_cleanup_independent import issued
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "agreement-history-cleanup")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    owner, fixture, _ = await issued(session)
    outsider = await _seed_user(session, "foreign-history@example.test", ["Legal"])
    row = Agreement(client_id=fixture["client_id"], kind="NDA", version_no=2,
        file_key="current.pdf", filename="current.pdf", file_size=4, uploaded_by=owner.id)
    session.add(row)
    await session.commit()
    bounds = dict(run_id=fixture["run_id"], owner_id=owner.id,
        min_age=timedelta(0), now=datetime.now(UTC) + timedelta(hours=25))
    assert len(await cleanup_manifest(session, **bounds)) == 1
    session.add(AgreementFileVersion(agreement_id=row.id, version_no=1, file_key="historical.pdf",
        filename="historical.pdf", file_size=4, uploaded_by=outsider.id))
    await session.commit()
    assert await cleanup_manifest(session, **bounds) == []


@pytest.mark.asyncio
async def test_sow_deletion_preserves_client_document_history(session, monkeypatch):
    from app.services.deletion import request_sow_deletion
    from app.services.deletion_storage import key_is_referenced
    from tests.test_deletion_by_state import _seed
    monkeypatch.setenv("DEALGATE_TENANT_ID", "agreement-sow-preservation")
    monkeypatch.setenv("AGREEMENTS_BUCKET", "synthetic-agreement-preservation")
    owner, deal, sow = await _seed(session, with_package=False)
    document = Agreement(client_id=deal.client_id, kind="MSA", version_no=2,
        file_key="msa-v2.pdf", filename="msa.pdf", file_size=4, uploaded_by=owner.id)
    session.add(document)
    await session.flush()
    for number in [1, 2]:
        session.add(AgreementFileVersion(agreement_id=document.id, version_no=number,
            file_key=f"msa-v{number}.pdf", filename="msa.pdf", file_size=4, uploaded_by=owner.id))
    await session.commit()
    await request_sow_deletion(session, actor_id=owner.id, sow_id=sow.id)
    await session.commit()
    assert await session.get(Agreement, document.id) is not None
    versions = (await session.scalars(select(AgreementFileVersion))).all()
    assert {row.version_no for row in versions} == {1, 2}
    for version in versions:
        assert await key_is_referenced(session, "synthetic-agreement-preservation", version.file_key)
