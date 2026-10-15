"""S23-PL2 — remember which Cognito login a DealGate user row belongs to.

A user first created by HubSpot intake or by an admin invite has a DealGate id
that is not their Cognito ``sub``, and the access token the web app sends
carries no email. Writes already find such a row by asking Cognito for the
email (``ensure_user``); reads must find the same row without asking Cognito
on every request. ``ensure_user`` now stores the ``sub`` on the row it adopts,
and reads match on it. One login per row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Alembic's version_num column is VARCHAR(32); keep revision <= 32 chars.
revision = "20261014_0071_cognito_sub"
down_revision = "20261014_0070_pl2_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("cognito_sub", sa.String(length=64), nullable=True))
    op.create_index(
        "ux_user_cognito_sub",
        "user",
        ["cognito_sub"],
        unique=True,
        postgresql_where=sa.text("cognito_sub IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_user_cognito_sub", table_name="user")
    op.drop_column("user", "cognito_sub")
