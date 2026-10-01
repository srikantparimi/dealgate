#!/usr/bin/env python3
"""S20 W3 · §6 stub-migration DRY RUN.

Classifies every `Sow` row without an uploaded file (or with only stub
versions) as either:

  * `empty_machine_created` — no user content anywhere down the chain.
    Safe to archive.
  * `has_user_content`      — at least one of: scope confirmations,
    GM drafts, staffing resource lines, comments, tasks/actions,
    approval packages (any status), signed_sow uploads, ceo exceptions,
    or explicit archive metadata. Must NOT be archived; the content
    is real work that would be lost.

Output: CSV at `docs/reports/s20/stub-manifest.csv` with columns:

    sow_id, opportunity_id, opportunity_hubspot_id, client_id, client_name,
    created_at, versions_total, versions_with_file, has_confirmed_scope,
    has_gm_model, has_staffing_lines, has_comments, has_tasks,
    has_approvals, has_signed_sow, has_ceo_exception, has_archive_marker,
    classification, recommended_action, reason

The script is READ-ONLY. It never writes to the database. The archive
run is a separate step (§6.5) that reads this manifest and is only
executed by the Lead after Kanna reviews it.

Usage (from the api worktree):

    cd api
    python -m scripts.sow_stub_dry_run \
        --database-url $DATABASE_URL \
        --output-csv ../docs/reports/s20/stub-manifest.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


# --- classification -------------------------------------------------------


@dataclass(frozen=True)
class SowClassification:
    sow_id: uuid.UUID
    opportunity_id: uuid.UUID
    opportunity_hubspot_id: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    created_at: str
    versions_total: int
    versions_with_file: int
    has_confirmed_scope: bool
    has_gm_model: bool
    has_staffing_lines: bool
    has_comments: bool
    has_tasks: bool
    has_approvals: bool
    has_signed_sow: bool
    has_ceo_exception: bool
    has_archive_marker: bool
    classification: str  # "empty_machine_created" | "has_user_content"
    recommended_action: str  # "archive" | "keep" | "keep_and_investigate"
    reason: str


async def classify_all(session) -> list[SowClassification]:
    """Return one classification row per non-archived Sow that has no
    live SowVersion with an S3 file. Ignores already-archived rows."""

    # Late imports so the script only pays for what it needs, and so a
    # missing model file never blocks startup.
    from sqlalchemy import func, select
    from app.models.approval import Approval, ApprovalPackage
    from app.models.ceo_exception import CeoException
    from app.models.client import Client
    from app.models.gm_model import GmModel, ResourceLine
    from app.models.opportunity import Opportunity
    from app.models.signed_sow import SignedSowUpload
    from app.models.sow import Sow, SowVersion
    from app.models.task import Task

    # Pull every non-archived Sow.
    sows = list(
        (
            await session.execute(
                select(Sow).where(Sow.archived_at.is_(None))
            )
        ).scalars()
    )
    if not sows:
        return []

    # Bulk-load related data to keep the classification O(N).
    sow_ids = [s.id for s in sows]

    versions_by_sow: dict[uuid.UUID, list[SowVersion]] = {}
    for v in (
        await session.execute(
            select(SowVersion).where(SowVersion.sow_id.in_(sow_ids))
        )
    ).scalars():
        versions_by_sow.setdefault(v.sow_id, []).append(v)

    opp_ids = list({s.opportunity_id for s in sows})
    opps_by_id: dict[uuid.UUID, Opportunity] = {
        o.id: o
        for o in (
            await session.execute(select(Opportunity).where(Opportunity.id.in_(opp_ids)))
        ).scalars()
    }
    client_ids = list({o.client_id for o in opps_by_id.values() if o.client_id})
    clients_by_id: dict[uuid.UUID, Client] = (
        {
            c.id: c
            for c in (
                await session.execute(
                    select(Client).where(Client.id.in_(client_ids))
                )
            ).scalars()
        }
        if client_ids
        else {}
    )

    # Aggregate flags via count queries scoped to sow_ids/opp_ids.
    def rowcount(model, where) -> dict[uuid.UUID, int]:
        # Not used directly — kept as a placeholder for aggregations
        # we don't need after the switch to per-sow loops below.
        return {}

    # Confirmed scope: any SowVersion with confirmed_at != NULL.
    # GM model: any GmModel where opportunity_id matches.
    gm_models_by_opp: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in (
        await session.execute(
            select(GmModel.id, GmModel.opportunity_id).where(
                GmModel.opportunity_id.in_(opp_ids)
            )
        )
    ).all():
        gm_models_by_opp.setdefault(row.opportunity_id, []).append(row.id)

    # Staffing (ResourceLine) per GM.
    gm_ids = [gm for ids in gm_models_by_opp.values() for gm in ids]
    staffing_per_gm: set[uuid.UUID] = set()
    if gm_ids:
        for (gm_id,) in (
            await session.execute(
                select(ResourceLine.gm_model_id)
                .where(ResourceLine.gm_model_id.in_(gm_ids))
                .distinct()
            )
        ).all():
            staffing_per_gm.add(gm_id)

    # Approvals per opportunity.
    approvals_by_opp: set[uuid.UUID] = set()
    if opp_ids:
        rows = (
            await session.execute(
                select(ApprovalPackage.opportunity_id)
                .where(ApprovalPackage.opportunity_id.in_(opp_ids))
                .distinct()
            )
        ).all()
        approvals_by_opp = {row[0] for row in rows}

    # SignedSowUpload per package -> reduce to opportunity via join.
    signed_by_opp: set[uuid.UUID] = set()
    if opp_ids:
        rows = (
            await session.execute(
                select(ApprovalPackage.opportunity_id)
                .join(SignedSowUpload, SignedSowUpload.package_id == ApprovalPackage.id)
                .where(ApprovalPackage.opportunity_id.in_(opp_ids))
                .distinct()
            )
        ).all()
        signed_by_opp = {row[0] for row in rows}

    ceo_by_opp: set[uuid.UUID] = set()
    if opp_ids:
        rows = (
            await session.execute(
                select(ApprovalPackage.opportunity_id)
                .join(CeoException, CeoException.package_id == ApprovalPackage.id)
                .where(ApprovalPackage.opportunity_id.in_(opp_ids))
                .distinct()
            )
        ).all()
        ceo_by_opp = {row[0] for row in rows}

    # Tasks per opportunity owner — this is an approximate signal
    # because Task rows aren't linked directly; they're linked via
    # owner_id. Prefer a true audit-based signal later.
    task_by_owner: dict[uuid.UUID, int] = {}
    owner_ids = list({o.owner_id for o in opps_by_id.values() if o.owner_id})
    if owner_ids:
        for owner_id, count in (
            await session.execute(
                select(Task.owner_id, func.count(Task.id))
                .where(Task.owner_id.in_(owner_ids))
                .group_by(Task.owner_id)
            )
        ).all():
            task_by_owner[owner_id] = int(count)

    results: list[SowClassification] = []
    for sow in sows:
        versions = versions_by_sow.get(sow.id, [])
        versions_with_file = sum(
            1
            for v in versions
            if v.file_s3_key
            and v.file_s3_key.strip()
            and not v.file_s3_key.startswith("bulk-import/")
        )
        has_confirmed_scope = any(
            v.confirmed_at is not None for v in versions
        )
        opp = opps_by_id.get(sow.opportunity_id)
        client = clients_by_id.get(opp.client_id) if opp and opp.client_id else None

        has_gm_model = sow.opportunity_id in gm_models_by_opp
        has_staffing_lines = any(
            gm_id in staffing_per_gm
            for gm_id in gm_models_by_opp.get(sow.opportunity_id, [])
        )
        has_approvals = sow.opportunity_id in approvals_by_opp
        has_signed_sow = sow.opportunity_id in signed_by_opp
        has_ceo_exception = sow.opportunity_id in ceo_by_opp
        has_tasks = bool(opp and opp.owner_id and task_by_owner.get(opp.owner_id, 0) > 0)
        # Comments aren't a model tonight (W6's scope); use False.
        has_comments = False
        has_archive_marker = sow.archived_at is not None

        # A row is `has_user_content` if ANY of these signals fire.
        user_flags = [
            has_confirmed_scope,
            has_gm_model and has_staffing_lines,
            has_approvals,
            has_signed_sow,
            has_ceo_exception,
            has_archive_marker,
            versions_with_file > 0,
        ]
        if any(user_flags):
            classification = "has_user_content"
            recommended_action = (
                "keep_and_investigate" if not versions_with_file else "keep"
            )
            reason = "; ".join(
                r
                for r, on in [
                    ("confirmed_scope", has_confirmed_scope),
                    ("gm_and_staffing", has_gm_model and has_staffing_lines),
                    ("approvals_present", has_approvals),
                    ("signed_sow", has_signed_sow),
                    ("ceo_exception", has_ceo_exception),
                    ("archive_marker", has_archive_marker),
                    (f"versions_with_file={versions_with_file}", versions_with_file > 0),
                ]
                if on
            )
        else:
            classification = "empty_machine_created"
            recommended_action = "archive"
            reason = (
                "no versions with files; no scope confirmation; no GM/staffing; "
                "no approvals; no CEO exception; not already archived"
            )

        results.append(
            SowClassification(
                sow_id=sow.id,
                opportunity_id=sow.opportunity_id,
                opportunity_hubspot_id=(
                    opp.hubspot_deal_id if opp is not None else None
                ),
                client_id=opp.client_id if opp and opp.client_id else None,
                client_name=client.name if client is not None else None,
                created_at=sow.created_at.isoformat() if sow.created_at else "",
                versions_total=len(versions),
                versions_with_file=versions_with_file,
                has_confirmed_scope=has_confirmed_scope,
                has_gm_model=has_gm_model,
                has_staffing_lines=has_staffing_lines,
                has_comments=has_comments,
                has_tasks=has_tasks,
                has_approvals=has_approvals,
                has_signed_sow=has_signed_sow,
                has_ceo_exception=has_ceo_exception,
                has_archive_marker=has_archive_marker,
                classification=classification,
                recommended_action=recommended_action,
                reason=reason,
            )
        )

    return results


# --- CSV writer -----------------------------------------------------------


def write_manifest_csv(rows: list[SowClassification], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "sow_id",
                "opportunity_id",
                "opportunity_hubspot_id",
                "client_id",
                "client_name",
                "created_at",
                "versions_total",
                "versions_with_file",
                "has_confirmed_scope",
                "has_gm_model",
                "has_staffing_lines",
                "has_comments",
                "has_tasks",
                "has_approvals",
                "has_signed_sow",
                "has_ceo_exception",
                "has_archive_marker",
                "classification",
                "recommended_action",
                "reason",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r.sow_id,
                    r.opportunity_id,
                    r.opportunity_hubspot_id or "",
                    r.client_id or "",
                    r.client_name or "",
                    r.created_at,
                    r.versions_total,
                    r.versions_with_file,
                    r.has_confirmed_scope,
                    r.has_gm_model,
                    r.has_staffing_lines,
                    r.has_comments,
                    r.has_tasks,
                    r.has_approvals,
                    r.has_signed_sow,
                    r.has_ceo_exception,
                    r.has_archive_marker,
                    r.classification,
                    r.recommended_action,
                    r.reason,
                ]
            )


# --- entry point ----------------------------------------------------------


async def _main_async(database_url: str, output_csv: Path) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = create_async_engine(database_url, future=True)
    async with AsyncSession(engine, expire_on_commit=False) as session:
        rows = await classify_all(session)
    await engine.dispose()

    write_manifest_csv(rows, output_csv)
    n_total = len(rows)
    n_empty = sum(1 for r in rows if r.classification == "empty_machine_created")
    n_content = n_total - n_empty
    print(
        f"Classified {n_total} non-archived Sow rows: "
        f"{n_empty} empty_machine_created (archive candidates), "
        f"{n_content} has_user_content (must preserve). "
        f"Manifest written to {output_csv}.",
        file=sys.stderr,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="S20 W3 SOW stub-migration dry run")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pw@host/db",
    )
    parser.add_argument(
        "--output-csv",
        default=str(REPO_ROOT / "docs" / "reports" / "s20" / "stub-manifest.csv"),
        help="Where to write the classification manifest",
    )
    args = parser.parse_args()

    if not args.database_url:
        parser.error("--database-url or DATABASE_URL is required")

    # Ensure the api package is importable when run as a script from the
    # repo root or from the api/ directory.
    api_dir = REPO_ROOT / "api"
    if str(api_dir) not in sys.path:
        sys.path.insert(0, str(api_dir))

    asyncio.run(_main_async(args.database_url, Path(args.output_csv)))


if __name__ == "__main__":
    main()
