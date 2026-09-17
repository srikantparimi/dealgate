"""initial schema — user, client/legal_entity/agreement, opportunity, task,
integration_event, audit_event

Revision ID: 20260917_0001
Revises:
Create Date: 2026-09-17

Notes for the DB admin (blueprint §12): the application role must be granted
only SELECT + INSERT on `audit_event`. No UPDATE, no DELETE, no TRUNCATE. The
grant is set in infra (CDK/psql), not here — see the CHECK on `row_hash` as an
in-DB sanity guard.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260917_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    # JSONB on Postgres, JSON on SQLite/others — matches app.db.base.JsonB.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("groups", _json_type(), nullable=False),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("email", name="uq_user_email"),
    )

    op.create_table(
        "client",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
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
    )

    op.create_table(
        "legal_entity",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
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
    )

    op.create_table(
        "agreement",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "legal_entity_id", sa.Uuid(), sa.ForeignKey("legal_entity.id"), nullable=False
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
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
    )

    op.create_table(
        "opportunity",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("hubspot_deal_id", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("engagement_type", sa.String(length=64), nullable=True),
        sa.Column("sales_stage", sa.String(length=64), nullable=True),
        sa.Column(
            "governance_status",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'Intake'"),
        ),
        sa.Column("next_client_action", sa.String(length=255), nullable=True),
        sa.Column("next_client_date", sa.Date(), nullable=True),
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
        sa.UniqueConstraint("hubspot_deal_id", name="uq_opportunity_hubspot_deal_id"),
    )

    op.create_table(
        "task",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "escalation_level",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status", sa.String(length=32), nullable=False, server_default=sa.text("'Open'")
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
    )

    op.create_table(
        "integration_event",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_event_id", sa.String(length=128), nullable=False),
        sa.Column("payload", _json_type(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_event_id", name="uq_integration_event_source_event_id"),
    )

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("before", _json_type(), nullable=True),
        sa.Column("after", _json_type(), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=True),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "length(row_hash) = 64", name="ck_audit_event_row_hash_len"
        ),
    )
    op.create_index("ix_audit_event_ts", "audit_event", ["ts"])
    op.create_index(
        "ix_audit_event_entity", "audit_event", ["entity", "entity_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_event_entity", table_name="audit_event")
    op.drop_index("ix_audit_event_ts", table_name="audit_event")
    op.drop_table("audit_event")
    op.drop_table("integration_event")
    op.drop_table("task")
    op.drop_table("opportunity")
    op.drop_table("agreement")
    op.drop_table("legal_entity")
    op.drop_table("client")
    op.drop_table("user")
