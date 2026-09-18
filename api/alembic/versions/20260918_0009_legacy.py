"""S6 (user-added scope): legacy SOW bulk upload + resource-line Excel import.

Lands after Agent P's ``sow`` / ``sow_version`` migration (0006). Agent R's
Builder migration (0007) descends from this one — the coordination note in
0007 explains the linear chain. This story creates:

- ``gm_model`` (base columns: engagement_type, currency, sow_id link).
  Agent R's 0007 extends with the Builder-only columns.
- ``resource_line`` (base columns: role/seniority/location/dates/hours/rates/
  revenue split). Agent R's 0007 adds ``person_name``, ``hourly_cost``, and
  ``validated_by``.
- ``legacy_import_batch`` — one row per bulk-upload session, with the
  lifecycle status ``uploading`` → ``reviewing`` → ``approved``.

And extends:

- ``sow`` with ``sow_ref`` (nullable), ``client_id`` (FK), ``filename``,
  and ``legacy_batch_id`` (FK). ``opportunity_id`` stays NOT NULL — the
  legacy service creates a synthetic ``Opportunity`` per legacy SOW so the
  1:1 invariant holds.
- ``sow_version`` with two governance flags:
    * ``legacy BOOLEAN NOT NULL DEFAULT false`` — imported via bulk upload.
    * ``approval_evidenced BOOLEAN NOT NULL DEFAULT false`` — never
      backfilled to ``true`` for legacy rows (blueprint §13 rollout rule).
      Enforced at write time in
      ``app.services.legacy_import.assert_not_legacy_for_approval``.

Reversible: ``downgrade()`` drops the new table + the two flags and the
sow additive columns. ``gm_model`` / ``resource_line`` are dropped last so
Agent R's downgrade doesn't leave orphan constraints.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0009"
down_revision: str | None = "20260918_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    # ---- legacy_import_batch ----------------------------------------------
    op.create_table(
        "legacy_import_batch",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "uploaded_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "sow_count", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "resource_line_count",
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
        sa.Column("approved_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploading', 'reviewing', 'approved')",
            name="ck_legacy_import_batch_status",
        ),
    )
    op.create_index(
        "ix_legacy_import_batch_status", "legacy_import_batch", ["status"]
    )

    # ---- sow: legacy grouping columns -------------------------------------
    # Use naming_convention so SQLite batch mode can name the FK constraints
    # it re-emits when it rebuilds the table.
    naming_convention = {
        "fk": "fk_%(table_name)s_%(column_0_name)s",
    }
    with op.batch_alter_table("sow", naming_convention=naming_convention) as batch:
        if not _column_exists("sow", "sow_ref"):
            batch.add_column(sa.Column("sow_ref", sa.String(length=128), nullable=True))
        if not _column_exists("sow", "client_id"):
            batch.add_column(
                sa.Column(
                    "client_id",
                    sa.Uuid(),
                    sa.ForeignKey("client.id", name="fk_sow_client_id"),
                    nullable=True,
                )
            )
        if not _column_exists("sow", "filename"):
            batch.add_column(sa.Column("filename", sa.String(length=512), nullable=True))
        if not _column_exists("sow", "legacy_batch_id"):
            batch.add_column(
                sa.Column(
                    "legacy_batch_id",
                    sa.Uuid(),
                    sa.ForeignKey(
                        "legacy_import_batch.id", name="fk_sow_legacy_batch_id"
                    ),
                    nullable=True,
                )
            )
    op.create_index("ix_sow_sow_ref", "sow", ["sow_ref"])
    op.create_index("ix_sow_legacy_batch_id", "sow", ["legacy_batch_id"])

    # ---- sow_version: governance flags ------------------------------------
    with op.batch_alter_table("sow_version") as batch:
        if not _column_exists("sow_version", "legacy"):
            batch.add_column(
                sa.Column(
                    "legacy",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )
        if not _column_exists("sow_version", "approval_evidenced"):
            batch.add_column(
                sa.Column(
                    "approval_evidenced",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    # ---- gm_model (base) --------------------------------------------------
    # Named FKs so Agent R's 0007 batch_alter_table can round-trip the table
    # without hitting SQLite's "constraint must have a name" rule.
    if not _table_exists("gm_model"):
        op.create_table(
            "gm_model",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "sow_id",
                sa.Uuid(),
                sa.ForeignKey("sow.id", name="fk_gm_model_sow_id"),
                nullable=True,
            ),
            sa.Column("engagement_type", sa.String(length=64), nullable=False),
            sa.Column(
                "currency",
                sa.String(length=8),
                nullable=False,
                server_default=sa.text("'USD'"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index("ix_gm_model_sow_id", "gm_model", ["sow_id"])

    # ---- resource_line (base) --------------------------------------------
    if not _table_exists("resource_line"):
        op.create_table(
            "resource_line",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "gm_model_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "gm_model.id", name="fk_resource_line_gm_model_id"
                ),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=128), nullable=False),
            sa.Column("seniority", sa.String(length=64), nullable=False),
            sa.Column("location", sa.String(length=16), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("allocation_pct", sa.Numeric(6, 4), nullable=False),
            sa.Column("billable_hours", sa.Numeric(12, 4), nullable=False),
            sa.Column("hourly_bill_rate", sa.Numeric(10, 4), nullable=False),
            sa.Column(
                "hourly_loaded_cost",
                sa.Numeric(10, 4),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("revenue_us", sa.Numeric(14, 4), nullable=True),
            sa.Column("revenue_india", sa.Numeric(14, 4), nullable=True),
            sa.Column("notes", sa.String(length=1024), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(
                "location IN ('US', 'India')",
                name="ck_resource_line_location",
            ),
        )
        op.create_index(
            "ix_resource_line_gm_model_id", "resource_line", ["gm_model_id"]
        )


def downgrade() -> None:
    if _table_exists("resource_line"):
        op.drop_index(
            "ix_resource_line_gm_model_id", table_name="resource_line"
        )
        op.drop_table("resource_line")
    if _table_exists("gm_model"):
        op.drop_index("ix_gm_model_sow_id", table_name="gm_model")
        op.drop_table("gm_model")

    with op.batch_alter_table("sow_version") as batch:
        batch.drop_column("approval_evidenced")
        batch.drop_column("legacy")

    op.drop_index("ix_sow_legacy_batch_id", table_name="sow")
    op.drop_index("ix_sow_sow_ref", table_name="sow")
    with op.batch_alter_table("sow") as batch:
        batch.drop_column("legacy_batch_id")
        batch.drop_column("filename")
        batch.drop_column("client_id")
        batch.drop_column("sow_ref")

    op.drop_index(
        "ix_legacy_import_batch_status", table_name="legacy_import_batch"
    )
    op.drop_table("legacy_import_batch")
