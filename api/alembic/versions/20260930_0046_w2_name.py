"""S20 W2 · L04 · opportunity.name column (mirrors HubSpot dealname).

Adds a nullable ``opportunity.name`` column so the mirror stores the
real deal title. Backfill + intake write it from ``props.dealname``;
the query service prefers it over the S19 slice-1 fallback of
``stage_label`` / ``sales_stage`` / ``hubspot_deal_id``.

Backward compatible: nullable, no default. Old rows have NULL until
the next backfill (or webhook fire per deal). The query service still
falls back through the S19 chain so an unmigrated row renders
something instead of a blank.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# Alembic version_num is VARCHAR(32); keep <= 32.
revision: str = "20260930_0046_w2_name"
down_revision: str | Sequence[str] | None = "20260930_0045_w1_own"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "opportunity",
        sa.Column("name", sa.String(255), nullable=True),
    )
    # Index for search — the query service (services/hubspot_pipeline.py)
    # LIKE-matches lower(name) in the search filter.
    op.create_index(
        "ix_opportunity_name_lower",
        "opportunity",
        [sa.text("lower(name)")],
        unique=False,
        postgresql_using="btree",
    )


def downgrade() -> None:
    op.drop_index("ix_opportunity_name_lower", table_name="opportunity")
    op.drop_column("opportunity", "name")
