"""SOW upload pipeline — shared entry point for single + bulk uploads.

Owns the derive-from-file chain used by both ``POST /sows/upload``
(agent BB's S10-01 single upload) and ``POST /admin/bulk-imports/sows``
(this story's S10-02 bulk import). One code path, two callers.

``apply_pipeline`` is the public entry: takes raw file bytes + the
uploader identity + a ``source`` tag, runs hash → document-type gate →
extract → classify → resolve-client → opportunity → sow_version →
auto-staffing → auto-GM, and returns a :class:`PipelineResult` the
caller uses to update its own envelope (a ``SowUploadJob`` for singles,
an ``ImportFile`` for bulk).

Everything is idempotent by file hash: a re-run with the same bytes
returns ``PipelineOutcome.duplicate`` and never creates a second SOW
version.
"""

from __future__ import annotations

import hashlib
import re
import uuid

import anyio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
    StubBedrock,
)
from app.models.client import Client
from app.models.client_alias import ClientAlias
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.services.auto_staffing import staff as auto_staff
from app.services.delivery_model import (
    GmModelPayload,
    create_gm_model_version,
    parse_resource_line,
)
from app.services.auto_staffing import lines_to_payload_dicts
from app.services.document_text import (
    DocumentText,
    UnreadableDocument,
    extract_document_text,
)
from app.services.document_type import (
    ALLOWED_START_TYPES,
    DocumentTypeResult,
    classify_document,
)
from app.services.engagement_classifier import classify as classify_engagement
from app.services.provenance import value_of, wrap as wrap_provenance


CLIENT_MATCH_MIN_SCORE = Decimal("0.85")
CLIENT_MATCH_MIN_GAP = Decimal("0.15")
NOTICE_WINDOW_DAYS = 60  # 2-month notice per docs/sow-first §7.


class PipelineOutcome(str, Enum):
    """The terminal state the pipeline reached."""

    IMPORTED = "imported"
    NEEDS_REVIEW = "needs_review"
    NEEDS_PICK = "needs_pick"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


@dataclass
class PipelineResult:
    outcome: PipelineOutcome
    sha256: str
    detected_type: str | None = None
    detected_confidence: float | None = None
    opportunity_id: uuid.UUID | None = None
    sow_version_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None
    matched_client_id: uuid.UUID | None = None
    matched_confidence: Decimal | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    needs_pick_candidates: list[dict[str, Any]] = field(default_factory=list)
    # S10-01 additions: preserved so the SowUploadJob envelope can save
    # them and the picker endpoint can replay the extract without
    # re-fetching the file. Only populated on the ``NEEDS_PICK`` path.
    extract_fields: dict[str, Any] | None = None
    extract_model: str | None = None
    extract_prompt_version: str | None = None
    client_signals: dict[str, Any] | None = None
    create_new: dict[str, Any] | None = None


# ---- helpers --------------------------------------------------------------


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


async def find_sow_by_hash(
    session: AsyncSession, file_hash: str
) -> SowVersion | None:
    return (
        await session.execute(
            select(SowVersion).where(SowVersion.file_hash == file_hash).limit(1)
        )
    ).scalar_one_or_none()


def _classify_type(
    file_bytes: bytes, content_type: str | None = None
) -> DocumentTypeResult:
    return classify_document(file_bytes, content_type=content_type)


@dataclass
class _ExtractOutcome:
    """Extract result wrapper — model + prompt version travel with the
    fields so the ``NEEDS_PICK`` picker payload can round-trip through
    the SowUploadJob envelope without a second extract call."""

    fields: dict[str, Any] | None
    model: str | None
    prompt_version: str | None
    error: str | None


