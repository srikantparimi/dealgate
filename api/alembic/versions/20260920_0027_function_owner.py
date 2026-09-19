"""S9 wave 1 — function_owner table for approver routing.

Revision ID: 20260920_0027
Revises: 20260919_0025
Create Date: 2026-09-20

Simple map: which user is the accountable owner for each function
(Delivery / HR / Finance / Legal) inside a business unit. Falls back to
the first member of the corresponding Cognito group when nothing is
configured (see :func:`app.services.approvers.resolve`).

Rows are immutable in spirit (rule 4) — SystemAdmin adds a new row to
change the owner. There is no UNIQUE across (function, business_unit)
so overlapping rows can coexist; the resolver picks ``is_default=true``
first, then most-recently-created.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260920_0027"
down_revision: str | Sequence[str] | None = "20260920_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "function_owner" in inspector.get_table_names():
        return
    op.create_table(
        "function_owner",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("function", sa.String(length=32), nullable=False),
        sa.Column("business_unit", sa.String(length=64), nullable=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", name="fk_function_owner_user_id"),
            nullable=False,
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1")
            if bind.dialect.name == "sqlite"
            else sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "function IN ('delivery', 'hr', 'finance', 'legal')",
            name="ck_function_owner_function",
        ),
    )
    op.create_index(
        "ix_function_owner_function",
        "function_owner",
        ["function", "business_unit"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "function_owner" in inspector.get_table_names():
        op.drop_index("ix_function_owner_function", table_name="function_owner")
        op.drop_table("function_owner")
