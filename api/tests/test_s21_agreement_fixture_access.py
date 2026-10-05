"""Agreement documents must follow the account's server-issued fixture scope."""
import pytest

from app.integrations.s3_evidence import StubS3, get_evidence_s3
from app.models.client import Agreement, Client
from app.services.test_fixtures import create_fixture
from tests.test_signed_sow import app_with_session, _client, _seed_user, _local_env


@pytest.mark.asyncio
async def test_agreement_fixture_list_and_direct_access(app_with_session, session, monkeypatch):
    monkeypatch.setenv("DEALGATE_TENANT_ID", "agreement-scope-test")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    owner = await _seed_user(session, "agreement-fixture@example.test", ["SystemAdmin", "officeapp-e2e"])
    normal = await _seed_user(session, "agreement-normal@example.test", ["SystemAdmin"])
    outsider = await _seed_user(session, "agreement-outsider@example.test", ["SystemAdmin", "officeapp-e2e"])
    fixture = await create_fixture(session, actor_id=owner.id, label="Agreement", reviewer_ids=[])
    real = Client(name="Ordinary business client")
    session.add(real)
    await session.flush()
    documents = []
    for client_id, uploader in [(fixture["client_id"], owner), (real.id, normal)]:
        row = Agreement(client_id=client_id, kind="NDA", file_key=f"{client_id}/nda.pdf",
                        filename="nda.pdf", file_size=4, uploaded_by=uploader.id)
        session.add(row)
        documents.append(row)
    await session.commit()
    storage = StubS3()
    monkeypatch.setitem(app_with_session.dependency_overrides, get_evidence_s3, lambda: storage)
    async with _client(app_with_session) as client:
        for actor, expected in [(owner, [str(documents[0].id)]), (normal, [str(documents[1].id)]), (outsider, [])]:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", ",".join(actor.groups))
            headers = {"X-Test-User": actor.email}
            response = await client.get("/agreements", headers=headers)
            assert response.status_code == 200, response.text
            assert [row["id"] for row in response.json()["items"]] == expected
        for actor, document in [(normal, documents[0]), (outsider, documents[0]), (owner, documents[1])]:
            monkeypatch.setenv("DEALGATE_TEST_GROUPS", ",".join(actor.groups))
            headers = {"X-Test-User": actor.email}
            assert (await client.get(f"/agreements?client_id={document.client_id}", headers=headers)).status_code == 404
            assert (await client.get(f"/agreements/{document.id}/download", headers=headers)).status_code == 404
            assert (await client.get(f"/agreements/{document.id}/versions", headers=headers)).status_code == 404
            assert (await client.get(f"/agreements/{document.id}/versions/1/download", headers=headers)).status_code == 404
            assert (await client.delete(f"/agreements/{document.id}", headers=headers)).status_code == 404
            assert (await client.post(f"/agreements/{document.id}/replace", headers=headers,
                data={"expected_version": "1"}, files={"file": ("nda.pdf", b"%PDF", "application/pdf")})).status_code == 404
            response = await client.post("/agreements", headers=headers,
                data={"client_id": str(document.client_id), "kind": "MSA"},
                files={"file": ("msa.pdf", b"%PDF", "application/pdf")})
            assert response.status_code == 404, response.text
        assert storage.objects == {}
        assert storage.download_calls == []
        monkeypatch.setenv("DEALGATE_TEST_GROUPS", ",".join(owner.groups))
        allowed = await client.get(f"/agreements/{documents[0].id}/download", headers={"X-Test-User": owner.email})
        assert allowed.status_code == 200, allowed.text
