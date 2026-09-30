"""S19 slice 1: pipeline mirror + opportunity cache + next-action + sync-status + user-preference.

Adds the tables and columns the Pipeline page reads directly. See
``docs/directives/s19-checklist.md`` sections A1–A8 for the contract.

New tables
----------
- ``hubspot_pipeline`` — one row per HubSpot pipeline (id, label, order).
- ``hubspot_stage`` — one row per stage inside a pipeline; is_closed flag
  drives the closed-won / closed-lost derivation on ``opportunity``.
- ``next_action`` — one row per outstanding next-step per opportunity;
  data model in slice 1, UI in slice 2.
- ``sync_status`` — one row per sync source (backfill / webhook /
  reconcile) with last-success + last-error + lag metrics.
- ``user_preference`` — key/value store for per-user UI state; used by
  the Pipeline view toggle in slice 1.

Opportunity additions
---------------------
- HubSpot mirror keys: ``hubspot_pipeline_id``, ``hubspot_stage_id``,
  ``stage_order`` — resolved via the mirror on every intake write.
- Closed-flags: ``is_closed_won``, ``is_closed_lost`` — derived from
  ``hubspot_stage.metadata.isClosed`` + display order.
- ``currency`` — deal_currency_code (per-deal in HubSpot).
- HubSpot timestamps: ``hubspot_created_at``,
  ``hubspot_last_activity_at``, ``hubspot_last_modified_at``.
- ``primary_client_id`` — the labeled association's DealGate client;
  ``client_id`` stays as the working "current" client for backwards
  compatibility with existing joins.
- ``hubspot_secondary_client_ids`` (JSONB) — list of secondary
  association DealGate client ids for multi-company deals (E3
  supporting data; UI shows "+N others").

Indexes match the S19 checklist A4.

Reversible: downgrade drops the tables and columns in reverse order.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_0041_s19_pipeline"
down_revision = "20260928_0040_hs_cache"
branch_labels = None
depends_on = None


def _jsonb():
    """Postgres JSONB in production, generic JSON in SQLite tests."""

    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.create_table(
        "hubspot_pipeline",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "hubspot_stage",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "pipeline_id",
            sa.String(32),
            sa.ForeignKey("hubspot_pipeline.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("probability", sa.Numeric(3, 2), nullable=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_hubspot_stage_pipeline_order",
        "hubspot_stage",
        ["pipeline_id", "display_order"],
    )

    op.create_table(
        "next_action",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("description", sa.String(1024), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            sa.CheckConstraint(
                "status IN ('open','in_progress','blocked','complete')",
                name="ck_next_action_status",
            ),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("user.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_next_action_opportunity_status", "next_action", ["opportunity_id", "status"]
    )
    op.create_index(
        "ix_next_action_owner_due", "next_action", ["owner_user_id", "due_date"]
    )

    op.create_table(
        "sync_status",
        sa.Column("source", sa.String(64), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(1024), nullable=True),
        sa.Column("lag_seconds", sa.Integer(), nullable=True),
        sa.Column("cursor", sa.String(255), nullable=True),
    )

    op.create_table(
        "user_preference",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", _jsonb(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_user_preference"),
    )

    # ---- Opportunity additions ---------------------------------------------
    if dialect == "sqlite":
        with op.batch_alter_table("opportunity") as batch:
            batch.add_column(sa.Column("hubspot_pipeline_id", sa.String(32), nullable=True))
            batch.add_column(sa.Column("hubspot_stage_id", sa.String(32), nullable=True))
            batch.add_column(sa.Column("stage_order", sa.Integer(), nullable=True))
            batch.add_column(
                sa.Column("is_closed_won", sa.Boolean(), nullable=False, server_default=sa.false())
            )
            batch.add_column(
                sa.Column("is_closed_lost", sa.Boolean(), nullable=False, server_default=sa.false())
            )
            batch.add_column(sa.Column("currency", sa.String(8), nullable=True))
            batch.add_column(
                sa.Column("hubspot_created_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch.add_column(
                sa.Column("hubspot_last_activity_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch.add_column(
                sa.Column("hubspot_last_modified_at", sa.DateTime(timezone=True), nullable=True)
            )
            batch.add_column(
                sa.Column(
                    "primary_client_id",
                    sa.Uuid(),
                    sa.ForeignKey("client.id"),
                    nullable=True,
                )
            )
            batch.add_column(
                sa.Column("hubspot_secondary_client_ids", _jsonb(), nullable=True)
            )
    else:
        op.add_column(
            "opportunity", sa.Column("hubspot_pipeline_id", sa.String(32), nullable=True)
        )
        op.add_column(
            "opportunity", sa.Column("hubspot_stage_id", sa.String(32), nullable=True)
        )
        op.add_column("opportunity", sa.Column("stage_order", sa.Integer(), nullable=True))
        op.add_column(
            "opportunity",
            sa.Column("is_closed_won", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column(
            "opportunity",
            sa.Column("is_closed_lost", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.add_column("opportunity", sa.Column("currency", sa.String(8), nullable=True))
        op.add_column(
            "opportunity",
            sa.Column("hubspot_created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "opportunity",
            sa.Column("hubspot_last_activity_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "opportunity",
            sa.Column("hubspot_last_modified_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(
            "opportunity",
            sa.Column(
                "primary_client_id",
                sa.Uuid(),
                sa.ForeignKey("client.id"),
                nullable=True,
            ),
        )
        op.add_column(
            "opportunity",
            sa.Column("hubspot_secondary_client_ids", _jsonb(), nullable=True),
        )

    op.create_index(
        "ix_opportunity_pipeline_stage",
        "opportunity",
        ["hubspot_pipeline_id", "hubspot_stage_id"],
    )
    op.create_index("ix_opportunity_owner_id", "opportunity", ["owner_id"])
    op.create_index(
        "ix_opportunity_last_activity", "opportunity", ["hubspot_last_activity_at"]
    )
    op.create_index("ix_opportunity_close_date", "opportunity", ["close_date"])
    op.create_index(
        "ix_opportunity_primary_client", "opportunity", ["primary_client_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_opportunity_primary_client", table_name="opportunity")
    op.drop_index("ix_opportunity_close_date", table_name="opportunity")
    op.drop_index("ix_opportunity_last_activity", table_name="opportunity")
    op.drop_index("ix_opportunity_owner_id", table_name="opportunity")
    op.drop_index("ix_opportunity_pipeline_stage", table_name="opportunity")

    if dialect == "sqlite":
        with op.batch_alter_table("opportunity") as batch:
            batch.drop_column("hubspot_secondary_client_ids")
            batch.drop_column("primary_client_id")
            batch.drop_column("hubspot_last_modified_at")
            batch.drop_column("hubspot_last_activity_at")
            batch.drop_column("hubspot_created_at")
            batch.drop_column("currency")
            batch.drop_column("is_closed_lost")
            batch.drop_column("is_closed_won")
            batch.drop_column("stage_order")
            batch.drop_column("hubspot_stage_id")
            batch.drop_column("hubspot_pipeline_id")
    else:
        op.drop_column("opportunity", "hubspot_secondary_client_ids")
        op.drop_column("opportunity", "primary_client_id")
        op.drop_column("opportunity", "hubspot_last_modified_at")
        op.drop_column("opportunity", "hubspot_last_activity_at")
        op.drop_column("opportunity", "hubspot_created_at")
        op.drop_column("opportunity", "currency")
        op.drop_column("opportunity", "is_closed_lost")
        op.drop_column("opportunity", "is_closed_won")
        op.drop_column("opportunity", "stage_order")
        op.drop_column("opportunity", "hubspot_stage_id")
        op.drop_column("opportunity", "hubspot_pipeline_id")

    op.drop_table("user_preference")
    op.drop_table("sync_status")
    op.drop_index("ix_next_action_owner_due", table_name="next_action")
    op.drop_index("ix_next_action_opportunity_status", table_name="next_action")
    op.drop_table("next_action")
    op.drop_index("ix_hubspot_stage_pipeline_order", table_name="hubspot_stage")
    op.drop_table("hubspot_stage")
    op.drop_table("hubspot_pipeline")
