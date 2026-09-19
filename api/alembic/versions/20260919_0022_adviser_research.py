"""S7 — Adviser: public research status column.

Wave 2 of Sprint 7 adds a real web-research pass (Tavily) before the LLM
proposes a team. When the research is unavailable the response carries
``research_status = "unavailable"`` so the UI can show the reader we
proceeded without public sources — Blueprint rule 6, never invent sources.

Persisting the flag alongside the row keeps the audit trail honest: a
reviewer opening an old estimate can see whether public research actually
happened at draft time.

Reversible: ``downgrade()`` drops the column. Existing rows keep NULL so
older estimates render as "unknown" (the UI treats NULL as pre-feature).

Revision ID: 20260919_0022
Revises: 20260919_0021
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0022"
down_revision: str | Sequence[str] | None = "20260919_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULLABLE by design: existing rows pre-date the research pass and must
    # keep their audit meaning. Both Postgres and SQLite handle a plain
    # nullable VARCHAR add without a table rewrite.
    op.add_column(
        "adviser_estimate",
        sa.Column("research_status", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    # SQLite < 3.35 could not drop columns, but the version alembic ships
    # against in this repo does — and Postgres has always supported it.
    with op.batch_alter_table("adviser_estimate") as batch:
        batch.drop_column("research_status")
