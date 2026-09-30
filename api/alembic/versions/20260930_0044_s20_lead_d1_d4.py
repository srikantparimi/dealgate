"""S20 Lead · D1 many-SOWs-per-deal + D4 sync_status watermarks.

Two logically-independent changes bundled into one revision because
both are Lead-owned per contracts.md §7 and both need to land in the
same D5 window.

**D1 — many SOWs per deal** (`sow.opportunity_id` uniqueness drop):
Requested by W3 in `docs/reports/s20/requests.md::W3-2026-09-30-01`.
Model-side change already landed at commit `9a2ebc2`
(`sow.opportunity_id = mapped_column(..., unique=False)`). This
revision drops the Postgres UNIQUE constraint so multi-SOW inserts
actually succeed on staging. `services.sow_rollup.compute_headline`
derives the deal-level headline from the per-package worst state
instead.

**D4 — typed watermark columns on `sync_status`**:
Requested by W1 in `docs/reports/s20/requests.md::W1-20260930T0700-01`.
Model side (`api/app/services/sync_status.py`) already feature-detects
each column via `hasattr()`, so the app runs on the un-migrated schema
too. This revision materialises the columns so watermarks actually
persist across worker restarts. Every column is nullable + default
NULL (backward compat per D5).

Both changes are backward compatible:
- Old containers writing to `sow.opportunity_id` continue to succeed
  because the FK + type stay identical; only the UNIQUE goes away.
- Old containers reading `sync_status` never touched the new columns
  in the first place; new writes land in nullable NULL by default and
  the `hasattr()` guards make partial-migrated staging safe.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260930_0044_s20_lead_d1_d4"
down_revision: str | Sequence[str] | None = "20260930_0043_s20_w7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- D1 · drop UNIQUE on sow.opportunity_id --------------------------
    # Postgres names the constraint after the table + column by default;
    # `if_exists` keeps the migration idempotent across environments where
    # a prior manual fix may have already dropped it.
    with op.batch_alter_table("sow") as batch:
        batch.drop_constraint("sow_opportunity_id_key", type_="unique")

    # ---- D4 · watermark columns on sync_status --------------------------
    # Nullable + no default so old rows don't need backfill; every writer
    # is `services.sync_status.touch_source` which sets values explicitly.
    op.add_column(
        "sync_status",
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("scan_generation", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("scan_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("backlog_age_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "sync_status",
        sa.Column("dlq_age_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    # ---- Reverse D4 -------------------------------------------------------
    op.drop_column("sync_status", "dlq_age_seconds")
    op.drop_column("sync_status", "backlog_age_seconds")
    op.drop_column("sync_status", "scan_completed_at")
    op.drop_column("sync_status", "scan_started_at")
    op.drop_column("sync_status", "scan_generation")
    op.drop_column("sync_status", "reconciled_at")
    op.drop_column("sync_status", "processed_at")
    op.drop_column("sync_status", "received_at")

    # ---- Reverse D1 (re-adds the unique constraint) ---------------------
    # This will fail if any deal already has more than one non-archived
    # Sow — that's intentional; a downgrade is not allowed to silently
    # lose rows. Ops must archive-all-but-one per deal before downgrade.
    with op.batch_alter_table("sow") as batch:
        batch.create_unique_constraint("sow_opportunity_id_key", ["opportunity_id"])
