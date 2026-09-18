"""S4 E7 — approval_package + approval.

Revision ID: 20260918_0011
Revises: 20260918_0010
Create Date: 2026-09-18

Creates:

- ``approval_package``: immutable envelope per submission. Freezes the
  sow_version + gm_model + policy_version + sha256 package_hash and moves
  through the state machine (pending_delivery_hr → pending_finance_legal →
  ready_to_sign | pending_ceo_exception | voided | rejected). CHECK
  constraint enforces the status alphabet.
- ``approval``: one row per (package, function, approver_id) decision.
  UNIQUE (package_id, function, approver_id) blocks a user holding two
  roles (e.g. Finance + Delivery) from double-counting on the same
  package. CHECK constraints police the function + decision alphabets.

Rule 4 (CLAUDE.md): both tables are append-only in the service layer —
no PATCH ever touches these rows. Rule 5: every state change writes an
``audit_event`` in the same transaction as the state change (see
``app.services.approvals``).

Reversible: ``downgrade()`` drops both tables in dependency order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260918_0011"
down_revision: str | None = "20260918_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_package",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id", name="fk_approval_package_opportunity_id"),
            nullable=False,
        ),
        sa.Column(
            "sow_version_id",
            sa.Uuid(),
            sa.ForeignKey("sow_version.id", name="fk_approval_package_sow_version_id"),
            nullable=False,
        ),
        sa.Column(
            "gm_model_id",
            sa.Uuid(),
            sa.ForeignKey("gm_model.id", name="fk_approval_package_gm_model_id"),
            nullable=False,
        ),
        sa.Column("package_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "submitted_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_approval_package_submitted_by"),
            nullable=False,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_reason", sa.String(length=1024), nullable=True),
        sa.Column(
            "policy_version_id",
            sa.Uuid(),
            sa.ForeignKey("policy_version.id", name="fk_approval_package_policy_version_id"),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status IN ("
            "'pending_delivery_hr', 'pending_finance_legal', "
            "'pending_ceo_exception', 'ready_to_sign', 'voided', 'rejected'"
            ")",
            name="ck_approval_package_status",
        ),
    )
    op.create_index(
        "ix_approval_package_opportunity_id",
        "approval_package",
        ["opportunity_id"],
    )
    op.create_index(
        "ix_approval_package_status", "approval_package", ["status"]
    )
    op.create_index(
        "ix_approval_package_package_hash",
        "approval_package",
        ["package_hash"],
    )

    op.create_table(
        "approval",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "package_id",
            sa.Uuid(),
            sa.ForeignKey("approval_package.id", name="fk_approval_package_id"),
            nullable=False,
        ),
        sa.Column("function", sa.String(length=16), nullable=False),
        sa.Column(
            "approver_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_approval_approver_id"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=2048), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "function IN ('delivery', 'hr', 'finance', 'legal')",
            name="ck_approval_function",
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'request_changes')",
            name="ck_approval_decision",
        ),
        sa.UniqueConstraint(
            "package_id", "function", "approver_id",
            name="uq_approval_pkg_function_approver",
        ),
    )
    op.create_index("ix_approval_package_id", "approval", ["package_id"])


def downgrade() -> None:
    op.drop_index("ix_approval_package_id", table_name="approval")
    op.drop_table("approval")
    op.drop_index("ix_approval_package_package_hash", table_name="approval_package")
    op.drop_index("ix_approval_package_status", table_name="approval_package")
    op.drop_index("ix_approval_package_opportunity_id", table_name="approval_package")
    op.drop_table("approval_package")
