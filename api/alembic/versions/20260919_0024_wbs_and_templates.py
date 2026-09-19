"""S7 wave 2 — WBS phases + reusable delivery-model templates.

Revision ID: 20260919_0024
Revises: 20260919_0021
Create Date: 2026-09-19

Story ``docs/backlog/s7-wbs-and-templates.md``. Blueprint §8 explicit
inputs list carries "Work breakdown" and "Reusable templates"; this
migration lands both:

- ``gm_model_phase`` — first-class WBS row grouping resource + cost lines
  under a named phase and (optionally) pointing at the SOW deliverable
  ref that phase implements. ``UNIQUE(gm_model_id, order)`` keeps the
  accordion order stable across reorders.
- ``resource_line.phase_id`` / ``cost_line.phase_id`` — NULLABLE FK to
  ``gm_model_phase``. NULL keeps legacy rows readable in the Builder's
  "Ungrouped" bucket (rule 4: no destructive backfills).
- ``gm_model_template`` — reusable model shape. ``template_json``
  captures phases + resource_lines (as a role/seniority/location shape
  with relative hours) + cost_lines. Blueprint §7 rule: templates
  NEVER carry cost values — those come from the active rate card when
  the user opens the Builder.

Reversible: ``downgrade()`` drops both tables + the added FK columns.
The core ``gm_model`` / ``resource_line`` / ``cost_line`` shape is
untouched so a partial rollback does not break the base Builder.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260919_0024"
down_revision: str | Sequence[str] | None = "20260919_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---- gm_model_phase ---------------------------------------------------
    if "gm_model_phase" not in inspector.get_table_names():
        op.create_table(
            "gm_model_phase",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "gm_model_id",
                sa.Uuid(),
                sa.ForeignKey("gm_model.id", name="fk_gm_model_phase_gm_model_id"),
                nullable=False,
            ),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("order", sa.Integer(), nullable=False),
            sa.Column(
                "sow_deliverable_ref", sa.String(length=255), nullable=True
            ),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "gm_model_id", "order", name="uq_gm_model_phase_order"
            ),
        )
        op.create_index(
            "ix_gm_model_phase_gm_model_id",
            "gm_model_phase",
            ["gm_model_id", "order"],
        )

    # ---- resource_line.phase_id + cost_line.phase_id ----------------------
    with op.batch_alter_table("resource_line") as batch:
        if not _column_exists("resource_line", "phase_id"):
            batch.add_column(
                sa.Column(
                    "phase_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "gm_model_phase.id",
                        name="fk_resource_line_phase_id",
                    ),
                    nullable=True,
                )
            )

    with op.batch_alter_table("cost_line") as batch:
        if not _column_exists("cost_line", "phase_id"):
            batch.add_column(
                sa.Column(
                    "phase_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "gm_model_phase.id",
                        name="fk_cost_line_phase_id",
                    ),
                    nullable=True,
                )
            )

    # ---- gm_model_template -----------------------------------------------
    if "gm_model_template" not in inspector.get_table_names():
        op.create_table(
            "gm_model_template",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False, unique=True),
            sa.Column("engagement_type", sa.String(length=64), nullable=False),
            sa.Column(
                "created_by",
                sa.Uuid(),
                sa.ForeignKey("user.id", name="fk_gm_model_template_created_by"),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("template_json", _json_type(), nullable=False),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("1")
                if bind.dialect.name == "sqlite"
                else sa.text("true"),
            ),
        )
        op.create_index(
            "ix_gm_model_template_engagement_type",
            "gm_model_template",
            ["engagement_type", "active"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "gm_model_template" in inspector.get_table_names():
        op.drop_index(
            "ix_gm_model_template_engagement_type", table_name="gm_model_template"
        )
        op.drop_table("gm_model_template")

    with op.batch_alter_table("cost_line") as batch:
        if _column_exists("cost_line", "phase_id"):
            batch.drop_column("phase_id")

    with op.batch_alter_table("resource_line") as batch:
        if _column_exists("resource_line", "phase_id"):
            batch.drop_column("phase_id")

    if "gm_model_phase" in inspector.get_table_names():
        op.drop_index("ix_gm_model_phase_gm_model_id", table_name="gm_model_phase")
        op.drop_table("gm_model_phase")
