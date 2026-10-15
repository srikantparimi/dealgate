"""S23-PL2 — the Pipeline workspace's own data.

1. ``user`` gains the link to a HubSpot owner (B4): ``hubspot_owner_id``, how it
   was decided (``email`` = automatic exact-email match, ``admin`` = override,
   including an override to no owner), and when. One DealGate user per owner.
2. ``hubspot_region_map`` maps a HubSpot region value to a business unit and the
   region shown beside it (B3), seeded with the four staging values. Deal rows
   join it at read time, so an edit takes effect with no resync.
3. Saved views (B11): the unique key on ``(owner_id, key, is_builtin)`` made a
   second custom view collide, because every custom view has ``key='custom'``.
   It becomes two partial indexes: built-ins stay unique per key, and a user's
   live custom views are unique by case-insensitive name.
4. Tracking groups (B11): live groups are unique per owner by case-insensitive
   name.

Downgrade restores the old saved-view constraint, unique over
``(owner_id, key, is_builtin)`` for every row, archived ones included, so it
allows one user-defined view per key and any user with two Pipeline views (or
one deleted and one live) would break it. The downgrade therefore first gives
every user-defined view a key of its own, ``<key>:<view id>``; built-ins keep
theirs. Nothing is deleted. After upgrading again, the Pipeline finds its views
by ``key='pipeline'``; restore the keys with
``UPDATE saved_view SET key = split_part(key, ':', 1) WHERE NOT is_builtin AND key LIKE '%:%'``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic's version_num column is VARCHAR(32); keep revision <= 32 chars.
revision = "20261014_0070_pl2_workspace"
down_revision = "20261014_0069_sync_run"
branch_labels = None
depends_on = None

REGION_SEED = (
    {"hubspot_value": "South Africa", "business_unit": "Retro Rabbit", "region": "South Africa", "note": None},
    {"hubspot_value": "US - IT Avalon (Staffing)", "business_unit": "IT Avalon", "region": "US", "note": "Staffing"},
    {"hubspot_value": "US - IT Avalon", "business_unit": "IT Avalon", "region": "US", "note": None},
    {"hubspot_value": "US", "business_unit": "ST21", "region": "US", "note": None},
)


def upgrade() -> None:
    op.add_column("user", sa.Column("hubspot_owner_id", sa.String(length=64), nullable=True))
    op.add_column("user", sa.Column("hubspot_owner_link", sa.String(length=8), nullable=True))
    op.add_column("user", sa.Column("hubspot_owner_linked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_user_hubspot_owner_link", "user", "hubspot_owner_link IN ('email','admin')"
    )
    op.create_index(
        "ux_user_hubspot_owner",
        "user",
        ["hubspot_owner_id"],
        unique=True,
        postgresql_where=sa.text("hubspot_owner_id IS NOT NULL"),
    )

    region_map = op.create_table(
        "hubspot_region_map",
        sa.Column("hubspot_value", sa.String(length=255), primary_key=True),
        sa.Column("business_unit", sa.String(length=32), nullable=False),
        sa.Column("region", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.CheckConstraint(
            "business_unit IN ('ST21','IT Avalon','Retro Rabbit')",
            name="ck_hubspot_region_map_business_unit",
        ),
    )
    op.bulk_insert(region_map, list(REGION_SEED))

    op.drop_constraint("uq_saved_view_owner_key_builtin", "saved_view", type_="unique")
    op.create_index(
        "ux_saved_view_builtin_key",
        "saved_view",
        ["owner_id", "key"],
        unique=True,
        postgresql_where=sa.text("is_builtin"),
    )
    op.create_index(
        "ux_saved_view_owner_name",
        "saved_view",
        [sa.text("owner_id"), sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL AND NOT is_builtin"),
    )
    op.create_index(
        "ux_tracking_group_owner_name",
        "tracking_group",
        [sa.text("owner_id"), sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_tracking_group_owner_name", table_name="tracking_group")
    op.drop_index("ux_saved_view_owner_name", table_name="saved_view")
    op.drop_index("ux_saved_view_builtin_key", table_name="saved_view")
    # One key per user-defined view, so the old constraint can be built (see the docstring);
    # 27 + 1 + 36 characters fit the column's 64.
    op.execute(sa.text(
        "UPDATE saved_view SET key = left(key, 27) || ':' || CAST(id AS VARCHAR) WHERE NOT is_builtin"
    ))
    op.create_unique_constraint(
        "uq_saved_view_owner_key_builtin", "saved_view", ["owner_id", "key", "is_builtin"]
    )
    op.drop_table("hubspot_region_map")
    op.drop_index("ux_user_hubspot_owner", table_name="user")
    op.drop_constraint("ck_user_hubspot_owner_link", "user", type_="check")
    op.drop_column("user", "hubspot_owner_linked_at")
    op.drop_column("user", "hubspot_owner_link")
    op.drop_column("user", "hubspot_owner_id")
