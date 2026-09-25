"""Idempotent, entity-scoped agreement gaps; caller owns the transaction."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.audit import append_audit
from app.models.agreement_tracking import AgreementGap
from app.models.client import Agreement, Client, LegalEntity
from app.models.task import Task
from app.models.user import User
from app.services.business_days import add_business_days
from app.services.coverage_gate import _is_valid_executed


async def ensure_agreement_tasks(session, *, client_id, owner_id, actor_id, correlation_id=None):
    client = await session.scalar(select(Client).where(Client.id == client_id).with_for_update())
    if not client or client.archived_at:
        return
    entities = list(
        (await session.scalars(select(LegalEntity).where(LegalEntity.client_id == client_id))).all()
    )
    if not entities:
        entity = LegalEntity(id=uuid.uuid4(), client_id=client.id, name=client.name)
        session.add(entity)
        await session.flush()
        entities = [entity]
        await append_audit(
            session,
            correlation_id=correlation_id,
            actor_id=actor_id,
            action="legal_entity.created",
            entity="legal_entity",
            entity_id=str(entity.id),
            before=None,
            after={"client_id": str(client.id), "name": entity.name},
        )
    owner = await session.get(User, owner_id) if owner_id else None
    for entity in entities:
        rows = list(
            (
                await session.scalars(
                    select(Agreement).where(Agreement.legal_entity_id == entity.id)
                )
            ).all()
        )
        for kind in ("NDA", "MSA"):
            covered = any(a.kind == kind and _is_valid_executed(a, date.today()) for a in rows)
            gap = await session.get(AgreementGap, (entity.id, kind))
            task = await session.get(Task, gap.task_id) if gap else None
            if covered:
                if task and task.status not in ("done", "cancelled"):
                    before = task.status
                    task.status, task.completed_at, task.completed_by = (
                        "done",
                        datetime.now(UTC),
                        actor_id,
                    )
                    await append_audit(
                        session,
                        correlation_id=correlation_id,
                        actor_id=actor_id,
                        action="task.transitioned",
                        entity="task",
                        entity_id=str(task.id),
                        before={"status": before},
                        after={"status": "done", "source": "agreement.executed"},
                    )
                continue
            if not any(a.kind == kind for a in rows):
                row = Agreement(
                    id=uuid.uuid4(),
                    legal_entity_id=entity.id,
                    kind=kind,
                    state="missing",
                    owner_email=owner.email if owner else None,
                    next_action=f"Obtain signed {kind}",
                )
                session.add(row)
                await session.flush()
                await append_audit(
                    session,
                    correlation_id=correlation_id,
                    actor_id=actor_id,
                    action="agreement.created",
                    entity="agreement",
                    entity_id=str(row.id),
                    before=None,
                    after={"kind": kind, "state": "missing", "legal_entity_id": str(entity.id)},
                )
            if task and task.status not in ("done", "cancelled"):
                continue
            task = Task(
                id=uuid.uuid4(),
                owner_id=owner_id,
                subject=f"Obtain {kind} - {entity.name}"[:255],
                category="coverage",
                status="assigned",
                due_date=add_business_days(date.today(), 2),
            )
            session.add(task)
            await session.flush()
            if gap:
                gap.task_id = task.id
            else:
                session.add(AgreementGap(legal_entity_id=entity.id, kind=kind, task_id=task.id))
            await session.flush()
            await append_audit(
                session,
                correlation_id=correlation_id,
                actor_id=actor_id,
                action="task.created",
                entity="task",
                entity_id=str(task.id),
                before=None,
                after={
                    "subject": task.subject,
                    "owner_id": str(owner_id) if owner_id else None,
                    "category": "coverage",
                    "legal_entity_id": str(entity.id),
                    "source": "agreement.gap",
                },
            )
