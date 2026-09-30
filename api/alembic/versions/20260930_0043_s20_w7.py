"""S20 W7 · release gate: signed_sow expand, delivery_acceptance, project.

Adds the tables + columns the S20 W7 slice needs, per the requests
recorded in ``docs/reports/s20/requests.md`` #W7-2026-09-30-01 through
#W7-2026-09-30-05. Every change is backward compatible (D5).

Changes:

1. ``signed_sow_upload``:
   - New columns ``verify_reason VARCHAR(512) NULL`` and
     ``signer_state VARCHAR(32) NULL``.
   - Extend the ``verify_status`` CHECK to include ``unsigned``,
     ``declined``, ``expired``.

2. New table ``delivery_acceptance`` with UNIQUE (``package_id``).

3. New table ``project`` with UNIQUE (``package_id``) idempotency guard
   and a JSONB ``baseline_snapshot_json`` column.

4. ``approval_package``:
   - New column ``superseded_by UUID NULL`` FK to same table.

Rule 4/5: every column is backward compatible; downgrade drops in
reverse order.

**Migration id is provisional**: Lead may re-assign on integration.
Named ``20260930_0042`` for now to sit above the S19 head (``0041``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "20260930_0042"
down_revision: str | Sequence[str] | None = "20260929_0041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_VERIFY_STATUSES: tuple[str, ...] = (
    "pending",
    "verified",
    "blocked",
    "unsigned",
    "declined",
    "expired",
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1a. signed_sow_upload: add verify_reason + signer_state columns.
    op.add_column(
        "signed_sow_upload",
        sa.Column("verify_reason", sa.String(length=512), nullable=True),
    )
    op.add_column(
        "signed_sow_upload",
        sa.Column("signer_state", sa.String(length=32), nullable=True),
    )

    # 1b. Expand the verify_status CHECK.
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE signed_sow_upload "
            "DROP CONSTRAINT IF EXISTS ck_signed_sow_upload_status"
        )
        quoted = ", ".join(f"'{s}'" for s in _VERIFY_STATUSES)
        op.execute(
            "ALTER TABLE signed_sow_upload "
            f"ADD CONSTRAINT ck_signed_sow_upload_status "
            f"CHECK (verify_status IN ({quoted}))"
        )
    # SQLite: CHECK is enforced via a table rebuild; skipped tonight
    # (test suite runs sqlite via `create_all`, not migrations).

    # 2. delivery_acceptance table.
    op.create_table(
        "delivery_acceptance",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "package_id",
            sa.UUID(),
            sa.ForeignKey("approval_package.id", name="fk_delivery_acceptance_pkg"),
            nullable=False,
        ),
        sa.Column(
            "accepted_by",
            sa.UUID(),
            sa.ForeignKey("user.id", name="fk_delivery_acceptance_user"),
            nullable=False,
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("notes", sa.String(length=2048), nullable=True),
        sa.Column(
            "staffing_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "billing_setup_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "po_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.UniqueConstraint("package_id", name="uq_delivery_acceptance_package"),
    )

    # 3. project table.
    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.UUID(),
            sa.ForeignKey("opportunity.id", name="fk_project_opportunity"),
            nullable=False,
        ),
        sa.Column(
            "sow_version_id",
            sa.UUID(),
            sa.ForeignKey("sow_version.id", name="fk_project_sow_version"),
            nullable=False,
        ),
        sa.Column(
            "gm_model_id",
            sa.UUID(),
            sa.ForeignKey("gm_model.id", name="fk_project_gm_model"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            sa.UUID(),
            sa.ForeignKey("approval_package.id", name="fk_project_package"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.UUID(),
            sa.ForeignKey("client.id", name="fk_project_client"),
            nullable=True,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("baseline_snapshot_json", _json_type(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("user.id", name="fk_project_created_by"),
            nullable=True,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_reason", sa.String(length=1024), nullable=True),
        sa.UniqueConstraint("package_id", name="uq_project_package"),
    )

    # 4. approval_package.superseded_by
    op.add_column(
        "approval_package",
        sa.Column(
            "superseded_by",
            sa.UUID(),
            sa.ForeignKey("approval_package.id", name="fk_pkg_superseded_by"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_column("approval_package", "superseded_by")
    op.drop_table("project")
    op.drop_table("delivery_acceptance")

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE signed_sow_upload "
            "DROP CONSTRAINT IF EXISTS ck_signed_sow_upload_status"
        )
        original = ("pending", "verified", "blocked")
        quoted = ", ".join(f"'{s}'" for s in original)
        op.execute(
            "ALTER TABLE signed_sow_upload "
            f"ADD CONSTRAINT ck_signed_sow_upload_status "
            f"CHECK (verify_status IN ({quoted}))"
        )
    op.drop_column("signed_sow_upload", "signer_state")
    op.drop_column("signed_sow_upload", "verify_reason")
