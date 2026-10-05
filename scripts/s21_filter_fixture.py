"""Seed ONLY an empty, already-migrated private T09 database; emit literal oracles.

This is declared synthetic CRM mirror data, not HubSpot integration evidence.
The lead creates/migrates/removes the database and runs the real browser proof.
"""

import json
import os
from pathlib import Path
import re
import sys
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
OBSERVED = datetime(2026, 10, 2, 12, tzinfo=UTC)
PIPELINE = "synthetic-t09"
STAGES = ("synthetic-discovery", "synthetic-negotiation")
EMAIL = "s21-filter-admin@example.test"
GUARDED_TABLES = (
    "user", "client", "opportunity", "sow", "sow_version", "gm_model",
    "approval_package", "project", "forecast_plan", "task", "audit_event",
    "agreement", "saved_view", "tracking_group", "notification",
    "hubspot_pipeline", "hubspot_stage", "hubspot_owner", "hubspot_property_mapping",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    require(len(sys.argv) == 1, "No positional targets or destructive options accepted")
    require(os.environ.get("DEALGATE_ENV") == "local", "DEALGATE_ENV must explicitly be local")
    require(not any(key.startswith("PG") for key in os.environ),
            "Remove libpq PG* overrides before selecting this private database")
    raw = os.environ.get("S21_FILTER_DATABASE_URL")
    require(raw, "Set S21_FILTER_DATABASE_URL to the already-migrated private database")
    url = make_url(raw)
    require((url.drivername, url.username, url.host, url.port) ==
            ("postgresql+psycopg", "s21", "127.0.0.1", 55421)
            and not url.query and not url.password,
            "Require trust-only s21 at literal 127.0.0.1:55421 with psycopg and no URL options")
    name = url.database or ""
    require(re.fullmatch(r"s21_filter_[0-9a-f]{32}", name),
            "Refusing target: database must be s21_filter_<32 lowercase hex>")
    require(os.environ.get("DEALGATE_TENANT_ID") == name,
            "Tenant must exactly equal the private database name")
    require(not any(key == "app" or key.startswith("app.") for key in sys.modules),
            "Run standalone before application imports")
    local_url = url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    os.environ.update(POSTGRES_URL=local_url, DATABASE_URL=local_url,
                      AWS_EC2_METADATA_DISABLED="true", PYTHONDONTWRITEBYTECODE="1")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT / "api"))
    from app.models.client import Client
    from app.models.hubspot_pipeline import HubspotPipeline, HubspotStage
    from app.models.opportunity import Opportunity
    from app.models.saved_view import SavedView
    from app.models.user import User
    from app.services.hubspot_owners import HubspotOwner
    from app.services.hubspot_properties import HubspotPropertyMapping

    def identity(kind):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{name}:{kind}")

    actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"dealgate:local:{EMAIL}")
    owners = [identity("owner-a"), identity("owner-b")]
    owner_external = ["synthetic-owner-a", "synthetic-owner-b"]
    # Independent authored cohorts: selection changes only one axis per cohort.
    cohorts = [
        (range(0, 64), 0, STAGES[0], "consulting", "USD", "1000.00"),
        (range(64, 72), 1, STAGES[0], "consulting", "USD", "2000.00"),
        (range(72, 80), 0, STAGES[1], "consulting", "CAD", "3000.00"),
        (range(80, 88), 0, STAGES[0], "delivery", "USD", "4000.00"),
    ]
    fixture_rows = []
    for indexes, owner, stage, bu, currency, amount in cohorts:
        for index in indexes:
            fixture_rows.append({
                "index": index, "id": str(identity(f"deal-{index}")),
                "name": f"Synthetic T09 Deal {index:03}",
                "client_id": str(identity(f"client-{index // 4}")),
                "client_name": f"Synthetic T09 Client {index // 4:02}",
                "owner_id": str(owners[owner]), "owner_external": owner_external[owner],
                "stage": stage, "business_unit": bu, "currency": currency, "amount": amount,
            })

    engine = create_engine(url, connect_args={"connect_timeout": 5,
        "application_name": "s21-filter-private-fixture",
        "options": "-c statement_timeout=15000 -c lock_timeout=5000"})
    try:
        with engine.begin() as connection:
            actual = connection.execute(text("SELECT current_database(), current_user, "
                "pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()" )).one()
            require(tuple(actual) == (name, "s21", "s21"), "Connected database/user/owner identity mismatch")
            present = set(inspect(connection).get_table_names(schema="public"))
            require(set(GUARDED_TABLES) | {"alembic_version"} <= present,
                    "Missing required migrated tables; lead must migrate first")
            require(connection.execute(text("SELECT count(*) FROM alembic_version")).scalar_one() == 1,
                    "Require exactly one recorded Alembic revision")
            # Serialize competing invocations and prevent writes racing the empty check.
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:name))"), {"name": name})
            connection.execute(text("LOCK TABLE " + ", ".join(f'"{table}"' for table in GUARDED_TABLES)
                                    + " IN SHARE ROW EXCLUSIVE MODE"))
            occupied = {table: count for table in GUARDED_TABLES
                        if (count := connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one())}
            require(not occupied, "Refusing nonempty database; no fixture written: " + json.dumps(occupied, sort_keys=True))
            with Session(bind=connection) as session:
                session.add(User(id=actor_id, email=EMAIL, name="Synthetic T09 Administrator", groups=["SystemAdmin"]))
                for index, owner in enumerate(owners):
                    session.add(User(id=owner, email=f"synthetic-owner-{index}@example.test",
                        name=f"Synthetic Owner {'A' if index == 0 else 'B'}", groups=[]))
                    session.add(HubspotOwner(id=owner_external[index],
                        email=f"synthetic-owner-{index}@example.test", first_name="Synthetic",
                        last_name=f"Owner {'A' if index == 0 else 'B'}", archived=False))
                session.add(HubspotPipeline(id=PIPELINE, label="Synthetic T09 Pipeline", display_order=0))
                session.flush()
                for order, stage in enumerate(STAGES):
                    session.add(HubspotStage(id=stage, pipeline_id=PIPELINE,
                        label="Discovery" if order == 0 else "Negotiation", display_order=order,
                        is_closed=False, probability=Decimal("0.50")))
                session.add(HubspotPropertyMapping(key="business_unit", internal_name="synthetic_bu",
                    object_type="deal", label="Business Unit", field_type="enumeration",
                    availability_state="configured", mapping_version=7, checked_at=OBSERVED,
                    last_success_at=OBSERVED, selected_by=actor_id,
                    evidence={"source": "declared isolated synthetic CRM fixture", "database": name},
                    options=[{"value": "consulting", "label": "Consulting"},
                             {"value": "delivery", "label": "Delivery"}]))
                for index in range(23):
                    session.add(Client(id=identity(f"client-{index}"),
                        name=f"Synthetic T09 Client {index:02}" if index < 22 else "Synthetic Empty Client",
                        hubspot_company_id=f"synthetic-company-{index}", timezone="America/Los_Angeles",
                        hubspot_owner_id=owner_external[0], hubspot_owner_observed_at=OBSERVED))
                session.flush()
                for row in fixture_rows:
                    session.add(Opportunity(id=uuid.UUID(row["id"]), name=row["name"],
                        source="hubspot", hubspot_deal_id=f"synthetic-deal-{row['index']}",
                        client_id=uuid.UUID(row["client_id"]), owner_id=uuid.UUID(row["owner_id"]),
                        hubspot_owner_id=row["owner_external"], hubspot_owner_observed_at=OBSERVED,
                        hubspot_pipeline_id=PIPELINE, hubspot_stage_id=row["stage"],
                        stage_label="Discovery" if row["stage"] == STAGES[0] else "Negotiation",
                        stage_order=0 if row["stage"] == STAGES[0] else 1,
                        business_unit_value=row["business_unit"], business_unit_mapping_version=7,
                        business_unit_observed_at=OBSERVED, amount=Decimal(row["amount"]),
                        currency=row["currency"], is_closed_won=False, is_closed_lost=False,
                        close_date=date(2026, 12, 15), hubspot_created_at=OBSERVED,
                        hubspot_last_activity_at=OBSERVED, hubspot_last_modified_at=OBSERVED,
                        hubspot_last_seen_at=OBSERVED, governance_status="Intake"))
                session.add(SavedView(id=identity("stage-only-view"), owner_id=actor_id,
                    key="custom", name="Synthetic Negotiation Only", visibility="private",
                    is_builtin=False, filter_json={"stage": [STAGES[1]]},
                    sort_json={"column": "client_name", "descending": False}))
                session.flush()
    finally:
        engine.dispose()

    # Oracle membership is declared by cohort indices, never queried from the
    # application filter/summary implementation under test. Money totals literal.
    cases = [
        ("all", {}, range(88), {"USD": "112000.00", "CAD": "24000.00"}),
        ("owner_a", {"owner": [str(owners[0])]}, list(range(64)) + list(range(72, 88)), {"USD": "96000.00", "CAD": "24000.00"}),
        ("discovery", {"stage": [STAGES[0]]}, list(range(72)) + list(range(80, 88)), {"USD": "112000.00"}),
        ("consulting", {"business_unit": ["consulting"]}, range(80), {"USD": "80000.00", "CAD": "24000.00"}),
        ("owner_stage", {"owner": [str(owners[0])], "stage": [STAGES[0]]}, list(range(64)) + list(range(80, 88)), {"USD": "96000.00"}),
        ("stage_bu", {"stage": [STAGES[0]], "business_unit": ["consulting"]}, range(72), {"USD": "80000.00"}),
        ("owner_bu", {"owner": [str(owners[0])], "business_unit": ["consulting"]}, list(range(64)) + list(range(72, 80)), {"USD": "64000.00", "CAD": "24000.00"}),
        ("selected", {"owner": [str(owners[0])], "stage": [STAGES[0]], "business_unit": ["consulting"]}, range(64), {"USD": "64000.00"}),
        ("stage_only_saved", {"stage": [STAGES[1]]}, range(72, 80), {"CAD": "24000.00"}),
        ("zero", {"owner": [str(owners[1])], "stage": [STAGES[1]]}, [], {}),
    ]
    expected = {}
    for key, filters, indexes, totals in cases:
        rows = sorted((fixture_rows[index] for index in indexes),
                      key=lambda row: (row["client_name"], row["id"]))
        expected[key] = {"filters": filters, "sort": "client_name", "total": len(rows),
            "ids": [row["id"] for row in rows],
            "clients": [{"id": client, "matching_deal_count": sum(row["client_id"] == client for row in rows)}
                        for client in dict.fromkeys(row["client_id"] for row in rows)],
            "currency_totals": totals,
            "pages_25": [[row["id"] for row in rows[offset:offset + 25]] for offset in range(0, len(rows), 25)]}
    print(json.dumps({"database": name, "tenant": name, "actor_email": EMAIL,
        "actor_id": str(actor_id), "boundary": "synthetic local mirror, not live HubSpot or staging",
        "counts_seeded": {"users": 3, "clients": 23, "deals": 88, "saved_views": 1},
        "pipeline": PIPELINE, "stage_only_saved_view_id": str(identity("stage-only-view")),
        "empty_client_id": str(identity("client-22")), "fixture_rows": fixture_rows,
        "expected": expected}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
