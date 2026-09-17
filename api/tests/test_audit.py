"""Audit chain: contiguous under normal writes, breaks under any tamper."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.audit import append_audit, verify_chain
from app.models.audit import AuditEvent


async def _append_three(session):
    actor = uuid.uuid4()
    await append_audit(
        session,
        actor_id=actor,
        action="opportunity.create",
        entity="opportunity",
        entity_id="O-1",
        before=None,
        after={"governance_status": "Intake"},
        correlation_id="corr-1",
    )
    await append_audit(
        session,
        actor_id=actor,
        action="opportunity.transition",
        entity="opportunity",
        entity_id="O-1",
        before={"governance_status": "Intake"},
        after={"governance_status": "Coverage"},
        correlation_id="corr-2",
    )
    await append_audit(
        session,
        actor_id=actor,
        action="opportunity.transition",
        entity="opportunity",
        entity_id="O-1",
        before={"governance_status": "Coverage"},
        after={"governance_status": "SOWDraft"},
        correlation_id="corr-3",
    )
    await session.commit()


async def _rows(session):
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.ts, AuditEvent.id))
    return list(result.scalars())


async def test_chain_is_contiguous(session):
    await _append_three(session)
    rows = await _rows(session)
    assert len(rows) == 3
    assert rows[0].prev_hash is None
    assert rows[1].prev_hash == rows[0].row_hash
    assert rows[2].prev_hash == rows[1].row_hash
    assert await verify_chain(session) is True


async def test_tampering_with_action_breaks_verify(session):
    await _append_three(session)
    rows = await _rows(session)
    rows[1].action = "opportunity.tampered"
    await session.commit()
    assert await verify_chain(session) is False


async def test_tampering_with_after_payload_breaks_verify(session):
    await _append_three(session)
    rows = await _rows(session)
    rows[0].after = {"governance_status": "Approved"}  # not what actually happened
    await session.commit()
    assert await verify_chain(session) is False


async def test_tampering_with_row_hash_breaks_verify(session):
    await _append_three(session)
    rows = await _rows(session)
    rows[2].row_hash = "0" * 64
    await session.commit()
    assert await verify_chain(session) is False


async def test_empty_chain_verifies(session):
    assert await verify_chain(session) is True
