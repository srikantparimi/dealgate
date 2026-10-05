"""Persistent scan state distinguishes resumable work from a successful scan."""
import pytest
from sqlalchemy import BigInteger
from sqlalchemy.exc import IntegrityError

from app.models.opportunity import Opportunity
from app.models.sync_status import SyncStatus


@pytest.mark.asyncio
async def test_legacy_scan_is_idle_without_fabricated_lease_or_seen_marker(session):
    status = SyncStatus(source="synthetic-scan", scan_generation=3)
    deal = Opportunity(source="manual", governance_status="Intake")
    session.add_all([status, deal])
    await session.commit()
    assert status.scan_phase == "idle"
    assert status.scan_failure_count == 0
    assert status.scan_context is None
    assert status.scan_lease_token is None
    assert status.scan_lease_expires_at is None
    assert deal.hubspot_seen_generation is None


@pytest.mark.asyncio
@pytest.mark.parametrize("values", [
    {"scan_phase": "finished"}, {"scan_failure_count": -1},
    {"scan_generation": -1},
])
async def test_scan_rejects_invalid_persisted_state(session, values):
    session.add(SyncStatus(source="synthetic-invalid", **values))
    with pytest.raises(IntegrityError):
        await session.commit()


def test_scan_counters_have_long_lived_storage():
    assert isinstance(SyncStatus.__table__.c.scan_generation.type, BigInteger)
    assert isinstance(Opportunity.__table__.c.hubspot_seen_generation.type, BigInteger)


@pytest.mark.asyncio
async def test_scan_context_and_generation_survive_reload(session):
    context = {"schema_version": 1, "tenant": "synthetic", "portal_id": "fixture",
        "environment": "local", "properties": ["dealname"], "mapping_version": 7}
    session.add(SyncStatus(source="synthetic-context", scan_generation=2147483648,
        scan_context=context, scan_phase="failed", scan_failure_count=2, cursor="page-2"))
    await session.commit()
    session.expunge_all()
    row = await session.get(SyncStatus, "synthetic-context")
    assert row.scan_context == context
    assert row.cursor == "page-2"
    assert row.scan_generation == 2147483648
    assert row.scan_phase == "failed"
    assert row.scan_failure_count == 2
