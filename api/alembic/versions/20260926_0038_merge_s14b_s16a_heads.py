"""merge s14b approval-routing and s16a agreement-tracking heads

s14b's 20260925_0036_approval_routing and s16a's
20260926_0037_agreement_tracking both descend from 20260924_0035_dc_settings
via different lines (s14b branched pre-S15, s16a on top of the S15
20260925_0036_extract_error revision). This revision closes the split so
`alembic upgrade head` resolves to a single tip on the integration branch.
"""

from __future__ import annotations

revision = "20260926_0038_merge_s14b_s16a"
down_revision = ("20260926_0037", "20260925_0036_approval_routing")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
