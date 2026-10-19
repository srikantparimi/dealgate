"""S24-AG1 B11/B15 — the agreement audit vocabulary and the Activity feed.

Every agreement write, every download and every export writes one audit row
through :func:`record` (in the caller's transaction, so the change and its
audit row land together). The Activity tab reads those rows back
(:func:`activity`); there is no second event store.

``after`` always carries the client's name at the time (``client_name``) so a
row still reads correctly after a rename or a deletion.

Who sees which event (:func:`visible_events`, used by the Activity list and by
the workspace's Activity tab count, so the two always agree):

* an event about a client follows the Pipeline's fixture visibility: a real
  user never sees an event on a server-issued test fixture, a test identity
  sees only events on its own fixtures;
* a real user never sees an event a test identity caused (an e2e run's
  download or export is not the business's activity);
* an event about no client (a standard upload, a batch, an export) is visible
  to every role, as the prototype shows it;
* the deletion job's own ``agreement.deleted`` row is folded into the
  ``agreement.detached`` row written for the same agreement, so one detach is
  one line.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.models.audit import AuditEvent
from app.models.user import User

# Audit action names. Activity-facing ones map to the contract's ActivityRow.action.
STANDARD_UPLOADED = "agreement.standard_uploaded"
CLIENT_UPLOADED = "agreement.uploaded"  # existing S17 name for a first client copy
CLIENT_REPLACED = "agreement.replaced"  # existing S21 name for a new version
STANDARD_ATTACHED = "agreement.standard_attached"
DETACHED = "agreement.detached"
DELETED = "agreement.deleted"  # existing deletion-job name; shown as "detached"
MARKED = "agreement.marked"
MARK_REMOVED = "agreement.mark_removed"
RELATIONSHIP_CHANGED = "client.relationship_changed"
BATCH_STARTED = "agreement.batch_started"  # the job began (not in the feed; BATCH_RUN is written when it ends)
BATCH_RUN = "agreement.batch_run"
BATCH_FAILED = "agreement.batch_failed"
BATCH_ATTACHED = "agreement.batch_attached"  # one per client a batch attaches to; summarised by BATCH_RUN
BATCH_UNDO_STARTED = "agreement.batch_undo_started"  # undo began (not in the feed; BATCH_UNDONE ends it)
BATCH_UNDONE = "agreement.batch_undone"
BATCH_DETACHED = "agreement.batch_detached"  # one per row an undo removes; summarised by BATCH_UNDONE
HUBSPOT_APPLIED = "agreement.hubspot_applied"
HUBSPOT_MARKED = "agreement.hubspot_marked"  # one per client a mapping apply marks; summarised by HUBSPOT_APPLIED
HUBSPOT_MAPPING_SAVED = "agreement.hubspot_mapping_saved"
DOWNLOADED = "agreement.downloaded"
EXPORTED = "agreement.exported"
CUTOVER_SET = "agreement.cutover_set"
RELATIONSHIP_STAMPED = "client.relationship_stamped"  # the rule's stamp at the cutover or at creation

ACTIVITY_ACTIONS: dict[str, str] = {
    STANDARD_UPLOADED: "standard_uploaded",
    CLIENT_UPLOADED: "client_uploaded",
    CLIENT_REPLACED: "client_replaced",
    STANDARD_ATTACHED: "standard_attached",
    DETACHED: "detached",
    DELETED: "detached",
    MARKED: "marked",
    MARK_REMOVED: "mark_removed",
    RELATIONSHIP_CHANGED: "relationship_changed",
    BATCH_RUN: "batch_run",
    BATCH_UNDONE: "batch_undone",
    # A batch or undo that stopped part-way still shows what it changed; see activity_action for the undo phase.
    BATCH_FAILED: "batch_run",
    HUBSPOT_APPLIED: "hubspot_applied",
    DOWNLOADED: "downloaded",
    EXPORTED: "exported",
}
# The entity of the export's audit row (an export changes no record; entity_id is a fresh id per export).
EXPORT_ENTITY = "agreements_export"
# Every entity an Activity event is recorded on. The feed filters on ``entity`` (indexed) AND ``action``;
# an event recorded on an entity outside this list never reaches the feed.
AGREEMENT_ENTITIES: tuple[str, ...] = (
    "agreement", "agreement_batch", "standard_agreement", "agreement_mark", "agreements_settings",
    "agreement_hubspot_map", EXPORT_ENTITY,
)

REASON_LABELS: dict[str, str] = {
    "signed_outside_dealgate": "Signed outside DealGate",
    "covered_by_earlier_work": "Covered by earlier work",
    "confirmed_with_client": "Confirmed with the client",
    "per_hubspot": "Per HubSpot",
    "other": "Other",
}


async def record(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: str | uuid.UUID,
    after: dict[str, Any] | None = None,
    before: dict[str, Any] | None = None,
) -> AuditEvent:
    """One audit row in the caller's transaction (never commits)."""
    return await append_audit(
        session, actor_id=actor_id, action=action, entity=entity, entity_id=str(entity_id),
        before=before, after=after,
    )


