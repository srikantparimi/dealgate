"""S13a-B2 — soft-archive columns for delete-with-governance.

Records that were ever approved or signed must not be hard-deleted (the
append-only audit rule stands, per docs/directives/s13a-delete-reset.md
"Archive (void), never hard delete"). Archived rows keep every child row
and their audit trail but leave the default lists and dashboards, and
the dedupe check treats them as informational hits rather than blocks.

Hard delete is enforced entirely at the service layer — we don't need a
column for it, the row is gone.

Revision ID: 20260924_0033
Revises: 20260923_0032
Create Date: 2026-09-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260924_0033"
down_revision = "20260923_0032"
branch_labels = None
depends_on = None


_TABLES = ("client", "opportunity", "sow")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in _TABLES:
        cols = {c["name"] for c in inspector.get_columns(table)}
        if "archived_at" not in cols:
            op.add_column(
                table,
                sa.Column(
                    "archived_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )
        if "archived_by" not in cols:
            op.add_column(
                table,
                sa.Column(
                    "archived_by",
                    sa.Uuid(),
                    sa.ForeignKey("user.id", name=f"fk_{table}_archived_by"),
                    nullable=True,
                ),
            )
        if "archived_reason" not in cols:
            op.add_column(
                table,
                sa.Column("archived_reason", sa.String(length=1024), nullable=True),
            )
        # Partial index so live-only filters (`WHERE archived_at IS NULL`)
        # stay fast on Postgres. SQLite ignores partial indexes silently.
        idx_name = f"ix_{table}_live"
        if bind.dialect.name == "postgresql":
            op.execute(
                f"CREATE INDEX IF NOT EXISTS {idx_name} "
                f"ON {table} (id) WHERE archived_at IS NULL"
            )


def downgrade() -> None:
    bind = op.get_bind()
    for table in _TABLES:
        if bind.dialect.name == "postgresql":
            op.execute(f"DROP INDEX IF EXISTS ix_{table}_live")
        with op.batch_alter_table(table) as batch:
            batch.drop_column("archived_reason")
            batch.drop_column("archived_by")
            batch.drop_column("archived_at")
