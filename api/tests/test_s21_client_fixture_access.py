import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auth import AuthUser, current_user
from app.db import get_session
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.deal_comment import DealComment
from app.models.opportunity import Opportunity
from app.models.user import User
from app.routers.clients import router
from app.routers.timeline import router as timeline_router
from app.services.test_fixtures import create_fixture


@pytest.fixture
async def clients_api(session, monkeypatch):
    monkeypatch.setenv('DEALGATE_ENV', 'local')
    monkeypatch.setenv('DEALGATE_TENANT_ID', 'client-scope')
    monkeypatch.setenv('ALLOW_DEV_SEED_ENDPOINT', '1')
    people = [User(id=uuid.uuid4(), email=f'{uuid.uuid4()}@example.test', name=name, groups=groups)
              for name, groups in [('Issuer', ['SystemAdmin', 'officeapp-e2e']),
                                   ('Normal', ['SystemAdmin']), ('Unissued', ['SystemAdmin', 'officeapp-e2e']),
                                   ('Sales', ['Sales'])]]
    session.add_all(people)
    await session.flush()
    issued = await create_fixture(session, actor_id=people[0].id, label='Private source', reviewer_ids=[])
    real = Client(name='Z Real business')
    session.add(real)
    await session.flush()
    session.add(Opportunity(client_id=real.id, owner_id=people[3].id, source='manual', name='Real deal', governance_status='Intake'))
    sibling = Opportunity(client_id=issued['client_id'], owner_id=people[2].id, source='manual', name='Not granted', governance_status='Intake')
    session.add(sibling)
    session.add(DealComment(opportunity_id=issued['opportunity_id'], author_id=people[0].id, body='Private fixture activity'))
    await session.commit()
    active = [0]
    app = FastAPI()
    app.include_router(router)
    app.include_router(timeline_router)
    async def db():
        yield session
    def actor():
        person = people[active[0]]
        return AuthUser(person.id, person.email, person.name, tuple(person.groups))
    app.dependency_overrides[get_session] = db
    app.dependency_overrides[current_user] = actor
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        yield client, active, people, issued, real, sibling


@pytest.mark.asyncio
@pytest.mark.parametrize('index,kind', [(0, 'fixture'), (1, 'real'), (2, 'none'), (3, 'real')])
async def test_visibility_precedes_pagination_and_detail_audit(session, clients_api, index, kind):
    client, active, people, issued, real, sibling = clients_api
    active[0] = index
    response = await client.get('/clients?size=1')
    assert response.status_code == 200
    data = response.json()
    expected = [str(issued['client_id'])] if kind == 'fixture' else [str(real.id)] if kind == 'real' else []
    assert [row['id'] for row in data['items']] == expected
    assert data['total'] == len(expected)
    assert (await client.get('/clients?size=1&page=2')).json()['items'] == []
    detail = await client.get(f"/clients/{issued['client_id']}")
    if kind == 'fixture':
        assert detail.status_code == 200
        assert [row['id'] for row in detail.json()['opportunities']] == [str(issued['opportunity_id'])]
        assert data['items'][0]['opportunity_count'] == 1
        assert data['items'][0]['owner_ids'] == [str(people[0].id)]
        timeline = await client.get(f"/clients/{issued['client_id']}/timeline")
        assert 'Private fixture activity' in timeline.text
    else:
        assert detail.status_code == 404
        assert 'Private source' not in detail.text
        timeline = await client.get(f"/clients/{issued['client_id']}/timeline")
        assert timeline.status_code == 200
        assert timeline.json()['items'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['expired', 'wrong_tenant', 'forged_owner'])
async def test_invalid_grant_never_visible(session, clients_api, damage):
    client, _, _, issued, _, _ = clients_api
    grant = await session.scalar(select(AuditEvent).where(AuditEvent.action == 'test.fixture_created', AuditEvent.entity_id == str(issued['client_id'])))
    changed = dict(grant.after)
    if damage == 'expired': changed['expires_at'] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    if damage == 'wrong_tenant': changed['tenant_id'] = 'elsewhere'
    if damage == 'forged_owner': changed['owner_id'] = str(uuid.uuid4())
    grant.after = changed
    await session.commit()
    assert (await client.get('/clients')).json()['total'] == 0
    assert (await client.get(f"/clients/{issued['client_id']}")).status_code == 404


@pytest.mark.asyncio
async def test_owning_unissued_sibling_does_not_grant_account_or_owner_filter(clients_api):
    client, active, people, issued, _, _ = clients_api
    assert (await client.get(f'/clients?owner={people[2].id}')).json()['total'] == 0
    active[0] = 2
    assert (await client.get('/clients?owner=me')).json()['total'] == 0
    assert (await client.get(f"/clients/{issued['client_id']}")).status_code == 404


@pytest.mark.asyncio
async def test_regular_sales_role_ownership_preserved(clients_api):
    client, active, _, _, real, _ = clients_api
    active[0] = 3
    assert (await client.get(f'/clients/{real.id}')).status_code == 200
    assert (await client.get('/clients?owner=me')).json()['total'] == 1


@pytest.mark.asyncio
async def test_agreement_root_audit_is_visible_only_in_authorized_client(session, clients_api):
    client, active, people, issued, real, _ = clients_api
    agreement = Agreement(client_id=issued['client_id'], kind='NDA', file_key='fixture/nda', filename='nda.pdf', file_size=1, uploaded_by=people[0].id)
    session.add(agreement)
    await session.flush()
    event = AuditEvent(actor_id=people[0].id, action='agreement.replaced', entity='agreement', entity_id=str(agreement.id), after={'filename': 'nda.pdf'}, row_hash='a' * 64)
    session.add(event)
    await session.commit()
    detail = (await client.get(f"/clients/{issued['client_id']}")).json()
    assert str(event.id) in [row['id'] for row in detail['recent_activity']]
    active[0] = 1
    assert (await client.get(f"/clients/{issued['client_id']}")).status_code == 404
    other = (await client.get(f'/clients/{real.id}')).json()
    assert str(event.id) not in [row['id'] for row in other['recent_activity']]