def _iso_z(value) -> str | None:
    from app.services.agreement_status import iso_z

    return iso_z(value)


def _kinds_text(kinds: list[str] | None) -> str:
    kinds = [k for k in (kinds or []) if k in ("NDA", "MSA")]
    return " and ".join(kinds) if kinds else "documents"


def _first_count(payload: dict[str, Any], *keys: str) -> int | None:
    """The first of ``keys`` that holds a whole number (a count the writer recorded), else None."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None


def _clients(n: int) -> str:
    return f"{n} client" if n == 1 else f"{n} clients"


def activity_action(action: str, after: dict[str, Any] | None) -> str:
    """The contract's Activity action for an audit action (a failed undo reads as ``batch_undone``)."""
    if action == BATCH_FAILED and isinstance(after, dict) and after.get("phase") == "undo":
        return "batch_undone"
    return ACTIVITY_ACTIONS[action]


def activity_text(action: str, after: dict[str, Any] | None, before: dict[str, Any] | None = None) -> str:
    """One readable sentence per event, worded as the prototype's ``log()`` lines. Never shows an id.

    A count the event did not record is left out of the sentence rather than shown as a zero.
    """
    a = after if isinstance(after, dict) else {}
    b = before if isinstance(before, dict) else {}
    client = a.get("client_name") or b.get("client_name") or "a client"
    kind = a.get("kind") or b.get("kind") or ""
    file_name = a.get("file_name") or a.get("filename")
    with_file = f" ({file_name})" if file_name else ""
    if action == STANDARD_UPLOADED:
        version = _first_count(a, "version_no", "standard_version")
        return f"Uploaded standard {kind or 'document'}{f' version {version}' if version else ''}{with_file}"
    if action == CLIENT_UPLOADED:
        return f"Uploaded client {kind or 'document'} for {client}{with_file}"
    if action == CLIENT_REPLACED:
        return f"Replaced client {kind or 'document'} for {client}{with_file}"
    if action == STANDARD_ATTACHED:
        return f"Attached standard {kind or 'document'} to {client}"
    if action in (DETACHED, DELETED):
        what = f"{kind} file" if kind else "file"
        if a.get("client_name") or b.get("client_name"):
            return f"Removed {what} from {client}"
        # The deletion job's own row carries only the file name (``before.name``).
        name = file_name or b.get("file_name") or b.get("filename") or b.get("name")
        return f"Removed {what}{f' ({name})' if name else ''} from a client"
    if action == MARKED:
        reason = REASON_LABELS.get(a.get("reason") or "", a.get("reason") or "")
        return f"Marked {kind or 'document'} covered for {client}{f' ({reason})' if reason else ''}"
    if action == MARK_REMOVED:
        return f"Removed {kind or 'document'} mark from {client}"
    if action == RELATIONSHIP_CHANGED:
        target = "existing" if a.get("relationship") == "existing" else "net new"
        return f"Changed {client} to {target}"
    if action == BATCH_RUN:
        label = a.get("label") or "the batch"
        n = _first_count(a, "attached_clients", "target_count")
        text = f"Attached standard {_kinds_text(a.get('kinds'))}"
        text += f" to {_clients(n)} (batch {label})" if n is not None else f" (batch {label})"
        net_new = _first_count(a, "net_new")
        existing = _first_count(a, "existing")
        if net_new:
            text += (f": {existing} existing and {net_new} net new in the pipeline" if existing is not None
                     else f", {net_new} of them net new in the pipeline")
        return text
    if action == BATCH_UNDONE:
        label = a.get("label") or "the batch"
        n = _first_count(a, "removed", "undone_count", "count")
        if n is None:
            return f"Undid batch {label}"
        return f"Undid batch {label}: removed {n} standard attachment{'' if n == 1 else 's'}"
    if action == BATCH_FAILED:
        label = a.get("label") or "the batch"
        if a.get("phase") == "undo":
            n = _first_count(a, "undone_count")
            if not n:
                return f"Undo of batch {label} stopped before it finished"
            return (f"Undo of batch {label} stopped after removing {n} standard "
                    f"attachment{'' if n == 1 else 's'}")
        n = _first_count(a, "attached_clients")
        if n is None:
            return f"Batch {label} stopped before it finished"
        if n == 0:
            return f"Batch {label} stopped before attaching anything"
        return f"Batch {label} stopped after attaching standard {_kinds_text(a.get('kinds'))} to {_clients(n)}"
    if action == HUBSPOT_APPLIED:
        n = _first_count(a, "marked", "count")
        if a.get("stopped"):
            return ("HubSpot msa_type mapping stopped before marking anything" if not n else
                    f"HubSpot msa_type mapping stopped after marking MSA covered for {_clients(n)}")
        if n is None:
            return "Applied HubSpot msa_type mapping"
        return f"Applied HubSpot msa_type mapping: marked MSA covered for {_clients(n)}"
    if action == DOWNLOADED:
        if a.get("standard"):
            return f"Downloaded the standard {kind or 'document'}"
        return f"Downloaded {kind or 'a document'} for {client}"
    if action == EXPORTED:
        n = _first_count(a, "rows")
        return f"Exported {_clients(n)} to CSV" if n is not None else "Exported the client view to CSV"
    return action


