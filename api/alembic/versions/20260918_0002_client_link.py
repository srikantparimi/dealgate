"""S2-E3: opportunity->client link + client.hubspot_company_id unique.

Adds:
- ``client.hubspot_company_id`` (VARCHAR, UNIQUE, nullable) so the HubSpot
  intake worker can upsert a client by company id.
- ``client.timezone`` (VARCHAR nullable) — carried over from HubSpot.
- ``opportunity.client_id`` (UUID FK to ``client.id``, NULLABLE) — nullable
  during backfill; a follow-up migration will flip to NOT NULL after existing
  rows are linked from HubSpot associations. See docs/questions.md.

Reversible: `downgrade()` drops the FK, the columns, and the unique constraint.

Revision ID: 20260918_0002
Revises: 20260917_0001
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0002a"
down_revision: str | None = "20260917_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---- client.hubspot_company_id + client.timezone --------------------
    # SQLite ALTER TABLE cannot add a UNIQUE constraint inline; add the
    # column then a separate unique index for portability.
    with op.batch_alter_table("client") as batch:
        batch.add_column(sa.Column("hubspot_company_id", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("timezone", sa.String(length=64), nullable=True))
    op.create_index(
        "uq_client_hubspot_company_id",
        "client",
        ["hubspot_company_id"],
        unique=True,
    )

    # ---- opportunity.client_id (nullable FK) ---------------------------
    with op.batch_alter_table("opportunity") as batch:
        batch.add_column(sa.Column("client_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_opportunity_client_id",
            "client",
            ["client_id"],
            ["id"],
        )
    op.create_index("ix_opportunity_client_id", "opportunity", ["client_id"])

    # Backfill: nothing to do here. Existing dev opportunities keep
    # client_id NULL. The worker will populate on the next webhook and a
    # follow-up story adds a NOT NULL migration once every row is linked.
    _ = dialect  # kept for future dialect-specific tweaks; silences lint.


def downgrade() -> None:
    op.drop_index("ix_opportunity_client_id", table_name="opportunity")
    with op.batch_alter_table("opportunity") as batch:
        batch.drop_constraint("fk_opportunity_client_id", type_="foreignkey")
        batch.drop_column("client_id")

    op.drop_index("uq_client_hubspot_company_id", table_name="client")
    with op.batch_alter_table("client") as batch:
        batch.drop_column("timezone")
        batch.drop_column("hubspot_company_id")
