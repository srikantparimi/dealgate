"""S3 E11 — adviser_estimate table.

The Opportunity Adviser records every AI-drafted estimate with the exact
inputs, structured output, sources, model name and prompt version. Rows are
immutable — every re-estimate creates a fresh row so the audit trail matches
the human review flow (CLAUDE.md rule 6).

Sales/Marketing/Presales/SystemAdmin write; every governance role reads.
Rate cards + policy floors are read at estimate-time — the row snapshots the
resulting cost band so the number stays reproducible even after Finance
publishes a new rate card version.

Revision ID: 20260918_0008
Revises: 20260918_0004
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0008"
down_revision: str | None = "20260918_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEFAULT_LABEL = (
    "Indicative estimate, requires Delivery and Finance validation"
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "adviser_estimate",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "submitted_by",
            sa.Uuid(),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("inputs", _json_type(), nullable=False),
        sa.Column("structured_output", _json_type(), nullable=False),
        sa.Column("sources", _json_type(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column(
            "reviewer_id",
            sa.Uuid(),
            sa.ForeignKey("user.id"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "label",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text(f"'{_DEFAULT_LABEL}'"),
        ),
    )
    op.create_index(
        "ix_adviser_estimate_submitted_by",
        "adviser_estimate",
        ["submitted_by", "submitted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_adviser_estimate_submitted_by", table_name="adviser_estimate"
    )
    op.drop_table("adviser_estimate")
