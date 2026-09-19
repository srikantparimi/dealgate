"""S7 wave 2 — merge pgvector + capability with WBS branches.

Revision ID: 20260919_0025
Revises: 20260919_0023, 20260919_0024
Create Date: 2026-09-19

Sprint 7 wave 2 lands three parallel stories on top of the same base
(``20260919_0021``): adviser research + retrieved columns (0022 -> 0023)
and WBS/templates (0024). This is a no-op merge so ``alembic heads``
collapses to a single head again.
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260919_0025"
down_revision: str | Sequence[str] | None = ("20260919_0023", "20260919_0024")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No schema change — this only reconciles multiple heads."""


def downgrade() -> None:
    """No schema change — this only reconciles multiple heads."""
