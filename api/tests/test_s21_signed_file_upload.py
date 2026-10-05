"""T17 real router upload boundary; storage stub isolates provider failures only."""
import hashlib
import uuid

import pytest
from sqlalchemy import select

from app.integrations.s3_sow import StubS3, get_sow_s3
from app.models.signed_sow import SignedSowUpload
from tests.test_signed_sow import app_with_session, _client, _seed_user, _seed_ready_to_sign_package, _local_env


@pytest.mark.asyncio
async def test_signed_file_hash_and_storage_are_bound_to_received_bytes(app_with_session, session, monkeypatch):
    owner = await _seed_user(session, "signed-file-owner@example.test", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_sow_s3, lambda: storage)
    content = b"%PDF-1.7 explicit synthetic signed test bytes"
    async with _client(app_with_session) as client:
        response = await client.post(f"/signed-sow/{package.id}/file", headers={"X-Test-User": owner.email},
            data={"has_signature_evidence": "true"}, files={"file": ("executed.pdf", content, "application/pdf")})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["file_hash"] == hashlib.sha256(content).hexdigest()
    assert result["verify_status"] == "pending"
    assert storage.put_calls == [(result["file_s3_key"], len(content), "application/pdf")]
    assert len((await session.scalars(select(SignedSowUpload))).all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("case,status", [("unsigned", 400), ("empty", 422), ("oversize", 413), ("mime", 422), ("role", 403), ("stale", 409)])
async def test_invalid_signed_file_never_writes_storage(app_with_session, session, monkeypatch, case, status):
    owner = await _seed_user(session, "signed-file-owner@example.test", ["Sales"])
    outsider = await _seed_user(session, "signed-file-other@example.test", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    if case == "stale":
        package.status = "voided"
        await session.commit()
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_sow_s3, lambda: storage)
    monkeypatch.setattr("app.routers.signed_sow.MAX_SOW_BYTES", 8)
    content = b"" if case == "empty" else b"123456789" if case == "oversize" else b"%PDF"
    async with _client(app_with_session) as client:
        response = await client.post(f"/signed-sow/{package.id}/file", headers={"X-Test-User": outsider.email if case == "role" else owner.email},
            data={"has_signature_evidence": "false" if case == "unsigned" else "true"},
            files={"file": ("executed.pdf", content, "text/plain" if case == "mime" else "application/pdf")})
    assert response.status_code == status, response.text
    assert storage.put_calls == []
    assert (await session.scalars(select(SignedSowUpload))).all() == []


@pytest.mark.asyncio
async def test_storage_failure_does_not_register_execution(app_with_session, session, monkeypatch):
    owner = await _seed_user(session, "signed-failure@example.test", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    storage = StubS3()
    def unavailable(*args):
        raise RuntimeError("provider unavailable")
    monkeypatch.setattr(storage, "put_object", unavailable)
    monkeypatch.setitem(app_with_session.dependency_overrides, get_sow_s3, lambda: storage)
    async with _client(app_with_session) as client:
        response = await client.post(f"/signed-sow/{package.id}/file", headers={"X-Test-User": owner.email},
            data={"has_signature_evidence": "true"}, files={"file": ("executed.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 502
    assert (await session.scalars(select(SignedSowUpload))).all() == []
    await session.refresh(package)
    assert package.status == "ready_to_sign"


@pytest.mark.asyncio
async def test_invited_owner_uses_canonical_identity(app_with_session, session, monkeypatch):
    from app.models.user import User
    owner = User(id=uuid.uuid4(), email="invited-signed@example.test", name="Invited owner", groups=["Sales"])
    session.add(owner)
    await session.commit()
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_sow_s3, lambda: storage)
    async with _client(app_with_session) as client:
        response = await client.post(f"/signed-sow/{package.id}/file", headers={"X-Test-User": owner.email},
            data={"has_signature_evidence": "true"}, files={"file": ("executed.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 201, response.text
    upload = (await session.scalars(select(SignedSowUpload))).one()
    assert upload.uploaded_by == owner.id


@pytest.mark.asyncio
async def test_owner_changed_during_body_read_is_rejected(app_with_session, session, monkeypatch):
    from starlette.datastructures import UploadFile
    from app.models.opportunity import Opportunity
    from sqlalchemy import update
    owner = await _seed_user(session, "signed-owner-race@example.test", ["Sales"])
    other = await _seed_user(session, "signed-new-owner@example.test", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_sow_s3, lambda: storage)
    original_read = UploadFile.read
    async def read_after_transfer(file, size=-1):
        data = await original_read(file, size)
        await session.execute(update(Opportunity).where(Opportunity.id == package.opportunity_id)
            .values(owner_id=other.id).execution_options(synchronize_session=False))
        return data
    monkeypatch.setattr(UploadFile, "read", read_after_transfer)
    async with _client(app_with_session) as client:
        response = await client.post(f"/signed-sow/{package.id}/file", headers={"X-Test-User": owner.email},
            data={"has_signature_evidence": "true"}, files={"file": ("executed.pdf", b"%PDF", "application/pdf")})
    assert response.status_code == 403, response.text
    assert storage.put_calls == []
    assert (await session.scalars(select(SignedSowUpload))).all() == []
