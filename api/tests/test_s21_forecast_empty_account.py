"""A selected empty account keeps its real label without widening read scope."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.auth import AuthUser
from app.models.audit import AuditEvent
from app.models.client import Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.forecast_plans import outlook
from app.services.test_fixtures import create_fixture


@pytest.fixture(autouse=True)
def scope(monkeypatch):
    monkeypatch.setenv("DEALGATE_ENV", "local")
    monkeypatch.setenv("DEALGATE_TENANT_ID", "t18-empty-account")
    monkeypatch.setenv("DEALGATE_REPORTING_TIMEZONE", "UTC")
    monkeypatch.setenv("DEALGATE_REPORTING_CURRENCY", "USD")
    monkeypatch.setenv("ALLOW_DEV_SEED_ENDPOINT", "1")


async def actor(session, groups=("Delivery",)):
    user = User(id=uuid.uuid4(), email=f"t18-{uuid.uuid4()}@example.test", name="T18 Reader", groups=list(groups))
    session.add(user)
    await session.commit()
    return AuthUser(id=user.id, email=user.email, name=user.name, groups=groups)


async def view(session, user, account=None):
    return await outlook(session, actor=user, account_id=account,
        as_of=datetime(2026, 10, 2, 12, tzinfo=UTC), future_quarters=4)


def assert_named_zero(result, account):
    assert len(result["accounts"]) == 1
    row = result["accounts"][0]
    assert row["account_id"] == str(account.id) and row["name"] == account.name
    for key in ("current_month", "current_quarter", "future"):
        assert row[key]["revenue"] == Decimal("0")
        assert row[key]["cost"] == Decimal("0")
        assert row[key]["gm"] is None
    assert len(row["quarters"]) == 5
    assert result["source_count"] == 0 and result["rows"] == []
    assert result["pending_sources"] == [] and result["unresolved_sources"] == []


@pytest.mark.asyncio
async def test_selected_business_account_is_named_without_expanding_company_universe(session):
    user = await actor(session)
    account = Client(id=uuid.uuid4(), name="Empty account, real name")
    unrelated = Client(id=uuid.uuid4(), name="Other empty account")
    session.add_all([account, unrelated])
    await session.commit()
    assert_named_zero(await view(session, user, account.id), account)
    assert (await view(session, user))["accounts"] == []


@pytest.mark.asyncio
async def test_archived_and_missing_accounts_do_not_disclose_labels(session):
    user = await actor(session)
    account = Client(id=uuid.uuid4(), name="Archived private name", archived_at=datetime.now(UTC))
    session.add(account)
    await session.commit()
    assert (await view(session, user, account.id))["accounts"] == []
    assert (await view(session, user, uuid.uuid4()))["accounts"] == []


@pytest.mark.asyncio
async def test_sales_requires_own_portfolio_not_merely_business_scope(session):
    user = await actor(session, ("Sales",))
    account = Client(id=uuid.uuid4(), name="Owner portfolio with no forecast")
    session.add(account)
    await session.commit()
    assert (await view(session, user, account.id))["accounts"] == []
    deal = Opportunity(id=uuid.uuid4(), client_id=account.id, owner_id=user.id,
                       source="sow_upload", name="Owned empty deal", governance_status="Intake")
    session.add(deal)
    await session.commit()
    assert_named_zero(await view(session, user, account.id), account)
    deal.archived_at = datetime.now(UTC)
    await session.commit()
    assert (await view(session, user, account.id))["accounts"] == []


@pytest.mark.asyncio
async def test_trusted_fixture_scope_never_falls_back_to_business_visibility(session, monkeypatch):
    owner = await actor(session, ("SystemAdmin", "officeapp-e2e"))
    outsider = await actor(session, ("SystemAdmin", "officeapp-e2e"))
    business = await actor(session, ("Delivery",))
    grant = await create_fixture(session, actor_id=owner.id, label="T18 Empty fixture",
                                 reviewer_ids=[owner.id])
    await session.commit()
    account = await session.get(Client, grant["client_id"])
    assert_named_zero(await view(session, owner, account.id), account)
    assert (await view(session, outsider, account.id))["accounts"] == []
    assert (await view(session, business, account.id))["accounts"] == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "wrong-tenant")
    assert (await view(session, owner, account.id))["accounts"] == []
    monkeypatch.setenv("DEALGATE_TENANT_ID", "t18-empty-account")
    event = await session.scalar(select(AuditEvent).where(AuditEvent.action == "test.fixture_created",
                                                         AuditEvent.entity_id == str(account.id)))
    event.after = {**event.after, "expires_at": (datetime.now(UTC) - timedelta(days=1)).isoformat()}
    await session.commit()
    assert (await view(session, owner, account.id))["accounts"] == []


@pytest.mark.asyncio
async def test_test_actor_cannot_discover_ungranted_business_account(session):
    user = await actor(session, ("SystemAdmin", "officeapp-e2e"))
    account = Client(id=uuid.uuid4(), name="Business secret")
    session.add(account)
    await session.commit()
    assert (await view(session, user, account.id))["accounts"] == []
