"""S24-AG1 B9 — HubSpot ``msa_type`` as a hint an admin may map to "MSA covered".

DealGate is the source of truth and HubSpot only hints:

* The deal sync stores each deal's raw ``msa_type`` on the opportunity
  (``hubspot_intake``). A client's hint is the value on its most recently
  modified live HubSpot deal that has one — the ONE definition is
  :func:`app.services.agreement_status.hint_subquery`. A hint is never a state.
* A SystemAdmin saves which values mean the MSA is covered (replace-all; every
  saved row records who saved it). Values not mapped are ignored.
* Applying the mapping marks the MSA covered only for a client that holds
  nothing for the MSA: no agreement row of that kind and no mark of that kind,
  active or removed. A mark a person removed is a DealGate record, so the
  nightly apply never puts it back; DealGate's own record always wins.
* Each mark has reason ``per_hubspot``, source ``hubspot``, the value found, and
  credits the admin who last saved the mapping (no system user is invented).
  Marks are DealGate rows: they stay if HubSpot is switched off.
* The same apply runs after every successful sync
  (:mod:`app.services.hubspot_sync_runs`), only for mapped values.

The apply commits every :data:`APPLY_CHUNK` clients. Each chunk locks its client
rows first, re-checks that each client still holds nothing, inserts the marks
and writes their audit rows last (the audit log serialises writers on one lock).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable, Literal

import structlog
from sqlalchemy import and_, case, delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agreements import AgreementHubspotMap, AgreementMark, AgreementsSettings
from app.models.client import Agreement, Client
from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus
from app.models.user import User
from app.services import agreement_audit
from app.services.agreement_status import hint_subquery, iso_z, person
from app.services.business_time import business_today

log = structlog.get_logger("agreement_hubspot")

KIND = "MSA"
PROPERTY = "msa_type"
ACTIONS: tuple[str, ...] = ("covered", "ignore")
APPLY_CHUNK = 25
MAPPING_ENTITY = "agreement_hubspot_map"
SYNC_SOURCE = "hubspot_backfill"
NOTE_MAX = 200

Trigger = Literal["dialog", "sync"]


@dataclass(frozen=True)
class ApplyResult:
    dry_run: bool
    would_mark: int
    marked: int

    def as_dict(self) -> dict[str, Any]:
        return {"dry_run": self.dry_run, "would_mark": self.would_mark, "marked": self.marked}


@dataclass(frozen=True)
class Mapping:
    """The saved mapping, newest save first, with who saved it last (the person a mark credits)."""

    actions: dict[str, str]
    saved_by_id: uuid.UUID | None
    saved_by: str | None
    saved_at: datetime | None

    @property
    def covered(self) -> list[str]:
        return sorted(v for v, a in self.actions.items() if a == "covered")


# --- predicates --------------------------------------------------------------------------------


def holds_no_msa(client_id_col) -> list[Any]:
    """The client holds nothing for the MSA: no agreement row of that kind (client or standard copy) and no
    mark of that kind, active or removed."""
    return [
        ~select(Agreement.id).where(Agreement.client_id == client_id_col, Agreement.kind == KIND).exists(),
        ~select(AgreementMark.id).where(AgreementMark.client_id == client_id_col, AgreementMark.kind == KIND)
        .exists(),
    ]


def _visible(scope) -> list[Any]:
    """Live clients; with a caller's Pipeline fixture scope, only the clients that caller may see."""
    if scope is None:
        return [Client.archived_at.is_(None)]
    from app.services.hubspot_pipeline import _client_visibility

    return _client_visibility(scope)


# --- reads -------------------------------------------------------------------------------------


async def load_mapping(session: AsyncSession) -> Mapping:
    rows = (await session.execute(
        select(AgreementHubspotMap.value, AgreementHubspotMap.action, AgreementHubspotMap.updated_by,
               AgreementHubspotMap.updated_at, User.name, User.email)
        .outerjoin(User, User.id == AgreementHubspotMap.updated_by)
        .order_by(AgreementHubspotMap.updated_at.desc(), AgreementHubspotMap.value)
    )).all()
    if not rows:
        return Mapping({}, None, None, None)
    latest = rows[0]
    return Mapping(
        actions={value: action for value, action, *_rest in rows},
        saved_by_id=latest[2], saved_by=person(latest[4], latest[5]), saved_at=latest[3],
    )