async def _run_extract(
    text_doc: DocumentText, *, bedrock: BedrockSowExtract | None = None
) -> _ExtractOutcome:
    """Run Bedrock extract; return the payload + provenance metadata.

    A ``ManualRequired`` outcome is not fatal for the bulk pipeline —
    the file lands as ``needs_review`` so the human can complete it. The
    caller decides how to react.
    """

    caller = bedrock if bedrock is not None else StubBedrock()
    try:
        # boto3 is synchronous; keep it off the event loop so one slow
        # extraction cannot stall every other request on the worker.
        raw = await anyio.to_thread.run_sync(caller.extract, text_doc)
    except Exception as exc:  # noqa: BLE001 — never crash the batch
        return _ExtractOutcome(None, None, None, f"extract crashed: {exc}")
    if isinstance(raw, ManualRequired):
        return _ExtractOutcome(
            None, None, None, f"extract manual_required: {raw.reason}"
        )
    if isinstance(raw, ExtractedFields):
        return _ExtractOutcome(
            fields=raw.fields,
            model=raw.model,
            prompt_version=raw.prompt_version,
            error=None,
        )
    return _ExtractOutcome(None, None, None, f"extract returned {type(raw).__name__}")


_DOMAIN_RE = re.compile(
    r"\b([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"  # first label
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+)\b",
    re.IGNORECASE,
)


def _client_signals(fields: dict[str, Any]) -> dict[str, Any]:
    """Pull legal-name / domain / aliases / address_lines from an
    extracted-field envelope."""

    scope = str(value_of(fields.get("scope_summary")) or "")
    signatories = value_of(fields.get("signatories")) or []

    # The extractor now reads the client's legal entity straight from the
    # parties clause (`client_legal_name`, added in S10-04). Prefer it.
    #
    # Deriving the name from `signatories` alone — as this did before — fails
    # on any SOW without a signature block, which is most drafts. The result
    # was a client picker with an empty "Legal name" field for the user to
    # type into: a CLAUDE.md rule 10 defect ("a blank form on open is a
    # defect"). The signatory and scope paths stay as fallbacks.
    legal_name = value_of(fields.get("client_legal_name")) or None
    if legal_name is not None:
        legal_name = str(legal_name).strip() or None
    domain = value_of(fields.get("client_domain")) or None
    if domain is not None:
        domain = str(domain).strip().lower() or None

    address_lines: list[str] = []
    if isinstance(signatories, list):
        for row in signatories:
            if isinstance(row, dict):
                nm = row.get("client_legal_name") or row.get("name")
                if nm and legal_name is None:
                    legal_name = str(nm)
                em = row.get("email")
                if em and domain is None and isinstance(em, str) and "@" in em:
                    domain = em.split("@", 1)[1].strip().lower()
                addr = row.get("address")
                if addr and not address_lines:
                    if isinstance(addr, list):
                        address_lines = [str(x) for x in addr if x]
                    elif isinstance(addr, str):
                        address_lines = [
                            line.strip()
                            for line in addr.splitlines()
                            if line.strip()
                        ]
    # Fall back to a scope-scan for "for {name}".
    if legal_name is None:
        m = re.search(r"for ([A-Z][\w& ,.\-]{2,60})", scope)
        if m:
            legal_name = m.group(1).strip()
    # Domain fallback — grep the scope for the first email-ish domain.
    if domain is None:
        m = _DOMAIN_RE.search(scope)
        if m:
            candidate = m.group(1).lower()
            # Filter common non-domain hits (e.g. "e.g", "v1.0").
            if "." in candidate and not candidate.endswith("."):
                parts = candidate.rsplit(".", 1)
                if len(parts[-1]) >= 2 and not parts[-1].isdigit():
                    domain = candidate
    aliases: list[str] = []
    if isinstance(signatories, list):
        for row in signatories:
            if isinstance(row, dict) and row.get("client_alias"):
                aliases.append(str(row["client_alias"]))
    return {
        "legal_name": legal_name,
        "domain": domain,
        "aliases": aliases,
        "address_lines": address_lines,
    }


