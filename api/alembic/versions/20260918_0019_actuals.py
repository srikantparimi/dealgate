"""S6 E9 — Actuals CSV import (timesheets + cost).

Revision ID: 20260918_0019
Revises: 20260918_0017
Create Date: 2026-09-18

Adds two tables for the month-end actuals CSV pilot (story
``docs/backlog/s6-actuals-import.md``):

- ``actual_period`` — one row per (resource_line, month). Numeric money
  columns per CLAUDE.md rule 2. UNIQUE (resource_line_id, period_month)
  supports the "re-import upserts" acceptance test.
- ``actual_import_batch`` — one row per uploaded CSV, with row_count,
  errors JSONB and a status lifecycle (uploading, validated, committed,
  failed).

Reversible: ``downgrade()`` drops both tables. Idempotent guards mirror
migration 0009 so a partial roll-forward can be re-applied.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0019"
down_revision: str | None = "20260918_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("actual_import_batch"):
        op.create_table(
            "actual_import_batch",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "uploaded_by",
                sa.Uuid(),
                sa.ForeignKey("user.id", name="fk_actual_import_batch_uploaded_by"),
                nullable=False,
            ),
            sa.Column(
                "uploaded_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "row_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("errors", _json_type(), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'uploading'"),
            ),
            sa.CheckConstraint(
                "status IN ('uploading', 'validated', 'committed', 'failed')",
                name="ck_actual_import_batch_status",
            ),
        )
        op.create_index(
            "ix_actual_import_batch_status", "actual_import_batch", ["status"]
        )
        op.create_index(
            "ix_actual_import_batch_uploaded_at",
            "actual_import_batch",
            ["uploaded_at"],
        )

    if not _table_exists("actual_period"):
        op.create_table(
            "actual_period",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "gm_model_id",
                sa.Uuid(),
                sa.ForeignKey("gm_model.id", name="fk_actual_period_gm_model_id"),
                nullable=False,
            ),
            sa.Column(
                "resource_line_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "resource_line.id", name="fk_actual_period_resource_line_id"
                ),
                nullable=False,
            ),
            sa.Column("period_month", sa.Date(), nullable=False),
            sa.Column("actual_hours", sa.Numeric(10, 2), nullable=False),
            sa.Column("actual_cost", sa.Numeric(14, 2), nullable=False),
            sa.Column("actual_revenue", sa.Numeric(14, 2), nullable=False),
            sa.Column(
                "imported_by",
                sa.Uuid(),
                sa.ForeignKey("user.id", name="fk_actual_period_imported_by"),
                nullable=False,
            ),
            sa.Column(
                "imported_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "batch_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "actual_import_batch.id",
                    name="fk_actual_period_batch_id",
                ),
                nullable=True,
            ),
            sa.UniqueConstraint(
                "resource_line_id",
                "period_month",
                name="uq_actual_period_line_month",
            ),
        )
        op.create_index(
            "ix_actual_period_gm_model_id", "actual_period", ["gm_model_id"]
        )
        op.create_index(
            "ix_actual_period_period_month", "actual_period", ["period_month"]
        )


def downgrade() -> None:
    if _table_exists("actual_period"):
        op.drop_index("ix_actual_period_period_month", table_name="actual_period")
        op.drop_index("ix_actual_period_gm_model_id", table_name="actual_period")
        op.drop_table("actual_period")
    if _table_exists("actual_import_batch"):
        op.drop_index(
            "ix_actual_import_batch_uploaded_at", table_name="actual_import_batch"
        )
        op.drop_index(
            "ix_actual_import_batch_status", table_name="actual_import_batch"
        )
        op.drop_table("actual_import_batch")
