"""Nightly S3 Object-Lock export of ``audit_event`` (S7).

Blueprint §12: the audit chain is append-only in the app; §12 also
requires an off-database WORM copy so a compromise of the RDS instance
cannot silently rewrite history. This worker runs once a day (EventBridge
at 03:00 UTC — see ``infra-tf/modules/schedulers``) and ships the
previous day's rows to
``s3://{AUDIT_EXPORT_BUCKET}/YYYY/MM/DD/audit.jsonl.gz``. The bucket has
Object Lock in COMPLIANCE mode with a 7-year default retention, so once
a PUT lands it cannot be edited or deleted for seven years — not even
by the account root.

One-shot: EventBridge invokes the container, the container runs
``run(session, s3, day)`` and exits. Backfill is the same code path
with an explicit ``day``. The worker is fully idempotent:

- The target key already exists AND the stored ``Content-MD5`` matches
  the fresh body → no-op (``audit_export.skipped``).
- Exists but MD5 mismatches → write a sidecar
  ``…/audit-r{n}.jsonl.gz`` and emit ``audit_export.reprocessed``.
- Missing → PUT and emit ``audit_export.written``.

Row order is deterministic (``ORDER BY ts, id``) so re-runs on the same
day hash to the same bytes; an md5 mismatch really means the source
table changed under our feet (i.e. tamper — which the DB grants
prevent, but this is belt+braces).
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.db import session_factory
from app.integrations.s3_audit import (
    AuditExportS3,
    AuditExportS3Protocol,
    compute_content_md5,
)
from app.models.audit import AuditEvent

log = structlog.get_logger("worker.audit_export")


# The export is one object per day. Sidecars are numbered ``-r1``, ``-r2`` …
# and only appear when a body mismatch is detected.
_KEY_TEMPLATE = "{yyyy}/{mm}/{dd}/audit.jsonl.gz"
_SIDECAR_TEMPLATE = "{yyyy}/{mm}/{dd}/audit-r{n}.jsonl.gz"


@dataclass(frozen=True)
class ExportResult:
    day: date
    row_count: int
    s3_key: str
    sha256: str
    action: str  # "written", "skipped", "reprocessed"


def _yesterday_utc(now: datetime | None = None) -> date:
    ts = (now or datetime.now(UTC)).astimezone(UTC)
    return (ts - timedelta(days=1)).date()


def _key_for(day: date) -> str:
    return _KEY_TEMPLATE.format(
        yyyy=f"{day.year:04d}", mm=f"{day.month:02d}", dd=f"{day.day:02d}"
    )


def _sidecar_key(day: date, n: int) -> str:
    return _SIDECAR_TEMPLATE.format(
        yyyy=f"{day.year:04d}",
        mm=f"{day.month:02d}",
        dd=f"{day.day:02d}",
        n=n,
    )


def _row_to_json(row: AuditEvent) -> dict[str, Any]:
    """One row as canonical JSON. Deterministic key order + string ids."""

    ts = row.ts
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return {
        "id": str(row.id),
        "ts": ts.isoformat() if ts is not None else None,
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "action": row.action,
        "entity": row.entity,
        "entity_id": row.entity_id,
        "before": row.before,
        "after": row.after,
        "correlation_id": row.correlation_id,
        "prev_hash": row.prev_hash,
        "row_hash": row.row_hash,
    }


def _serialize(rows: list[AuditEvent]) -> bytes:
    """Return the gzipped JSONL bytes for ``rows``.

    ``mtime=0`` on the gzip header removes the only source of
    non-determinism in the gzip format, so two runs on the same rows
    produce byte-identical output.
    """

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        for row in rows:
            line = json.dumps(
                _row_to_json(row), sort_keys=True, separators=(",", ":"), default=str
            )
            gz.write(line.encode("utf-8"))
            gz.write(b"\n")
    return buf.getvalue()


async def _rows_for_day(session: AsyncSession, day: date) -> list[AuditEvent]:
    """Load every audit row whose ``ts`` falls inside ``day`` (UTC)."""

    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.ts >= start)
        .where(AuditEvent.ts < end)
        .order_by(AuditEvent.ts, AuditEvent.id)
    )
    return list((await session.execute(stmt)).scalars())


async def run(
    session: AsyncSession,
    s3: AuditExportS3Protocol,
    day: date | None = None,
) -> ExportResult:
    """Export ``day``'s (or yesterday's) audit rows to S3.

    The caller owns the session; ``run`` commits so the ``audit_export.*``
    row + any sidecar accounting is durable before the container exits.
    Safe to call multiple times per day.
    """

    when = day or _yesterday_utc()
    try:
        rows = await _rows_for_day(session, when)
        body = _serialize(rows)
        body_md5 = compute_content_md5(body)
        body_sha256 = hashlib.sha256(body).hexdigest()
        base_key = _key_for(when)

        head = await s3.head(base_key)
        if head.exists and head.content_md5 == body_md5:
            # Perfect no-op. Still emit an audit row so the chain
            # reflects that the tick ran — it makes "did the export run
            # last night?" a one-query question against the chain.
            action = "audit_export.skipped"
            await append_audit(
                session,
                actor_id=None,
                action=action,
                entity="audit_export",
                entity_id=when.isoformat(),
                before=None,
                after={
                    "day": when.isoformat(),
                    "row_count": len(rows),
                    "s3_key": base_key,
                    "sha256": body_sha256,
                },
                correlation_id=f"audit_export:{when.isoformat()}",
            )
            await session.commit()
            return ExportResult(
                day=when,
                row_count=len(rows),
                s3_key=base_key,
                sha256=body_sha256,
                action="skipped",
            )

        if head.exists and head.content_md5 != body_md5:
            # Tamper / drift: the earlier export disagrees with what we
            # would write now. Never overwrite (bucket also refuses under
            # Object Lock); land the new bytes at a sidecar key.
            n = 1
            sidecar = _sidecar_key(when, n)
            # Extremely unlikely, but a previous mismatch could have
            # already created r1; walk forward until we find a free slot.
            while True:
                probe = await s3.head(sidecar)
                if not probe.exists:
                    break
                n += 1
                sidecar = _sidecar_key(when, n)

            await s3.put(
                sidecar,
                body=body,
                content_type="application/gzip",
                content_md5=body_md5,
            )
            await append_audit(
                session,
                actor_id=None,
                action="audit_export.reprocessed",
                entity="audit_export",
                entity_id=when.isoformat(),
                before={"original_key": base_key, "original_md5": head.content_md5},
                after={
                    "day": when.isoformat(),
                    "row_count": len(rows),
                    "s3_key": sidecar,
                    "sha256": body_sha256,
                },
                correlation_id=f"audit_export:{when.isoformat()}",
            )
            await session.commit()
            return ExportResult(
                day=when,
                row_count=len(rows),
                s3_key=sidecar,
                sha256=body_sha256,
                action="reprocessed",
            )

        # Missing → write it. Empty day still writes an empty gzip so
        # "the export ran" is provable even when there was no traffic.
        await s3.put(
            base_key,
            body=body,
            content_type="application/gzip",
            content_md5=body_md5,
        )
        await append_audit(
            session,
            actor_id=None,
            action="audit_export.written",
            entity="audit_export",
            entity_id=when.isoformat(),
            before=None,
            after={
                "day": when.isoformat(),
                "row_count": len(rows),
                "s3_key": base_key,
                "sha256": body_sha256,
            },
            correlation_id=f"audit_export:{when.isoformat()}",
        )
        await session.commit()
        return ExportResult(
            day=when,
            row_count=len(rows),
            s3_key=base_key,
            sha256=body_sha256,
            action="written",
        )
    except Exception as exc:
        # Roll back the transaction so the failure audit row lands on a
        # clean slate. If the session is unusable we swallow the rollback
        # error and try to log at least once.
        await session.rollback()
        try:
            await append_audit(
                session,
                actor_id=None,
                action="audit_export.failed",
                entity="audit_export",
                entity_id=when.isoformat(),
                before=None,
                after={"day": when.isoformat(), "error": repr(exc)},
                correlation_id=f"audit_export:{when.isoformat()}",
            )
            await session.commit()
        except Exception:  # pragma: no cover - defensive
            log.exception("audit_export_failure_audit_failed", day=when.isoformat())
        raise


def _parse_day_arg(args: list[str]) -> date | None:
    """Optional ``--day YYYY-MM-DD`` CLI flag for manual backfill."""

    for i, a in enumerate(args):
        if a == "--day" and i + 1 < len(args):
            return date.fromisoformat(args[i + 1])
        if a.startswith("--day="):
            return date.fromisoformat(a.split("=", 1)[1])
    return None


async def _run_once(day: date | None) -> None:
    s3 = AuditExportS3()
    try:
        async with session_factory() as session:
            result = await run(session, s3, day)
        log.info(
            "audit_export_ok",
            day=result.day.isoformat(),
            action=result.action,
            row_count=result.row_count,
            s3_key=result.s3_key,
        )
    finally:
        await s3.aclose()


def main() -> None:
    day = _parse_day_arg(sys.argv[1:])
    override = os.environ.get("AUDIT_EXPORT_DAY")
    if day is None and override:
        day = date.fromisoformat(override)
    try:
        asyncio.run(_run_once(day))
    except KeyboardInterrupt:  # pragma: no cover - operator quit
        log.info("audit_export_stopped")


if __name__ == "__main__":
    main()


__all__ = ["ExportResult", "main", "run"]
