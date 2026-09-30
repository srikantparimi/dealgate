"""S20 W1 · hubspot_owner + hubspot_property_mapping tables.

W1 landed the model classes (`services/hubspot_owners.py::HubspotOwner`,
`services/hubspot_properties.py::HubspotPropertyMapping`) but their
alembic revisions were owed to the Lead per contracts.md §7. This
revision materialises both tables on Postgres so:

- D2 owner-mirror sync (active + archived owners from
  ``/crm/v3/owners``) has a place to write.
- D10 Business Unit discovery persists its mapping row instead of
  re-fetching properties every request.

Both tables are new (no data migration). Every column matches the
model declaration exactly so `Base.metadata.create_all` (used by the
SQLite test path) and this migration (used by Postgres staging) agree.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


# Alembic's version_num column is VARCHAR(32); keep revision <=32 chars.
revision: str = "20260930_0045_w1_own"
down_revision: str | Sequence[str] | None = "20260930_0044_s20_lead_d1_d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hubspot_owner",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=True),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column(
            "archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("hubspot_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hubspot_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_hubspot_owner_email",
        "hubspot_owner",
        ["email"],
        unique=False,
    )

    op.create_table(
        "hubspot_property_mapping",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("internal_name", sa.String(128), nullable=False),
        sa.Column("object_type", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("field_type", sa.String(32), nullable=False),
        sa.Column("options", JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("hubspot_property_mapping")
    op.drop_index("ix_hubspot_owner_email", table_name="hubspot_owner")
    op.drop_table("hubspot_owner")