def activity_predicate():
    """The audit rows the Activity tab shows (uses the (entity, entity_id) index through ``entity``)."""
    return and_(
        or_(AuditEvent.entity.in_(AGREEMENT_ENTITIES),
            and_(AuditEvent.entity == "client", AuditEvent.action == RELATIONSHIP_CHANGED)),
        AuditEvent.action.in_(list(ACTIVITY_ACTIONS)),
    )


def client_of(after: Any, before: Any = None) -> uuid.UUID | None:
    """The client an event is about (``client_id`` in ``after``, else in ``before``), or None."""
    for payload in (after, before):
        if not isinstance(payload, dict):
            continue
        raw = payload.get("client_id")
        if raw:
            try:
                return uuid.UUID(str(raw))
            except ValueError:
                return None
    return None


def is_test_actor(groups: Any) -> bool:
    from app.services.test_fixtures import E2E_USER_GROUP

    return isinstance(groups, (list, tuple)) and E2E_USER_GROUP in groups


GLOBAL_ENTITIES: frozenset[str] = frozenset(
    {"standard_agreement", "agreement_batch", "agreements_settings", "agreement_hubspot_map", "agreements_export"})


class _Viewer:
    """The visibility sets of one caller, computed once per feed."""

    def __init__(self, scope: Any = None, client_ids: set[uuid.UUID] | None = None) -> None:
        self.scoped = scope is not None
        authorized = getattr(scope, "authorized_client_ids", None) if scope is not None else None
        self.authorized = set(authorized) if authorized is not None else None
        self.hidden = set(getattr(scope, "hidden_client_ids", ()) or ()) if scope is not None else set()
        self.client_ids = client_ids

    def sees(self, client_id: uuid.UUID | None, actor_groups: Any, entity: str | None = None) -> bool:
        if self.scoped:
            if self.authorized is not None:
                # A test identity sees its own fixtures and events about no client at all (standard copies,
                # batches, settings, the HubSpot map, exports). An event on a client-level entity whose client
                # cannot be resolved (older rows written before AG1 carried no client id) may name a real
                # client's document, so it stays hidden.
                if client_id is None:
                    return entity in GLOBAL_ENTITIES
                return client_id in self.authorized
            if client_id is not None and client_id in self.hidden:
                return False
            return not is_test_actor(actor_groups)
        return self.client_ids is None or client_id is None or client_id in self.client_ids


def event_visible(
    client_id: uuid.UUID | None, actor_groups: Any, *, scope: Any = None, client_ids: set[uuid.UUID] | None = None,
) -> bool:
    """Whether the caller sees one event. ``scope`` is the caller's Pipeline fixture scope
    (agreement_status.visibility_scope); without it, ``client_ids`` limits client events (the S24 foundation
    behaviour)."""
    return _Viewer(scope, client_ids).sees(client_id, actor_groups)


