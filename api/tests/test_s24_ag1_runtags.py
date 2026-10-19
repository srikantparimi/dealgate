"""S24-AG1 T11 server part (lane T-A) — test uploads live under agreements/e2e/<run_id>/, nowhere else.

The leak gate (scripts/check-test-data-clean.sh) can only find a leftover test upload if every test upload is
keyed under the run-tagged prefix, and no real upload ever is. BE-B checked one client-copy upload on a
fixture; this file covers:

* every upload route a test identity can use on its server-issued fixture (client copy, a new version, the
  legacy create and replace): every stored key and every history key is
  ``agreements/e2e/<run_id>/<agreement_id>/<stamp>-<8 hex>-<name>``; downloads point at those keys;
* removing the fixture's copy queues exactly those keys, and the cleanup worker leaves nothing under the
  run's prefix (so a passing run leaves the gate clean);
* a real client's keys never carry an e2e segment, even when its NAME looks like a run tag (a name confers no
  trust; the client-list check of the gate is what catches such a client);
* outside local/test (DEALGATE_ENV=staging and any other value) a test identity cannot upload a standard
  copy (403, nothing stored or written), while it still reaches its own fixture, keyed under the run, and
  never a real client.

SQLite with foreign keys on; StubS3.
"""

from __future__ import annotations

import re
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.auth import AuthUser
from app.models.agreements import StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.models.user import User
from app.routers.agreements_workspace import TEST_IDENTITY_DETAIL
from app.services.deletion_cleanup import process_deletion_jobs
from tests.test_s24_ag1_uploads import (  # noqa: F401  (engine and env are fixtures)
    ADMIN,
    DOCX,
    E2E,
    LEGAL,
    PDF,
    STAMP_NONCE,
    STANDARD_KEY,
    StubVersions,
    World,
    client_for,
    counts,
    engine,
    env,
    seed_world,
)

TENANT = "lane-ta-runtags"


def run_key(run_id, agreement_id) -> re.Pattern:
    return re.compile(rf"agreements/e2e/{run_id}/{agreement_id}/{STAMP_NONCE}")


def real_key(agreement_id) -> re.Pattern:
    return re.compile(rf"agreements/{agreement_id}/{STAMP_NONCE}")