async def msa_type_stored(session: AsyncSession) -> bool:
    """True once the sync stores ``msa_type``: its deal scan requests the property, or a deal holds a value."""
    context, any_value = (await session.execute(select(
        select(SyncStatus.scan_context).where(SyncStatus.source == SYNC_SOURCE).scalar_subquery(),
        select(Opportunity.id).where(Opportunity.hubspot_msa_type.is_not(None)).exists(),
    ))).one()
    if isinstance(context, str):
        try:
            context = json.loads(context)
        except ValueError:
            context = None
    properties = context.get("properties") if isinstance(context, dict) else None
    return bool(any_value) or (isinstance(properties, list) and PROPERTY in properties)


async def hubspot_values(session: AsyncSession, *, scope=None, can_edit: bool = False) -> dict[str, Any]:
    """``HubspotValues``: every value found as a client's hint (and every saved value), with how many visible
    clients hold it and the saved action. Empty with ``stored`` false until the sync stores the property.

    Additive: per value, ``would_mark`` (clients with that hint holding nothing for the MSA, so the dialog
    can show the count for an unsaved choice); ``saved_by`` / ``saved_at`` (the last save, which marks
    credit); ``can_edit``.
    """
    mapping = await load_mapping(session)
    stored = await msa_type_stored(session)
    items: list[dict[str, Any]] = []
    if stored:
        hint = hint_subquery()
        unheld = case((and_(*holds_no_msa(Client.id)), 1), else_=0)
        counts = {
            value: (int(clients or 0), int(would or 0))
            for value, clients, would in (await session.execute(
                select(hint.c.value, func.count(Client.id), func.sum(unheld))
                .select_from(Client).join(hint, hint.c.client_id == Client.id)
                .where(*_visible(scope)).group_by(hint.c.value)
            )).all()
        }
        for value in set(counts) | set(mapping.actions):
            clients, would = counts.get(value, (0, 0))
            items.append({"value": value, "clients": clients, "action": mapping.actions.get(value, "ignore"),
                          "would_mark": would})
        items.sort(key=lambda item: (-item["clients"], item["value"].casefold(), item["value"]))
    return {
        "stored": stored, "items": items,
        "saved_by": mapping.saved_by, "saved_at": iso_z(mapping.saved_at), "can_edit": can_edit,
    }


# --- writes ------------------------------------------------------------------------------------


async def _lock_settings(session: AsyncSession) -> None:
    """The settings row is the first lock of every agreements write; it serialises mapping saves.
    Migration 0072 inserts it; SQLite ``create_all`` does not, so it is upserted."""
    if session.bind.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    await session.execute(dialect_insert(AgreementsSettings).values(id=1).on_conflict_do_nothing(
        index_elements=["id"]))
    await session.execute(select(AgreementsSettings.id).where(AgreementsSettings.id == 1).with_for_update())


