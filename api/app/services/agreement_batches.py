"""S24-AG1 B7 — the one-time attach of the standard copies: dry run, a resumable job, and undo.

* **Dry run** (the default) changes nothing. Targets follow the directive and the prototype's ``wizTargets``:
  existing clients missing a chosen kind start ticked; with ``include_net_new_past_stage_1`` the net-new clients
  whose requirement is ``required`` start ticked too; existing clients whose deals are only in stage 1, and test
  data, are listed unticked with their reason. Server-issued test fixtures are never offered or included.
* **Real run** (SystemAdmin): refused while another batch runs (409, ``running_guard``), when the confirm phrase
  is not exactly ``ATTACH <will_receive>`` or a chosen kind has no standard copy (422). A repeated idempotency
  key returns the original batch. The FIRST real run sets the cutover (America/Los_Angeles date) and stamps every
  client whose relationship is still empty with the live rule as of that date — once, in the same transaction
  as the batch row. The job then commits every 25 clients, with that chunk's audit rows in the same transaction
  (the audit chain serialises on one global lock, so one long transaction would stall every writer).
* **Durability**: the batch row is the job (``done_count`` is the cursor, ``heartbeat_at`` the lease). The API
  runs it as an asyncio task; ``worker/deletion_cleanup.py`` (every minute) and ``python -m
  worker.agreement_batches`` resume any running or undoing batch whose heartbeat is stale. Re-running a chunk
  never duplicates a row: a client that holds the kind (file or mark) is skipped, under the client row lock,
  and ``ux_agreement_client_kind`` is the last guard.
* **Undo** removes only this batch's rows whose source is still ``standard``; client copies and marks made since
  are untouched; the standard files, the cutover and every relationship stay.

Rows created by the batch carry its id and credit the admin who ran it (``uploaded_by``).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.agreements import AgreementBatch, AgreementMark, AgreementsSettings, StandardAgreement
from app.models.client import Agreement, AgreementFileVersion, Client
from app.models.user import User
from app.services import agreement_audit as audit
from app.services.agreement_status import (
    KINDS,
    BatchInfo,
    ClientFacts,
    Population,
    batch_payload,
    iso_z,
    live_relationship,
    load_agreement_population,
    person,
)
from app.services.agreements_service import snapshot, test_identity_blocked
from app.services.business_time import business_today

log = logging.getLogger("dealgate.agreement_batches")

CHUNK = 25
STALE_AFTER = timedelta(minutes=2)
REASONS = ("", "stage_1_only", "test_data")


# --- dry run ----------------------------------------------------------------------------------


def chosen_kinds(kinds) -> list[str]:
    requested = list(kinds or [])
    if not requested or any(k not in KINDS for k in requested):
        raise HTTPException(422, "Choose the NDA, the MSA or both.")
    return [k for k in KINDS if k in requested]


def holds(facts: ClientFacts, kind: str) -> bool:
    """A file of either source, or an active mark."""
    detail = facts.docs[kind]
    return detail.source in ("client", "standard") or detail.mark_source is not None


def stage_1_only(facts: ClientFacts) -> bool:
    """All open deals are in stage 1 and there is no Closed Won deal (Hold counts as past stage 1)."""
    s = facts.status
    return s.stage_bucket == "stage_1_only" and s.won_deals == 0


@dataclass
class Plan:
    kinds: list[str]
    targets: list[dict[str, Any]]
    included: list[ClientFacts]
    already_hold: int
    net_new_total: int

    @property
    def will_receive(self) -> int:
        return len(self.included)

    @property
    def net_new_included(self) -> int:
        return sum(1 for f in self.included if f.status.relationship == "net_new")

    @property
    def net_new_untouched(self) -> int:
        return self.net_new_total - self.net_new_included

    def preview(self, pop: Population) -> dict[str, Any]:
        return {
            "kinds": self.kinds, "will_receive": self.will_receive, "net_new_included": self.net_new_included,
            "already_hold": self.already_hold, "net_new_untouched": self.net_new_untouched,
            "targets": self.targets,
            # additive
            "existing_included": self.will_receive - self.net_new_included,
            "standard_missing": [k for k in self.kinds if pop.standard.get(k) is None],
            "cutover": {"set": pop.cutover is not None, "date": pop.cutover.isoformat() if pop.cutover else None},
        }


def plan(pop: Population, *, kinds: list[str], include_net_new: bool,
         include_ids: list[uuid.UUID] | None = None, exclude_ids: list[uuid.UUID] | None = None) -> Plan:
    """Who would receive the chosen standard copies. Pure over the shared population (no classification here)."""
    include = set(include_ids or ())
    exclude = set(exclude_ids or ())
    fixtures = set(getattr(pop.scope, "authorized_client_ids", None) or ())
    unknown = [i for i in include | exclude if i not in pop.clients]
    if unknown:
        raise HTTPException(422, "A chosen client is not known. Run the dry run again.")
    if include & fixtures:
        raise HTTPException(422, "Test fixtures are never attached in a backfill.")

    def by_name(items):
        return sorted(items, key=lambda f: (f[0] if isinstance(f, tuple) else f).input.name.casefold())

    base: list[ClientFacts] = []
    pipe: list[ClientFacts] = []
    held_back: list[tuple[ClientFacts, str]] = []
    for facts in pop.clients.values():
        status = facts.status
        if status.client_id in fixtures:
            continue
        test = "test_data" in status.flags
        if status.relationship == "existing":
            if test or stage_1_only(facts):
                held_back.append((facts, "test_data" if test else "stage_1_only"))
            else:
                base.append(facts)
        elif include_net_new and status.requirement == "required":
            if test:
                held_back.append((facts, "test_data"))
            else:
                pipe.append(facts)

    def needs(facts: ClientFacts) -> bool:
        return any(not holds(facts, k) for k in kinds)

    rows: list[tuple[ClientFacts, bool, str]] = [
        *((f, True, "") for f in by_name(base) if needs(f)),
        *((f, True, "") for f in by_name(pipe) if needs(f)),
        *((f, False, reason) for f, reason in by_name(held_back) if needs(f)),
    ]
    targets: list[dict[str, Any]] = []
    included: list[ClientFacts] = []
    for facts, default, reason in rows:
        cid = facts.status.client_id
        chosen = (default or cid in include) and cid not in exclude
        targets.append({"client_id": str(cid), "name": facts.status.name, "relationship": facts.status.relationship,
                        "included": chosen, "reason": reason})
        if chosen:
            included.append(facts)
    return Plan(
        kinds=kinds, targets=targets, included=included,
        already_hold=sum(1 for f in (*base, *pipe) if not needs(f)),
        net_new_total=sum(1 for f in pop.clients.values() if f.status.relationship == "net_new"),
    )


async def dry_run(session: AsyncSession, viewer, *, kinds, include_net_new: bool, include_ids=None,
                  exclude_ids=None) -> dict[str, Any]:
    """Changes nothing. Works without a standard copy (the 422 for a missing standard applies to a real run)."""
    pop = await load_agreement_population(session, viewer)
    return plan(pop, kinds=chosen_kinds(kinds), include_net_new=include_net_new, include_ids=include_ids,
                exclude_ids=exclude_ids).preview(pop)


# --- start ------------------------------------------------------------------------------------


async def _lock_settings(session: AsyncSession) -> AgreementsSettings:
    stmt = (select(AgreementsSettings).where(AgreementsSettings.id == 1).with_for_update()
            .execution_options(populate_existing=True))
    row = await session.scalar(stmt)
    if row is None:  # migration 0072 inserts it; a create_all test database does not
        session.add(AgreementsSettings(id=1))
        await session.flush()
        row = await session.scalar(stmt)
    return row


async def _by_key(session: AsyncSession, key: str) -> AgreementBatch | None:
    return await session.scalar(select(AgreementBatch).where(AgreementBatch.idempotency_key == key)
                                .execution_options(populate_existing=True))


async def _running(session: AsyncSession) -> AgreementBatch | None:
    return await session.scalar(select(AgreementBatch).where(
        or_(AgreementBatch.running_guard.is_(True), AgreementBatch.status.in_(("running", "undoing"))))
        .order_by(AgreementBatch.created_at.desc()).limit(1).execution_options(populate_existing=True))


async def _stamp_relationships(session: AsyncSession, actor: User, cutover: date,
                               stamp_at: datetime) -> tuple[list[tuple[Client, str, str]], dict[str, int]]:
    """Stamp every client whose relationship is still empty with the live rule as of the cutover.

    Judged over ALL non-archived clients (test fixtures included), not only what the admin can see. A stored
    value (a writer's manual change made before the cutover) is never overwritten."""
    from app.services.hubspot_pipeline import PipelineFilters

    every = await load_agreement_population(
        session, actor, scope=PipelineFilters(include_closed=True, open_closed="any"))
    pending = [f for f in every.clients.values() if f.input.stored_relationship is None]
    if not pending:
        return [], {"existing": 0, "net_new": 0}
    locked = {c.id: c for c in (await session.scalars(
        select(Client).where(Client.id.in_([f.input.id for f in pending]), Client.relationship.is_(None))
        .order_by(Client.id).with_for_update().execution_options(populate_existing=True))).all()}
    stamped: list[tuple[Client, str, str]] = []
    counts = {"existing": 0, "net_new": 0}
    for facts in pending:
        client = locked.get(facts.input.id)
        if client is None or client.relationship is not None:
            continue
        relationship, basis = live_relationship(facts.input, cutover)
        client.relationship, client.relationship_basis = relationship, basis
        client.relationship_set_by, client.relationship_set_at = actor.id, stamp_at
        stamped.append((client, relationship, basis))
        counts[relationship] += 1
    await session.flush()
    return stamped, counts


async def start(session: AsyncSession, *, actor: User, kinds, include_net_new: bool, include_ids=None,
                exclude_ids=None, idempotency_key: str | None, confirm: str | None,
                now: datetime | None = None) -> tuple[uuid.UUID, bool]:
    """Start a real run. Returns (batch id, created); a repeated idempotency key returns the original batch."""
    if test_identity_blocked(actor):
        raise HTTPException(403, "A test identity cannot run a real batch outside local and test.")
    key = (idempotency_key or "").strip()
    if not key or len(key) > 80:
        raise HTTPException(422, "A real run needs an idempotency_key (1 to 80 characters).")
    if confirm is None:
        raise HTTPException(422, "A real run needs the confirm phrase.")
    chosen = chosen_kinds(kinds)
    # Settings first (lock order: settings, batch, clients, agreement rows; audit last). It also serialises
    # two starts, so the running check and the label below cannot race.
    settings = await _lock_settings(session)
    original = await _by_key(session, key)
    if original is not None:
        original_id = original.id
        await session.rollback()
        return original_id, False
    running = await _running(session)
    if running is not None:
        raise HTTPException(409, f"Batch {running.label} is still running. Wait for it to finish.")
    pop = await load_agreement_population(session, actor, now=now)
    the_plan = plan(pop, kinds=chosen, include_net_new=include_net_new, include_ids=include_ids,
                    exclude_ids=exclude_ids)
    standards: dict[str, Any] = {}
    for kind in chosen:
        info = pop.standard.get(kind)
        if info is None:
            raise HTTPException(422, f"No standard {kind} has been uploaded yet. Upload it before attaching it.")
        standards[kind] = info
    if the_plan.will_receive == 0:
        raise HTTPException(422, "No client is selected to receive a copy.")
    expected = f"ATTACH {the_plan.will_receive}"
    if confirm != expected:
        raise HTTPException(422, f"Type {expected} to confirm.")

    stamp_at = datetime.now(UTC)
    count = int(await session.scalar(select(func.count()).select_from(AgreementBatch)) or 0)
    label = f"AG-{count + 1:04d}"
    stamped: list[tuple[Client, str, str]] = []
    stamp_counts: dict[str, int] = {}
    cutover_set = settings.cutover_date is None
    if cutover_set:
        cutover = business_today(now)
        settings.cutover_date, settings.set_by, settings.set_at = cutover, actor.id, stamp_at
        stamped, stamp_counts = await _stamp_relationships(session, actor, cutover, stamp_at)
    batch = AgreementBatch(
        id=uuid.uuid4(), label=label, status="running", kinds=chosen, include_net_new=bool(include_net_new),
        target_client_ids=[str(f.status.client_id) for f in the_plan.included],
        standard_ids={k: str(info.id) for k, info in standards.items()},
        target_count=the_plan.will_receive, done_count=0, attached_count=0, skipped_count=0, attached_clients=0,
        undone_count=0, idempotency_key=key, running_guard=True, heartbeat_at=stamp_at, created_by=actor.id,
        created_at=stamp_at)
    session.add(batch)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return await _after_conflict(session, key)
    # Audit LAST.
    if cutover_set:
        for client, relationship, basis in stamped:
            await audit.record(
                session, actor_id=actor.id, action=audit.RELATIONSHIP_STAMPED, entity="client", entity_id=client.id,
                before={"relationship": None},
                after={"client_id": str(client.id), "client_name": client.name, "relationship": relationship,
                       "relationship_basis": basis, "cutover_date": settings.cutover_date.isoformat(),
                       "batch": label, "reason": "cutover"})
        await audit.record(
            session, actor_id=actor.id, action=audit.CUTOVER_SET, entity="agreements_settings", entity_id="1",
            before={"cutover_date": None},
            after={"cutover_date": settings.cutover_date.isoformat(), "batch": label,
                   "stamped": len(stamped), **stamp_counts})
    await audit.record(
        session, actor_id=actor.id, action=audit.BATCH_STARTED, entity="agreement_batch", entity_id=batch.id,
        after={"label": label, "kinds": chosen, "target_count": the_plan.will_receive,
               "existing": the_plan.will_receive - the_plan.net_new_included,
               "net_new": the_plan.net_new_included, "include_net_new": bool(include_net_new),
               "standard_versions": {k: info.version for k, info in standards.items()}})
    batch_id = batch.id
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return await _after_conflict(session, key)
    return batch_id, True


async def _after_conflict(session: AsyncSession, key: str) -> tuple[uuid.UUID, bool]:
    """A concurrent start won the race: same key -> that batch; otherwise the one-running-batch guard."""
    original = await _by_key(session, key)
    if original is not None:
        return original.id, False
    running = await _running(session)
    if running is not None:
        raise HTTPException(409, f"Batch {running.label} is still running. Wait for it to finish.")
    raise HTTPException(409, "Another batch started at the same moment. Run the dry run again.")


# --- the job ----------------------------------------------------------------------------------


async def _lock_batch(session: AsyncSession, batch_id: uuid.UUID) -> AgreementBatch | None:
    return await session.scalar(select(AgreementBatch).where(AgreementBatch.id == batch_id).with_for_update()
                                .execution_options(populate_existing=True))


def _error_text(batch: AgreementBatch | None, exc: BaseException, undo: bool) -> str:
    """A sentence for people. The exception class stays in the server log and the audit row, never on screen."""
    if undo:
        return "The undo stopped before it finished. Press Undo again to finish removing the standard copies."
    done = f" after {batch.done_count} of {batch.target_count} clients" if batch is not None else ""
    return (f"The batch stopped{done}. Run it again to finish; clients that already hold a copy are "
            "skipped.")[:1024]


async def _fail(factory, batch_id: uuid.UUID, exc: BaseException, *, undo: bool) -> None:
    try:
        async with factory() as session:
            batch = await _lock_batch(session, batch_id)
            if batch is None or batch.status not in ("running", "undoing"):
                return
            stamp = datetime.now(UTC)
            batch.status, batch.running_guard = "failed", None
            batch.error = _error_text(batch, exc, undo)
            batch.finished_at = batch.heartbeat_at = stamp
            await session.flush()
            await audit.record(
                session, actor_id=(batch.undone_by if undo and batch.undone_by else batch.created_by),
                action=audit.BATCH_FAILED, entity="agreement_batch", entity_id=batch.id,
                after={"label": batch.label, "phase": "undo" if undo else "run", "error": batch.error,
                       "exception": type(exc).__name__, "kinds": list(batch.kinds or []),
                       "done_count": batch.done_count, "attached_count": batch.attached_count,
                       "attached_clients": batch.attached_clients, "undone_count": batch.undone_count})
            await session.commit()
    except Exception:  # noqa: BLE001
        log.exception("agreement batch: could not record the failure")


async def _run_chunk(session: AsyncSession, batch: AgreementBatch, chunk_size: int) -> None:
    start_at = batch.done_count
    chunk = [uuid.UUID(str(v)) for v in batch.target_client_ids[start_at:start_at + chunk_size]]
    kinds = [k for k in KINDS if k in (batch.kinds or [])]
    standard_ids = {k: uuid.UUID(str(v)) for k, v in (batch.standard_ids or {}).items()}
    standards = {s.kind: s for s in (await session.scalars(
        select(StandardAgreement).where(StandardAgreement.id.in_(list(standard_ids.values()))))).all()}
    if any(k not in standards for k in kinds):
        raise RuntimeError("standard copy missing")
    clients = {c.id: c for c in (await session.scalars(
        select(Client).where(Client.id.in_(chunk)).order_by(Client.id).with_for_update()
        .execution_options(populate_existing=True))).all()}
    held = {(r[0], r[1]) for r in (await session.execute(
        select(Agreement.client_id, Agreement.kind).where(Agreement.client_id.in_(chunk)))).all()}
    held |= {(r[0], r[1]) for r in (await session.execute(
        select(AgreementMark.client_id, AgreementMark.kind).where(
            AgreementMark.client_id.in_(chunk), AgreementMark.removed_at.is_(None)))).all()}
    stamp = datetime.now(UTC)
    attached: list[tuple[Client, list[Agreement]]] = []
    skipped = 0
    for cid in chunk:
        client = clients.get(cid)
        if client is None or client.archived_at is not None:
            skipped += len(kinds)
            continue
        rows: list[Agreement] = []
        for kind in kinds:
            if (cid, kind) in held:
                skipped += 1
                continue
            standard = standards[kind]
            rows.append(Agreement(
                id=uuid.uuid4(), client_id=cid, kind=kind, file_key=standard.file_key, filename=standard.filename,
                file_size=standard.file_size, uploaded_by=batch.created_by, uploaded_at=stamp, version_no=1,
                source="standard", standard_agreement_id=standard.id, batch_id=batch.id))
        if rows:
            session.add_all(rows)
            attached.append((client, rows))
    await session.flush()
    for _client, rows in attached:
        session.add_all([snapshot(row, standards[row.kind].sha256) for row in rows])
    await session.flush()
    for client, rows in attached:
        await audit.record(
            session, actor_id=batch.created_by, action=audit.BATCH_ATTACHED, entity="agreement_batch",
            entity_id=batch.id,
            after={"client_id": str(client.id), "client_name": client.name, "kinds": [r.kind for r in rows],
                   "label": batch.label, "source": "standard",
                   "standard_versions": {r.kind: standards[r.kind].version_no for r in rows}})
    batch.done_count = start_at + len(chunk)
    batch.attached_count += sum(len(rows) for _c, rows in attached)
    batch.attached_clients += len(attached)
    batch.skipped_count += skipped
    batch.heartbeat_at = stamp
    await session.commit()


async def _finish_run(session: AsyncSession, batch: AgreementBatch) -> None:
    existing = int(await session.scalar(
        select(func.count(func.distinct(Agreement.client_id))).select_from(AgreementFileVersion)
        .join(Agreement, Agreement.id == AgreementFileVersion.agreement_id)
        .join(Client, Client.id == Agreement.client_id)
        .where(AgreementFileVersion.batch_id == batch.id, Client.relationship == "existing")) or 0)
    existing = min(existing, batch.attached_clients)
    stamp = datetime.now(UTC)
    batch.status, batch.running_guard = "done", None
    batch.finished_at = batch.heartbeat_at = stamp
    await session.flush()
    await audit.record(
        session, actor_id=batch.created_by, action=audit.BATCH_RUN, entity="agreement_batch", entity_id=batch.id,
        after={"label": batch.label, "kinds": list(batch.kinds or []), "attached_clients": batch.attached_clients,
               "attached_count": batch.attached_count, "skipped_count": batch.skipped_count,
               "target_count": batch.target_count, "existing": existing,
               "net_new": batch.attached_clients - existing})
    await session.commit()


Hook = Callable[[uuid.UUID], Awaitable[None]]


async def run_batch(factory, batch_id: uuid.UUID, *, chunk_size: int = CHUNK, on_chunk: Hook | None = None) -> str:
    """Run (or resume) a batch to the end, one committed chunk at a time. Returns the final status.

    ``on_chunk`` runs after every committed chunk (tests use it to kill the job: a BaseException leaves the
    batch running, exactly as a dead process would, and the resume continues from ``done_count``)."""
    try:
        while True:
            async with factory() as session:
                batch = await _lock_batch(session, batch_id)
                if batch is None:
                    return "missing"
                if batch.status != "running":
                    return batch.status
                if batch.done_count >= len(batch.target_client_ids or []):
                    await _finish_run(session, batch)
                    return "done"
                await _run_chunk(session, batch, chunk_size)
            if on_chunk is not None:
                await on_chunk(batch_id)
    except Exception as exc:  # noqa: BLE001 — recorded on the batch; a BaseException (kill) leaves it running
        log.exception("agreement batch failed")
        await _fail(factory, batch_id, exc, undo=False)
        return "failed"


# --- undo -------------------------------------------------------------------------------------


async def start_undo(session: AsyncSession, *, actor: User, label: str) -> tuple[uuid.UUID, bool]:
    """Mark the batch undoing (one job at a time). Returns (batch id, started)."""
    if test_identity_blocked(actor):
        raise HTTPException(403, "A test identity cannot undo a real batch outside local and test.")
    batch = await session.scalar(select(AgreementBatch).where(AgreementBatch.label == label).with_for_update()
                                 .execution_options(populate_existing=True))
    if batch is None:
        raise HTTPException(404, "Unknown batch")
    if batch.status == "undone":
        raise HTTPException(409, f"Batch {batch.label} is already undone.")
    if batch.status == "undoing":
        return batch.id, False
    if batch.status == "running":
        raise HTTPException(409, f"Batch {batch.label} is still running. Undo it when it has finished.")
    other = await _running(session)
    if other is not None and other.id != batch.id:
        raise HTTPException(409, f"Batch {other.label} is running. Try again when it has finished.")
    batch.status, batch.running_guard, batch.error = "undoing", True, None
    batch.undone_by, batch.heartbeat_at = actor.id, datetime.now(UTC)
    batch_id = batch.id
    try:
        await session.flush()
        # Every write is an audit row in the same transaction (rule 5); the feed shows BATCH_UNDONE when it ends.
        await audit.record(session, actor_id=actor.id, action=audit.BATCH_UNDO_STARTED, entity="agreement_batch",
                           entity_id=batch_id, after={"label": batch.label, "kinds": list(batch.kinds or [])})
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Another batch is running. Try again when it has finished.") from exc
    return batch_id, True


async def _undo_chunk(session: AsyncSession, batch: AgreementBatch, candidates: list[uuid.UUID]) -> None:
    from app.services.deletion_storage import agreement_bucket, key_is_referenced
    from app.services.parent_deletion import queue_storage_cleanup

    clients = {c.id: c for c in (await session.scalars(
        select(Client).where(Client.id.in_(candidates)).order_by(Client.id).with_for_update()
        .execution_options(populate_existing=True))).all()}
    rows = (await session.scalars(
        select(Agreement).where(Agreement.batch_id == batch.id, Agreement.source == "standard",
                                Agreement.client_id.in_(candidates))
        .order_by(Agreement.client_id, Agreement.kind).with_for_update()
        .execution_options(populate_existing=True))).all()
    ids = [r.id for r in rows]
    keys = {r.file_key for r in rows}
    if ids:
        keys |= set((await session.scalars(
            select(AgreementFileVersion.file_key).where(AgreementFileVersion.agreement_id.in_(ids)))).all())
    removed: dict[uuid.UUID, list[str]] = {}
    for row in rows:
        removed.setdefault(row.client_id, []).append(row.kind)
    if ids:
        await session.execute(delete(AgreementFileVersion).where(AgreementFileVersion.agreement_id.in_(ids)))
        await session.execute(delete(Agreement).where(Agreement.id.in_(ids)))
        await session.flush()
    # The shared standard objects stay; only a key nothing else references would be queued (never expected).
    loose = [k for k in sorted(keys) if not await key_is_referenced(session, agreement_bucket(), k)]
    if loose:
        await queue_storage_cleanup(session, actor_id=batch.undone_by or batch.created_by, account_id=None,
                                    keys=loose, title=f"Batch {batch.label}", subject_type="agreement_undo")
    for client_id, kinds in removed.items():
        client = clients.get(client_id)
        await audit.record(
            session, actor_id=batch.undone_by or batch.created_by, action=audit.BATCH_DETACHED,
            entity="agreement_batch", entity_id=batch.id,
            after={"client_id": str(client_id), "client_name": client.name if client else None,
                   "kinds": kinds, "label": batch.label, "source": "standard"})
    batch.undone_count += len(ids)
    batch.heartbeat_at = datetime.now(UTC)
    await session.commit()


async def _finish_undo(session: AsyncSession, batch: AgreementBatch) -> None:
    stamp = datetime.now(UTC)
    batch.status, batch.running_guard = "undone", None
    batch.undone_at = batch.heartbeat_at = stamp
    await session.flush()
    await audit.record(
        session, actor_id=batch.undone_by or batch.created_by, action=audit.BATCH_UNDONE,
        entity="agreement_batch", entity_id=batch.id,
        after={"label": batch.label, "kinds": list(batch.kinds or []), "removed": batch.undone_count})
    await session.commit()


async def run_undo(factory, batch_id: uuid.UUID, *, chunk_size: int = CHUNK, on_chunk: Hook | None = None) -> str:
    """Remove this batch's rows that are still standard copies, 25 clients per committed chunk."""
    try:
        while True:
            async with factory() as session:
                batch = await _lock_batch(session, batch_id)
                if batch is None:
                    return "missing"
                if batch.status != "undoing":
                    return batch.status
                candidates = list((await session.scalars(
                    select(Agreement.client_id).where(Agreement.batch_id == batch.id, Agreement.source == "standard")
                    .distinct().order_by(Agreement.client_id).limit(chunk_size))).all())
                if not candidates:
                    await _finish_undo(session, batch)
                    return "undone"
                await _undo_chunk(session, batch, candidates)
            if on_chunk is not None:
                await on_chunk(batch_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("agreement batch undo failed")
        await _fail(factory, batch_id, exc, undo=True)
        return "failed"


# --- launching and resuming -------------------------------------------------------------------

_JOBS: set[asyncio.Task] = set()  # strong references: a bare create_task may be garbage-collected mid-run


async def launch_in_background(batch_id: uuid.UUID, phase: str) -> None:
    """The API's launcher: run the job as an asyncio task on the app's own session factory."""
    from app.db import session_factory

    runner = run_batch if phase == "run" else run_undo
    task = asyncio.get_running_loop().create_task(runner(session_factory, batch_id))
    _JOBS.add(task)
    task.add_done_callback(_JOBS.discard)


async def resume_stale(factory, *, stale_after: timedelta = STALE_AFTER, now: datetime | None = None,
                       label: str | None = None) -> list[dict[str, Any]]:
    """Continue every running or undoing batch whose heartbeat is older than ``stale_after`` (its process died).

    With ``label`` the named batch is continued whatever its heartbeat (the CLI). Two runners never duplicate
    work: each chunk locks the batch row and re-reads the cursor."""
    cutoff = (now or datetime.now(UTC)) - stale_after
    async with factory() as session:
        stmt = select(AgreementBatch.id, AgreementBatch.label, AgreementBatch.status).where(
            AgreementBatch.status.in_(("running", "undoing")))
        if label is not None:
            stmt = stmt.where(AgreementBatch.label == label)
        else:
            stmt = stmt.where(or_(AgreementBatch.heartbeat_at.is_(None), AgreementBatch.heartbeat_at < cutoff))
        rows = (await session.execute(stmt.order_by(AgreementBatch.created_at))).all()
    results: list[dict[str, Any]] = []
    for batch_id, batch_label, status in rows:
        final = await (run_batch if status == "running" else run_undo)(factory, batch_id)
        results.append({"batch": batch_label, "was": status, "now": final})
    return results


# --- payloads ---------------------------------------------------------------------------------


async def batch_payloads(session: AsyncSession, *, label: str | None = None) -> list[dict[str, Any]]:
    """Batches newest first (one, with ``label``), with display names and the count an undo would remove."""
    creator = aliased(User, name="batch_creator")
    undoer = aliased(User, name="batch_undoer")
    stmt = (select(AgreementBatch, creator.name, creator.email, undoer.name, undoer.email)
            .outerjoin(creator, creator.id == AgreementBatch.created_by)
            .outerjoin(undoer, undoer.id == AgreementBatch.undone_by)
            .order_by(AgreementBatch.created_at.desc(), AgreementBatch.id.desc())
            .execution_options(populate_existing=True))
    if label is not None:
        stmt = stmt.where(AgreementBatch.label == label)
    rows = (await session.execute(stmt)).all()
    if not rows:
        return []
    would = {r[0]: int(r[1]) for r in (await session.execute(
        select(Agreement.batch_id, func.count()).where(
            Agreement.batch_id.in_([b.id for b, *_ in rows]), Agreement.source == "standard")
        .group_by(Agreement.batch_id))).all()}
    out: list[dict[str, Any]] = []
    for batch, c_name, c_email, u_name, u_email in rows:
        info = BatchInfo(
            id=batch.id, label=batch.label, status=batch.status, kinds=list(batch.kinds or []),
            created_by=person(c_name, c_email), created_at=batch.created_at, target_count=batch.target_count,
            done_count=batch.done_count, attached_count=batch.attached_count,
            attached_clients=batch.attached_clients, skipped_count=batch.skipped_count,
            undone_count=batch.undone_count, error=batch.error, undone_at=batch.undone_at,
            undone_by=person(u_name, u_email) if batch.undone_by is not None else None,
            undo_would_remove=would.get(batch.id, 0), undo_started=batch.undone_by is not None)
        payload = batch_payload(info) or {}
        payload.update({"include_net_new": batch.include_net_new, "finished_at": iso_z(batch.finished_at)})
        out.append(payload)
    return out


async def batch_payload_by_id(session: AsyncSession, batch_id: uuid.UUID) -> dict[str, Any]:
    found = await session.scalar(select(AgreementBatch.label).where(AgreementBatch.id == batch_id))
    items = await batch_payloads(session, label=found) if found else []
    if not items:
        raise HTTPException(404, "Unknown batch")
    return items[0]


__all__ = [
    "CHUNK", "Plan", "REASONS", "STALE_AFTER", "batch_payload_by_id", "batch_payloads", "chosen_kinds", "dry_run",
    "holds", "launch_in_background", "plan", "resume_stale", "run_batch", "run_undo", "stage_1_only", "start",
    "start_undo",
]
