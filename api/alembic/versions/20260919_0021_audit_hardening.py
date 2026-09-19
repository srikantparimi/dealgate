"""S7 — DB-level audit hardening (grants + trigger).

Revision ID: 20260919_0021
Revises: 20260918_0020
Create Date: 2026-09-19

Blueprint §12: the application's Postgres role must not hold ``UPDATE``,
``DELETE`` or ``TRUNCATE`` on ``audit_event``. Sprint 1 shipped a length
CHECK on ``row_hash`` but left the real grant enforcement open (see
``docs/questions.md`` — "audit_event DB grants"). This migration closes
that gap on Postgres. On SQLite (the default test path) grants do not
exist, so this migration is a no-op — chain integrity is still exercised
by the application-level tests in ``test_audit.py``.

Belt + braces:

- ``REVOKE UPDATE, DELETE, TRUNCATE`` off the current role so the app
  role literally cannot issue those statements.
- Create a ``BEFORE UPDATE OR DELETE`` trigger that ``RAISE EXCEPTION``s.
  A future re-``GRANT`` (accidental or malicious) still hits the trigger,
  which cannot be bypassed without dropping it — and dropping a trigger
  is a schema change that shows up in ``pg_event_trigger`` audit tails.

Reversible: ``downgrade()`` drops the trigger + function and restores the
grants so the earlier schema behaviour is recoverable if we ever need to
roll this migration back.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260919_0021"
down_revision: str | Sequence[str] | None = "20260918_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Function + trigger name — kept as module constants so downgrade drops
# the exact same names upgrade created.
_TRIGGER_FN = "audit_event_no_update_delete"
_TRIGGER_NAME = "audit_event_no_update_delete_trg"


_CREATE_FN_SQL = f"""
CREATE OR REPLACE FUNCTION {_TRIGGER_FN}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_event is append-only (blueprint §12); % rejected', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;
"""

_CREATE_TRG_SQL = f"""
CREATE TRIGGER {_TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON audit_event
FOR EACH ROW EXECUTE FUNCTION {_TRIGGER_FN}();
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # SQLite (test path) has no grants and no trigger language we use
        # here. The app-level append_audit tests still verify chain
        # semantics; CI runs this migration against real Postgres.
        return

    # Grant hygiene: revoke first, then re-grant only what the app needs.
    # ``CURRENT_USER`` binds to whichever role runs the migration — in dev
    # that is ``dealgate_admin``; in prod the deploy pipeline is the app
    # role too. Blueprint §12 does not name the role, so keying off
    # CURRENT_USER keeps this migration portable across environments.
    op.execute(
        "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_event FROM CURRENT_USER"
    )
    op.execute("GRANT INSERT, SELECT ON TABLE audit_event TO CURRENT_USER")

    # Belt: trigger. Function is CREATE OR REPLACE so re-running is safe.
    op.execute(_CREATE_FN_SQL)
    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON audit_event")
    op.execute(_CREATE_TRG_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON audit_event")
    op.execute(f"DROP FUNCTION IF EXISTS {_TRIGGER_FN}()")
    # Restore prior grants so a rollback leaves the table usable.
    op.execute(
        "GRANT UPDATE, DELETE ON TABLE audit_event TO CURRENT_USER"
    )
