"""Sourcing rules and drafts retain scoped immutable revision identities."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.people_sourcing import SourcingRuleSet, SourcingRuleVersion
from app.models.user import User


async def seed(session):
    actor = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.test", name="Synthetic HR", groups=["HR"])
    root = SourcingRuleSet(id=uuid.uuid4(), tenant_id="schema-test", environment="local", test_fixture=False)
    session.add_all([actor, root])
    await session.flush()
    return actor, root


def version(actor, root, **changes):
    values = dict(id=uuid.uuid4(), rule_set_id=root.id, revision=1, request_key="first",
        request_hash="a" * 64, rules=[{"skill": "python", "location": "US", "lead_days": 45}],
        reason="Synthetic approved lead time", created_by=actor.id)
    return SourcingRuleVersion(**(values | changes))


async def test_rules_roundtrip_with_actor_reason_and_exact_scoped_identity(session):
    actor, root = await seed(session)
    row = version(actor, root)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.rules == [{"skill": "python", "location": "US", "lead_days": 45}]
    assert row.reason == "Synthetic approved lead time" and row.created_by == actor.id
    session.add(SourcingRuleSet(tenant_id=root.tenant_id, environment=root.environment, test_fixture=True))
    await session.commit()


@pytest.mark.parametrize("changes", [{}, {"revision": 2}, {"request_key": "different"}])
async def test_rule_revision_and_request_key_are_independently_unique(session, changes):
    actor, root = await seed(session)
    session.add(version(actor, root))
    await session.commit()
    session.add(version(actor, root, **changes))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_rule_root_scope_is_unique(session):
    _, root = await seed(session)
    session.add(SourcingRuleSet(tenant_id=root.tenant_id, environment=root.environment, test_fixture=False))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_nonpositive_revision_refused(session):
    actor, root = await seed(session)
    session.add(version(actor, root, revision=0))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()