def _file(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


async def _issue(session, monkeypatch, environment: str) -> dict:
    """A server-issued fixture for the e2e identity, the way the e2e specs get one (dev seed enabled)."""
    from app.services.test_fixtures import create_fixture

    monkeypatch.setenv("DEALGATE_ENV", environment)
    monkeypatch.setenv("DEALGATE_TENANT_ID", TENANT)
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")
    fixture = await create_fixture(session, actor_id=E2E.id, label="Agreements run tags", reviewer_ids=[])
    await session.commit()
    return fixture


@pytest_asyncio.fixture
async def world(session, env) -> World:  # noqa: F811 — env is imported
    return await seed_world(session, users=(ADMIN, LEGAL, E2E))


async def _versions(session, agreement_id) -> dict[int, str]:
    rows = (await session.scalars(select(AgreementFileVersion).where(
        AgreementFileVersion.agreement_id == agreement_id))).all()
    return {row.version_no: row.file_key for row in rows}


async def test_every_fixture_upload_route_keys_under_the_run(session, world, monkeypatch):
    fixture = await _issue(session, monkeypatch, "local")
    fx, run = fixture["client_id"], fixture["run_id"]
    storage = world.storage
    async with client_for(session, E2E, storage) as bot:
        first = await bot.post(f"/clients/{fx}/agreements/NDA/client-copy", files=_file("run nda.pdf", PDF))
        second = await bot.post(f"/clients/{fx}/agreements/NDA/client-copy", data={"note": "Second run"},
                                files=_file("run nda v2.pdf", PDF))
        created = await bot.post("/agreements", data={"client_id": str(fx), "kind": "MSA"},
                                 files=_file("run msa.docx", DOCX))
        assert (first.status_code, second.status_code, created.status_code) == (201, 201, 201), created.text
        replaced = await bot.post(f"/agreements/{created.json()['id']}/replace", data={"expected_version": "1"},
                                  files=_file("run msa v2.pdf", PDF))
        assert replaced.status_code == 200, replaced.text
        nda_link = (await bot.get(f"/clients/{fx}/agreements/NDA/download")).json()
        msa_v1_link = (await bot.get(f"/agreements/{created.json()['id']}/versions/1/download")).json()
        documents = (await bot.get("/agreements/documents")).json()
    nda_id, msa_id = uuid.UUID(first.json()["agreement_id"]), uuid.UUID(created.json()["id"])
    nda_keys, msa_keys = await _versions(session, nda_id), await _versions(session, msa_id)
    expected_names = {(nda_id, 1): "run nda.pdf", (nda_id, 2): "run nda v2.pdf",
                      (msa_id, 1): "run msa.docx", (msa_id, 2): "run msa v2.pdf"}
    for (agreement_id, version), name in expected_names.items():
        key = (nda_keys if agreement_id == nda_id else msa_keys)[version]
        match = run_key(run, agreement_id).fullmatch(key)
        assert match and match["name"] == name, key
    # Every object the run stored is under its run's prefix, and nothing else was stored.
    fixture_objects = {k for k in storage.objects if k.startswith(f"agreements/e2e/{run}/")}
    assert fixture_objects == set(nda_keys.values()) | set(msa_keys.values())
    assert set(storage.objects) - fixture_objects == set(world.standard_keys.values())
    # The rows point at the latest versions; downloads hand out links to the run's keys.
    rows = {r.kind: r for r in (await session.scalars(select(Agreement).where(Agreement.client_id == fx))).all()}
    assert (rows["NDA"].file_key, rows["MSA"].file_key) == (nda_keys[2], msa_keys[2])
    assert nda_keys[2] in nda_link["url"] and msa_keys[1] in msa_v1_link["url"]
    assert {d["file_name"] for d in documents["items"]} == {"run nda v2.pdf", "run msa v2.pdf"}


async def test_removing_a_fixture_copy_leaves_nothing_under_the_run(session, world, monkeypatch):
    fixture = await _issue(session, monkeypatch, "local")
    fx, run = fixture["client_id"], fixture["run_id"]
    storage = world.storage
    async with client_for(session, E2E, storage) as bot:
        for name in ("teardown v1.pdf", "teardown v2.pdf", "teardown v3.pdf"):
            assert (await bot.post(f"/clients/{fx}/agreements/NDA/client-copy",
                                   files=_file(name, PDF))).status_code == 201
        assert (await bot.post(f"/clients/{fx}/agreements/MSA/attach-standard")).status_code == 201
        detach_copy = await bot.delete(f"/clients/{fx}/agreements/NDA")
        detach_standard = await bot.delete(f"/clients/{fx}/agreements/MSA")
    assert (detach_copy.status_code, detach_standard.status_code) == (202, 200)
    prefix = f"agreements/e2e/{run}/"
    left = sorted(k for k in storage.objects if k.startswith(prefix))
    assert len(left) == 3  # stored, and now waiting for the cleanup worker
    job = (await session.scalars(select(DeletionJob))).one()  # the standard detach queued nothing
    assert sorted(item["key"] for item in job.objects) == left
    assert {item["bucket"] for item in job.objects} == {storage.bucket}
    assert await process_deletion_jobs(session, s3=StubVersions(storage)) == 1
    assert not any(k.startswith(prefix) for k in storage.objects)  # the gate's prefix is clean again
    assert world.standard_keys["MSA"] in storage.objects  # the shared standard object is never a test leftover


async def test_a_real_client_is_never_keyed_under_e2e_even_with_a_run_tag_name(session, world, monkeypatch):
    fixture = await _issue(session, monkeypatch, "local")
    lookalike = Client(name="S24 e2e 1760000000000 Lookalike", hubspot_company_id=None)
    session.add(lookalike)
    await session.commit()
    storage = world.storage
    async with client_for(session, LEGAL, storage) as legal:
        responses = [
            await legal.post(f"/clients/{world.clients['cinder']}/agreements/NDA/client-copy",
                             files=_file("cinder.pdf", PDF)),
            await legal.post(f"/clients/{lookalike.id}/agreements/NDA/client-copy", files=_file("look.pdf", PDF)),
            await legal.post("/agreements", data={"client_id": str(world.clients["heron"]), "kind": "MSA"},
                             files=_file("heron.docx", DOCX)),
            await legal.post("/agreements/standard/NDA", files=_file("Real Standard NDA.pdf", PDF)),
        ]
        panel = (await legal.get(f"/clients/{lookalike.id}/agreements")).json()
        fixture_for_legal = await legal.post(f"/clients/{fixture['client_id']}/agreements/NDA/client-copy",
                                             files=_file("x.pdf", PDF))
    assert [r.status_code for r in responses] == [201, 201, 201, 201], [r.text for r in responses]
    assert fixture_for_legal.status_code == 404  # a real user never sees, let alone writes to, a fixture
    for response in responses[:2]:
        assert real_key(response.json()["agreement_id"]).fullmatch(
            (await session.get(Agreement, uuid.UUID(response.json()["agreement_id"]))).file_key)
    assert real_key(responses[2].json()["id"]).fullmatch(
        (await session.get(Agreement, uuid.UUID(responses[2].json()["id"]))).file_key)
    standard = (await session.scalars(select(StandardAgreement).where(StandardAgreement.version_no == 2))).one()
    assert STANDARD_KEY.fullmatch(standard.file_key)
    assert not any("/e2e/" in key for key in storage.objects)
    # The name alone makes the client test data on the page (the gate's client list catches it by name).
    assert "test_data" in panel["flags"]


OUTSIDE_LOCAL = ("staging", "production", "prod", "dev", "demo")


@pytest.mark.parametrize("environment", OUTSIDE_LOCAL)
async def test_a_test_identity_cannot_upload_a_standard_outside_local_and_test(session, world, monkeypatch,
                                                                               environment):
    monkeypatch.setenv("DEALGATE_ENV", environment)
    monkeypatch.setenv("DEALGATE_TENANT_ID", TENANT)
    storage = world.storage
    # A second e2e identity that has never signed in: the refusal must not even provision its user row.
    newcomer = AuthUser(uuid.UUID("7a000000-0000-4000-8000-0000000000e3"), "lane-bot-2@example.test",
                        "Lane Bot Two", ("SystemAdmin", "officeapp-e2e"))
    for bot in (E2E, newcomer):
        objects, before = dict(storage.objects), await counts(session)
        async with client_for(session, bot, storage) as api:
            refused = await api.post("/agreements/standard/MSA", files=_file("e2e standard.pdf", PDF))
        assert (refused.status_code, refused.json()["detail"]) == (403, TEST_IDENTITY_DETAIL), refused.text
        assert storage.objects == objects and await counts(session) == before
    assert await session.get(User, newcomer.id) is None
    # A real SystemAdmin in the same environment uploads normally: only test identities are refused.
    async with client_for(session, ADMIN, storage) as api:
        accepted = await api.post("/agreements/standard/MSA", files=_file("Real Standard MSA.pdf", PDF))
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["version"] == 2


@pytest.mark.parametrize("environment", ("local", "test"))
async def test_in_local_and_test_a_test_identity_may_upload_a_standard(session, world, monkeypatch, environment):
    monkeypatch.setenv("DEALGATE_ENV", environment)
    async with client_for(session, E2E, world.storage) as api:
        response = await api.post("/agreements/standard/NDA", files=_file("Local Standard NDA.pdf", PDF))
    assert response.status_code == 201, response.text
    key = (await session.scalars(select(StandardAgreement.file_key).where(
        StandardAgreement.version_no == 2))).one()
    assert STANDARD_KEY.fullmatch(key)  # a standard copy is global data, never under a run's prefix


async def test_on_staging_the_test_identity_reaches_only_its_fixture_keyed_under_the_run(session, world,
                                                                                       monkeypatch):
    fixture = await _issue(session, monkeypatch, "staging")
    fx, run = fixture["client_id"], fixture["run_id"]
    real = world.clients["cinder"]
    storage = world.storage
    async with client_for(session, E2E, storage) as bot:
        mine = await bot.post(f"/clients/{fx}/agreements/NDA/client-copy", files=_file("staging run.pdf", PDF))
        assert mine.status_code == 201, mine.text
        objects, before = dict(storage.objects), await counts(session)
        attempts = [
            await bot.post(f"/clients/{real}/agreements/NDA/client-copy", files=_file("leak.pdf", PDF)),
            await bot.post("/agreements", data={"client_id": str(real), "kind": "MSA"},
                           files=_file("leak.docx", DOCX)),
            await bot.put(f"/clients/{real}/agreements/NDA/mark",
                          json={"reason": "other", "marked_on": "2026-10-01"}),
            await bot.post(f"/clients/{real}/agreements/NDA/attach-standard"),
            await bot.get(f"/clients/{real}/agreements"),
            await bot.post("/agreements/standard/NDA", files=_file("leak standard.pdf", PDF)),
        ]
    assert [a.status_code for a in attempts] == [404, 404, 404, 404, 404, 403], [a.text for a in attempts]
    assert storage.objects == objects and await counts(session) == before
    key = (await session.get(Agreement, uuid.UUID(mine.json()["agreement_id"]))).file_key
    assert run_key(run, mine.json()["agreement_id"]).fullmatch(key)
    uploaded = (await session.scalars(select(AuditEvent).where(AuditEvent.actor_id == E2E.id,
                                                                AuditEvent.action == "agreement.uploaded"))).one()
    assert uploaded.after["file_key"] == key and uploaded.after["client_id"] == str(fx)
