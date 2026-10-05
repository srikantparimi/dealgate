"""0054 legacy-row upgrade and loss-refusing downgrade in owned scratch PG."""
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import app.db
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

url = os.environ["DEALGATE_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.hostname in {"127.0.0.1", "localhost"} and parsed.path == "/s21_schema"
assert url.startswith("postgresql+psycopg://")
root = Path(__file__).resolve().parents[1]
config = Config(str(root / "api/alembic.ini"))
config.set_main_option("script_location", str(root / "api/alembic"))
app.db.DATABASE_URL = url
engine = create_engine(url)
account_id = uuid.uuid4()
mapping_key = f"s21-migration-{uuid.uuid4().hex}"
try:
    command.downgrade(config, "20261002_0053_parent_deletion")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO client(id,name) VALUES (:id,'Synthetic migration retained client')"), {"id": account_id})
        conn.execute(text("INSERT INTO hubspot_property_mapping(key,internal_name,object_type,label,field_type,updated_at) "
            "VALUES (:key,'synthetic_bu','deal','Synthetic BU','enumeration',CURRENT_TIMESTAMP)"), {"key": mapping_key})
    command.upgrade(config, "20261002_0054_source_facts")
    with engine.begin() as conn:
        row = conn.execute(text("SELECT hubspot_owner_id,hubspot_owner_observed_at,business_unit_value,"
            "business_unit_mapping_version,business_unit_observed_at FROM client WHERE id=:id"), {"id": account_id}).one()
        assert all(value is None for value in row), row
        mapping = conn.execute(text("SELECT availability_state,mapping_version,last_success_at FROM hubspot_property_mapping WHERE key=:key"),
            {"key": mapping_key}).one()
        assert tuple(mapping) == ("unknown", 1, None), mapping
    command.downgrade(config, "20261002_0053_parent_deletion")
    command.upgrade(config, "20261002_0054_source_facts")
    with engine.begin() as conn:
        conn.execute(text("UPDATE client SET hubspot_owner_id='external-owner-no-local-user',hubspot_owner_observed_at=CURRENT_TIMESTAMP WHERE id=:id"),
            {"id": account_id})
    try:
        command.downgrade(config, "20261002_0053_parent_deletion")
    except RuntimeError as error:
        assert "Cannot discard CRM source observations" in str(error), error
    else:
        raise AssertionError("Downgrade silently discarded source observation")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT hubspot_owner_id FROM client WHERE id=:id"), {"id": account_id}).scalar_one() == "external-owner-no-local-user"
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "20261002_0054_source_facts"
        # Only this runner's synthetic observation is reset to exercise the separate mapping guard.
        conn.execute(text("UPDATE client SET hubspot_owner_id=NULL,hubspot_owner_observed_at=NULL WHERE id=:id"), {"id": account_id})
        conn.execute(text("UPDATE hubspot_property_mapping SET availability_state='unavailable',"
            "availability_reason='Synthetic permission failure',checked_at=CURRENT_TIMESTAMP WHERE key=:key"), {"key": mapping_key})
    try:
        command.downgrade(config, "20261002_0053_parent_deletion")
    except RuntimeError as error:
        assert "Cannot discard CRM mapping evidence" in str(error), error
    else:
        raise AssertionError("Downgrade silently discarded metadata availability")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT availability_state FROM hubspot_property_mapping WHERE key=:key"), {"key": mapping_key}).scalar_one() == "unavailable"
        conn.execute(text("DELETE FROM hubspot_property_mapping WHERE key=:key"), {"key": mapping_key})
        conn.execute(text("DELETE FROM client WHERE id=:id"), {"id": account_id})
    print(json.dumps({"migration": "0054", "legacy_defaults": "passed", "empty_roundtrip": "passed",
        "observation_loss_refused": True, "mapping_loss_refused": True, "shared_database_touched": False}))
finally:
    engine.dispose()
