"""The signature HTTP path must inspect the stored executed bytes, never a canned success."""

import hashlib
from pathlib import Path

from app.integrations.bedrock_sow_extract import ExtractedFields, get_bedrock_sow
from app.integrations.s3_sow import get_sow_s3
from app.main import app as main_app
from app.services.document_text import DocumentText
from app.services.signed_sow import create_upload
from tests.test_signed_sow import (
    _approved_fields, _client, _seed_ready_to_sign_package, _seed_user,
    app_with_session,  # noqa: F401
)

DOCUMENT = (Path(__file__).parents[2] / "fixtures/sample_sows/08_assessment_fixed_fee.docx").read_bytes()


class StoredObject:
    def __init__(self):
        self.keys = []

    def download_bytes(self, key):
        self.keys.append(key)
        return DOCUMENT


class Extractor:
    def __init__(self):
        self.documents = []

    def extract(self, doc):
        assert isinstance(doc, DocumentText)
        assert doc.blocks
        self.documents.append(doc)
        return ExtractedFields(fields=_approved_fields())


async def exercise(session, app, *, valid_hash):
    owner = await _seed_user(session, "binding@smartek21.com", ["Sales"])
    package, _, _ = await _seed_ready_to_sign_package(session, owner=owner)
    upload = await create_upload(session, actor_id=owner.id, package_id=package.id,
        file_s3_key="sow/owned/executed.docx",
        file_hash=hashlib.sha256(DOCUMENT).hexdigest() if valid_hash else "0" * 64)
    storage, extractor = StoredObject(), Extractor()
    main_app.dependency_overrides[get_sow_s3] = lambda: storage
    main_app.dependency_overrides[get_bedrock_sow] = lambda: extractor
    try:
        async with _client(app) as client:
            response = await client.post(f"/signed-sow/{package.id}/verify",
                headers={"X-Test-User": owner.email})
    finally:
        main_app.dependency_overrides.pop(get_sow_s3, None)
        main_app.dependency_overrides.pop(get_bedrock_sow, None)
    await session.refresh(upload)
    return response, upload, storage, extractor


async def test_http_verification_reads_recorded_key_and_parses_document(app_with_session, session):  # noqa: F811
    response, upload, storage, extractor = await exercise(session, app_with_session, valid_hash=True)
    assert response.status_code == 200, response.text
    assert storage.keys == [upload.file_s3_key]
    assert len(extractor.documents) == 1
    assert upload.verify_status == "verified"


async def test_mutated_storage_bytes_cannot_verify(app_with_session, session):  # noqa: F811
    response, upload, storage, extractor = await exercise(session, app_with_session, valid_hash=False)
    assert response.status_code == 200, response.text
    assert storage.keys == [upload.file_s3_key]
    assert upload.verify_status == "blocked"
    assert "hash" in upload.verify_reason
    assert extractor.documents == []
