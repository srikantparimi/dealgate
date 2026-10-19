"""S24-AG1 T5 (lane T-B): the one-time attach batch on PostgreSQL, clause by clause (fixtures only).

Each clause of the directive's T5 sentence is one test or one named step (a ``step_...`` function, so a failure
names its clause):

 1. dry run changes nothing ...................... step_a_dry_run_changes_nothing (row counts, audit tail, every
                                                    row and relationship identical; not one INSERT/UPDATE/DELETE
                                                    or row lock is even sent)
 2. include_net_new_past_stage_1 targets exactly
    the net-new clients whose requirement is
    required, and they stay net new with state
    standard .................................... step_the_option_targets_exactly_the_required_net_new_clients
                                                    + step_net_new_targets_stay_net_new_with_state_standard
 3. idempotent re-run ............................ step_a_repeated_key_returns_the_same_batch_and_nothing_is_left
                                                    + step_a_new_key_attaches_only_what_is_missing_and_counts_skips
                                                    + step_a_new_key_attaches_nothing_new_once_its_client_holds_
                                                      everything_and_counts_skips
 4. commits every 25 ............................. test_t5_the_job_commits_every_25_clients_...
 5. kill mid-run, then resume: no duplicate
    (client, kind) rows; attached + skipped add up  test_t5_a_job_killed_inside_a_chunk_...
 6. a concurrent second batch gets 409 ........... test_t5_the_job_commits_every_25_clients_... (while it runs)
 7. wrong confirm phrase refused ................. step_a_wrong_confirm_phrase_is_refused_with_nothing_written
 8. uploader is the running admin ................ step_the_rows_credit_the_admin_who_ran_it (+ after a resume by
                                                    label, as the CLI runs it, in the kill test)
 9. undo touches only that batch's standard rows . test_t5_undo_removes_only_this_batchs_standard_rows_...
10. client copies and marks made since untouched . (same test)
11. cutover set once, the America/Los_Angeles date step_the_cutover_is_the_los_angeles_date_of_the_first_run
                                                    + step_the_cutover_is_set_once_and_nothing_is_stamped_again
12. each relationship stamped once ............... step_every_relationship_is_stamped_once
13. audit rows present, verify_chain true ........ step_the_audit_rows_are_present_and_the_chain_verifies (and in
                                                    every other test)

The seed is test_s24_ag1_beb_client.seed (synthetic clients): existing Atlas (Closed Won) and Beacon (SOW);
net-new past stage 1 Cobalt (stage 3), Falcon (Hold) and Harbor (stage 5); Dune existing with stage-1 deals
only; Ember net new at stage 1; Granite net new with nothing; one run-tagged test client. Each test has its own
migrated scratch database (tests/s24_pg.py).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import event, select, text

from app.audit import _ADVISORY_LOCK_KEY, verify_chain
from app.models.agreements import AgreementBatch, AgreementMark, AgreementsSettings, StandardAgreement
from app.models.audit import AuditEvent
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.deletion import DeletionJob
from app.services import agreement_audit as aa
from app.services import agreement_batches
from tests.s24_pg import POSTGRES, scratch_postgres
from tests.test_s24_ag1_beb_client import ADMIN, LEGAL, PDF, SALES, TODAY, deal, env, seed, upload  # noqa: F401
from tests.test_s24_ag1_shared_object_pg import (
    BOTH,
    RUNNER,
    Jobs,
    VersionedStore,
    add_user,
    api_for,
    count,
    real,
    snapshot,
)

pytestmark = POSTGRES

FIRST_FIVE = ["Atlas Foods", "Beacon Logistics", "Cobalt Systems", "Falcon Capital", "Harbor Labs"]


async def audit_rows(session, action: str) -> list[AuditEvent]:
    return list((await session.scalars(select(AuditEvent).where(AuditEvent.action == action)
                                       .order_by(AuditEvent.ts, AuditEvent.id))).all())


# --- 1 and 2 (dry-run half) --------------------------------------------------------------------------------


async def step_a_dry_run_changes_nothing(engine, factory, c) -> tuple[dict, list[dict]]:
    before = await snapshot(factory)
    sent: list[str] = []

    def watch(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        words = " ".join(statement.split()).upper()
        if words.startswith(("INSERT", "UPDATE", "DELETE")) or " FOR UPDATE" in words:
            sent.append(statement)

    requests = {
        "default": {"kinds": list(BOTH)},  # dry_run is the default
        "net_new": {"kinds": list(BOTH), "dry_run": True, "include_net_new_past_stage_1": True},
        "msa_only": {"kinds": ["MSA"], "include_net_new_past_stage_1": True},
        "chosen": {"kinds": list(BOTH), "include_net_new_past_stage_1": True,
                   "include_client_ids": [str(c["dune"]), str(c["kestrel"])],
                   "exclude_client_ids": [str(c["harbor"])]},
    }
    bodies: dict[str, dict] = {}
    event.listen(engine.sync_engine, "before_cursor_execute", watch)
    try:
        async with api_for(factory, ADMIN) as admin:
            for name, body in requests.items():
                response = await admin.post("/agreements/batches", json=body)
                assert response.status_code == 200, (name, response.text)
                bodies[name] = response.json()
            workspace = await admin.get("/agreements/workspace", params={"relationship": "net_new", "page_size": 100})
            assert workspace.status_code == 200, workspace.text
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", watch)
    assert sent == []
    assert await snapshot(factory) == before
    return bodies, workspace.json()["items"]


def step_the_option_targets_exactly_the_required_net_new_clients(bodies: dict, rows: list[dict]) -> None:
    required = {r["name"] for r in rows if r["requirement"] == "required"}
    test_data = {r["name"] for r in rows if "test_data" in r["flags"]}
    assert required == {"Cobalt Systems", "Falcon Capital", "Harbor Labs", "smoke Kestrel Pilot"}
    assert test_data == {"smoke Kestrel Pilot"}

    def picked(body: dict, relationship: str | None = None) -> set[str]:
        return {t["name"] for t in body["targets"] if t["included"] and relationship in (None, t["relationship"])}

    plain, wide = bodies["default"], bodies["net_new"]
    assert picked(plain, "net_new") == set() and {t["relationship"] for t in plain["targets"]} == {"existing"}
    assert picked(wide, "net_new") == required - test_data
    assert picked(wide) - picked(plain) == required - test_data  # the option adds exactly these, nothing else
    assert picked(plain) <= picked(wide)
    listed = {t["name"]: (t["included"], t["reason"]) for t in wide["targets"]}
    assert listed["smoke Kestrel Pilot"] == (False, "test_data")  # required, but test data: offered unticked
    assert not {"Ember Retail", "Granite Media"} & set(listed)  # stage 1 only / nothing needed: never offered
    assert (wide["will_receive"], wide["net_new_included"], wide["existing_included"],
            wide["net_new_untouched"]) == (5, 3, 2, 3)
    assert (plain["will_receive"], plain["net_new_included"], plain["net_new_untouched"]) == (2, 0, 6)
    msa = bodies["msa_only"]  # Beacon already holds an MSA (a mark): counted as holding, not listed
    assert "Beacon Logistics" not in {t["name"] for t in msa["targets"]}
    assert (msa["will_receive"], msa["already_hold"]) == (4, 1)
    assert picked(bodies["chosen"]) == {"Atlas Foods", "Beacon Logistics", "Cobalt Systems", "Falcon Capital",
                                        "Dune Farms", "smoke Kestrel Pilot"}


async def test_t5_a_dry_run_changes_nothing_and_the_option_adds_exactly_the_required_net_new_clients(env):  # noqa: F811
    async with scratch_postgres() as (engine, factory):
        async with factory() as s:
            seeded = await seed(s)
            kestrel = Client(name="smoke Kestrel Pilot", hubspot_company_id="c-kestrel")  # run-tagged: test data
            s.add(kestrel)
            await s.flush()
            s.add(deal(kestrel.id, 3, "kestrel-0"))
            await s.commit()
        c = {**seeded.clients, "kestrel": kestrel.id}
        async with api_for(factory, LEGAL) as legal:  # earlier writes, so the audit tail is not empty
            marked = await legal.put(f"/clients/{c['beacon']}/agreements/MSA/mark",
                                     json={"reason": "other", "marked_on": TODAY.isoformat()})
            assert marked.status_code == 200, marked.text
            pinned = await legal.put(f"/clients/{c['granite']}/relationship", json={"relationship": "net_new"})
            assert pinned.status_code == 200, pinned.text
        bodies, rows = await step_a_dry_run_changes_nothing(engine, factory, c)
        step_the_option_targets_exactly_the_required_net_new_clients(bodies, rows)
        async with factory() as s:
            assert len((await snapshot(factory))["audit_tail"]) == 2 and await verify_chain(s)


# --- 7, 8, 2 (run half), 11, 12, 13, 3 ---------------------------------------------------------------------


async def step_a_wrong_confirm_phrase_is_refused_with_nothing_written(factory, jobs: Jobs) -> None:
    before = await snapshot(factory)
    async with api_for(factory, RUNNER, launcher=jobs) as runner:
        for i, phrase in enumerate(("ATTACH 4", "ATTACH 6", "attach 5", "Attach 5", "ATTACH  5", "ATTACH 5 ",
                                    " ATTACH 5", "ATTACH 05", "ATTACH5", "ATTACH", "5", "")):
            response = await runner.post("/agreements/batches", json=real(f"t5-wrong-{i}", phrase))
            assert (response.status_code, response.json()["detail"]) == (422, "Type ATTACH 5 to confirm."), phrase
        missing = await runner.post("/agreements/batches", json=real("t5-wrong-none", None))
        assert missing.status_code == 422, missing.text
    assert jobs.calls == []
    assert await snapshot(factory) == before


async def step_the_rows_credit_the_admin_who_ran_it(factory, c) -> None:
    async with factory() as s:
        batch = (await s.scalars(select(AgreementBatch))).one()
        rows = (await s.scalars(select(Agreement))).all()
        versions = (await s.scalars(select(AgreementFileVersion))).all()
        assert batch.created_by == RUNNER.id
        assert len(rows) == 10 and {(r.uploaded_by, r.batch_id, r.source) for r in rows} == {
            (RUNNER.id, batch.id, "standard")}
        assert len(versions) == 10 and {(v.uploaded_by, v.batch_id) for v in versions} == {(RUNNER.id, batch.id)}
        # The standard copies were uploaded by someone else, who is never credited with the attachments.
        assert set((await s.scalars(select(StandardAgreement.uploaded_by))).all()) == {ADMIN.id}
        assert {a.actor_id for a in await audit_rows(s, aa.BATCH_ATTACHED)} == {RUNNER.id}
    async with api_for(factory, SALES) as viewer:
        card = (await viewer.get(f"/clients/{c['cobalt']}/agreements")).json()["nda"]
    assert (card["uploaded_by"], card["batch_id"], card["source_label"]) == ("Bree Batch", "AG-0001", "Standard v1")


async def step_net_new_targets_stay_net_new_with_state_standard(factory, c) -> None:
    async with api_for(factory, SALES) as viewer:
        workspace = (await viewer.get("/agreements/workspace",
                                      params={"relationship": "net_new", "page_size": 100})).json()
        panels = {k: (await viewer.get(f"/clients/{c[k]}/agreements")).json() for k in ("cobalt", "falcon", "harbor")}
    for key, panel in panels.items():
        assert (panel["relationship"], panel["provisional"], panel["requirement"], panel["nda"]["state"],
                panel["msa"]["state"], panel["needs_attention"]) == (
            "net_new", False, "required", "standard", "standard", False), key
    rows = {r["name"]: r for r in workspace["items"]}
    required = {name for name, r in rows.items() if r["requirement"] == "required"}
    assert required == {"Cobalt Systems", "Falcon Capital", "Harbor Labs"}
    assert {(rows[n]["nda"]["state"], rows[n]["msa"]["state"]) for n in required} == {("standard", "standard")}
    cards = {card["key"]: card["value"] for card in workspace["cards"]}
    assert (cards["needs_attention"], cards["standard_attached"]) == (0, 5)
    async with factory() as s:
        stored = (await s.execute(select(Client.relationship, Client.relationship_basis).where(
            Client.id.in_([c["cobalt"], c["falcon"], c["harbor"]])))).all()
    assert set(stored) == {("net_new", "none")}


async def step_the_cutover_is_the_los_angeles_date_of_the_first_run(factory) -> tuple:
    async with factory() as s:
        settings = await s.get(AgreementsSettings, 1)
        # DEALGATE_NOW is 05:30 UTC on 16 October: still 15 October in Los Angeles.
        assert (settings.cutover_date, settings.set_by) == (date(2026, 10, 15), RUNNER.id)
        (cut,) = await audit_rows(s, aa.CUTOVER_SET)
        assert cut.after == {"cutover_date": "2026-10-15", "batch": "AG-0001", "stamped": 8, "existing": 4,
                             "net_new": 4}
        row = (settings.cutover_date, settings.set_by, settings.set_at)
    async with api_for(factory, SALES) as viewer:
        cutover = (await viewer.get("/agreements/workspace")).json()["cutover"]
    assert (cutover["set"], cutover["date"]) == (True, "2026-10-15")
    return row


async def step_every_relationship_is_stamped_once(factory, c) -> dict:
    async with factory() as s:
        clients = {r.id: r for r in (await s.scalars(select(Client))).all()}
        stamps = await audit_rows(s, aa.RELATIONSHIP_STAMPED)
    stamped = [uuid.UUID(e.entity_id) for e in stamps]
    expected = {cid for key, cid in c.items() if key not in ("ember", "retired")}
    assert len(stamped) == len(set(stamped)) == 8 and set(stamped) == expected
    assert {e.actor_id for e in stamps} == {RUNNER.id}
    for cid in expected:
        stamp = next(e for e in stamps if e.entity_id == str(cid))
        client = clients[cid]
        assert (client.relationship, client.relationship_basis, client.relationship_set_by) == (
            stamp.after["relationship"], stamp.after["relationship_basis"], RUNNER.id)
    # A writer's earlier manual choice is never stamped over; an archived client is not stamped.
    ember, retired = clients[c["ember"]], clients[c["retired"]]
    assert (ember.relationship, ember.relationship_basis, ember.relationship_set_by) == ("existing", "manual", LEGAL.id)
    assert (retired.relationship, retired.relationship_set_at) == (None, None)
    return {cid: (r.relationship, r.relationship_basis, r.relationship_set_by, r.relationship_set_at)
            for cid, r in clients.items()}


async def step_the_audit_rows_are_present_and_the_chain_verifies(factory) -> None:
    async with factory() as s:
        (started,) = await audit_rows(s, aa.BATCH_STARTED)
        assert started.after == {"label": "AG-0001", "kinds": ["NDA", "MSA"], "target_count": 5, "existing": 2,
                                 "net_new": 3, "include_net_new": True, "standard_versions": {"NDA": 1, "MSA": 1}}
        attached = await audit_rows(s, aa.BATCH_ATTACHED)
        assert sorted(a.after["client_name"] for a in attached) == FIRST_FIVE
        assert {(a.after["label"], tuple(a.after["kinds"]), a.entity_id) for a in attached} == {
            ("AG-0001", ("NDA", "MSA"), started.entity_id)}
        (run,) = await audit_rows(s, aa.BATCH_RUN)
        assert {k: run.after[k] for k in ("label", "attached_clients", "attached_count", "skipped_count",
                                          "target_count", "existing", "net_new")} == {
            "label": "AG-0001", "attached_clients": 5, "attached_count": 10, "skipped_count": 0, "target_count": 5,
            "existing": 2, "net_new": 3}
        assert {e.actor_id for e in (started, *attached, run)} == {RUNNER.id}
        assert await verify_chain(s)


async def step_a_repeated_key_returns_the_same_batch_and_nothing_is_left(factory, jobs: Jobs) -> None:
    before = await snapshot(factory)
    async with api_for(factory, RUNNER, launcher=jobs) as runner:
        again = await runner.post("/agreements/batches", json=real("t5-first", "ATTACH 5"))
        nothing_left = await runner.post("/agreements/batches", json=real("t5-nothing-left", "ATTACH 0"))
    assert again.status_code == 202, again.text
    assert (again.json()["id"], again.json()["status"], again.json()["attached_count"]) == ("AG-0001", "done", 10)
    assert len(jobs.calls) == 1  # the original is returned; no second job is launched
    assert (nothing_left.status_code, nothing_left.json()["detail"]) == (
        422, "No client is selected to receive a copy.")
    assert await snapshot(factory) == before


async def step_a_new_key_attaches_only_what_is_missing_and_counts_skips(factory, jobs: Jobs, c) -> None:
    async with api_for(factory, LEGAL) as legal:  # two clients lose their NDA; they keep the batch's MSA
        for key in ("beacon", "cobalt"):
            assert (await legal.delete(f"/clients/{c[key]}/agreements/NDA")).status_code == 200
    async with factory() as s:
        kept = {(r.client_id, r.kind): (r.id, r.batch_id, r.uploaded_by) for r in (await s.scalars(
            select(Agreement).where(Agreement.client_id.in_([c["beacon"], c["cobalt"]])))).all()}
    assert set(kept) == {(c["beacon"], "MSA"), (c["cobalt"], "MSA")}
    async with api_for(factory, ADMIN, launcher=jobs) as admin:
        dry = (await admin.post("/agreements/batches", json={"kinds": list(BOTH),
                                                             "include_net_new_past_stage_1": True})).json()
        assert ({t["name"] for t in dry["targets"] if t["included"]}, dry["will_receive"], dry["already_hold"]) == (
            {"Beacon Logistics", "Cobalt Systems"}, 2, 3)
        second = await admin.post("/agreements/batches", json=real("t5-second", "ATTACH 2"))
    assert second.status_code == 202, second.text
    body = second.json()
    assert (body["id"], body["status"], body["created_by"]) == ("AG-0002", "done", "Ada Admin")
    assert (body["target_count"], body["attached_count"], body["attached_clients"], body["skipped_count"]) == (
        2, 2, 2, 2)
    assert body["attached_count"] + body["skipped_count"] == body["target_count"] * len(BOTH)
    async with factory() as s:
        pairs = (await s.execute(select(Agreement.client_id, Agreement.kind))).all()
        assert len(pairs) == len(set(pairs)) == 10
        second_id = await s.scalar(select(AgreementBatch.id).where(AgreementBatch.label == "AG-0002"))
        after = {(r.client_id, r.kind): (r.id, r.batch_id, r.uploaded_by) for r in (await s.scalars(
            select(Agreement).where(Agreement.client_id.in_([c["beacon"], c["cobalt"]])))).all()}
    assert {k: v for k, v in after.items() if k[1] == "MSA"} == kept  # the held kind is untouched
    assert {(v[1], v[2]) for k, v in after.items() if k[1] == "NDA"} == {(second_id, ADMIN.id)}


async def step_a_new_key_attaches_nothing_new_once_its_client_holds_everything_and_counts_skips(factory, c) -> None:
    # Harbor loses its MSA and a new batch is started for it; before the job runs, a writer marks the MSA covered.
    async with api_for(factory, LEGAL) as legal:
        assert (await legal.delete(f"/clients/{c['harbor']}/agreements/MSA")).status_code == 200
    deferred = Jobs(factory, "deferred")
    async with api_for(factory, ADMIN, launcher=deferred) as admin:
        third = await admin.post("/agreements/batches", json=real("t5-third", "ATTACH 1"))
    assert third.status_code == 202, third.text
    assert (third.json()["id"], third.json()["status"], third.json()["target_count"]) == ("AG-0003", "running", 1)
    ((batch_id, _phase),) = deferred.calls
    async with api_for(factory, LEGAL) as legal:
        marked = await legal.put(f"/clients/{c['harbor']}/agreements/MSA/mark",
                                 json={"reason": "confirmed_with_client", "marked_on": TODAY.isoformat()})
        assert marked.status_code == 200, marked.text
    rows_before = (await snapshot(factory))["agreements"]
    assert await agreement_batches.run_batch(factory, batch_id) == "done"
    async with api_for(factory, SALES) as viewer:
        body = (await viewer.get("/agreements/batches/AG-0003")).json()
    assert (body["status"], body["target_count"], body["done_count"], body["attached_count"],
            body["attached_clients"], body["skipped_count"]) == ("done", 1, 1, 0, 0, 2)
    assert body["attached_count"] + body["skipped_count"] == body["target_count"] * len(BOTH)
    assert (await snapshot(factory))["agreements"] == rows_before  # not one row added, changed or removed
    async with factory() as s:
        assert await count(s, Agreement, Agreement.batch_id == batch_id) == 0
        (run,) = [e for e in await audit_rows(s, aa.BATCH_RUN) if e.after["label"] == "AG-0003"]
        assert (run.after["attached_clients"], run.after["attached_count"], run.after["skipped_count"]) == (0, 0, 2)
        assert await count(s, AuditEvent, AuditEvent.action == aa.BATCH_ATTACHED,
                           AuditEvent.entity_id == str(batch_id)) == 0
        assert await verify_chain(s)


async def step_the_cutover_is_set_once_and_nothing_is_stamped_again(factory, cutover_row, relationships) -> None:
    async with factory() as s:
        settings = await s.get(AgreementsSettings, 1)
        assert (settings.cutover_date, settings.set_by, settings.set_at) == cutover_row
        assert len(await audit_rows(s, aa.CUTOVER_SET)) == 1
        assert len(await audit_rows(s, aa.RELATIONSHIP_STAMPED)) == 8
        now = {r.id: (r.relationship, r.relationship_basis, r.relationship_set_by, r.relationship_set_at)
               for r in (await s.scalars(select(Client))).all()}
        assert now == relationships
        assert await verify_chain(s)


async def test_t5_a_real_run_credits_the_runner_keeps_net_new_sets_the_cutover_once_stamps_once_and_reruns_safely(
        env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DEALGATE_NOW", "2026-10-16T05:30:00+00:00")  # 22:30 on 15 October in Los Angeles
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            seeded = await seed(s)
            retired = Client(name="Retired Quarry Co", hubspot_company_id="c-retired",
                             archived_at=datetime(2026, 9, 1, tzinfo=UTC))
            s.add(retired)
            await s.commit()
        await add_user(factory, RUNNER)
        c = {**seeded.clients, "retired": retired.id}
        async with api_for(factory, LEGAL) as legal:  # a writer's correction made before the cutover
            pinned = await legal.put(f"/clients/{c['ember']}/relationship", json={"relationship": "existing"})
            assert pinned.status_code == 200, pinned.text
        jobs = Jobs(factory)

        await step_a_wrong_confirm_phrase_is_refused_with_nothing_written(factory, jobs)
        async with api_for(factory, RUNNER, launcher=jobs) as runner:
            first = await runner.post("/agreements/batches", json=real("t5-first", "ATTACH 5"))
        assert first.status_code == 202, first.text
        body = first.json()
        assert (body["id"], body["status"], body["created_by"], body["target_count"], body["done_count"],
                body["attached_count"], body["attached_clients"], body["skipped_count"]) == (
            "AG-0001", "done", "Bree Batch", 5, 5, 10, 5, 0)
        await step_the_rows_credit_the_admin_who_ran_it(factory, c)
        await step_net_new_targets_stay_net_new_with_state_standard(factory, c)
        cutover_row = await step_the_cutover_is_the_los_angeles_date_of_the_first_run(factory)
        relationships = await step_every_relationship_is_stamped_once(factory, c)
        await step_the_audit_rows_are_present_and_the_chain_verifies(factory)

        await step_a_repeated_key_returns_the_same_batch_and_nothing_is_left(factory, jobs)
        monkeypatch.setenv("DEALGATE_NOW", "2026-10-20T18:00:00+00:00")  # a later day: nothing may move
        await step_a_new_key_attaches_only_what_is_missing_and_counts_skips(factory, jobs, c)
        await step_a_new_key_attaches_nothing_new_once_its_client_holds_everything_and_counts_skips(factory, c)
        await step_the_cutover_is_set_once_and_nothing_is_stamped_again(factory, cutover_row, relationships)


# --- 4 and 6 -----------------------------------------------------------------------------------------------


async def test_t5_the_job_commits_every_25_clients_and_a_second_batch_or_an_undo_gets_409_while_it_runs(
        env):  # noqa: F811
    async with scratch_postgres() as (engine, factory):
        async with factory() as s:
            await seed(s, extra_existing=50)  # 52 existing + 3 net new past stage 1 = 55 targets
        jobs = Jobs(factory, "deferred")
        async with api_for(factory, ADMIN, launcher=jobs) as admin:
            started = await admin.post("/agreements/batches", json=real("t5-chunks", "ATTACH 55"))
            assert started.status_code == 202, started.text
            assert (started.json()["status"], started.json()["done_count"]) == ("running", 0)
            ((batch_id, phase),) = jobs.calls
            assert phase == "run"

            commits: list[int] = []
            counting = [True]
            progress: list[tuple[int, int, int, int]] = []
            while_running: dict[str, object] = {}

            def on_commit(conn):  # noqa: ARG001
                if counting[0]:
                    commits.append(1)

            async def after_each_chunk(_batch_id):
                async with factory() as s:
                    batch = await s.get(AgreementBatch, batch_id)
                    progress.append((len(commits), batch.done_count, await count(s, Agreement),
                                     await count(s, AuditEvent, AuditEvent.action == aa.BATCH_ATTACHED)))
                if len(progress) == 1:  # the job is mid-run: a second batch and an undo must wait
                    counting[0] = False
                    try:
                        while_running["second"] = await admin.post("/agreements/batches",
                                                                   json=real("t5-second", "ATTACH 55"))
                        while_running["undo"] = await admin.post("/agreements/batches/AG-0001/undo")
                        while_running["poll"] = await admin.get("/agreements/batches/AG-0001")
                    finally:
                        counting[0] = True

            event.listen(engine.sync_engine, "commit", on_commit)
            try:
                final = await agreement_batches.run_batch(factory, batch_id, on_chunk=after_each_chunk)
            finally:
                event.remove(engine.sync_engine, "commit", on_commit)
        assert final == "done"
        # One commit per chunk of at most 25 clients (rows and their audit rows together), then the finish.
        assert progress == [(1, 25, 50, 25), (2, 50, 100, 50), (3, 55, 110, 55)]
        assert len(commits) == 4
        second, undo, poll = while_running["second"], while_running["undo"], while_running["poll"]
        assert (second.status_code, second.json()["detail"]) == (
            409, "Batch AG-0001 is still running. Wait for it to finish.")
        assert (undo.status_code, undo.json()["detail"]) == (
            409, "Batch AG-0001 is still running. Undo it when it has finished.")
        assert (poll.status_code, poll.json()["status"], poll.json()["done_count"]) == (200, "running", 25)
        async with factory() as s:
            (batch,) = (await s.scalars(select(AgreementBatch))).all()  # the refused start left no batch
            assert (batch.status, batch.done_count, batch.attached_count, batch.running_guard) == (
                "done", 55, 110, None)
            assert await count(s, AuditEvent, AuditEvent.action == aa.BATCH_STARTED) == 1
            assert await verify_chain(s)


# --- 5 (and 8 after a resume) ------------------------------------------------------------------------------


async def wait_for_the_audit_lock_waiter(factory, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        async with factory() as s:
            waiting = await s.scalar(text(
                "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                "AND wait_event_type = 'Lock' AND wait_event = 'advisory'"))
        if waiting:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the job never reached the audit lock")


async def test_t5_a_job_killed_inside_a_chunk_resumes_without_duplicates_and_its_counts_add_up(env):  # noqa: F811
    store = VersionedStore()
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            await seed(s, extra_existing=50)  # 55 targets
        holder: dict[str, object] = {}
        armed = asyncio.Event()

        async def hold_the_audit_lock_after_the_first_chunk(_batch_id):
            # The next chunk inserts its rows, then waits on the audit chain's lock: the kill lands mid-chunk.
            if "session" not in holder:
                side = factory()
                await side.execute(text("SELECT pg_advisory_xact_lock(:k)").bindparams(k=_ADVISORY_LOCK_KEY))
                holder["session"] = side
                armed.set()

        jobs = Jobs(factory, "background", on_chunk=hold_the_audit_lock_after_the_first_chunk)
        async with api_for(factory, ADMIN, launcher=jobs) as admin:
            started = await admin.post("/agreements/batches", json=real("t5-kill", "ATTACH 55"))
        assert started.status_code == 202, started.text
        (task,) = jobs.tasks
        await asyncio.wait_for(armed.wait(), 30)
        await wait_for_the_audit_lock_waiter(factory)
        task.cancel()  # the process dies inside chunk 2
        with pytest.raises(asyncio.CancelledError):
            await task
        side = holder["session"]
        await side.rollback()
        await side.close()

        async with factory() as s:
            batch = (await s.scalars(select(AgreementBatch))).one()
            targets = [uuid.UUID(v) for v in batch.target_client_ids]
            # Chunk 1 is committed; nothing of chunk 2 survived; the batch still reads running.
            assert (batch.status, batch.done_count, batch.attached_count, batch.running_guard) == (
                "running", 25, 50, True)
            assert await count(s, Agreement) == 50
            assert await count(s, AuditEvent, AuditEvent.action == aa.BATCH_ATTACHED) == 25
        # While the job is dead, a writer gives two later targets what the batch would attach.
        async with api_for(factory, LEGAL, storage=store) as legal:
            assert (await legal.post(f"/clients/{targets[-1]}/agreements/NDA/client-copy",
                                     **upload("own-nda.pdf", PDF))).status_code == 201
            for client_id, kind in ((targets[-1], "MSA"), (targets[-2], "NDA")):
                marked = await legal.put(f"/clients/{client_id}/agreements/{kind}/mark",
                                         json={"reason": "signed_outside_dealgate", "marked_on": TODAY.isoformat()})
                assert marked.status_code == 200, marked.text

        # Its heartbeat is fresh, so the every-minute resume leaves it alone; the named resume continues it.
        assert await agreement_batches.resume_stale(factory) == []
        resumed = await asyncio.wait_for(agreement_batches.resume_stale(factory, label="AG-0001"), 60)
        assert resumed == [{"batch": "AG-0001", "was": "running", "now": "done"}]

        async with factory() as s:
            batch = (await s.scalars(select(AgreementBatch))).one()
            assert (batch.status, batch.done_count, batch.running_guard) == ("done", 55, None)
            assert (batch.attached_count, batch.skipped_count, batch.attached_clients) == (107, 3, 54)
            assert batch.attached_count + batch.skipped_count == batch.target_count * len(BOTH) == 110
            pairs = (await s.execute(select(Agreement.client_id, Agreement.kind))).all()
            assert len(pairs) == len(set(pairs)) == 108  # 107 attached + the writer's own copy
            mine = (await s.scalars(select(Agreement).where(Agreement.batch_id == batch.id))).all()
            assert len(mine) == batch.attached_count
            assert {(r.uploaded_by, r.source) for r in mine} == {(ADMIN.id, "standard")}  # not the resumer
            attached = await audit_rows(s, aa.BATCH_ATTACHED)
            assert len(attached) == len({a.after["client_id"] for a in attached}) == batch.attached_clients
            assert await count(s, AgreementMark, AgreementMark.removed_at.is_(None)) == 2
            assert await verify_chain(s)


# --- 9 and 10 ----------------------------------------------------------------------------------------------


async def test_t5_undo_removes_only_this_batchs_standard_rows_and_leaves_client_copies_and_marks_made_since(
        env):  # noqa: F811
    store = VersionedStore()
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            seeded = await seed(s)
        await add_user(factory, RUNNER)
        for standard in seeded.standards.values():
            store.hold(standard.file_key)
        c = seeded.clients
        jobs = Jobs(factory)
        async with api_for(factory, ADMIN, storage=store, launcher=jobs) as admin, \
                api_for(factory, LEGAL, storage=store) as legal:
            assert (await admin.post("/agreements/batches", json=real("t5-undo-1", "ATTACH 5"))).status_code == 202
            # Another batch: Dune (stage 1 only, left out by default) included by the admin.
            other = await admin.post("/agreements/batches", json=real("t5-undo-2", "ATTACH 1",
                                                                       include_client_ids=[str(c["dune"])]))
            assert (other.status_code, other.json()["id"], other.json()["attached_count"]) == (202, "AG-0002", 2)
            # Made since AG-0001: client copies over two of its rows, and a mark where one of its rows was removed.
            for key, kind, name, note in (("atlas", "NDA", "atlas-nda.pdf", "Updated payment terms"),
                                          ("falcon", "MSA", "falcon-msa.pdf", None)):
                copy = await legal.post(f"/clients/{c[key]}/agreements/{kind}/client-copy", **upload(name, PDF, note))
                assert copy.status_code == 201, copy.text
            assert (await legal.delete(f"/clients/{c['beacon']}/agreements/MSA")).status_code == 200
            marked = await legal.put(f"/clients/{c['beacon']}/agreements/MSA/mark",
                                     json={"reason": "signed_outside_dealgate", "marked_on": TODAY.isoformat(),
                                           "note": "Signed copy is held by Legal"})
            assert marked.status_code == 200, marked.text
        before = await snapshot(factory)
        async with factory() as s:
            copies = {(r.client_id, r.kind): (r.id, r.file_key, r.version_no, r.source, r.note) for r in (
                await s.scalars(select(Agreement).where(Agreement.source == "client"))).all()}
            copy_history = sorted((str(v.agreement_id), v.version_no, v.file_key, v.source, str(v.batch_id))
                                  for v in (await s.scalars(select(AgreementFileVersion).where(
                                      AgreementFileVersion.agreement_id.in_([v[0] for v in copies.values()])))).all())
            marks = [(m.id, m.client_id, m.kind, m.removed_at, m.note) for m in (await s.scalars(
                select(AgreementMark))).all()]
            other_rows = sorted((str(r.id), r.batch_id) for r in (await s.scalars(
                select(Agreement).where(Agreement.client_id == c["dune"]))).all())
            written = {a: len(await audit_rows(s, a)) for a in (aa.CLIENT_REPLACED, aa.MARKED, aa.DETACHED)}
        assert set(copies) == {(c["atlas"], "NDA"), (c["falcon"], "MSA")} and len(copy_history) == 4
        objects = dict(store.objects)

        async with api_for(factory, RUNNER, storage=store, launcher=jobs) as runner:
            assert (await runner.get("/agreements/batches/AG-0001")).json()["undo_would_remove"] == 7
            undo = await runner.post("/agreements/batches/AG-0001/undo")
            assert undo.status_code == 202, undo.text
            panels = {k: (await runner.get(f"/clients/{c[k]}/agreements")).json()
                      for k in ("atlas", "beacon", "cobalt", "dune", "falcon")}
        body = undo.json()
        assert (body["status"], body["undone_count"], body["undone_by"], body["undo_would_remove"]) == (
            "undone", 7, "Bree Batch", 0)

        after = await snapshot(factory)
        async with factory() as s:
            left = {(r.client_id, r.kind): (r.id, r.file_key, r.version_no, r.source, r.note) for r in (
                await s.scalars(select(Agreement).where(Agreement.source == "client"))).all()}
            assert left == copies  # the client copies made since are untouched ...
            history_now = sorted((str(v.agreement_id), v.version_no, v.file_key, v.source, str(v.batch_id))
                                 for v in (await s.scalars(select(AgreementFileVersion).where(
                                     AgreementFileVersion.agreement_id.in_([v[0] for v in copies.values()])))).all())
            assert history_now == copy_history  # ... and keep the batch's standard entry in their history
            assert [(m.id, m.client_id, m.kind, m.removed_at, m.note) for m in (await s.scalars(
                select(AgreementMark))).all()] == marks  # the mark too
            assert sorted((str(r.id), r.batch_id) for r in (await s.scalars(
                select(Agreement).where(Agreement.client_id == c["dune"]))).all()) == other_rows  # AG-0002 stays
            assert await count(s, Agreement, Agreement.source == "standard") == 2  # only Dune's, from AG-0002
            assert {a: len(await audit_rows(s, a)) for a in written} == written
            detached = await audit_rows(s, aa.BATCH_DETACHED)
            assert sorted((d.after["client_name"], tuple(d.after["kinds"])) for d in detached) == [
                ("Atlas Foods", ("MSA",)), ("Beacon Logistics", ("NDA",)), ("Cobalt Systems", ("MSA", "NDA")),
                ("Falcon Capital", ("NDA",)), ("Harbor Labs", ("MSA", "NDA"))]
            (undone,) = await audit_rows(s, aa.BATCH_UNDONE)
            assert (undone.after["removed"], undone.actor_id) == (7, RUNNER.id)
            assert await count(s, DeletionJob) == 0  # nothing to clean: the shared standard objects stay
            assert await count(s, StandardAgreement) == 2
            assert await verify_chain(s)
        assert store.objects == objects and store.delete_requests == []
        # The cutover and every relationship stay.
        assert (after["settings"], after["relationships"]) == (before["settings"], before["relationships"])

        assert (panels["atlas"]["nda"]["state"], panels["atlas"]["msa"]["state"]) == ("client", "existing_none")
        assert [h["what"] for h in panels["atlas"]["nda"]["history"]] == [
            "Standard copy replaced with a client copy: atlas-nda.pdf. Note: Updated payment terms",
            "Standard NDA v1 attached (batch AG-0001)"]
        assert (panels["beacon"]["nda"]["state"], panels["beacon"]["msa"]["state"]) == ("existing_none", "covered")
        assert (panels["dune"]["nda"]["batch_id"], panels["dune"]["msa"]["batch_id"]) == ("AG-0002", "AG-0002")
        # Undo restores the warning for the net-new clients that lost their standard copy.
        assert (panels["cobalt"]["needs_attention"], panels["cobalt"]["missing_kinds"]) == (True, ["NDA", "MSA"])
        assert (panels["falcon"]["nda"]["state"], panels["falcon"]["msa"]["state"],
                panels["falcon"]["needs_attention"]) == ("missing", "client", True)
