"""S4 E2: HubSpot write-back outbox.

Creates ``hubspot_writeback_job`` — the immutable outbox that the write-back
worker drains. One row per governance transition that needs to reach HubSpot.

Blueprint rule (CLAUDE.md #7): HubSpot is master for identity / owner /
stage. DealGate only writes back the three governance properties:

- ``dealgate_governance_status``
- ``dealgate_approved_gm_pct``
- ``dealgate_link``

The service layer (`app.services.hubspot_writeback`) enforces the property
allow-list; this table only carries whatever JSON the service already
validated.

Reversible: ``downgrade()`` drops the table + index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260918_0013"
down_revision: str | None = "20260918_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "hubspot_writeback_job",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id", name="fk_hubspot_writeback_opportunity_id"),
            nullable=False,
        ),
        sa.Column("hubspot_deal_id", sa.String(length=64), nullable=False),
        sa.Column("target_state", _json_type(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=2000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'deal_missing')",
            name="ck_hubspot_writeback_status",
        ),
    )
    op.create_index(
        "ix_hubspot_writeback_status",
        "hubspot_writeback_job",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_hubspot_writeback_deal_id",
        "hubspot_writeback_job",
        ["hubspot_deal_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_hubspot_writeback_deal_id", table_name="hubspot_writeback_job"
    )
    op.drop_index(
        "ix_hubspot_writeback_status", table_name="hubspot_writeback_job"
    )
    op.drop_table("hubspot_writeback_job")