async def _resolve_client(
    session: AsyncSession, signals: dict[str, Any]
) -> tuple[uuid.UUID | None, Decimal | None, list[dict[str, Any]]]:
    """Match against clients + aliases; return (client_id, confidence, candidates).

    Returns ``(client_id, confidence, [])`` when a decisive match wins.
    Returns ``(None, None, [top-3 candidates])`` when the resolver needs
    a picker (bulk pipeline treats this as ``needs_review``).
    """

    legal = (signals.get("legal_name") or "").strip()
    if not legal:
        return None, None, []

    # Pull all clients + aliases in one shot — the corpus is small.
    clients = list((await session.execute(select(Client))).scalars())
    aliases = list((await session.execute(select(ClientAlias))).scalars())
    by_alias: dict[uuid.UUID, list[str]] = {}
    for a in aliases:
        by_alias.setdefault(a.client_id, []).append(a.alias)

    scored: list[tuple[Client, Decimal]] = []
    for c in clients:
        # Exact case-insensitive
        if c.name.strip().lower() == legal.lower():
            scored.append((c, Decimal("1.000")))
            continue
        alias_hits = by_alias.get(c.id, [])
        if any(a.strip().lower() == legal.lower() for a in alias_hits):
            scored.append((c, Decimal("0.900")))
            continue
        # Fuzzy on name + aliases.
        candidate_strings = [c.name] + alias_hits
        best_ratio = max(
            (fuzz.token_set_ratio(legal, s) for s in candidate_strings),
            default=0,
        )
        if best_ratio >= 85:
            # Normalise 0-100 → 0-1 to 3 dp.
            scored.append((c, Decimal(str(best_ratio / 100)).quantize(Decimal("0.001"))))

    scored.sort(key=lambda t: t[1], reverse=True)
    if not scored:
        return None, None, []

    top = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else Decimal("0")
    if top[1] >= CLIENT_MATCH_MIN_SCORE and (top[1] - second_score) >= CLIENT_MATCH_MIN_GAP:
        return top[0].id, top[1], []

    candidates = [
        {"client_id": str(c.id), "name": c.name, "confidence": format(score, "f")}
        for (c, score) in scored[:3]
    ]
    return None, None, candidates


async def _ensure_opportunity(
    session: AsyncSession,
    *,
    client_id: uuid.UUID,
    owner_id: uuid.UUID,
    source: str,
) -> Opportunity:
    """Create an Opportunity (never HubSpot-linked) for a bulk import."""

    opp = Opportunity(
        id=uuid.uuid4(),
        hubspot_deal_id=None,
        owner_id=owner_id,
        client_id=client_id,
        governance_status="Intake",
    )
    # ``source`` column was added by 0028; set only when the attribute exists.
    if hasattr(opp, "source"):
        setattr(opp, "source", source)
    session.add(opp)
    await session.flush()
    return opp


async def _persist_sow_version(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    uploader_id: uuid.UUID,
    file_bytes: bytes,
    file_hash: str,
    extracted_fields: dict[str, Any] | None,
    source: str,
) -> SowVersion:
    """Create a ``sow`` row (if missing) + one ``sow_version``.

    Legacy imports land with ``governance_status='legacy_not_evidenced'``
    and ``execution_state='draft'``; the pipeline never sets
    ``approval_evidenced=True``.
    """

    sow_row = (
        await session.execute(
            select(Sow).where(Sow.opportunity_id == opportunity.id)
        )
    ).scalar_one_or_none()
    if sow_row is None:
        sow_row = Sow(id=uuid.uuid4(), opportunity_id=opportunity.id)
        session.add(sow_row)
        await session.flush()

    # Number the version. The model default is 1, which is right for the
    # first one and a unique-index collision for every one after it — the
    # ordinal has to be computed against what is already stored.
    from app.services.sow_lifecycle import reserve_version_no

    version = SowVersion(
        id=uuid.uuid4(),
        sow_id=sow_row.id,
        uploaded_by=uploader_id,
        file_s3_key=f"bulk-import/{file_hash}",
        file_hash=file_hash,
        extract_status="complete" if extracted_fields else "manual_required",
        extracted_fields=_wrap_extract_for_storage(extracted_fields),
        version_no=await reserve_version_no(session, sow_row.id),
    )
    if hasattr(version, "governance_status"):
        setattr(
            version,
            "governance_status",
            "legacy_not_evidenced" if source == "bulk_import" else None,
        )
    if hasattr(version, "execution_state"):
        # Executed once a signatory row lands in the extract; otherwise draft.
        setattr(
            version,
            "execution_state",
            "executed" if _has_signatory(extracted_fields) else "draft",
        )
    session.add(version)
    await session.flush()
    return version