async def save_mapping(session: AsyncSession, *, actor_id: uuid.UUID,
                       items: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Replace the whole mapping with ``items`` ((value, action) pairs, values already trimmed and unique).

    Every row records the saver, so the next apply (and every nightly one) credits this person. Writes one
    ``agreement.hubspot_mapping_saved`` audit row. The caller commits.
    """
    new = {value: action for value, action in items}
    if any(action not in ACTIONS for action in new.values()):
        raise ValueError("action must be covered or ignore")
    await _lock_settings(session)
    before = {value: action for value, action in (await session.execute(
        select(AgreementHubspotMap.value, AgreementHubspotMap.action).order_by(AgreementHubspotMap.value)
    )).all()}
    await session.execute(delete(AgreementHubspotMap))
    now = datetime.now(UTC)
    if new:
        await session.execute(insert(AgreementHubspotMap), [
            {"value": value, "action": action, "updated_by": actor_id, "updated_at": now}
            for value, action in new.items()
        ])
    await agreement_audit.record(
        session, actor_id=actor_id, action=agreement_audit.HUBSPOT_MAPPING_SAVED, entity=MAPPING_ENTITY,
        entity_id=PROPERTY,
        before={"items": [{"value": v, "action": a} for v, a in sorted(before.items())]},
        after={"items": [{"value": v, "action": a} for v, a in sorted(new.items())],
               "covered": sorted(v for v, a in new.items() if a == "covered")},
    )
    return new


def _candidates(covered: list[str], scope, client_ids: list[uuid.UUID] | None = None):
    hint = hint_subquery()
    stmt = (
        select(Client.id, Client.name, hint.c.value)
        .select_from(Client).join(hint, hint.c.client_id == Client.id)
        .where(hint.c.value.in_(covered), *_visible(scope), *holds_no_msa(Client.id))
        .order_by(Client.id)
    )
    if client_ids is not None:
        stmt = stmt.where(Client.id.in_(client_ids))
    return stmt


def _note(value: str) -> str:
    """The mark's note, worded as the approved Agreements design shows it: msa_type “Signed MSA”."""
    room = NOTE_MAX - len("msa_type “”")
    return f"msa_type “{value[:room]}”"


async def apply_mapping(
    session: AsyncSession,
    *,
    dry_run: bool,
    trigger: Trigger,
    actor_id: uuid.UUID | None,
    scope=None,
    now: datetime | None = None,
) -> ApplyResult:
    """Mark the MSA covered for every client whose hint is mapped to covered and that holds nothing for it.

    ``dry_run`` only counts (``would_mark``) and writes nothing. A real run commits every
    :data:`APPLY_CHUNK` clients and then writes one ``agreement.hubspot_applied`` summary (always for a run
    started from the dialog; for a sync-triggered run only when it marked someone, so the Activity feed is
    not filled with nightly zeros). ``actor_id`` is the person who pressed Apply (None after a sync); the
    marks always credit the admin who last saved the mapping. ``scope`` limits the run to the clients a
    caller may see (None = every live client).
    """
    mapping = await load_mapping(session)
    covered = mapping.covered
    if not covered or mapping.saved_by_id is None:
        candidates: list[Any] = []
    else:
        candidates = list((await session.execute(_candidates(covered, scope))).all())
    would_mark = len(candidates)
    if dry_run:
        return ApplyResult(True, would_mark, 0)
    # End the read transaction: every chunk below is its own transaction.
    await session.commit()
    apply_id = uuid.uuid4()
    today = business_today(now)
    marked = 0
    ids = [row[0] for row in candidates]
    stopped: Exception | None = None
    try:
        for start in range(0, len(ids), APPLY_CHUNK):
            chunk = ids[start:start + APPLY_CHUNK]
            # Lock order: client rows first (the per-client agreement writes lock the same rows), then re-check.
            await session.execute(
                select(Client.id).where(Client.id.in_(chunk)).order_by(Client.id).with_for_update())
            rows = (await session.execute(_candidates(covered, scope, chunk))).all()
            marks: list[tuple[AgreementMark, str]] = []
            for client_id, client_name, value in rows:
                mark = AgreementMark(
                    id=uuid.uuid4(), client_id=client_id, kind=KIND, reason="per_hubspot", note=_note(value),
                    marked_on=today, marked_by=mapping.saved_by_id, source="hubspot", hubspot_value=value,
                )
                session.add(mark)
                marks.append((mark, client_name or ""))
            await session.flush()
            for mark, client_name in marks:  # audit last, then commit
                await agreement_audit.record(
                    session, actor_id=actor_id, action=agreement_audit.HUBSPOT_MARKED, entity="agreement_mark",
                    entity_id=mark.id, before=None,
                    after={"client_id": str(mark.client_id), "client_name": client_name, "kind": KIND,
                           "reason": "per_hubspot", "source": "hubspot", "hubspot_value": mark.hubspot_value,
                           "marked_on": today.isoformat(), "marked_by": mapping.saved_by,
                           "trigger": trigger, "apply_id": str(apply_id)},
                )
            await session.commit()
            marked += len(marks)
    except Exception as exc:  # noqa: BLE001 - recorded below, then raised again
        # Earlier chunks are committed and stay; the summary below says how far the run got.
        stopped = exc
        await session.rollback()
    if trigger == "dialog" or marked:
        summary = {"kind": KIND, "trigger": trigger, "would_mark": would_mark, "marked": marked,
                   "values": covered, "credited_to": mapping.saved_by, "apply_id": str(apply_id)}
        if stopped is not None:
            summary |= {"stopped": True, "exception": type(stopped).__name__}
        try:
            await agreement_audit.record(
                session, actor_id=actor_id, action=agreement_audit.HUBSPOT_APPLIED, entity=MAPPING_ENTITY,
                entity_id=PROPERTY, before=None, after=summary,
            )
            await session.commit()
        except Exception:
            if stopped is None:
                raise
            log.exception("agreements_hubspot_apply_summary_failed")
    if stopped is not None:
        log.error("agreements_hubspot_apply_stopped", trigger=trigger, would_mark=would_mark, marked=marked)
        raise stopped
    log.info("agreements_hubspot_applied", trigger=trigger, would_mark=would_mark, marked=marked)
    return ApplyResult(False, would_mark, marked)


__all__ = [
    "ACTIONS", "APPLY_CHUNK", "ApplyResult", "KIND", "Mapping", "PROPERTY", "apply_mapping", "holds_no_msa",
    "hubspot_values", "load_mapping", "msa_type_stored", "save_mapping",
]
