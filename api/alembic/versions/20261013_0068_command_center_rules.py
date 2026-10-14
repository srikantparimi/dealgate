"""Command Center renewal evidence and billing-loss policy.

Renewals remain unassessed until a user explicitly records likelihood and a
proposal basis.  The billing-loss threshold is a USD amount per engagement in
the latest closed actual month; NULL means alerts are not configured.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# Alembic's version_num column is VARCHAR(32); keep revision <= 32 chars.
revision = "20261013_0068_cc_rules"
down_revision = "20261013_0067_import_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("forecast_policy") as batch:
        batch.add_column(
            sa.Column("billing_loss_threshold_amount", sa.Numeric(38, 18), nullable=True)
        )
        batch.add_column(sa.Column("renewal_likely_probability", sa.Numeric(38, 18), nullable=True))
        batch.add_column(
            sa.Column("renewal_unlikely_probability", sa.Numeric(38, 18), nullable=True)
        )
    with op.batch_alter_table("renewal") as batch:
        batch.add_column(
            sa.Column(
                "likelihood", sa.String(length=16), nullable=False, server_default="unassessed"
            )
        )
        batch.add_column(sa.Column("proposed_amount", sa.Numeric(38, 18), nullable=True))
        batch.add_column(sa.Column("currency", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("proposed_start", sa.Date(), nullable=True))
        batch.add_column(sa.Column("proposed_end", sa.Date(), nullable=True))
        batch.add_column(sa.Column("probability", sa.Numeric(38, 18), nullable=True))
        batch.add_column(sa.Column("probability_basis", sa.Text(), nullable=True))
        batch.create_check_constraint(
            op.f("ck_renewal_likelihood"),
            "likelihood IN ('likely','unlikely','unassessed')",
        )


def downgrade() -> None:
    with op.batch_alter_table("renewal") as batch:
        batch.drop_constraint(op.f("ck_renewal_likelihood"), type_="check")
        batch.drop_column("probability_basis")
        batch.drop_column("probability")
        batch.drop_column("proposed_end")
        batch.drop_column("proposed_start")
        batch.drop_column("currency")
        batch.drop_column("proposed_amount")
        batch.drop_column("likelihood")
    with op.batch_alter_table("forecast_policy") as batch:
        batch.drop_column("renewal_unlikely_probability")
        batch.drop_column("renewal_likely_probability")
        batch.drop_column("billing_loss_threshold_amount")
