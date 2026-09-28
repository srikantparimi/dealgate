"""Exercise the additive migration in a disposable SQLite schema."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from app.models.agreement_tracking import AgreementDocument, AgreementGap


async def test_tracking_migration_up_down_up(session):
    spec = importlib.util.spec_from_file_location("s16_migration", Path(__file__).parents[1] / "alembic/versions/20260926_0037_agreement_tracking.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await session.connection()

    def exercise(conn):
        AgreementDocument.__table__.drop(conn)
        AgreementGap.__table__.drop(conn)
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        for model in (AgreementDocument, AgreementGap):
            columns = inspect(conn).get_columns(model.__tablename__)
            assert {c["name"] for c in columns} == set(model.__table__.columns.keys())
        migration.downgrade()
        assert "agreement_document" not in inspect(conn).get_table_names()
        migration.upgrade()

    await connection.run_sync(exercise)
