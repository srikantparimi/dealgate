"""merge approvals + ceo_exception + hubspot_writeback heads.

Revision ID: 20260918_0014
Revises: 20260918_0011, 20260918_0012, 20260918_0013
Create Date: 2026-09-18

Wave 3 landed three parallel migrations that all branch off ``0010``:

- ``0011`` — approval_package + approval (Agent U).
- ``0012`` — ceo_exception + ceo_delegate (Agent V).
- ``0013`` — hubspot_writeback_job (Agent H).

This merge collapses them back into a single head so ``alembic upgrade
head`` remains deterministic. No schema changes.
"""

from __future__ import annotations

from collections.abc import Sequence


revision: str = "20260918_0014"
down_revision: str | Sequence[str] | None = (
    "20260918_0011",
    "20260918_0012",
    "20260918_0013",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
