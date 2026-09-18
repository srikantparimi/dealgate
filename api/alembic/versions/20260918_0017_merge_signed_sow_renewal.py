"""Merge signed_sow (0015, Agent X2) + renewal_indexes (0016, Agent Y2).

Revision ID: 20260918_0017
Revises: 20260918_0015, 20260918_0016
Create Date: 2026-09-18

Two Sprint 5 migrations branched off 0014 in parallel:

- ``0015`` — signed_sow_upload + renewal (Agent X2).
- ``0016`` — renewal indexes + fallback renewal table (Agent Y2).

Both are idempotent with respect to the ``renewal`` table (X2 guards its
create, Y2 guards its create + indexes). This revision collapses them
into a single head so ``alembic upgrade head`` stays deterministic.
No schema changes.
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260918_0017"
down_revision: str | Sequence[str] | None = (
    "20260918_0015",
    "20260918_0016",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
