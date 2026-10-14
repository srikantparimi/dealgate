"""S23-PL1 item 1 — one row per HubSpot deal sync run.

No existing table records individual runs: ``sync_status`` holds one row per
source and ``audit_event`` holds per-page checkpoints. Every deal reconcile
(nightly, the SystemAdmin trigger, or a test run) now writes one row here, and
``GET /hubspot/sync-health`` reads freshness from it instead of the intake
heartbeat.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# Alembic's version_num column is VARCHAR(32); keep revision <= 32 chars.
revision = "20261014_0069_sync_run"
down_revision = "20261013_0068_cc_rules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    op.create_table(
        "hubspot_sync_run",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="running"),
        sa.Column("deals_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deals_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", json_type, nullable=False, server_default=sa.text("'[]'")),
        sa.Column("fatal_error", sa.String(length=255), nullable=True),
        sa.Column("counts", json_type, nullable=True),
        sa.CheckConstraint("kind IN ('nightly','manual','test')", name="ck_hubspot_sync_run_kind"),
        sa.CheckConstraint(
            "status IN ('running','ok','partial','failed')", name="ck_hubspot_sync_run_status"
        ),
        sa.CheckConstraint(
            "deals_seen >= 0 AND deals_written >= 0 AND error_count >= 0",
            name="ck_hubspot_sync_run_counts",
        ),
    )
    op.create_index("ix_hubspot_sync_run_started_at", "hubspot_sync_run", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_hubspot_sync_run_started_at", table_name="hubspot_sync_run")
    op.drop_table("hubspot_sync_run")
