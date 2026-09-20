"""S11 slice 2 — backfill gm_model.sow_id from opportunity so the staffing
query can key on sow_id.

Today the invariant is one Sow per opportunity (`sow_extract._load_or_create_sow`
uses `scalar_one_or_none()`), so the join below is unambiguous. If a repair
script or a future codepath ever puts two Sow rows under one opportunity,
this backfill would need review — but the read query (`_existing_gm_for_sow`)
is what keeps the invariant honest going forward.

Revision ID: 20260923_0032
Revises: 20260923_0031
Create Date: 2026-09-23
"""

from __future__ import annotations

from alembic import op


revision = "20260923_0032"
down_revision = "20260923_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE gm_model
           SET sow_id = sow.id
          FROM sow
         WHERE gm_model.opportunity_id = sow.opportunity_id
           AND gm_model.sow_id IS NULL
        """
    )


def downgrade() -> None:
    # Nothing to undo — the column stays populated. Setting sow_id back to
    # NULL would re-create the original bug, and clients hold no data that
    # depended on the NULL state.
    pass
