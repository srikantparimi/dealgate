"""S2-E3 Wave 2: ``scheduler_fired`` idempotency ledger.

The alert scheduler (`worker.alert_scheduler`) writes one row per (trigger,
entity, window) it has already processed. A UNIQUE constraint on
``trigger_key`` makes duplicate insertions fail loudly so the scheduler can
run every 5 minutes without duping tasks or notifications.

This is the only new schema Agent N introduces; all task + notification
writes flow through the existing services.

Revision ID: 20260918_0005
Revises: 20260918_0004
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0005"
down_revision: str | None = "20260918_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scheduler_fired",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        # Deterministic hash of (trigger, entity_id, window) — see
        # `worker.alert_scheduler._trigger_key`. Kept as opaque text so the
        # scheduler owns the format and the DB just enforces uniqueness.
        sa.Column("trigger_key", sa.String(length=256), nullable=False),
        # Human-readable classification so ops can see what fired.
        sa.Column("trigger_name", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("trigger_key", name="uq_scheduler_fired_trigger_key"),
    )
    op.create_index(
        "ix_scheduler_fired_entity",
        "scheduler_fired",
        ["entity", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduler_fired_entity", table_name="scheduler_fired")
    op.drop_table("scheduler_fired")
