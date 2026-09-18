"""gm_model + resource_line + cost_line — S3 E6 Delivery Model Builder.

Revision ID: 20260918_0007
Revises: 20260918_0009
Create Date: 2026-09-18

Extends the base tables that Agent legacy (S6) landed with the columns the
Builder needs, and creates ``cost_line`` fresh. Every operation is guarded
by an ``_exists`` check so this migration lands cleanly in whichever order
the sibling S3 stories are applied.

Additions on ``gm_model``:
  * ``opportunity_id`` (nullable Uuid FK)
  * ``sow_version_id`` (nullable Uuid, soft ref — no FK so we don't tie the
    physical foreign key to whichever of the two ``sow_version`` shapes
    lands first in staging)
  * ``delivery_pattern`` / ``contingency_pct`` / ``warranty_days``
  * ``revenue_us`` / ``revenue_india`` (bookkeeping fields snapshotted at
    save time so the list view does not have to re-run the GM engine)
  * ``created_by``

Additions on ``resource_line``:
  * ``person_name`` (nullable — NULL means "to hire")
  * ``hourly_cost`` (nullable — NULL means Delivery still owes Finance the
    validated cost; blueprint §2 forbids treating that as zero)
  * ``validated_by``

New table ``cost_line`` (non-labor costs — tools/travel/subcontractor/other).

Reversible: ``downgrade()`` drops ``cost_line`` and the additive columns.
The legacy-owned base columns are left in place so a partial rollback does
not break the legacy import path.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0007"
# Land after both the legacy S6 story (which creates gm_model + resource_line)
# and Agent P's sow_version. Keeping a linear head avoids the multi-head merge
# dance during dev-migrations.
down_revision: str | None = "20260918_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _index_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == name for ix in inspector.get_indexes(table))


def upgrade() -> None:
    # ---- gm_model ---------------------------------------------------------
    with op.batch_alter_table("gm_model") as batch:
        if not _column_exists("gm_model", "opportunity_id"):
            batch.add_column(
                sa.Column(
                    "opportunity_id",
                    sa.Uuid(),
                    sa.ForeignKey("opportunity.id"),
                    nullable=True,
                )
            )
        if not _column_exists("gm_model", "sow_version_id"):
            batch.add_column(sa.Column("sow_version_id", sa.Uuid(), nullable=True))
        if not _column_exists("gm_model", "delivery_pattern"):
            batch.add_column(sa.Column("delivery_pattern", sa.String(length=128), nullable=True))
        if not _column_exists("gm_model", "contingency_pct"):
            batch.add_column(sa.Column("contingency_pct", sa.Numeric(5, 2), nullable=True))
        if not _column_exists("gm_model", "warranty_days"):
            batch.add_column(sa.Column("warranty_days", sa.Integer(), nullable=True))
        if not _column_exists("gm_model", "revenue_us"):
            batch.add_column(
                sa.Column(
                    "revenue_us",
                    sa.Numeric(14, 2),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
        if not _column_exists("gm_model", "revenue_india"):
            batch.add_column(
                sa.Column(
                    "revenue_india",
                    sa.Numeric(14, 2),
                    nullable=False,
                    server_default=sa.text("0"),
                )
            )
        if not _column_exists("gm_model", "created_by"):
            batch.add_column(sa.Column("created_by", sa.Uuid(), nullable=True))

    if not _index_exists("gm_model", "ix_gm_model_opportunity_created"):
        op.create_index(
            "ix_gm_model_opportunity_created",
            "gm_model",
            ["opportunity_id", "created_at"],
        )

    # ---- resource_line ----------------------------------------------------
    with op.batch_alter_table("resource_line") as batch:
        if not _column_exists("resource_line", "person_name"):
            batch.add_column(sa.Column("person_name", sa.String(length=255), nullable=True))
        if not _column_exists("resource_line", "hourly_cost"):
            batch.add_column(sa.Column("hourly_cost", sa.Numeric(10, 4), nullable=True))
        if not _column_exists("resource_line", "validated_by"):
            batch.add_column(sa.Column("validated_by", sa.Uuid(), nullable=True))

    if not _index_exists("resource_line", "ix_resource_line_person"):
        op.create_index(
            "ix_resource_line_person",
            "resource_line",
            ["person_name"],
        )

    # ---- cost_line (new table) -------------------------------------------
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_line" not in inspector.get_table_names():
        op.create_table(
            "cost_line",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "gm_model_id",
                sa.Uuid(),
                sa.ForeignKey("gm_model.id"),
                nullable=False,
            ),
            sa.Column("category", sa.String(length=32), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("note", sa.String(length=1024), nullable=True),
            sa.Column(
                "location",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'US'"),
            ),
        )
        op.create_index(
            "ix_cost_line_gm_model",
            "cost_line",
            ["gm_model_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "cost_line" in inspector.get_table_names():
        op.drop_index("ix_cost_line_gm_model", table_name="cost_line")
        op.drop_table("cost_line")

    if _index_exists("resource_line", "ix_resource_line_person"):
        op.drop_index("ix_resource_line_person", table_name="resource_line")
    with op.batch_alter_table("resource_line") as batch:
        for col in ("validated_by", "hourly_cost", "person_name"):
            if _column_exists("resource_line", col):
                batch.drop_column(col)

    if _index_exists("gm_model", "ix_gm_model_opportunity_created"):
        op.drop_index("ix_gm_model_opportunity_created", table_name="gm_model")
    with op.batch_alter_table("gm_model") as batch:
        for col in (
            "created_by",
            "revenue_india",
            "revenue_us",
            "warranty_days",
            "contingency_pct",
            "delivery_pattern",
            "sow_version_id",
            "opportunity_id",
        ):
            if _column_exists("gm_model", col):
                batch.drop_column(col)
