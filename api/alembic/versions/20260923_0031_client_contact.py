"""S11 — client_contact for the signatories picker.

Backs the Confirm-screen signatories dropdown so a "needs you" row is a real
input, not a label. Contacts persist per client so the reviewer picks them
again next time rather than re-typing every SOW.

Revision ID: 20260923_0031
Revises: 20260922_0030
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260923_0031"
down_revision = "20260922_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "client_contact" in set(inspector.get_table_names()):
        return
    op.create_table(
        "client_contact",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Uuid(),
            sa.ForeignKey("client.id", name="fk_client_contact_client_id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_client_contact_created_by"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "client_id", "email", name="uq_client_contact_client_email"
        ),
    )
    op.create_index(
        "ix_client_contact_client_id", "client_contact", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_client_contact_client_id", table_name="client_contact")
    op.drop_table("client_contact")
