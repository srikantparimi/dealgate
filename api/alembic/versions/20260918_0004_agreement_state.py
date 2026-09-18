"""S2-E3: agreement state machine + evidence key columns.

Extends the `agreement` table with the columns needed for the Legal NDA/MSA
lifecycle (build-guide §6.2):

- `state` (VARCHAR NOT NULL, default `missing`) with a CHECK constraint
  restricting it to the 10 documented states.
- `owner_email`, `next_action`, `due_date` — Legal's working columns.
- `effective_from`, `expiry`, `notice_days` — the dates the alert scheduler
  reads for the 60-day expiry warning (Agent N's story).
- `evidence_s3_key` — pointer to the uploaded signed file in the
  `officeapp-dev-agreements-{account_id}` S3 bucket. NULL until upload.
- `signatories` (JSONB) — free-form list of `{name, email, role}` dicts.

Existing S1 rows keep their `kind` / `effective_date` / `expiry_date`
values; the two "*_date" columns are left in place so any older code still
reads / writes them. The new `effective_from` / `expiry` columns are the
S2 canonical names.

Reversible: `downgrade()` drops the CHECK constraint (SQLite via batch)
and every new column in reverse order.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260918_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Kept in lock-step with `app.services.agreement_state.ALLOWED_STATES`.
_STATES: tuple[str, ...] = (
    "missing",
    "requested",
    "drafting",
    "under_review",
    "sent",
    "partially_signed",
    "executed",
    "expired",
    "terminated",
    "superseded",
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return JSONB()
    return sa.JSON()


def _state_check_expr() -> str:
    quoted = ", ".join(f"'{s}'" for s in _STATES)
    return f"state IN ({quoted})"


def upgrade() -> None:
    with op.batch_alter_table("agreement") as batch:
        batch.add_column(
            sa.Column(
                "state",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'missing'"),
            )
        )
        batch.add_column(sa.Column("owner_email", sa.String(length=320), nullable=True))
        batch.add_column(sa.Column("next_action", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("due_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("effective_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("expiry", sa.Date(), nullable=True))
        batch.add_column(sa.Column("notice_days", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evidence_s3_key", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("signatories", _json_type(), nullable=True))
        batch.create_check_constraint(
            "ck_agreement_state_allowed",
            _state_check_expr(),
        )

    op.create_index(
        "ix_agreement_legal_entity_state",
        "agreement",
        ["legal_entity_id", "state"],
    )
    op.create_index(
        "ix_agreement_expiry",
        "agreement",
        ["expiry"],
    )


def downgrade() -> None:
    op.drop_index("ix_agreement_expiry", table_name="agreement")
    op.drop_index("ix_agreement_legal_entity_state", table_name="agreement")
    with op.batch_alter_table("agreement") as batch:
        batch.drop_constraint("ck_agreement_state_allowed", type_="check")
        batch.drop_column("signatories")
        batch.drop_column("evidence_s3_key")
        batch.drop_column("notice_days")
        batch.drop_column("expiry")
        batch.drop_column("effective_from")
        batch.drop_column("due_date")
        batch.drop_column("next_action")
        batch.drop_column("owner_email")
        batch.drop_column("state")
