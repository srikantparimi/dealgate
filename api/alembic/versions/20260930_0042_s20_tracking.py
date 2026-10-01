"""S20 · W6 · tracking features: structured next-action + comments + groups + saved views.

Adds all tables/columns owned by W6. See ``docs/directives/s20-overnight.md``
§2 W6 and ``docs/reports/s20/contracts.md`` §6.

All changes are backward-compatible (D5):

- ``next_action`` gets ``title``, ``assignee_user_id``, ``blocker``,
  ``outcome``, ``approval_package_id``, ``updated_at`` — all nullable
  (or with a default). S19-seeded rows keep ``description`` +
  ``owner_user_id``; the S20 service mirrors ``title`` into
  ``description`` on create and reads ``assignee_user_id`` first,
  ``owner_user_id`` second.
- ``next_action_event`` — new table, append-only history.
- ``deal_comment`` — new table.
- ``tracking_group`` + ``tracking_group_member`` — new tables.
- ``saved_view`` — new table.

Reversible: downgrade drops the added columns/tables in reverse order.
The Lead-owned migration numbering is off ``20260929_0041_s19_pipeline``.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260930_0042_s20_tracking"
down_revision = "20260929_0041_s19_pipeline"
branch_labels = None
depends_on = None


def _jsonb():
    """Postgres JSONB in production, generic JSON in SQLite tests."""

    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---- next_action additions --------------------------------------------
    if dialect == "sqlite":
        with op.batch_alter_table("next_action") as batch:
            batch.add_column(sa.Column("title", sa.String(255), nullable=True))
            batch.add_column(
                sa.Column(
                    "assignee_user_id",
                    sa.Uuid(),
                    sa.ForeignKey("user.id"),
                    nullable=True,
                )
            )
            batch.add_column(sa.Column("blocker", sa.Text(), nullable=True))
            batch.add_column(sa.Column("outcome", sa.Text(), nullable=True))
            batch.add_column(
                sa.Column(
                    "approval_package_id",
                    sa.Uuid(),
                    sa.ForeignKey("approval_package.id", ondelete="SET NULL"),
                    nullable=True,
                )
            )
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    server_default=sa.func.now(),
                    nullable=False,
                )
            )
    else:
        op.add_column(
            "next_action", sa.Column("title", sa.String(255), nullable=True)
        )
        op.add_column(
            "next_action",
            sa.Column(
                "assignee_user_id",
                sa.Uuid(),
                sa.ForeignKey("user.id"),
                nullable=True,
            ),
        )
        op.add_column("next_action", sa.Column("blocker", sa.Text(), nullable=True))
        op.add_column("next_action", sa.Column("outcome", sa.Text(), nullable=True))
        op.add_column(
            "next_action",
            sa.Column(
                "approval_package_id",
                sa.Uuid(),
                sa.ForeignKey("approval_package.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.add_column(
            "next_action",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    op.create_index(
        "ix_next_action_assignee_due",
        "next_action",
        ["assignee_user_id", "due_date"],
    )
    op.create_index(
        "ix_next_action_approval_package",
        "next_action",
        ["approval_package_id"],
    )

    # ---- next_action_event (append-only history) --------------------------
    op.create_table(
        "next_action_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "next_action_id",
            sa.Uuid(),
            sa.ForeignKey("next_action.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(16), nullable=True),
        sa.Column("to_status", sa.String(16), nullable=True),
        sa.Column("before", _jsonb(), nullable=True),
        sa.Column("after", _jsonb(), nullable=True),
        sa.Column("note", sa.String(1024), nullable=True),
    )
    op.create_index(
        "ix_next_action_event_action_ts", "next_action_event", ["next_action_id", "ts"]
    )

    # ---- deal_comment ------------------------------------------------------
    op.create_table(
        "deal_comment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column("author_name_fallback", sa.String(255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "source",
            sa.String(16),
            sa.CheckConstraint(
                "source IN ('internal','hubspot_note')",
                name="ck_deal_comment_source",
            ),
            nullable=False,
            server_default="internal",
        ),
        sa.Column("hubspot_note_id", sa.String(64), nullable=True, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "deleted_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True
        ),
    )
    op.create_index(
        "ix_deal_comment_opportunity_created",
        "deal_comment",
        ["opportunity_id", "created_at"],
    )
    op.create_index(
        "ix_deal_comment_pinned", "deal_comment", ["opportunity_id", "pinned"]
    )
    op.create_index(
        "ix_deal_comment_hubspot_note", "deal_comment", ["hubspot_note_id"]
    )

    # ---- tracking_group ---------------------------------------------------
    op.create_table(
        "tracking_group",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "visibility",
            sa.String(16),
            sa.CheckConstraint(
                "visibility IN ('private','team')",
                name="ck_tracking_group_visibility",
            ),
            nullable=False,
            server_default="private",
        ),
        sa.Column(
            "member_kind",
            sa.String(16),
            sa.CheckConstraint(
                "member_kind IN ('client','opportunity')",
                name="ck_tracking_group_member_kind",
            ),
            nullable=False,
        ),
        sa.Column("filter_json", _jsonb(), nullable=True),
        sa.Column(
            "include_future_deals",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tracking_group_owner", "tracking_group", ["owner_id"])
    op.create_index(
        "ix_tracking_group_visibility", "tracking_group", ["visibility"]
    )

    # ---- tracking_group_member (manual membership) ------------------------
    op.create_table(
        "tracking_group_member",
        sa.Column(
            "group_id",
            sa.Uuid(),
            sa.ForeignKey("tracking_group.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "group_id", "member_id", name="pk_tracking_group_member"
        ),
    )
    op.create_index(
        "ix_tracking_group_member_group", "tracking_group_member", ["group_id"]
    )
    op.create_index(
        "ix_tracking_group_member_member", "tracking_group_member", ["member_id"]
    )

    # ---- saved_view -------------------------------------------------------
    op.create_table(
        "saved_view",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False
        ),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filter_json", _jsonb(), nullable=False),
        sa.Column("sort_json", _jsonb(), nullable=True),
        sa.Column(
            "visibility",
            sa.String(16),
            sa.CheckConstraint(
                "visibility IN ('private','team')",
                name="ck_saved_view_visibility",
            ),
            nullable=False,
            server_default="private",
        ),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "owner_id", "key", "is_builtin",
            name="uq_saved_view_owner_key_builtin",
        ),
    )
    op.create_index("ix_saved_view_owner", "saved_view", ["owner_id"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.drop_index("ix_saved_view_owner", table_name="saved_view")
    op.drop_table("saved_view")

    op.drop_index(
        "ix_tracking_group_member_member", table_name="tracking_group_member"
    )
    op.drop_index(
        "ix_tracking_group_member_group", table_name="tracking_group_member"
    )
    op.drop_table("tracking_group_member")

    op.drop_index("ix_tracking_group_visibility", table_name="tracking_group")
    op.drop_index("ix_tracking_group_owner", table_name="tracking_group")
    op.drop_table("tracking_group")

    op.drop_index("ix_deal_comment_hubspot_note", table_name="deal_comment")
    op.drop_index("ix_deal_comment_pinned", table_name="deal_comment")
    op.drop_index(
        "ix_deal_comment_opportunity_created", table_name="deal_comment"
    )
    op.drop_table("deal_comment")

    op.drop_index(
        "ix_next_action_event_action_ts", table_name="next_action_event"
    )
    op.drop_table("next_action_event")

    op.drop_index(
        "ix_next_action_approval_package", table_name="next_action"
    )
    op.drop_index("ix_next_action_assignee_due", table_name="next_action")

    if dialect == "sqlite":
        with op.batch_alter_table("next_action") as batch:
            batch.drop_column("updated_at")
            batch.drop_column("approval_package_id")
            batch.drop_column("outcome")
            batch.drop_column("blocker")
            batch.drop_column("assignee_user_id")
            batch.drop_column("title")
    else:
        op.drop_column("next_action", "updated_at")
        op.drop_column("next_action", "approval_package_id")
        op.drop_column("next_action", "outcome")
        op.drop_column("next_action", "blocker")
        op.drop_column("next_action", "assignee_user_id")
        op.drop_column("next_action", "title")