def _wrap_extract_for_storage(
    fields: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Wrap raw extract fields with provenance for persistence."""

    if fields is None:
        return None
    out: dict[str, Any] = {}
    for name, entry in fields.items():
        if isinstance(entry, dict) and "value" in entry:
            out[name] = wrap_provenance(
                entry.get("value"),
                provenance="extracted",
                page_ref=entry.get("page_ref"),
                confidence=entry.get("confidence"),
                status=entry.get("status", "unconfirmed"),
            )
        else:
            out[name] = wrap_provenance(entry, provenance="extracted", status="unconfirmed")
    return out


def _has_signatory(fields: dict[str, Any] | None) -> bool:
    if not fields:
        return False
    sig = fields.get("signatories")
    if isinstance(sig, dict):
        sig = sig.get("value")
    if isinstance(sig, list) and sig:
        return True
    return False


async def _run_auto_staff_and_gm(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    sow_version: SowVersion,
    engagement_type: str,
    uploader_id: uuid.UUID,
) -> tuple[Any | None, list[str]]:
    """Run auto-staffing + auto-GM; return (gm_model, warnings).

    Never blocks the pipeline: any failure surfaces as a warning on the
    import file so the human can rebuild the model in the SOW workspace.
    """

    warnings: list[str] = []
    try:
        staffing = await auto_staff(engagement_type, sow_version.extracted_fields)
    except Exception as exc:  # noqa: BLE001 — never crash the batch
        return None, [f"auto-staff failed: {exc}"]
    warnings.extend(staffing.warnings)
    payload_rows = lines_to_payload_dicts(staffing.lines)
    if not payload_rows:
        return None, warnings + ["no staffing lines proposed"]
    try:
        parsed = [
            parse_resource_line(r, field=f"resource_lines[{i}]")
            for i, r in enumerate(payload_rows)
        ]
        payload = GmModelPayload(
            engagement_type=engagement_type,
            sow_version_id=sow_version.id,
            delivery_pattern=None,
            contingency_pct=None,
            warranty_days=None,
            resource_lines=parsed,
            cost_lines=[],
            phases=[],
        )
        gm = await create_gm_model_version(
            session,
            opportunity_id=opportunity.id,
            payload=payload,
            actor_id=uploader_id,
        )
        return gm, warnings
    except Exception as exc:  # noqa: BLE001
        return None, warnings + [f"auto-GM failed: {exc}"]


def _extract_term_end(fields: dict[str, Any] | None) -> date | None:
    if not fields:
        return None
    entry = fields.get("term_end")
    raw = entry.get("value") if isinstance(entry, dict) else entry
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    return None


async def _schedule_renewal_if_executed(
    session: AsyncSession,
    *,
    opportunity: Opportunity,
    sow_version: SowVersion,
) -> None:
    """Open a renewal review if the imported SOW is executed + has term_end.

    A SOW already inside its notice window (term_end - 60d < today) opens
    the review immediately. Idempotent per (opportunity, term_end).
    """

    execution_state = getattr(sow_version, "execution_state", "draft")
    if execution_state != "executed":
        return
    term_end = _extract_term_end(sow_version.extracted_fields)
    if term_end is None:
        return
    from app.services.renewals import open_renewal

    today = datetime.now(UTC).date()
    trigger = term_end - timedelta(days=NOTICE_WINDOW_DAYS)
    # If the SOW is already inside its notice window, the trigger is today.
    if trigger < today:
        trigger = today
    await open_renewal(
        session,
        opportunity=opportunity,
        term_end=term_end,
        trigger_date=trigger,
    )


# ---- second dedupe pass --------------------------------------------------


async def _find_business_key_duplicate(
    session: AsyncSession,
    *,
    client_id: uuid.UUID | None,
    fields: dict[str, Any] | None,
) -> uuid.UUID | None:
    """Match on (client_id, title, term_start, term_end) — a business key.

    Used as the second dedupe pass per S10-02 §"Second dedupe pass". Runs
    after the hash dedupe, so the caller only invokes it for SOWs the
    hash pass missed.
    """

    if client_id is None or not fields:
        return None
    title = value_of(fields.get("scope_summary"))
    term_start = _extract_term_end({"term_end": fields.get("term_start")})
    term_end = _extract_term_end(fields)
    if not title or term_start is None or term_end is None:
        return None
    stmt = (
        select(SowVersion)
        .join(Sow, Sow.id == SowVersion.sow_id)
        .join(Opportunity, Opportunity.id == Sow.opportunity_id)
        .where(Opportunity.client_id == client_id)
    )
    rows = list((await session.execute(stmt)).scalars())
    for r in rows:
        r_fields = r.extracted_fields or {}
        r_title = value_of(r_fields.get("scope_summary"))
        r_end = _extract_term_end(r_fields)
        r_start = _extract_term_end({"term_end": r_fields.get("term_start")})
        if r_title == title and r_start == term_start and r_end == term_end:
            return r.id
    return None


# ---- public entry --------------------------------------------------------


async def apply_pipeline(
    session: AsyncSession,
    *,
    file_bytes: bytes,
    uploader_id: uuid.UUID,
    source: str,
    content_type: str | None = None,
    bedrock: BedrockSowExtract | None = None,
) -> PipelineResult:
    """Drive one SOW/MSA/NDA file through the full derive chain.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the uploaded document (PDF/DOCX). The bytes are
        hashed inside the pipeline so callers do not pre-hash.
    uploader_id:
        User the resulting opportunity + sow_version + audit rows belong
        to.
    source:
        ``'sow_upload'`` or ``'bulk_import'``. Threaded into the
        opportunity's ``source`` column and used to decide governance
        defaults (bulk lands as ``legacy_not_evidenced``).
    bedrock:
        Optional Bedrock adapter override (tests pass a
        :class:`StubBedrock`).

    Returns
    -------
    PipelineResult:
        A snapshot of what was created/detected. The caller updates its
        own envelope (``SowUploadJob`` for singles, ``ImportFile`` for
        bulk) with these fields. Never raises for expected failure
        modes — every terminal outcome carries a matching
        :class:`PipelineOutcome`.
    """

    file_hash = sha256_hex(file_bytes)

    # 1. Hash-first dedupe.
    existing = await find_sow_by_hash(session, file_hash)
    if existing is not None:
        opp_id = None
        row = (
            await session.execute(select(Sow).where(Sow.id == existing.sow_id))
        ).scalar_one_or_none()
        if row is not None:
            opp_id = row.opportunity_id
        return PipelineResult(
            outcome=PipelineOutcome.DUPLICATE,
            sha256=file_hash,
            duplicate_of=existing.id,
            sow_version_id=existing.id,
            opportunity_id=opp_id,
        )

    # 2. Read the text once — both the type gate and the extractor use it.
    #    A file we cannot open is REJECTED, not raised: bulk import must
    #    never crash the batch over one bad file. `detected_type` is
    #    "unreadable" (not "other") so the caller can tell "we could not open
    #    this" apart from "this is not a SOW" and say so to the user.
    try:
        text_doc = extract_document_text(file_bytes, content_type)
    except UnreadableDocument as exc:
        return PipelineResult(
            outcome=PipelineOutcome.REJECTED,
            sha256=file_hash,
            detected_type="unreadable",
            errors=[exc.reason],
        )

    # 3. Document-type gate.
    doc = _classify_type(file_bytes, content_type)
    if doc.type not in ALLOWED_START_TYPES:
        return PipelineResult(
            outcome=PipelineOutcome.REJECTED,
            sha256=file_hash,
            detected_type=doc.type,
            errors=[
                f"file is not a SOW/MSA/NDA (detected: {doc.type})",
            ],
        )

    # 3. MSA / NDA: file against a legal entity — no SOW created.
    if doc.type in ("msa", "nda"):
        return PipelineResult(
            outcome=PipelineOutcome.IMPORTED,
            sha256=file_hash,
            detected_type=doc.type,
            warnings=[
                f"{doc.type.upper()} filed against a legal entity — no SOW created"
            ],
        )

    # 4. SOW path: extract.
    ex = await _run_extract(text_doc, bedrock=bedrock)
    fields = ex.fields
    warnings: list[str] = []
    if ex.error is not None:
        warnings.append(ex.error)

    # 5. Client resolution.
    signals = _client_signals(fields or {})
    client_id, confidence, candidates = await _resolve_client(session, signals)

    if client_id is None:
        # S10-01 story maps this to NEEDS_PICK. Bulk callers (S10-02)
        # treat it the same as NEEDS_REVIEW — no DB rows yet.
        create_new = {
            "legal_name": signals.get("legal_name"),
            "domain": signals.get("domain"),
            "address_lines": signals.get("address_lines") or [],
        }
        return PipelineResult(
            outcome=PipelineOutcome.NEEDS_PICK,
            sha256=file_hash,
            detected_type=doc.type,
            detected_confidence=doc.confidence,
            warnings=warnings + ["client resolver could not lock a match"],
            needs_pick_candidates=candidates,
            extract_fields=fields,
            extract_model=ex.model,
            extract_prompt_version=ex.prompt_version,
            client_signals=signals,
            create_new=create_new,
        )

    # 5a. Second dedupe pass on business key.
    business_dupe = await _find_business_key_duplicate(
        session, client_id=client_id, fields=fields
    )
    if business_dupe is not None:
        return PipelineResult(
            outcome=PipelineOutcome.DUPLICATE,
            sha256=file_hash,
            detected_type=doc.type,
            duplicate_of=business_dupe,
            matched_client_id=client_id,
            matched_confidence=confidence,
            sow_version_id=business_dupe,
        )

    # 6. Opportunity + sow_version.
    opportunity = await _ensure_opportunity(
        session, client_id=client_id, owner_id=uploader_id, source=source
    )
    # Record what a `page_ref` on this version actually refers to. A PDF's
    # refs are page numbers; a Word file has no pages, so its refs are body
    # block ordinals. Storing the unit means the confirm screen can cite
    # provenance truthfully instead of labelling every ref "p." — and it is
    # the one piece of context a reader needs to verify a field against the
    # source document.
    if fields is not None:
        metadata = dict(fields.get("metadata") or {})
        metadata["ref_unit"] = text_doc.ref_unit
        metadata["document_kind"] = text_doc.kind
        fields = {**fields, "metadata": metadata}

    sow_version = await _persist_sow_version(
        session,
        opportunity=opportunity,
        uploader_id=uploader_id,
        file_bytes=file_bytes,
        file_hash=file_hash,
        extracted_fields=fields,
        source=source,
    )
    await append_audit(
        session,
        actor_id=uploader_id,
        action="sow.imported",
        entity="sow_version",
        entity_id=str(sow_version.id),
        before=None,
        after={
            "opportunity_id": str(opportunity.id),
            "source": source,
            "governance_status": getattr(sow_version, "governance_status", None),
            "execution_state": getattr(sow_version, "execution_state", None),
            "file_hash": file_hash,
        },
    )

    # 7. Classify + auto-staff + auto-GM.
    classifier = classify_engagement(sow_version.extracted_fields)
    engagement_type = classifier.primary.type
    _gm, gm_warnings = await _run_auto_staff_and_gm(
        session,
        opportunity=opportunity,
        sow_version=sow_version,
        engagement_type=engagement_type,
        uploader_id=uploader_id,
    )
    warnings.extend(gm_warnings)

    # 8. Renewal schedule (only when executed).
    await _schedule_renewal_if_executed(
        session, opportunity=opportunity, sow_version=sow_version
    )

    outcome = (
        PipelineOutcome.NEEDS_REVIEW
        if warnings or not classifier.auto_confirm
        else PipelineOutcome.IMPORTED
    )
    return PipelineResult(
        outcome=outcome,
        sha256=file_hash,
        detected_type=doc.type,
        detected_confidence=doc.confidence,
        opportunity_id=opportunity.id,
        sow_version_id=sow_version.id,
        matched_client_id=client_id,
        matched_confidence=confidence,
        warnings=warnings,
    )


__all__ = [
    "CLIENT_MATCH_MIN_GAP",
    "CLIENT_MATCH_MIN_SCORE",
    "PipelineOutcome",
    "PipelineResult",
    "apply_pipeline",
    "find_sow_by_hash",
    "sha256_hex",
]
