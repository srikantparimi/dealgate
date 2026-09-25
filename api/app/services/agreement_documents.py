"""Shared document extraction followed by explicit Legal confirmation."""

import hashlib
import uuid
from datetime import UTC, datetime

import anyio
from fastapi import HTTPException
from sqlalchemy import select

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import ManualRequired
from app.integrations.textract import TextractClient
from app.models.agreement_tracking import AgreementDocument
from app.models.client import Agreement, LegalEntity
from app.models.opportunity import Opportunity
from app.services.agreement_state import transition
from app.services.agreement_tracking import ensure_agreement_tasks
from app.services.document_text import (
    UnreadableDocument,
    extract_document_text,
    text_document_from_string,
)
from app.services.provenance import value_of
from app.services.sow_extract import _needs_textract


def extract_dates(payload, content_type, bedrock):
    doc = (
        text_document_from_string(TextractClient().extract_text(payload))
        if _needs_textract(payload)
        else extract_document_text(payload, content_type)
    )
    result = bedrock.extract(doc)
    if isinstance(result, ManualRequired):
        raise HTTPException(422, f"Could not extract agreement dates: {result.reason}")
    return {
        "effective_from": result.fields.get("term_start"),
        "expiry": result.fields.get("term_end"),
        "client_legal_name": result.fields.get("client_legal_name"),
        "model": result.model,
        "prompt_version": result.prompt_version,
        "ref_unit": doc.ref_unit,
    }


def document_view(row):
    return {
        "id": str(row.id),
        "agreement_id": str(row.agreement_id),
        "fields": row.extracted_fields,
        "confirmed": bool(row.confirmed_at),
    }


async def extract_document(
    session, *, agreement, actor_id, payload, filename, content_type, bedrock, s3
):
    # Serialize duplicate uploads before extraction and object storage side effects.
    await session.scalar(select(Agreement.id).where(Agreement.id == agreement.id).with_for_update())
    file_hash = hashlib.sha256(payload).hexdigest()
    existing = await session.scalar(
        select(AgreementDocument).where(
            AgreementDocument.agreement_id == agreement.id, AgreementDocument.file_hash == file_hash
        )
    )
    if existing:
        return document_view(existing)
    try:
        fields = await anyio.to_thread.run_sync(extract_dates, payload, content_type, bedrock)
    except HTTPException:
        raise
    except (ValueError, UnreadableDocument) as exc:
        raise HTTPException(422, "The agreement file could not be read") from exc
    key = await anyio.to_thread.run_sync(
        s3.put_object, agreement.id, filename, content_type, payload
    )
    row = AgreementDocument(
        id=uuid.uuid4(),
        agreement_id=agreement.id,
        file_hash=file_hash,
        file_s3_key=key,
        extracted_fields=fields,
        uploaded_by=actor_id,
    )
    session.add(row)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="agreement.document_extracted",
        entity="agreement",
        entity_id=str(agreement.id),
        before=None,
        after={
            "document_id": str(row.id),
            "file_hash": file_hash,
            "file_s3_key": key,
            "fields": fields,
        },
    )
    await session.commit()
    return document_view(row)


async def execute_document(
    session, *, agreement_id, document_id, actor_id, effective_from, expiry, correction_reason
):
    agreement = await session.scalar(
        select(Agreement).where(Agreement.id == agreement_id).with_for_update()
    )
    if not agreement:
        raise HTTPException(404, "Agreement not found")
    doc = await session.get(AgreementDocument, document_id)
    if not doc or doc.agreement_id != agreement.id:
        raise HTTPException(404, "Agreement document not found")
    if doc.confirmed_at:
        return agreement
    if agreement.state in ("terminated", "superseded"):
        raise HTTPException(409, "Create a new tracking record for this historical agreement")
    changed = any(
        str(value_of(doc.extracted_fields.get(key)) or "") != str(value)
        for key, value in (("effective_from", effective_from), ("expiry", expiry))
    )
    if changed and not (correction_reason or "").strip():
        raise HTTPException(422, "Explain corrected or missing extracted dates")
    before = {
        "state": agreement.state,
        "evidence_s3_key": agreement.evidence_s3_key,
        "effective_from": str(agreement.effective_from),
        "expiry": str(agreement.expiry),
        "next_action": agreement.next_action,
        "due_date": str(agreement.due_date) if agreement.due_date else None,
    }
    agreement.effective_from, agreement.expiry = effective_from, expiry
    agreement.evidence_s3_key = doc.file_s3_key
    if agreement.next_action == f"Obtain signed {agreement.kind}":
        agreement.next_action, agreement.due_date = None, None
    # Renewals and replacement evidence are still tracking, not a review cycle.
    if agreement.state in ("executed", "expired"):
        agreement.state = "sent"
    transition(agreement, "executed", actor_id)
    doc.confirmed_at = datetime.now(UTC)
    await append_audit(
        session,
        actor_id=actor_id,
        action="agreement.state_changed",
        entity="agreement",
        entity_id=str(agreement.id),
        before=before,
        after={
            "state": "executed",
            "document_id": str(doc.id),
            "evidence_s3_key": doc.file_s3_key,
            "effective_from": str(effective_from),
            "expiry": str(expiry),
            "next_action": agreement.next_action,
            "due_date": str(agreement.due_date) if agreement.due_date else None,
            "provenance": "manual" if changed else "extracted",
            "correction_reason": correction_reason,
        },
    )
    entity = await session.get(LegalEntity, agreement.legal_entity_id)
    owner_id = await session.scalar(
        select(Opportunity.owner_id)
        .where(Opportunity.client_id == entity.client_id)
        .order_by(Opportunity.created_at.desc())
        .limit(1)
    )
    await ensure_agreement_tasks(
        session, client_id=entity.client_id, owner_id=owner_id, actor_id=actor_id
    )
    await session.commit()
    return agreement
