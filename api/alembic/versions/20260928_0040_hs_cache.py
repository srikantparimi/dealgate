"""S18 §2: cache HubSpot deal metadata on opportunity for Pipeline reads.

The Pipeline page needs amount, close_date, stage_label and a "last synced"
timestamp for every HubSpot-sourced deal without a per-row HubSpot round
trip. These four columns are cached on ``opportunity`` and populated by
``services.hubspot_intake`` during backfill, webhook processing and the
nightly reconcile.

All four are nullable. SOW-upload opportunities (source='sow_upload') leave
them null; the shared query service filters on ``source='hubspot'``.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260928_0040_hs_cache"
down_revision = "20260928_0039_s17_simplify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("opportunity") as batch:
            batch.add_column(sa.Column("amount", sa.Numeric(14, 2), nullable=True))
            batch.add_column(sa.Column("close_date", sa.Date(), nullable=True))
            batch.add_column(sa.Column("stage_label", sa.String(64), nullable=True))
            batch.add_column(
                sa.Column("hubspot_last_seen_at", sa.DateTime(timezone=True), nullable=True)
            )
    else:
        op.add_column("opportunity", sa.Column("amount", sa.Numeric(14, 2), nullable=True))
        op.add_column("opportunity", sa.Column("close_date", sa.Date(), nullable=True))
        op.add_column("opportunity", sa.Column("stage_label", sa.String(64), nullable=True))
        op.add_column(
            "opportunity",
            sa.Column("hubspot_last_seen_at", sa.DateTime(timezone=True), nullable=True),
        )

    op.create_index(
        "ix_opportunity_source_archived",
        "opportunity",
        ["source", "archived_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_opportunity_source_archived", table_name="opportunity")

    if dialect == "sqlite":
        with op.batch_alter_table("opportunity") as batch:
            batch.drop_column("hubspot_last_seen_at")
            batch.drop_column("stage_label")
            batch.drop_column("close_date")
            batch.drop_column("amount")
    else:
        op.drop_column("opportunity", "hubspot_last_seen_at")
        op.drop_column("opportunity", "stage_label")
        op.drop_column("opportunity", "close_date")
        op.drop_column("opportunity", "amount")
