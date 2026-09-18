"""Merge S6 forecast (0018, Agent AA) + actuals (0019, sibling).

Revision ID: 20260918_0020
Revises: 20260918_0018, 20260918_0019
Create Date: 2026-09-18

Two Sprint 6 migrations branched off 0017 in parallel:

- ``0018`` — forecast_period (weekly Delivery-lead forecast, Agent AA).
- ``0019`` — actuals CSV import (actual_period + actual_import_batch).

Both add independent tables. This revision collapses them into a single
head so ``alembic upgrade head`` stays deterministic. No schema changes.
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260918_0020"
down_revision: str | Sequence[str] | None = (
    "20260918_0018",
    "20260918_0019",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
