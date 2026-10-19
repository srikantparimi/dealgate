"""S24-AG1 lane BE-D on Postgres (B8, B9; T8's "also on Postgres").

The hook, the settle and the msa_type mapping use SQL that SQLite does not
exercise the same way: row locks (FOR UPDATE) per chunk, the settings-row upsert,
a correlated EXISTS inside an aggregate, row_number() for the hint, and real
foreign keys and partial unique indexes. Each test runs on a fresh, migrated
scratch database (tests/s24_pg.py). Skipped without DEALGATE_POSTGRES_URL.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update

from app.integrations.hubspot import StubHubSpotClient
from app.models.agreements import AgreementMark, AgreementsSettings
from app.models.audit import AuditEvent
from app.models.client import Agreement, Client
from app.models.hubspot_sync_run import HubspotSyncRun
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import agreement_audit
from app.services.agreement_hooks import settle_pending_relationships, stamp_new_client
from app.services.agreement_hubspot import apply_mapping, hubspot_values, save_mapping
from app.services.hubspot_sync_runs import run_deal_sync
from tests.s24_pg import POSTGRES, scratch_postgres

pytestmark = POSTGRES

CUTOVER = date(2026, 10, 1)
T1 = datetime(2026, 10, 1, tzinfo=UTC)
T2 = datetime(2026, 10, 5, tzinfo=UTC)


async def _user(s, email: str, name: str, groups=("SystemAdmin",)) -> User:
    user = User(id=uuid.uuid4(), email=email, name=name, groups=list(groups))
    s.add(user)
    await s.flush()
    return user


async def _client(s, name: str) -> Client:
    client = Client(id=uuid.uuid4(), name=name, hubspot_company_id=f"co-{uuid.uuid4().hex[:8]}")
    s.add(client)
    await s.flush()
    return client


def _deal(client: Client, *, msa: str | None = None, modified: datetime = T1, won: bool = False,
          close: date | None = None) -> Opportunity:
    return Opportunity(id=uuid.uuid4(), client_id=client.id, source="hubspot", governance_status="Intake",
                       hubspot_deal_id=f"d-{uuid.uuid4().hex[:10]}", hubspot_msa_type=msa,
                       hubspot_last_modified_at=modified, is_closed_won=won, close_date=close)


async def test_values_mapping_and_apply_on_postgres():
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            saver = await _user(s, "saver@example.test", "Sam Saver")
            presser = await _user(s, "presser@example.test", "Pat Presser")
            legal = await _user(s, "legal@example.test", "Lee Legal", ("Legal",))
            empty = [await _client(s, f"Empty {i}") for i in range(30)]
            held = await _client(s, "Holds A File")
            marked = await _client(s, "Removed Mark")
            moved = await _client(s, "Moved On")
            for c in (*empty, held, marked):
                s.add(_deal(c, msa="Signed MSA"))
            s.add_all([_deal(moved, msa="Signed MSA", modified=T1), _deal(moved, msa="In progress", modified=T2)])
            await s.flush()
            s.add(Agreement(id=uuid.uuid4(), client_id=held.id, kind="MSA", file_key="k", filename="msa.pdf",
                            file_size=10, uploaded_by=legal.id))
            s.add(AgreementMark(id=uuid.uuid4(), client_id=marked.id, kind="MSA", reason="other",
                                marked_on=date(2026, 10, 2), marked_by=legal.id,
                                removed_at=datetime.now(UTC), removed_by=legal.id))
            await s.commit()
            await save_mapping(s, actor_id=saver.id, items=[("Signed MSA", "covered"), ("In progress", "ignore")])
            await s.commit()

        async with factory() as s:
            values = await hubspot_values(s)
            items = {i["value"]: i for i in values["items"]}
            assert values["stored"] is True and values["saved_by"] == "Sam Saver"
            assert items["Signed MSA"] == {"value": "Signed MSA", "clients": 32, "action": "covered",
                                           "would_mark": 30}
            assert items["In progress"] == {"value": "In progress", "clients": 1, "action": "ignore",
                                            "would_mark": 1}
            dry = await apply_mapping(s, dry_run=True, trigger="dialog", actor_id=None)
            assert dry.as_dict() == {"dry_run": True, "would_mark": 30, "marked": 0}
            real = await apply_mapping(s, dry_run=False, trigger="dialog", actor_id=presser.id)
            assert real.as_dict() == {"dry_run": False, "would_mark": 30, "marked": 30}

        async with factory() as s:
            marks = (await s.scalars(select(AgreementMark).where(AgreementMark.source == "hubspot"))).all()
            assert {m.client_id for m in marks} == {c.id for c in empty}
            assert {m.marked_by for m in marks} == {saver.id}
            assert (await s.scalar(select(func.count()).select_from(AuditEvent).where(
                AuditEvent.action == agreement_audit.HUBSPOT_MARKED))) == 30
            # A second run (as the nightly one would) never adds or changes anything.
            again = await apply_mapping(s, dry_run=False, trigger="sync", actor_id=None)
            assert again.as_dict() == {"dry_run": False, "would_mark": 0, "marked": 0}


async def test_hook_settle_and_post_sync_steps_on_postgres():
    async with scratch_postgres() as (_engine, factory):
        async with factory() as s:
            saver = await _user(s, "saver@example.test", "Sam Saver")
            # Migration 0072 inserted the settings row; the first real batch sets the cutover.
            await s.execute(update(AgreementsSettings).where(AgreementsSettings.id == 1).values(
                cutover_date=CUTOVER, set_at=datetime.now(UTC) - timedelta(hours=1)))
            await s.commit()
            manual = Client(id=uuid.uuid4(), name="By Hand")
            s.add(manual)
            await s.flush()
            assert await stamp_new_client(s, manual, actor_id=saver.id, origin="manual") == "net_new"
            await s.commit()
            await save_mapping(s, actor_id=saver.id, items=[("Signed MSA", "covered")])
            await s.commit()

        def deal(deal_id, company, stage, close, msa=None):
            props = {"dealname": deal_id, "dealstage": stage, "pipeline": "default", "amount": "1",
                     "deal_currency_code": "USD", "closedate": close, "hs_lastmodifieddate": "2026-10-13T12:00:00Z"}
            if msa:
                props["msa_type"] = msa
            return {"id": deal_id, "properties": props,
                    "associations": {"companies": {"results": [{"id": company, "type": "deal_to_company"}]}}}

        stub = StubHubSpotClient(
            deals={"d1": deal("d1", "c1", "closedwon", "2026-09-20", "Signed MSA"),
                   "d2": deal("d2", "c2", "closedwon", "2026-10-12"),
                   "d3": deal("d3", "c3", "qualifiedtobuy", "2026-12-31", "Signed MSA")},
            companies={"c1": {"id": "c1", "properties": {"name": "Old Friend"}},
                       "c2": {"id": "c2", "properties": {"name": "First Win"}},
                       "c3": {"id": "c3", "properties": {"name": "Prospect"}}})
        outcome = await run_deal_sync("nightly", stub, session_factory=factory)
        assert outcome.status == "ok"

        async with factory() as s:
            rels = {c.name: (c.relationship, c.relationship_basis)
                    for c in (await s.scalars(select(Client))).all()}
            assert rels == {"By Hand": ("net_new", "none"), "Old Friend": ("existing", "closed_won"),
                            "First Win": ("net_new", "none"), "Prospect": ("net_new", "none")}
            marks = (await s.execute(select(Client.name, AgreementMark.marked_by).join(
                AgreementMark, AgreementMark.client_id == Client.id))).all()
            assert sorted(marks) == sorted([("Old Friend", saver.id), ("Prospect", saver.id)])
            [run] = (await s.scalars(select(HubspotSyncRun))).all()
            assert (run.status, run.deals_seen, run.deals_written, run.error_count) == ("ok", 3, 3, 0)
            assert await settle_pending_relationships(s) == 0
