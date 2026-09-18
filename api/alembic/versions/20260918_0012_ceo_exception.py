"""S4 E7 — CEO exception + CEO delegate (Agent V, wave 3).

Adds two tables:

- ``ceo_exception``: immutable record of a CEO's decision on a package
  that failed a policy floor (US or India). Rows are set-once at
  ``ceo_exception.drafted`` time; the rationale / decision fields are
  filled in-place later but never versioned (there is only ever one row
  per ``approval_package`` — approvals are never reused across
  packages, per blueprint §6.6).
- ``ceo_delegate``: time-bound delegation from the CEO to a specific
  user. The service layer treats an active delegate as CEO for the
  approve/reject/return endpoints. Kept as an audited ledger — new rows
  are appended, existing rows never edited.

Agent U owns the ``approval_package`` table (S4 wave 2). The FK from
``ceo_exception.package_id`` is added if that table exists at migrate
time, otherwise the column is created without a hard FK and a runtime
guard in ``app.services.ceo_exception`` reports the missing dependency.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0012"
down_revision: str | None = "20260918_0010"
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
    package_fk: list[sa.SchemaItem] = []
    if _table_exists("approval_package"):
        package_fk = [
            sa.ForeignKeyConstraint(
                ["package_id"],
                ["approval_package.id"],
                name="fk_ceo_exception_package_id",
            )
        ]

    op.create_table(
        "ceo_exception",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        # Nullable ForeignKey until Agent U's approval_package migration
        # runs; the service layer guards against orphans regardless.
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("brief_json", _json_type(), nullable=False),
        sa.Column("rationale_text", sa.Text(), nullable=True),
        sa.Column("rationale_tidied_text", sa.Text(), nullable=True),
        sa.Column("rationale_set_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("rationale_set_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("conditions_text", sa.Text(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("decided_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "drafted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('approve', 'reject', 'return_for_changes')",
            name="ck_ceo_exception_decision",
        ),
        sa.UniqueConstraint("package_id", name="uq_ceo_exception_package_id"),
        *package_fk,
    )
    op.create_index(
        "ix_ceo_exception_package_id", "ceo_exception", ["package_id"]
    )
    op.create_index(
        "ix_ceo_exception_decision", "ceo_exception", ["decision"]
    )

    op.create_table(
        "ceo_delegate",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "delegate_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_ceo_delegate_delegate_id"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("expiry", sa.Date(), nullable=False),
        sa.Column(
            "granted_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_ceo_delegate_granted_by"),
            nullable=False,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "expiry >= effective_from",
            name="ck_ceo_delegate_window",
        ),
    )
    op.create_index(
        "ix_ceo_delegate_delegate_id", "ceo_delegate", ["delegate_id"]
    )
    op.create_index(
        "ix_ceo_delegate_effective_from", "ceo_delegate", ["effective_from"]
    )
    op.create_index("ix_ceo_delegate_expiry", "ceo_delegate", ["expiry"])


def downgrade() -> None:
    op.drop_index("ix_ceo_delegate_expiry", table_name="ceo_delegate")
    op.drop_index("ix_ceo_delegate_effective_from", table_name="ceo_delegate")
    op.drop_index("ix_ceo_delegate_delegate_id", table_name="ceo_delegate")
    op.drop_table("ceo_delegate")

    op.drop_index("ix_ceo_exception_decision", table_name="ceo_exception")
    op.drop_index("ix_ceo_exception_package_id", table_name="ceo_exception")
    op.drop_table("ceo_exception")
