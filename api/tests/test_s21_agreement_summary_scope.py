"""Agreement counts include deal-less accounts only in unfiltered authorized scope."""

import pytest

from app.models.client import Agreement, Client
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.hubspot_pipeline import PipelineFilters, summary


@pytest.mark.asyncio
async def test_agreement_count_preserves_hidden_archived_and_selected_account_scope(session):
    owner = User(email="agreement-scope@example.test", name="Scope owner", groups=[])
    clients = [Client(name=name) for name in ("Deal-less", "Matched", "Hidden", "Archived")]
    session.add_all([owner, *clients])
    await session.flush()
    from datetime import UTC, datetime
    clients[3].archived_at = datetime.now(UTC)
    session.add(Opportunity(client_id=clients[1].id, owner_id=owner.id, source="hubspot",
        hubspot_deal_id="agreement-scope-deal", hubspot_pipeline_id="selected", name="Matching deal"))
    for client in clients:
        session.add(Agreement(client_id=client.id, kind="NDA", file_key=f"{client.id}.pdf",
            filename="NDA.pdf", file_size=10, uploaded_by=owner.id))
    await session.commit()
    hidden = (clients[2].id,)
    assert (await summary(session, filters=PipelineFilters(hidden_client_ids=hidden))).agreements_uploaded == 2
    assert (await summary(session, filters=PipelineFilters(hidden_client_ids=hidden,
        pipeline="selected"))).agreements_uploaded == 1
    assert (await summary(session, filters=PipelineFilters(hidden_client_ids=hidden,
        pipeline="no matches"))).agreements_uploaded == 0
    assert (await summary(session, filters=PipelineFilters(
        authorized_client_ids=(clients[0].id,), authorized_opportunity_ids=()))).agreements_uploaded == 1
    assert (await summary(session, filters=PipelineFilters(
        authorized_client_ids=(), authorized_opportunity_ids=()))).agreements_uploaded == 0
