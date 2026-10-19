"""S24-AG1 B13 — read-only report of stored agreement objects that no database row points at.

Lists every live object in the WHOLE agreements bucket (the latest version of a key that is not a delete
marker), not only ``agreements/``: the three objects AG0 expects sit under ``verification/s21/…``, where the
S21 proof script wrote them. An object is an orphan when no agreement row, agreement version or standard copy
references its key and it is older than 24 hours (a younger one may still be waiting for its row). Keys that a
deletion job has already queued for removal are listed separately. The report is one JSON document grouped by
top-level prefix. **It deletes nothing**: it only lists the bucket and reads the database.

Run it with the deletion-cleanup task definition (its role has ``s3:ListBucketVersions`` on the bucket; the
API's role cannot list it) and a command override::

    python -m worker.agreement_orphans

Locally: ``AGREEMENTS_BUCKET=<bucket> POSTGRES_URL=<url> python -m worker.agreement_orphans`` with credentials
that may list the bucket. See docs/runbooks/agreement-orphans.md.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.db import session_factory

MIN_AGE = timedelta(hours=24)
SAMPLE_PER_GROUP = 200  # keys printed per group; the counts and byte totals always cover every key
QUEUED_STATUSES = ("pending", "failed")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def list_live_objects(s3: Any, bucket: str) -> Iterator[dict[str, Any]]:
    """Every key whose latest version is an object (a delete marker as the latest version means the key is
    deleted). Uses ListObjectVersions, the one listing permission the cleanup role holds."""
    paginator = s3.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=bucket):
        for version in page.get("Versions", []) or []:
            if version.get("IsLatest"):
                yield {"key": version["Key"], "size": int(version.get("Size") or 0),
                       "last_modified": _aware(version["LastModified"])}


async def referenced_keys(session) -> set[str]:
    """Every key a database row points at: the agreement rows, their versions and the standard copies."""
    from app.models.agreements import StandardAgreement
    from app.models.client import Agreement, AgreementFileVersion

    keys: set[str] = set()
    for column in (Agreement.file_key, AgreementFileVersion.file_key, StandardAgreement.file_key):
        keys.update(key for key in (await session.scalars(select(column))).all() if key)
    return keys


async def queued_keys(session, bucket: str) -> set[str]:
    """Keys in this bucket that a pending or retrying deletion job will remove."""
    from app.models.deletion import DeletionJob

    keys: set[str] = set()
    for objects in (await session.scalars(
            select(DeletionJob.objects).where(DeletionJob.status.in_(QUEUED_STATUSES)))).all():
        for item in objects or []:
            if isinstance(item, dict) and item.get("bucket") == bucket and item.get("key"):
                keys.add(str(item["key"]))
    return keys


def top_level(key: str) -> str:
    head, sep, _rest = key.partition("/")
    return head if sep else "(bucket root)"


def build_report(objects: Iterable[dict[str, Any]], *, referenced: set[str], queued: set[str], bucket: str,
                 now: datetime) -> dict[str, Any]:
    cutoff = _aware(now) - MIN_AGE
    groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "bytes": 0, "oldest": None,
                                                             "newest": None, "keys": []})
    live = linked = recent = 0
    queued_rows: list[dict[str, Any]] = []
    for obj in objects:
        live += 1
        key = obj["key"]
        if key in referenced:
            linked += 1
            continue
        row = {"key": key, "size": obj["size"], "last_modified": _iso(obj["last_modified"])}
        if key in queued:
            queued_rows.append(row)
            continue
        if obj["last_modified"] > cutoff:
            recent += 1
            continue
        group = groups[top_level(key)]
        group["count"] += 1
        group["bytes"] += obj["size"]
        group["oldest"] = min(filter(None, (group["oldest"], row["last_modified"])))
        group["newest"] = max(filter(None, (group["newest"], row["last_modified"])))
        if len(group["keys"]) < SAMPLE_PER_GROUP:
            group["keys"].append(row)
    for group in groups.values():
        group["keys"].sort(key=lambda r: r["key"])
    orphans = sum(g["count"] for g in groups.values())
    return {
        "worker": "agreement_orphans",
        "read_only": True,
        "bucket": bucket,
        "scanned_at": _iso(now),
        "min_age_hours": int(MIN_AGE.total_seconds() // 3600),
        "live_objects": live,
        "referenced": linked,
        "unreferenced_younger_than_min_age": recent,
        "queued_for_cleanup": sorted(queued_rows, key=lambda r: r["key"]),
        "orphans": orphans,
        "orphan_bytes": sum(g["bytes"] for g in groups.values()),
        "groups": {name: groups[name] for name in sorted(groups)},
    }


async def run(session, s3: Any, bucket: str, *, now: datetime | None = None) -> dict[str, Any]:
    """Read the database, list the bucket, return the report. Never deletes or writes anything."""
    referenced = await referenced_keys(session)
    queued = await queued_keys(session, bucket)
    objects = await asyncio.to_thread(lambda: list(list_live_objects(s3, bucket)))
    return build_report(objects, referenced=referenced, queued=queued, bucket=bucket,
                        now=now or datetime.now(UTC))


async def main() -> int:
    from app.integrations.s3_sow import _client
    from app.services.deletion_storage import agreement_bucket

    bucket = agreement_bucket()
    try:
        async with session_factory() as session:
            report = await run(session, _client(), bucket)
    except Exception as exc:  # noqa: BLE001 — print the reason, exit non-zero, never retry blindly
        print(json.dumps({"worker": "agreement_orphans", "read_only": True, "bucket": bucket,
                          "error": f"{type(exc).__name__}: {str(exc)[:300]}"}))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
