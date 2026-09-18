"""S2-E3: task lifecycle columns + notification outbox + settings.

Extends ``task`` with lifecycle metadata (status default -> ``assigned``,
``category``, ``wake_at``, ``completed_at``, ``completed_by``) and introduces
two new tables:

- ``notification`` — the transactional outbox drained by the alert worker.
- ``notification_setting`` — per user × category × channel opt-in flag.

Revision ID: 20260918_0003
Revises: 20260918_0002b
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0003"
down_revision: str | None = "20260918_0002b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- task extensions ------------------------------------------------
    # SQLite ALTER TABLE cannot change defaults inline; use batch mode so the
    # migration works on both SQLite (dev/tests) and Postgres (staging/prod).
    with op.batch_alter_table("task") as batch:
        batch.add_column(sa.Column("category", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_by", sa.Uuid(), nullable=True))
    # Flip the S1 default from 'Open' -> 'assigned' for freshly created rows.
    # Existing 'Open' rows are tolerated by the service (see TASK_TRANSITIONS).
    with op.batch_alter_table("task") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=32),
            server_default=sa.text("'assigned'"),
            existing_nullable=False,
        )

    # ---- notification (outbox) -----------------------------------------
    op.create_table(
        "notification",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_md", sa.String(length=4000), nullable=False),
        sa.Column("related_entity", sa.String(length=64), nullable=True),
        sa.Column("related_entity_id", sa.String(length=128), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notification_status_next_attempt",
        "notification",
        ["status", "next_attempt_at"],
    )
    op.create_index(
        "ix_notification_user_channel",
        "notification",
        ["user_id", "channel"],
    )

    # ---- notification_setting -----------------------------------------
    op.create_table(
        "notification_setting",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False
        ),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "category",
            "channel",
            name="uq_notification_setting_user_category_channel",
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_setting")
    op.drop_index("ix_notification_user_channel", table_name="notification")
    op.drop_index("ix_notification_status_next_attempt", table_name="notification")
    op.drop_table("notification")
    with op.batch_alter_table("task") as batch:
        batch.alter_column(
            "status",
            existing_type=sa.String(length=32),
            server_default=sa.text("'Open'"),
            existing_nullable=False,
        )
        batch.drop_column("completed_by")
        batch.drop_column("completed_at")
        batch.drop_column("wake_at")
        batch.drop_column("category")
