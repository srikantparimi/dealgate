"""S24-AG1 T6 (lane T-A) — the permission matrix, enforced by the server.

Every role (the ten app roles, plus a caller with no role) calls every route in
docs/reference/openapi-agreements.yaml and the legacy /agreements routes kept for existing callers:

* view (workspace, documents, activity, standard, the client panel, HubSpot values, the legacy list and
  versions, batches) and download (client, standard, legacy, a legacy version) and export: all ten roles;
* upload (client copy, legacy create, legacy replace, standard), attach, mark, unmark, detach (standard,
  client copy, legacy), relationship: Legal and SystemAdmin (B11);
* batch dry run, run and undo, HubSpot mapping save and apply (dry and real): SystemAdmin only, so Legal
  gets 403 too.

A refused call answers 403 "insufficient role" from the server's role check and leaves the world exactly as
it was: the same stored objects (keys and bytes) and the same rows in every table this feature writes,
including the audit log and the user table. A permitted read writes nothing either; a permitted write,
download or export changes something. Earlier lanes covered Sales only, or reads only, or the HubSpot routes
only; this is the whole matrix in one place. SQLite with foreign keys on; StubS3 for storage; the batch job
runs inline.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import AuthUser
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
from app.services import agreement_batches
from tests.test_s24_ag1_uploads import (  # noqa: F401  (engine and env are fixtures)
    ADMIN,
    DOCX,
    LEGAL,
    NOW,
    PDF,
    World,
    client_for,
    engine,
    env,
    seed_world,
)

ROLES = ("Marketing", "Sales", "SalesLeader", "Presales", "Delivery", "HR", "Finance", "Legal", "CEO",
         "SystemAdmin")
EVERY_ROLE = frozenset(ROLES)
WRITERS = frozenset({"Legal", "SystemAdmin"})
ADMINS = frozenset({"SystemAdmin"})
REFUSED = {"detail": "insufficient role"}
WATCHED = (User, Client, Agreement, AgreementFileVersion, AgreementMark, StandardAgreement, AgreementBatch,
           AgreementHubspotMap, AgreementsSettings, DeletionJob, AuditEvent, Opportunity)


@dataclass
class PermWorld:
    base: World
    arden_nda: uuid.UUID  # a client copy every role can download (with a version 1)
    heron_msa: uuid.UUID  # a client copy writers replace, then remove through the legacy route


async def _seed_copy(session, world: World, key: str, kind: str, file_name: str) -> uuid.UUID:
    agreement_id = uuid.uuid4()
    file_key = f"agreements/{agreement_id}/20261001T120000Z-0a0b0c0d-{file_name}"
    row = Agreement(id=agreement_id, client_id=world.clients[key], kind=kind, file_key=file_key,
                    filename=file_name, file_size=len(PDF), uploaded_by=LEGAL.id,
                    uploaded_at=NOW - timedelta(days=3), version_no=1, source="client")
    session.add(row)
    await session.flush()
    session.add(AgreementFileVersion(agreement_id=agreement_id, version_no=1, file_key=file_key,
                                     filename=file_name, file_size=len(PDF), uploaded_by=LEGAL.id,
                                     uploaded_at=row.uploaded_at, source="client"))
    world.storage.objects[file_key] = PDF
    return agreement_id


@pytest_asyncio.fixture
async def perm_world(session, env) -> PermWorld:  # noqa: F811 — env is imported
    world = await seed_world(session)
    arden = await _seed_copy(session, world, "arden", "NDA", "arden-nda.pdf")
    heron = await _seed_copy(session, world, "heron", "MSA", "heron-msa.pdf")
    # A finished batch (attached nothing) so GET /agreements/batches/AG-0001 has something to show.
    session.add(AgreementBatch(label="AG-0001", status="done", kinds=["NDA"], target_client_ids=[],
                               standard_ids={"NDA": str(world.standard_ids["NDA"])}, target_count=0,
                               idempotency_key="ta-perm-seeded", created_by=ADMIN.id))
    # Elm's deal carries a HubSpot msa_type, so the mapping has a value to save and apply.
    deal = (await session.scalars(select(Opportunity).where(Opportunity.client_id == world.clients["elm"]))).one()
    deal.hubspot_msa_type = "Signed MSA"
    await session.commit()
    return PermWorld(base=world, arden_nda=arden, heron_msa=heron)


async def snapshot(session, storage) -> dict:
    """Everything a call could change: stored objects (key and bytes) and every row of the watched tables."""
    state: dict = {"objects": dict(storage.objects)}
    for model in WATCHED:
        rows = (await session.execute(select(model.__table__))).all()
        state[model.__tablename__] = sorted(repr(tuple(row)) for row in rows)
    return state


def business(state: dict) -> dict:
    """The state without the caller's own sign-in bookkeeping (its user row and the ``user.*`` audit rows
    ensure_user writes the first time a role calls a write or a download), so an allowed write must have
    changed the agreements themselves, not just provisioned its caller."""
    trimmed = {k: v for k, v in state.items() if k != User.__tablename__}
    trimmed[AuditEvent.__tablename__] = [row for row in state[AuditEvent.__tablename__] if "'user." not in row]
    return trimmed


def inline(session):
    factory = async_sessionmaker(session.bind, expire_on_commit=False, class_=AsyncSession)

    async def launch(batch_id, phase):
        runner = agreement_batches.run_batch if phase == "run" else agreement_batches.run_undo
        await runner(factory, batch_id)

    return launch


Send = Callable[..., Awaitable]


@dataclass(frozen=True)
class Call:
    name: str
    route: tuple[str, str]  # method and path template, as the server registers it
    allowed: frozenset[str]
    status: int  # the answer when the role is allowed
    effect: str  # "none": writes nothing even when allowed; "some": an allowed call changes something
    send: Send


def _file(name: str, content: bytes) -> dict:
    return {"file": (name, content, "application/octet-stream")}


def _c(w: PermWorld, key: str) -> uuid.UUID:
    return w.base.clients[key]


async def _batch_dry_run(api, w, state):
    response = await api.post("/agreements/batches", json={"kinds": ["NDA"], "include_net_new_past_stage_1": True})
    if response.status_code == 200:
        state["will_receive"] = response.json()["will_receive"]
    return response


async def _batch_run(api, w, state):
    response = await api.post("/agreements/batches", json={
        "kinds": ["NDA"], "dry_run": False, "include_net_new_past_stage_1": True,
        "idempotency_key": f"ta-perm-{uuid.uuid4().hex[:12]}", "confirm": f"ATTACH {state.get('will_receive', 1)}"})
    if response.status_code == 202:
        state["label"] = response.json()["id"]
    return response


CALLS: tuple[Call, ...] = (
    # view
    Call("workspace", ("GET", "/agreements/workspace"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/workspace")),
    Call("documents", ("GET", "/agreements/documents"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/documents")),
    Call("activity", ("GET", "/agreements/activity"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/activity")),
    Call("standard", ("GET", "/agreements/standard"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/standard")),
    Call("panel", ("GET", "/clients/{client_id}/agreements"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get(f"/clients/{_c(w, 'cinder')}/agreements")),
    Call("hubspot values", ("GET", "/agreements/hubspot-values"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/hubspot-values")),
    Call("legacy list", ("GET", "/agreements"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements")),
    Call("legacy versions", ("GET", "/agreements/{agreement_id}/versions"), EVERY_ROLE, 200, "none",
         lambda api, w, s: api.get(f"/agreements/{w.arden_nda}/versions")),
    Call("batches", ("GET", "/agreements/batches"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/batches")),
    Call("one batch", ("GET", "/agreements/batches/{label}"), EVERY_ROLE, 200, "none", lambda api, w, s: api.get("/agreements/batches/AG-0001")),
    # download and export (audited)
    Call("client download", ("GET", "/clients/{client_id}/agreements/{kind}/download"), EVERY_ROLE, 200, "some",
         lambda api, w, s: api.get(f"/clients/{_c(w, 'arden')}/agreements/NDA/download")),
    Call("standard download", ("GET", "/agreements/standard/{kind}/download"), EVERY_ROLE, 200, "some", lambda api, w, s: api.get("/agreements/standard/NDA/download")),
    Call("legacy download", ("GET", "/agreements/{agreement_id}/download"), EVERY_ROLE, 200, "some", lambda api, w, s: api.get(f"/agreements/{w.arden_nda}/download")),
    Call("legacy version download", ("GET", "/agreements/{agreement_id}/versions/{version_no}/download"), EVERY_ROLE, 200, "some",
         lambda api, w, s: api.get(f"/agreements/{w.arden_nda}/versions/1/download")),
    Call("export", ("GET", "/agreements/export"), EVERY_ROLE, 200, "some", lambda api, w, s: api.get("/agreements/export")),
    # writes: Legal and SystemAdmin
    Call("client copy", ("POST", "/clients/{client_id}/agreements/{kind}/client-copy"), WRITERS, 201, "some",
         lambda api, w, s: api.post(f"/clients/{_c(w, 'cinder')}/agreements/NDA/client-copy",
                                    data={"note": "Synthetic note"}, files=_file("cinder-nda.pdf", PDF))),
    Call("legacy upload", ("POST", "/agreements"), WRITERS, 201, "some",
         lambda api, w, s: api.post("/agreements", data={"client_id": str(_c(w, "heron")), "kind": "MSA"},
                                    files=_file("heron-msa-v2.docx", DOCX))),
    Call("legacy replace", ("POST", "/agreements/{agreement_id}/replace"), WRITERS, 200, "some",
         lambda api, w, s: api.post(f"/agreements/{w.heron_msa}/replace", data={"expected_version": "2"},
                                    files=_file("heron-msa-v3.pdf", PDF))),
    Call("attach standard", ("POST", "/clients/{client_id}/agreements/{kind}/attach-standard"), WRITERS, 201, "some",
         lambda api, w, s: api.post(f"/clients/{_c(w, 'birch')}/agreements/NDA/attach-standard")),
    Call("mark", ("PUT", "/clients/{client_id}/agreements/{kind}/mark"), WRITERS, 200, "some",
         lambda api, w, s: api.put(f"/clients/{_c(w, 'elm')}/agreements/NDA/mark",
                                   json={"reason": "signed_outside_dealgate", "marked_on": "2026-10-01"})),
    Call("unmark", ("DELETE", "/clients/{client_id}/agreements/{kind}/mark"), WRITERS, 200, "some", lambda api, w, s: api.delete(f"/clients/{_c(w, 'elm')}/agreements/NDA/mark")),
    Call("detach standard", ("DELETE", "/clients/{client_id}/agreements/{kind}"), WRITERS, 200, "some",
         lambda api, w, s: api.delete(f"/clients/{_c(w, 'birch')}/agreements/NDA")),
    Call("detach client copy", ("DELETE", "/clients/{client_id}/agreements/{kind}"), WRITERS, 202, "some",
         lambda api, w, s: api.delete(f"/clients/{_c(w, 'cinder')}/agreements/NDA")),
    Call("legacy delete", ("DELETE", "/agreements/{agreement_id}"), WRITERS, 202, "some", lambda api, w, s: api.delete(f"/agreements/{w.heron_msa}")),
    Call("relationship", ("PUT", "/clients/{client_id}/relationship"), WRITERS, 200, "some",
         lambda api, w, s: api.put(f"/clients/{_c(w, 'dorado')}/relationship",
                                   json={"relationship": "existing", "note": "Worked with them before"})),
    Call("standard upload", ("POST", "/agreements/standard/{kind}"), WRITERS, 201, "some",
         lambda api, w, s: api.post("/agreements/standard/MSA", files=_file("Lane Standard MSA v2.pdf", PDF))),
    # SystemAdmin only
    Call("batch dry run", ("POST", "/agreements/batches"), ADMINS, 200, "none", _batch_dry_run),
    Call("batch run", ("POST", "/agreements/batches"), ADMINS, 202, "some", _batch_run),
    Call("batch undo", ("POST", "/agreements/batches/{label}/undo"), ADMINS, 202, "some",
         lambda api, w, s: api.post(f"/agreements/batches/{s.get('label', 'AG-0002')}/undo")),
    Call("mapping save", ("PUT", "/agreements/hubspot-mapping"), ADMINS, 200, "some",
         lambda api, w, s: api.put("/agreements/hubspot-mapping",
                                   json={"items": [{"value": "Signed MSA", "action": "covered"}]})),
    Call("mapping apply dry run", ("POST", "/agreements/hubspot-mapping/apply"), ADMINS, 200, "none", lambda api, w, s: api.post("/agreements/hubspot-mapping/apply")),
    Call("mapping apply", ("POST", "/agreements/hubspot-mapping/apply"), ADMINS, 200, "some",
         lambda api, w, s: api.post("/agreements/hubspot-mapping/apply", params={"dry_run": "false"})),
)


def caller(role: str | None) -> AuthUser:
    label = role or "No role"
    return AuthUser(uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:lane-ta:{label}"),
                    f"{label.lower().replace(' ', '-')}.perm@example.test", f"{label} Person",
                    (role,) if role else ())


def test_the_matrix_names_every_contract_route():
    """The calls cover every method and path of the contract (and the legacy routes kept beside it)."""
    contract = {
        ("GET", "/agreements/workspace"), ("GET", "/agreements/export"), ("GET", "/agreements/documents"),
        ("GET", "/agreements/activity"), ("GET", "/agreements/standard"), ("POST", "/agreements/standard/{kind}"),
        ("GET", "/agreements/standard/{kind}/download"), ("GET", "/clients/{client_id}/agreements"),
        ("POST", "/clients/{client_id}/agreements/{kind}/client-copy"),
        ("POST", "/clients/{client_id}/agreements/{kind}/attach-standard"),
        ("PUT", "/clients/{client_id}/agreements/{kind}/mark"), ("DELETE", "/clients/{client_id}/agreements/{kind}/mark"),
        ("DELETE", "/clients/{client_id}/agreements/{kind}"), ("GET", "/clients/{client_id}/agreements/{kind}/download"),
        ("PUT", "/clients/{client_id}/relationship"), ("POST", "/agreements/batches"), ("GET", "/agreements/batches"),
        ("GET", "/agreements/batches/{batch_id}"), ("POST", "/agreements/batches/{batch_id}/undo"),
        ("GET", "/agreements/hubspot-values"), ("PUT", "/agreements/hubspot-mapping"),
        ("POST", "/agreements/hubspot-mapping/apply"),
    }
    import pathlib

    import yaml

    spec = yaml.safe_load((pathlib.Path(__file__).resolve().parents[2] / "docs/reference/openapi-agreements.yaml")
                          .read_text())
    listed = {(method.upper(), path.removeprefix("/api")) for path, item in spec["paths"].items()
              for method in item if method in ("get", "post", "put", "delete")}
    assert listed == contract
    assert len(CALLS) == 32 and len({c.name for c in CALLS}) == 32
    # The calls' own routes cover every contract route (placeholder names aside: {label} is the contract's
    # {batch_id}); each call is checked against the request it really sends in the matrix test below.
    def shape(route):
        return route[0], re.sub(r"\{[^}]+\}", "{}", route[1])

    assert {shape(r) for r in contract} <= {shape(c.route) for c in CALLS}


def _route_pattern(template: str) -> re.Pattern[str]:
    """A registered path template ('/clients/{client_id}/agreements') as a regex over a concrete path."""
    return re.compile("^" + "[^/]+".join(re.escape(part) for part in re.split(r"\{[^}]+\}", template)) + "$")


@pytest.mark.parametrize("role", [*ROLES, None], ids=[*ROLES, "no-role"])
async def test_every_route_answers_each_role_on_the_server(session, perm_world, role):
    storage = perm_world.base.storage
    state: dict = {}
    results: dict[str, int] = {}
    sent: list[tuple[str, str]] = []

    async def record(request):
        sent.append((request.method, request.url.path))

    async with client_for(session, caller(role), storage, launcher=inline(session)) as api:
        api.event_hooks["request"].append(record)
        for call in CALLS:
            before = await snapshot(session, storage)
            mark = len(sent)
            response = await call.send(api, perm_world, state)
            after = await snapshot(session, storage)
            results[call.name] = response.status_code
            # The call really sends the request it claims to cover (not just any route that answers alike).
            assert sent[mark:], call.name
            method, path = sent[-1]
            assert method == call.route[0] and _route_pattern(call.route[1]).match(path), (call.name, sent[mark:])
            if role in call.allowed:
                assert response.status_code == call.status, (role, call.name, response.text)
                if call.effect == "none":
                    assert after == before, (role, call.name)  # a read (or a dry run) writes nothing
                else:
                    assert business(after) != business(before), (role, call.name)
            else:
                # 403 from the server's role check, and no side effect at all.
                assert (response.status_code, response.json()) == (403, REFUSED), (role, call.name, response.text)
                assert after == before, (role, call.name)
    allowed = {c.name for c in CALLS if role in c.allowed}
    assert {name for name, status in results.items() if status != 403} == allowed
    if role in ADMINS:
        # The admin's batch ran inline and was undone; its rows are gone, the cutover stays.
        batch = (await session.scalars(select(AgreementBatch).where(AgreementBatch.label == state["label"]))).one()
        assert batch.status == "undone" and state["will_receive"] > 0
        assert (await session.get(AgreementsSettings, 1)).cutover_date is not None
    if role not in WRITERS:
        # Nothing a refused writer would have touched moved: the seeded copies are still the only rows.
        rows = (await session.scalars(select(Agreement))).all()
        assert {(r.id, r.version_no) for r in rows} == {(perm_world.arden_nda, 1), (perm_world.heron_msa, 1)}
        assert (await session.scalars(select(AgreementMark))).all() == []
