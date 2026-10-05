"""Actual PostgreSQL lock races through tracking HTTP routes on an issued fixture."""
import asyncio
import json
import os
import uuid
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import AuthUser, current_user
from app.db import get_session
from app.main import app
from app.models.audit import AuditEvent
from app.models.deal_comment import DealComment
from app.models.next_action import NextAction, NextActionEvent
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.test_fixtures import account_scope


async def main():
    url = os.environ["POSTGRES_URL"]
    parsed = urlparse(url)
    assert (parsed.hostname, parsed.port, parsed.path) == ("127.0.0.1", 55421, "/s21_journey")
    assert os.environ["DEALGATE_ENV"] == "local" and os.environ["DEALGATE_TENANT_ID"] == "s21-lead"
    run = f"s21-t11-race-{uuid.uuid4().hex}"
    engine = create_async_engine(url, pool_size=5, connect_args={"server_settings": {"application_name": run}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tasks = []
    try:
        async with sessions() as session:
            deal = await session.get(Opportunity, uuid.UUID(os.environ["S21_TRACKING_DEAL"]))
            assert deal and deal.source == "sow_upload" and deal.hubspot_deal_id is None
            owner = await session.get(User, deal.owner_id)
            assert owner and owner.email.startswith("s21-t11-") and owner.email.endswith("@example.test")
            scope = await account_scope(session, deal.client_id, opportunity_id=deal.id)
            assert scope and owner.id in scope
            actor = AuthUser(id=owner.id, email=owner.email, name=owner.name, groups=tuple(owner.groups))
            assert {"SystemAdmin", "officeapp-e2e"} <= set(actor.groups)
            peer = await session.get(User, uuid.UUID(os.environ["S21_TRACKING_PEER"]))
            assert peer and peer.id in scope and peer.id != owner.id
            assert peer.email.startswith("s21-t11-peer-") and peer.email.endswith("@example.test")

        async def db():
            async with sessions() as session:
                yield session

        app.dependency_overrides[get_session] = db
        app.dependency_overrides[current_user] = lambda: actor
        proofs = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-proof") as client:
            for kind, model, create_url, payload, field, patch_prefix in (
                ("deal_comment", DealComment, f"/deals/{deal.id}/comments", {"body": "PG race original"}, "body", "/deal-comments"),
                ("next_action", NextAction, "/next-actions", {"opportunity_id": str(deal.id), "title": "PG race original", "assignee_user_id": str(owner.id)}, "title", "/next-actions"),
            ):
                created = await client.post(create_url, json=payload)
                assert created.status_code == 201, created.text
                row = created.json()
                row_id = uuid.UUID(row["id"])
                async with sessions() as inspection:
                    audits_before = await inspection.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity == kind, AuditEvent.entity_id == str(row_id)))
                    events_before = await inspection.scalar(select(func.count()).select_from(NextActionEvent).where(NextActionEvent.next_action_id == row_id)) if kind == "next_action" else None
                async with sessions() as blocker:
                    blocker_pid = await blocker.scalar(text("SELECT pg_backend_pid()"))
                    await blocker.scalar(select(model).where(model.id == row_id).with_for_update())
                    changes = [{"pinned": True}, {"body": "PG race edited"}] if kind == "deal_comment" else [{"status": "complete"}, {"title": "PG race edited"}]
                    tasks = [asyncio.create_task(client.patch(f"{patch_prefix}/{row_id}", json={
                        "expected_revision": row["revision"], **change,
                    })) for change in changes]
                    try:
                        # Observe both actual database waiters before releasing the row lock.
                        async with asyncio.timeout(15):
                            while True:
                                async with sessions() as inspection:
                                    waiters = (await inspection.execute(text("SELECT pid, pg_blocking_pids(pid) AS blockers, query FROM pg_stat_activity WHERE application_name=:run AND wait_event_type='Lock'"), {"run": run})).mappings().all()
                                waiting = len(waiters)
                                if waiting == 2:
                                    assert all("FOR UPDATE" in waiter["query"].upper() for waiter in waiters)
                                    assert any(blocker_pid in waiter["blockers"] for waiter in waiters)
                                    break
                                assert not any(task.done() for task in tasks), "Request escaped before both row locks waited"
                                await asyncio.sleep(0.05)
                    finally:
                        await blocker.rollback()
                    responses = await asyncio.gather(*tasks)
                    tasks = []
                assert sorted(response.status_code for response in responses) == [200, 409], [r.text for r in responses]
                winner_index = next(i for i, response in enumerate(responses) if response.status_code == 200)
                winner = responses[winner_index].json()
                expected = (("PG race original", True), ("PG race edited", False)) if kind == "deal_comment" else (("PG race original", "complete"), ("PG race edited", "open"))
                second_field = "pinned" if kind == "deal_comment" else "status"
                assert (winner[field], winner[second_field]) == expected[winner_index]
                assert winner["revision"] != row["revision"]
                async with sessions() as inspection:
                    stored = await inspection.get(model, row_id)
                    assert (getattr(stored, field), getattr(stored, second_field)) == expected[winner_index]
                    audits_after = await inspection.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity == kind, AuditEvent.entity_id == str(row_id)))
                    assert audits_after == audits_before + 1
                    if kind == "next_action":
                        events_after = await inspection.scalar(select(func.count()).select_from(NextActionEvent).where(NextActionEvent.next_action_id == row_id))
                        assert events_after == events_before + 1
                proofs.append({"entity": kind, "id": str(row_id), "observed_lock_waiters": waiting,
                    "blocker_pid": blocker_pid, "waiters": [{"pid": w["pid"], "blockers": w["blockers"]} for w in waiters],
                    "http_statuses": sorted(r.status_code for r in responses), "mutation_audit_delta": audits_after - audits_before,
                    "stored_winner": winner[field]})
            # Local auth adapter; HTTP routes, persisted grants and audits are real.
            actor = AuthUser(id=peer.id, email=peer.email, name=peer.name, groups=("Sales", "officeapp-e2e"))
            read = await client.get(f"/deals/{deal.id}/comments")
            assert read.status_code == 200, read.text
            foreign_comment = next(row for row in read.json()["items"] if row["author_id"] == str(owner.id))
            async with sessions() as inspection:
                denied_before = await inspection.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity == "deal_comment", AuditEvent.entity_id == foreign_comment["id"]))
            denied = await client.patch(f"/deal-comments/{foreign_comment['id']}", json={"expected_revision": foreign_comment["revision"], "body": "Unauthorized overwrite"})
            assert denied.status_code == 403, denied.text
            async with sessions() as inspection:
                stored = await inspection.get(DealComment, uuid.UUID(foreign_comment["id"]))
                assert stored.body == foreign_comment["body"]
                assert await inspection.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity == "deal_comment", AuditEvent.entity_id == foreign_comment["id"])) == denied_before
            own = await client.post(f"/deals/{deal.id}/comments", json={"body": "Sales role own comment"})
            assert own.status_code == 201, own.text
            own_row = own.json()
            own_edit = await client.patch(f"/deal-comments/{own_row['id']}", json={"expected_revision": own_row["revision"], "body": "Sales role edited comment"})
            assert own_edit.status_code == 200, own_edit.text
            actor = AuthUser(id=peer.id, email=peer.email, name=peer.name, groups=("HR", "officeapp-e2e"))
            leader = await client.patch(f"/deal-comments/{foreign_comment['id']}", json={"expected_revision": foreign_comment["revision"], "body": "HR authorized edit of another author"})
            assert leader.status_code == 200, leader.text
            assert leader.json()["body"] == "HR authorized edit of another author"
            proofs.append({"role_checks": "Sales allowed read/create/own edit; non-owner denied403 with unchanged row/audit; HR allowed cross-author edit"})
        print(json.dumps({"deal_id": str(deal.id), "database": parsed.path, "proofs": proofs,
            "scope": "local real HTTP application and independent PostgreSQL sessions; not Cognito or staging"}))
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        app.dependency_overrides.clear()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