def visible_events(
    items: Iterable[Sequence[Any]], *, scope: Any = None, client_ids: set[uuid.UUID] | None = None,
) -> list[tuple[uuid.UUID | None, Any]]:
    """Filter candidate events, newest first. Each item is ``(action, entity_id, after, before, actor_groups,
    payload[, entity])``; returns ``(client_id, payload)`` for every event the caller sees, in the same order."""
    rows = list(items)
    viewer = _Viewer(scope, client_ids)
    detached = {str(row[1]) for row in rows if row[0] == DETACHED}
    out: list[tuple[uuid.UUID | None, Any]] = []
    for row in rows:
        action, entity_id, after, before, groups, payload = row[:6]
        entity = row[6] if len(row) > 6 else None
        if action == DELETED and str(entity_id) in detached:
            continue  # the deletion job's row for a detach already written as agreement.detached
        client_id = client_of(after, before)
        if viewer.sees(client_id, groups, entity):
            out.append((client_id, payload))
    return out


def feed_count_statement():
    """The light read the workspace uses for the Activity tab count (same rows as :func:`activity`)."""
    return (
        select(AuditEvent.action, AuditEvent.entity_id, AuditEvent.after, AuditEvent.before, User.groups,
               AuditEvent.entity)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(activity_predicate())
    )


def count_visible(rows: Iterable[Sequence[Any]], *, scope: Any = None) -> int:
    """Rows of :func:`feed_count_statement` the caller sees (equals ``activity(...)[0]`` with no search)."""
    return len(visible_events(((r[0], r[1], r[2], r[3], r[4], None, r[5] if len(r) > 5 else None)
                               for r in rows), scope=scope))


def _person(name: str | None, email: str | None, actor_id: uuid.UUID | None) -> str:
    from app.services.agreement_status import person

    if actor_id is None:
        return "DealGate"
    return person(name, email)


async def activity(
    session: AsyncSession, *, q: str | None, page: int, page_size: int, client_ids: set[uuid.UUID] | None = None,
    scope: Any = None, linkable_client_ids: set[uuid.UUID] | None = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Agreement events, newest first, with a total.

    ``scope`` (preferred) applies the visibility rules in the module docstring; ``client_ids`` alone limits
    client events to those clients. ``linkable_client_ids`` keeps ``client_id`` on a row only for a client the
    page can open (a deleted or archived client's event still reads by name, with no link).
    Search (``q``) matches the sentence and the person, as the prototype does.
    """
    stmt = (
        select(AuditEvent, User.name, User.email, User.groups)
        .outerjoin(User, User.id == AuditEvent.actor_id)
        .where(activity_predicate())
        .order_by(AuditEvent.ts.desc(), AuditEvent.id.desc())
    )
    rows = (await session.execute(stmt)).all()
    candidates = [
        (event.action, event.entity_id, event.after, event.before, groups, (event, name, email), event.entity)
        for event, name, email, groups in rows
    ]
    items: list[dict[str, Any]] = []
    needle = (q or "").strip().casefold()
    for client_id, (event, name, email) in visible_events(candidates, scope=scope, client_ids=client_ids):
        after = event.after if isinstance(event.after, dict) else {}
        before = event.before if isinstance(event.before, dict) else {}
        by = _person(name, email, event.actor_id)
        text = activity_text(event.action, after, before)
        if needle and needle not in f"{text} {by}".casefold():
            continue
        link = client_id if client_id is not None and (
            linkable_client_ids is None or client_id in linkable_client_ids) else None
        items.append({
            "at": _iso_z(event.ts), "by": by,
            "action": activity_action(event.action, after), "text": text,
            "client_id": str(link) if link else None,
        })
    total = len(items)
    start = (page - 1) * page_size
    return total, items[start:start + page_size]


async def activity_count(session: AsyncSession) -> int:
    """Every agreement event in the audit log, unfiltered (the Activity tab count uses :func:`count_visible`)."""
    stmt = select(func.count()).select_from(AuditEvent).where(activity_predicate())
    return int((await session.execute(stmt)).scalar_one())


__all__ = [name for name in dir() if name.isupper()] + [
    "activity", "activity_count", "activity_predicate", "activity_text", "client_of", "count_visible",
    "event_visible", "feed_count_statement", "GLOBAL_ENTITIES", "is_test_actor", "record", "visible_events"]
