"""One server-persisted Staffing & GM working draft per opportunity.

S22 click-through root cause: the commercial plan lived only in browser
memory, so a reload lost it and the Confirm page could not see it. The
draft is mutable working state (NOT an immutable GM version — rule 4
versions are untouched) shared by every surface.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261006_0064_commercial_draft"
down_revision = "20261003_0063_agreement_versions"
branch_labels = None
depends_on = None


def _json_type() -> sa.types.TypeEngine:
    # JSONB on Postgres, JSON on SQLite/others — matches app.db.base.JsonB.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def upgrade():
    op.create_table(
        "commercial_draft",
        sa.Column(
            "opportunity_id",
            sa.Uuid(),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("sow_version_id", sa.Uuid(), nullable=True),
        sa.Column("inputs", _json_type(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade():
    # Drafts are working state, not governed records — reversible.
    op.drop_table("commercial_draft")
