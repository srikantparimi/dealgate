"""S24-AG1 lane BE-A — agreements storage: the CI stub (S18), the upload-link signer (B13 / AG0 S14) and the
read-only orphan report (B13)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.integrations import s3_evidence
from app.integrations.s3_evidence import EvidenceS3, SignerCredentialsMissing, StubS3, get_evidence_s3
from app.models.agreements import StandardAgreement
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.user import User
from worker import agreement_orphans

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fresh_process_stub(monkeypatch):
    monkeypatch.setattr(s3_evidence, "_PROCESS_STUB", None)
    for name in ("S3_STUB", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGREEMENTS_BUCKET", "dealgate-agreements-test")


# --- S18: the stub the CI e2e job asks for --------------------------------------------------------------


@pytest.mark.parametrize(("env", "stub"), [({"S3_STUB": "1", "DEALGATE_ENV": "staging"}, True),
                                           ({"DEALGATE_ENV": "local"}, True), ({"DEALGATE_ENV": "test"}, True),
                                           ({"DEALGATE_ENV": "staging"}, False), ({"DEALGATE_ENV": "prod"}, False)])
def test_the_stub_is_chosen_by_s3_stub_or_a_local_environment(monkeypatch, env, stub):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    first, second = get_evidence_s3(), get_evidence_s3()
    assert isinstance(first, StubS3) is stub
    if stub:
        assert first is second  # one store per process: an upload is still there for its download
        assert first.bucket == "dealgate-agreements-test"  # the bucket deletion jobs resolve
        key = first.put_object_at("agreements/x/a.pdf", "application/pdf", b"%PDF-1.4")
        assert get_evidence_s3().objects[key] == b"%PDF-1.4"
    else:
        assert type(first) is EvidenceS3 and first.bucket == "dealgate-agreements-test"


# --- B13: the signer never signs with placeholder keys outside local/test --------------------------------


class _Frozen:
    def __init__(self, access, secret, token):
        self.access_key, self.secret_key, self.token = access, secret, token


class _Resolved:
    def __init__(self, frozen):
        self._frozen = frozen

    def get_frozen_credentials(self):
        return self._frozen


def _boto_session(resolved):
    class _Session:
        def get_credentials(self):
            return resolved

    return _Session


def test_environment_keys_are_used_everywhere(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAREALKEY")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "real-secret")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "token")
    assert s3_evidence._aws_credentials() == ("AKIAREALKEY", "real-secret", "token")


@pytest.mark.parametrize("env", ["local", "test"])
def test_placeholders_remain_only_for_local_and_test(monkeypatch, env):
    monkeypatch.setenv("DEALGATE_ENV", env)
    assert s3_evidence._aws_credentials() == ("AKIAEXAMPLE", "SECRETEXAMPLE", None)


def test_outside_local_the_task_role_chain_is_used(monkeypatch):
    import boto3

    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setattr(boto3, "Session", _boto_session(_Resolved(_Frozen("ASIAROLE", "role-secret", "role-token"))))
    assert s3_evidence._aws_credentials() == ("ASIAROLE", "role-secret", "role-token")


@pytest.mark.parametrize("resolved", [None, _Resolved(_Frozen(None, None, None))])
def test_outside_local_no_credentials_fails_loudly(monkeypatch, resolved):
    import boto3

    monkeypatch.setenv("DEALGATE_ENV", "staging")
    monkeypatch.setattr(boto3, "Session", _boto_session(resolved))
    with pytest.raises(SignerCredentialsMissing):
        s3_evidence._aws_credentials()
    with pytest.raises(SignerCredentialsMissing):
        EvidenceS3(bucket="dealgate-agreements-test").generate_upload_url(
            uuid.uuid4(), "nda.pdf", "application/pdf")


def test_a_resolver_error_is_the_same_refusal(monkeypatch):
    import boto3

    def broken():
        raise RuntimeError("no metadata endpoint")

    monkeypatch.setenv("DEALGATE_ENV", "prod")
    monkeypatch.setattr(boto3, "Session", broken)
    with pytest.raises(SignerCredentialsMissing):
        s3_evidence._aws_credentials()


# --- B13: the read-only orphan report --------------------------------------------------------------------


class ListOnlyBucket:
    """ListObjectVersions only: the report must never need (or call) anything that deletes."""

    def __init__(self, versions, markers=()):
        self.pages = [{"Versions": list(versions[:3]), "DeleteMarkers": list(markers)},
                      {"Versions": list(versions[3:])}]
        self.calls: list[str] = []

    def get_paginator(self, name):
        self.calls.append(name)
        assert name == "list_object_versions"
        return self

    def paginate(self, **kwargs):
        assert kwargs == {"Bucket": "dealgate-agreements-test"}  # the whole bucket, no prefix
        return self.pages

    def __getattr__(self, name):  # delete_object(s), put_object, … would be a defect
        raise AssertionError(f"the orphan report called {name}")


def _version(key, *, days, latest=True, size=100):
    return {"Key": key, "VersionId": uuid.uuid4().hex, "IsLatest": latest, "Size": size,
            "LastModified": NOW - timedelta(days=days)}


async def test_orphan_report_lists_unreferenced_objects_by_top_level_prefix(session):
    user = User(id=uuid.uuid4(), email="legal@example.test", name="Legal", groups=["Legal"])
    client = Client(name="Report Co")
    session.add_all([user, client])
    await session.flush()
    agreement = Agreement(client_id=client.id, kind="NDA", file_key="agreements/a1/current.pdf",
                          filename="current.pdf", file_size=1, uploaded_by=user.id, version_no=2)
    session.add(agreement)
    await session.flush()
    session.add(AgreementFileVersion(agreement_id=agreement.id, version_no=1, file_key="agreements/a1/old.pdf",
                                     filename="old.pdf", file_size=1, uploaded_by=user.id))
    session.add(StandardAgreement(kind="MSA", version_no=1, file_key="agreements/standard/MSA/std.pdf",
                                  filename="std.pdf", file_size=1, sha256="0" * 64, uploaded_by=user.id))
    session.add(DeletionJob(id=uuid.uuid4(), tenant_id="local", environment="local", subject_type="agreement_upload",
                            subject_id=uuid.uuid4(), status="pending", summary={},
                            objects=[{"bucket": "dealgate-agreements-test", "key": "agreements/a9/queued.pdf"},
                                     {"bucket": "another-bucket", "key": "agreements/a9/elsewhere.pdf"}]))
    await session.commit()
    bucket = ListOnlyBucket([
        _version("agreements/a1/current.pdf", days=40),
        _version("agreements/a1/old.pdf", days=60),
        _version("agreements/standard/MSA/std.pdf", days=10),
        _version("agreements/a2/orphan.pdf", days=3, size=2048),
        _version("verification/s21/run1/agreements/a3/proof.pdf", days=30, size=10),
        _version("verification/s21/run1/agreements/a3/proof-2.pdf", days=29, size=20),
        _version("verification/s21/run2/agreements/a4/proof.pdf", days=28, size=30),
        _version("agreements/a5/just-uploaded.pdf", days=0),  # younger than 24 hours
        _version("agreements/a9/queued.pdf", days=5),
        _version("agreements/a6/deleted.pdf", days=9, latest=False),  # its latest version is a delete marker
        _version("loose.pdf", days=2, size=5),
    ], markers=[{"Key": "agreements/a6/deleted.pdf", "VersionId": "m", "IsLatest": True}])
    report = await agreement_orphans.run(session, bucket, "dealgate-agreements-test", now=NOW)
    assert report["read_only"] is True and report["bucket"] == "dealgate-agreements-test"
    assert report["live_objects"] == 10 and report["referenced"] == 3
    assert report["unreferenced_younger_than_min_age"] == 1
    assert [row["key"] for row in report["queued_for_cleanup"]] == ["agreements/a9/queued.pdf"]
    assert report["orphans"] == 5 and report["orphan_bytes"] == 2048 + 10 + 20 + 30 + 5
    assert list(report["groups"]) == ["(bucket root)", "agreements", "verification"]
    verification = report["groups"]["verification"]
    assert verification["count"] == 3 and verification["bytes"] == 60
    assert [row["key"] for row in verification["keys"]] == [
        "verification/s21/run1/agreements/a3/proof-2.pdf", "verification/s21/run1/agreements/a3/proof.pdf",
        "verification/s21/run2/agreements/a4/proof.pdf"]
    assert verification["oldest"] < verification["newest"] and verification["oldest"].endswith("Z")
    assert report["groups"]["agreements"]["keys"] == [
        {"key": "agreements/a2/orphan.pdf", "size": 2048, "last_modified": "2026-10-12T12:00:00Z"}]
    assert bucket.calls == ["list_object_versions"]
    json.dumps(report)  # printable as one JSON document


async def test_orphan_report_main_prints_one_json_line_and_exits_non_zero_on_failure(monkeypatch, capsys):
    from contextlib import asynccontextmanager

    from app.integrations import s3_sow

    class Denied:
        def get_paginator(self, name):
            raise PermissionError("AccessDenied: s3:ListBucketVersions")

    @asynccontextmanager
    async def no_db():
        class _Session:
            async def scalars(self, statement):
                class _Result:
                    def all(self):
                        return []

                return _Result()

        yield _Session()

    monkeypatch.setattr(agreement_orphans, "session_factory", no_db)
    monkeypatch.setattr(s3_sow, "_client", lambda: Denied())
    assert await agreement_orphans.main() == 1
    printed = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert printed["read_only"] is True and printed["error"].startswith("PermissionError: AccessDenied")
