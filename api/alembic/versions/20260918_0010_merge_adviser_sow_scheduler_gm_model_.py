"""merge adviser + sow + scheduler + gm_model + legacy heads

Revision ID: 20260918_0010
Revises: 20260918_0005, 20260918_0007, 20260918_0008
Create Date: 2026-09-17 20:20:06.293661

The S6 legacy story (0009) landed on the sow branch and Agent R's Builder
migration (0007) now descends from 0009 — so listing 0007 pulls in the
0006 → 0009 → 0007 chain transitively. 0005 (scheduler) and 0008
(adviser) still need to be merged in explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '20260918_0010'
down_revision: str | None = ('20260918_0005', '20260918_0007', '20260918_0008')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
