"""S10-02 — bulk SOW import tables + sow_version.execution_state.

Revision ID: 20260921_0029
Revises: 20260921_0028
Create Date: 2026-09-21

Creates the ``import_batch`` + ``import_file`` tables that hold one bulk
upload session's queue and per-file lifecycle. Extends ``sow_version``
with ``execution_state`` (draft | executed | superseded) so imported
SOWs with a signature page (or later confirmation) can be scheduled for
renewal without pretending they were approved.

Legacy imports always land with ``governance_status='legacy_not_evidenced'``
on the sow_version — CLAUDE.md forbids backfilling fake approvals
(``approval_evidenced`` stays False). This migration only adds the
scaffolding; the write path lives in ``app.services.bulk_import``.

Reversible: :func:`downgrade` drops both tables in reverse-FK order and
removes the ``execution_state`` column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260921_0029"
down_revision: str | Sequence[str] | None = "20260921_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in sa.inspect(bind).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    if not _table_exists("import_batch"):
        op.create_table(
            "import_batch",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "run_by",
                sa.Uuid(),
                sa.ForeignKey("user.id", name="fk_import_batch_run_by"),
                nullable=False,
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
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'processing'"),
            ),
            sa.Column(
                "file_count", sa.Integer(), nullable=False, server_default=sa.text("0")
            ),
            sa.Column(
                "queued_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "imported_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "rejected_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "duplicate_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "needs_review_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column("note", sa.Text(), nullable=True),
            sa.CheckConstraint(
                "status IN ('processing', 'completed', 'failed')",
                name="ck_import_batch_status",
            ),
        )
        op.create_index("ix_import_batch_status", "import_batch", ["status"])

    if not _table_exists("import_file"):
        op.create_table(
            "import_file",
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column(
                "batch_id",
                sa.Uuid(),
                sa.ForeignKey("import_batch.id", name="fk_import_file_batch_id"),
                nullable=False,
            ),
            sa.Column("filename", sa.String(length=512), nullable=False),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False),
            sa.Column("sha256", sa.String(length=128), nullable=False),
            sa.Column("detected_type", sa.String(length=32), nullable=True),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'queued'"),
            ),
            sa.Column(
                "matched_client_id",
                sa.Uuid(),
                sa.ForeignKey("client.id", name="fk_import_file_client_id"),
                nullable=True,
            ),
            sa.Column("matched_confidence", sa.Numeric(4, 3), nullable=True),
            sa.Column(
                "opportunity_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "opportunity.id", name="fk_import_file_opportunity_id"
                ),
                nullable=True,
            ),
            sa.Column(
                "sow_version_id",
                sa.Uuid(),
                sa.ForeignKey(
                    "sow_version.id", name="fk_import_file_sow_version_id"
                ),
                nullable=True,
            ),
            sa.Column(
                "duplicate_of",
                sa.Uuid(),
                sa.ForeignKey(
                    "sow_version.id", name="fk_import_file_duplicate_of"
                ),
                nullable=True,
            ),
            sa.Column(
                "warnings",
                _json_type(),
                nullable=False,
                server_default=sa.text("'[]'"),
            ),
            sa.Column(
                "errors",
                _json_type(),
                nullable=False,
                server_default=sa.text("'[]'"),
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
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_import_file_batch_id", "import_file", ["batch_id"]
        )
        op.create_index("ix_import_file_status", "import_file", ["status"])
        op.create_index("ix_import_file_sha256", "import_file", ["sha256"])

    if not _column_exists("sow_version", "execution_state"):
        with op.batch_alter_table("sow_version") as batch:
            batch.add_column(
                sa.Column(
                    "execution_state",
                    sa.String(length=16),
                    nullable=False,
                    server_default=sa.text("'draft'"),
                )
            )

    if not _column_exists("sow_version", "governance_status"):
        with op.batch_alter_table("sow_version") as batch:
            batch.add_column(
                sa.Column(
                    "governance_status",
                    sa.String(length=48),
                    nullable=True,
                )
            )


def downgrade() -> None:
    if _column_exists("sow_version", "execution_state"):
        with op.batch_alter_table("sow_version") as batch:
            batch.drop_column("execution_state")
    if _column_exists("sow_version", "governance_status"):
        with op.batch_alter_table("sow_version") as batch:
            batch.drop_column("governance_status")

    if _table_exists("import_file"):
        op.drop_index("ix_import_file_sha256", table_name="import_file")
        op.drop_index("ix_import_file_status", table_name="import_file")
        op.drop_index("ix_import_file_batch_id", table_name="import_file")
        op.drop_table("import_file")

    if _table_exists("import_batch"):
        op.drop_index("ix_import_batch_status", table_name="import_batch")
        op.drop_table("import_batch")
