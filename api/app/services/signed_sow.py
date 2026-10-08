"""S5 E8 — signed SOW verify + distribution (build-guide §6.7).

Every state change here writes an ``audit_event`` in the same
transaction (CLAUDE.md rule 5) and — when the story calls for it —
queues a notification via :func:`app.services.notifications.queue_notification`.
Money never lands as a float; the price diff uses :class:`Decimal`
(CLAUDE.md rule 2 / blueprint §2). ``signed_sow_upload`` rows are
immutable versions (rule 4) except for the state-machine columns
``verify_status`` / ``diff_json`` / ``verified_at`` / ``released_at``,
which the state machine below is the *only* writer of.

Flow:

    create_upload(package_id, s3_key, hash)          # verify_status=pending
        │
        ├── verify(upload_id, bedrock)               # → verified | blocked
        │
        └── release(upload_id, ses)                  # verified only
              ├── SES → owner + delivery + finance + legal
              ├── kickoff + billing_setup tasks
              ├── renewal row opened
              └── approvals.mark_released(package)   # → released

Re-uploading a fresh executed pdf for the same package creates a new
:class:`SignedSowUpload` row and audits ``signed_sow.replaced`` on the
prior row so its verification state is invalidated for the audit trail.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import anyio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.integrations.bedrock_sow_extract import (
    BedrockSowExtract,
    ExtractedFields,
    ManualRequired,
)
from app.integrations.ses import SESClient
from app.models.approval import ApprovalPackage
from app.models.opportunity import Opportunity
from app.models.renewal import Renewal
from app.models.signed_sow import SIGNER_STATES, VERIFY_STATUSES, SignedSowUpload
from app.models.sow import SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.approvals import ApprovalError, load_package, mark_released
from app.services.notifications import queue_notification
from app.services.renewals import compute_alert_date


# ---- errors --------------------------------------------------------------


class SignedSowError(HTTPException):
    """Base error surfaced by the router as-is."""


# ---- diff engine ---------------------------------------------------------


# The five "material terms" the story locks against.
#
# S20 W7 (item 1): ``signatories`` joins the diff. The approved SOW's
# signatory list (the names the Legal review signed off on) must match
# the executed PDF's signatory block. A different set of names is a
# material change — a stranger countersigning the SOW is exactly the
# kind of silent swap we need to catch before release.
_MATERIAL_FIELDS: tuple[str, ...] = (
    "price",
    "term_start",
    "term_end",
    "scope_summary",
    "signatories",
)

# Text similarity threshold for the scope diff. Below this the row lands
# blocked with the mismatch captured in ``diff_json``.
_SCOPE_SIMILARITY_THRESHOLD = 0.9

def _to_decimal(raw: Any) -> Decimal | None:
    """Best-effort ``Decimal`` cast for the price diff.

    ``None`` / empty / un-parseable values return ``None`` so the diff
    surfaces a "missing" mismatch rather than raising.
    """

    if raw is None:
        return None
    try:
        value = Decimal(str(raw).strip())
        return value if value.is_finite() else None
    except (InvalidOperation, ValueError, AttributeError):
        return None


def _to_date(raw: Any) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _field_value(payload: dict[str, Any] | None, name: str) -> Any:
    if not payload:
        return None
    entry = payload.get(name)
    if isinstance(entry, dict):
        return entry.get("value")
    return entry


def _scope_similarity(a: str | None, b: str | None) -> float:
    """Character-level ratio via :class:`difflib.SequenceMatcher`.

    Not a business number — just a similarity score used to gate the
    scope diff. Whitespace + case are normalised so trivial cosmetic
    changes do not trip the threshold.
    """

    left = (a or "").strip().lower()
    right = (b or "").strip().lower()
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _price_value(raw: Any, currency: Any) -> tuple[Decimal | None, str | None]:
    context = str(currency).strip().upper() if currency is not None else None
    if context is not None and not re.fullmatch(r"[A-Z]{3}", context):
        return None, None
    parsed = re.fullmatch(
        r"(?:(?P<prefix>[A-Za-z]{3}|\$)\s*)?"
        r"(?P<amount>[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?)"
        r"\s*(?P<suffix>[A-Za-z]{3})?", str(raw).strip(),
    )
    if parsed is None:
        return None, context
    prefix, suffix = parsed["prefix"], parsed["suffix"]
    if prefix == "$":
        # A dollar sign alone does not establish which dollar currency it is.
        dollar_currency = context or (suffix.upper() if suffix else None)
        if dollar_currency not in {"USD", "CAD", "AUD", "NZD", "SGD", "HKD"}:
            return None, context
        prefix = dollar_currency
    currencies = {value.upper() for value in (context, prefix, suffix) if value}
    if len(currencies) > 1:
        return None, context
    return _to_decimal(parsed["amount"].replace(",", "")), next(iter(currencies), None)


def _diff_price(approved: Any, extracted: Any, approved_currency: Any = None,
                extracted_currency: Any = None) -> dict[str, Any]:
    ap, ac = _price_value(approved, approved_currency)
    ex, ec = _price_value(extracted, extracted_currency)
    match = ap is not None and ex is not None and ap == ex and ac == ec
    return {
        "field": "price",
        "approved": str(approved) if approved is not None else None,
        "extracted": str(extracted) if extracted is not None else None,
        "approved_currency": ac,
        "extracted_currency": ec,
        "match": match,
    }


def _diff_date(field: str, approved: Any, extracted: Any) -> dict[str, Any]:
    ap = _to_date(approved)
    ex = _to_date(extracted)
    match = ap is not None and ex is not None and ap == ex
    return {
        "field": field,
        "approved": ap.isoformat() if ap else None,
        "extracted": ex.isoformat() if ex else None,
        "match": match,
    }


def _diff_scope(approved: Any, extracted: Any) -> dict[str, Any]:
    ap_text = "" if approved is None else str(approved)
    ex_text = "" if extracted is None else str(extracted)
    ratio = _scope_similarity(ap_text, ex_text)
    return {
        "field": "scope_summary",
        "approved": ap_text or None,
        "extracted": ex_text or None,
        "similarity": round(ratio, 4),
        "threshold": _SCOPE_SIMILARITY_THRESHOLD,
        "match": ratio >= _SCOPE_SIMILARITY_THRESHOLD,
    }


# ---- signatory diff (S20 W7 item 1) --------------------------------------


def _normalise_signatory_name(raw: Any) -> str:
    """Canonical name string for signatory comparison.

    Accepts either a bare string (legacy rows) or the standard
    ``{name, role}`` dict. Whitespace + case + punctuation are
    folded so trivial cosmetic variation (``"J. Doe"`` vs ``"J Doe"``)
    does not trip the diff — but a different human still does.
    """

    if isinstance(raw, dict):
        name = raw.get("name") or raw.get("value") or ""
    else:
        name = raw or ""
    text = str(name).strip().lower()
    # Collapse interior whitespace + strip trailing punctuation that
    # OCR routinely attaches ("J. Doe," → "j doe").
    text = " ".join(text.split())
    text = text.rstrip(".,;:")
    return text


def _signatory_names(raw: Any) -> list[str]:
    """Return the normalised, de-duped signatory name list from an extract
    value.

    The extract carries ``[{"name": "...", "role": "..."}, ...]``. We
    only diff on the name identity — role mismatches are a Legal-review
    concern, not a signature-verification concern (the point of this
    diff is "did the people we approved actually sign").
    """

    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for row in raw:
        canonical = _normalise_signatory_name(row)
        if canonical and canonical not in seen:
            seen.append(canonical)
    return seen


def _diff_signatories(approved: Any, extracted: Any) -> dict[str, Any]:
    """Compare approved vs executed signatory name sets.

    Match rule (S20 W7 item 1): the sets must be equal. A missing name
    (approved signer not on the executed doc) or an unexpected name (a
    name on the executed doc nobody approved) is a mismatch. The diff
    payload names the two sides so the UI's inline editor can render
    "add Jane Doe" / "remove Someone Else" affordances.
    """

    approved_names = _signatory_names(approved)
    extracted_names = _signatory_names(extracted)
    # A source SOW does not always name its eventual signing parties. In that
    # case there is no approved identity set to compare against, so do not
    # invent one from approval reviewers or reject the executed document for
    # containing real signatures. When the source does name signers, the
    # equality check below remains strict.
    if not approved_names:
        return {
            "field": "signatories",
            "approved": [],
            "extracted": extracted_names,
            "missing": [],
            "unexpected": [],
            "enforced": False,
            "match": True,
        }
    approved_set = set(approved_names)
    extracted_set = set(extracted_names)
    missing = sorted(approved_set - extracted_set)
    unexpected = sorted(extracted_set - approved_set)
    return {
        "field": "signatories",
        "approved": approved_names,
        "extracted": extracted_names,
        "missing": missing,
        "unexpected": unexpected,
        "enforced": True,
        "match": not missing and not unexpected,
    }


@dataclass(frozen=True)
class DiffResult:
    """Structured diff persisted verbatim as ``signed_sow_upload.diff_json``."""

    fields: list[dict[str, Any]]

    @property
    def all_match(self) -> bool:
        return all(f["match"] for f in self.fields)

    def to_json(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "match": self.all_match,
        }


def compute_diff(
    approved: dict[str, Any] | None, extracted: dict[str, Any] | None
) -> DiffResult:
    """Diff the four material fields between the approved + extracted payloads.

    ``approved`` is the pinned ``sow_version.extracted_fields`` block from
    the ready-to-sign package. ``extracted`` is the fresh Bedrock output
    on the executed pdf. Both use the ``{value, page_ref, status}`` shape.
    """

    fields: list[dict[str, Any]] = [
        _diff_price(
            _field_value(approved, "price"), _field_value(extracted, "price"),
            _field_value(approved, "currency"), _field_value(extracted, "currency"),
        ),
        _diff_date(
            "term_start",
            _field_value(approved, "term_start"),
            _field_value(extracted, "term_start"),
        ),
        _diff_date(
            "term_end",
            _field_value(approved, "term_end"),
            _field_value(extracted, "term_end"),
        ),
        _diff_scope(
            _field_value(approved, "scope_summary"),
            _field_value(extracted, "scope_summary"),
        ),
        _diff_signatories(
            _field_value(approved, "signatories"),
            _field_value(extracted, "signatories"),
        ),
    ]
    return DiffResult(fields=fields)


# ---- read helpers --------------------------------------------------------


async def _load_package_or_error(
    session: AsyncSession, package_id: uuid.UUID
) -> ApprovalPackage:
    try:
        return await load_package(session, package_id)
    except ApprovalError as exc:
        raise SignedSowError(status_code=exc.status_code, detail=exc.detail) from exc


async def _load_upload(
    session: AsyncSession, upload_id: uuid.UUID
) -> SignedSowUpload:
    row = (
        await session.execute(
            select(SignedSowUpload).where(SignedSowUpload.id == upload_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise SignedSowError(status_code=404, detail="signed_sow_upload not found")
    return row


async def latest_upload_for(
    session: AsyncSession, package_id: uuid.UUID
) -> SignedSowUpload | None:
    """Newest :class:`SignedSowUpload` for a package, if any."""

    stmt = (
        select(SignedSowUpload)
        .where(SignedSowUpload.package_id == package_id)
        .order_by(SignedSowUpload.uploaded_at.desc(), SignedSowUpload.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _load_sow_version(
    session: AsyncSession, sow_version_id: uuid.UUID
) -> SowVersion:
    row = (
        await session.execute(
            select(SowVersion).where(SowVersion.id == sow_version_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise SignedSowError(status_code=404, detail="pinned sow_version not found")
    return row


async def _require_current_callback(
    session: AsyncSession, upload: SignedSowUpload
) -> tuple[ApprovalPackage, SowVersion]:
    """Refuse a signature callback that no longer targets current economics.

    `verify`, `mark_declined` and `mark_expired` can arrive late — an
    external signer replying after the package was voided, released or
    superseded, after the upload was replaced by a re-upload, or after an
    amendment superseded the pinned SOW version. Accepting any of those
    would record a signature outcome against stale economics (S21-16,
    T14.07), so each one is a 409 and the upload row stays untouched.
    """

    package = await _load_package_or_error(session, upload.package_id)
    if package.superseded_by is not None:
        raise SignedSowError(
            status_code=409,
            detail=(
                f"package has been superseded by {package.superseded_by}; "
                "the signature outcome belongs to the newer package"
            ),
        )
    if package.status != "ready_to_sign":
        raise SignedSowError(
            status_code=409,
            detail=(
                f"package is {package.status!r}; a signature callback is "
                "only valid while it is 'ready_to_sign'"
            ),
        )
    pinned = await _load_sow_version(session, package.sow_version_id)
    if pinned.superseded_by is not None or pinned.discarded_at is not None:
        raise SignedSowError(
            status_code=409,
            detail=(
                "the pinned SOW version was superseded or discarded; "
                "re-route approvals on the current version before signing"
            ),
        )
    # Replaced = a strictly newer upload exists. A timestamp tie is not
    # treated as replacement: the stored clock is second-granular on the
    # test engine, and a real late callback arrives long after the
    # re-upload, never inside the same instant.
    import sqlalchemy as sa

    newest = await session.scalar(
        sa.select(sa.func.max(SignedSowUpload.uploaded_at)).where(
            SignedSowUpload.package_id == upload.package_id
        )
    )
    def _utc(value):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    if newest is not None and _utc(upload.uploaded_at) < _utc(newest):
        raise SignedSowError(
            status_code=409,
            detail=(
                "this signed upload was replaced by a newer one; the "
                "callback must target the current upload"
            ),
        )
    return package, pinned


# ---- create --------------------------------------------------------------


async def _require_signature_eligibility(session, package):
    from app.services.approval_workflow import require_signature_eligibility
    from app.services.approvals import ApprovalError
    try:
        await require_signature_eligibility(session, package)
    except ApprovalError as exc:
        raise SignedSowError(status_code=exc.status_code, detail=exc.detail) from exc


async def create_upload(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    package_id: uuid.UUID,
    file_s3_key: str,
    file_hash: str,
    has_signature_evidence: bool = True,
) -> SignedSowUpload:
    """Register a new signed-pdf upload against ``package_id``.

    Requires the package to be in status ``ready_to_sign``. A re-upload
    creates a fresh row and audits ``signed_sow.replaced`` on the
    previous row so the audit trail can reconstruct the sequence
    (rule 4: rows are set-once; a new version replaces).

    S20 W7 (T22): if ``has_signature_evidence`` is False (the caller
    could not detect a signature-form field, an image signature, or a
    DocuSign/HelloSign envelope id), the upload is refused with 400 —
    upload alone is never `verified`. Superseded packages are also
    refused (409) so a stale UI cannot submit against an old package.
    """

    if not has_signature_evidence:
        raise SignedSowError(
            status_code=400,
            detail=(
                "unsigned upload rejected — the executed document must "
                "carry signature evidence (form-field signature, image "
                "or external envelope id). Upload alone is not execution."
            ),
        )

    package = await _load_package_or_error(session, package_id)
    if package.superseded_by is not None:
        raise SignedSowError(
            status_code=409,
            detail=(
                f"package has been superseded by {package.superseded_by}; "
                "signature belongs to the newer package"
            ),
        )
    if package.status != "ready_to_sign":
        raise SignedSowError(
            status_code=409,
            detail=(
                f"package is {package.status!r}; must be 'ready_to_sign' "
                "before a signed SOW can be uploaded"
            ),
        )

    await _require_signature_eligibility(session, package)
    previous = await latest_upload_for(session, package_id)

    upload = SignedSowUpload(
        id=uuid.uuid4(),
        package_id=package_id,
        file_s3_key=file_s3_key,
        file_hash=file_hash,
        uploaded_by=actor_id,
        verify_status="pending",
        verify_reason=None,
        signer_state="signed",
    )
    session.add(upload)
    await session.flush()

    await append_audit(
        session,
        actor_id=actor_id,
        action="signed_sow.uploaded",
        entity="signed_sow_upload",
        entity_id=str(upload.id),
        before=None,
        after={
            "package_id": str(package_id),
            "file_s3_key": file_s3_key,
            "file_hash": file_hash,
            "verify_status": "pending",
        },
    )

    if previous is not None and previous.id != upload.id:
        # A re-upload voids the earlier verification for audit purposes.
        # We do not mutate the previous row's ``verify_status`` (row is
        # set-once for that field once flipped by ``verify``); the audit
        # ``signed_sow.replaced`` is the trail marker.
        await append_audit(
            session,
            actor_id=actor_id,
            action="signed_sow.replaced",
            entity="signed_sow_upload",
            entity_id=str(previous.id),
            before={"verify_status": previous.verify_status},
            after={
                "replaced_by": str(upload.id),
                "package_id": str(package_id),
            },
        )

    await session.commit()
    await session.refresh(upload)
    return upload


# ---- verify --------------------------------------------------------------


async def verify(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    upload_id: uuid.UUID,
    bedrock: BedrockSowExtract,
    file_bytes: bytes = b"",
) -> SignedSowUpload:
    """Re-run the Bedrock extract on the signed pdf and diff the terms.

    Threshold: exact match on price + term_start + term_end; text
    similarity ≥ 0.9 on scope_summary. Verified on all-match, blocked
    otherwise. The diff lands verbatim in ``diff_json`` so the UI can
    render a side-by-side view without re-fetching.
    """

    upload = await _load_upload(session, upload_id)
    package, pinned = await _require_current_callback(session, upload)

    try:
        from app.services.document_text import extract_document_text

        if not file_bytes or hashlib.sha256(file_bytes).hexdigest() != upload.file_hash.removeprefix("sha256:"):
            raw = ManualRequired(reason="stored document hash mismatch or empty document")
        else:
            document = await anyio.to_thread.run_sync(extract_document_text, file_bytes)
            raw = await anyio.to_thread.run_sync(bedrock.extract, document)
    except Exception as exc:  # noqa: BLE001 — LLM safety net
        raw = ManualRequired(reason=f"bedrock failed: {exc}")

    new_reason: str | None = None
    if isinstance(raw, ManualRequired):
        # No extract → we cannot verify. Block with a machine-readable
        # marker so the UI shows the "manual review" state.
        diff_payload: dict[str, Any] = {
            "fields": [],
            "match": False,
            "reason": raw.reason,
        }
        new_status = "blocked"
        new_reason = f"bedrock_manual_required: {raw.reason}"
    elif isinstance(raw, ExtractedFields):
        extracted_map = raw.fields
        diff = compute_diff(pinned.extracted_fields, extracted_map)
        diff_payload = diff.to_json()
        if diff.all_match:
            new_status = "verified"
        else:
            new_status = "blocked"
            # Name the first failing field so the UI + audit have a
            # specific pointer rather than a generic "diff failed".
            failed = next(
                (f for f in diff.fields if not f["match"]), None
            )
            if failed is not None:
                new_reason = f"{failed['field']}_mismatch"
    else:
        diff_payload = {
            "fields": [],
            "match": False,
            "reason": f"bedrock returned {type(raw).__name__}",
        }
        new_status = "blocked"
        new_reason = f"bedrock_unexpected: {type(raw).__name__}"

    before = {"verify_status": upload.verify_status, "verify_reason": upload.verify_reason}
    upload.verify_status = new_status
    upload.verify_reason = new_reason
    upload.diff_json = diff_payload
    if new_status == "verified":
        upload.verified_at = datetime.now(UTC)
    else:
        upload.verified_at = None

    action = "signed_sow.verified" if new_status == "verified" else "signed_sow.blocked"
    await append_audit(
        session,
        actor_id=actor_id,
        action=action,
        entity="signed_sow_upload",
        entity_id=str(upload.id),
        before=before,
        after={
            "verify_status": new_status,
            "verify_reason": new_reason,
            "diff": diff_payload,
        },
    )
    await session.commit()
    await session.refresh(upload)
    return upload


# ---- external signature-request transitions (T22) ------------------------


async def mark_declined(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    upload_id: uuid.UUID,
    reason: str,
) -> SignedSowUpload:
    """Record that the external signer declined the request.

    A declined request is a *separate* status from a verify-diff failure —
    the signer never returned an executed pdf. `verify_status='declined'`
    with `signer_state='declined'`. The caller supplies the reason
    string surfaced by the external service.
    """

    if not reason or not reason.strip():
        raise SignedSowError(
            status_code=400,
            detail="reason required when marking a signature request declined",
        )
    upload = await _load_upload(session, upload_id)
    await _require_current_callback(session, upload)
    before = {
        "verify_status": upload.verify_status,
        "signer_state": upload.signer_state,
        "verify_reason": upload.verify_reason,
    }
    upload.verify_status = "declined"
    upload.signer_state = "declined"
    upload.verify_reason = f"declined_by_signer: {reason.strip()[:400]}"
    upload.verified_at = None
    await append_audit(
        session,
        actor_id=actor_id,
        action="signed_sow.declined",
        entity="signed_sow_upload",
        entity_id=str(upload.id),
        before=before,
        after={
            "verify_status": "declined",
            "signer_state": "declined",
            "verify_reason": upload.verify_reason,
        },
    )
    await session.commit()
    await session.refresh(upload)
    return upload


async def mark_expired(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    upload_id: uuid.UUID,
    reason: str | None = None,
) -> SignedSowUpload:
    """Record that the external signature request expired without a return.

    Separate status from `declined` — the signer never actioned the
    request. UI can offer "Resend to signer" as the next step.
    """

    upload = await _load_upload(session, upload_id)
    await _require_current_callback(session, upload)
    before = {
        "verify_status": upload.verify_status,
        "signer_state": upload.signer_state,
        "verify_reason": upload.verify_reason,
    }
    upload.verify_status = "expired"
    upload.signer_state = "expired"
    upload.verify_reason = (
        f"signature_request_expired: {reason.strip()[:400]}"
        if reason and reason.strip()
        else "signature_request_expired"
    )
    upload.verified_at = None
    await append_audit(
        session,
        actor_id=actor_id,
        action="signed_sow.expired",
        entity="signed_sow_upload",
        entity_id=str(upload.id),
        before=before,
        after={
            "verify_status": "expired",
            "signer_state": "expired",
            "verify_reason": upload.verify_reason,
        },
    )
    await session.commit()
    await session.refresh(upload)
    return upload


# ---- release -------------------------------------------------------------


# Groups pulled off ``users.groups`` to compose the distribution list.
# Kept broad — a missing recipient is silently skipped so the release
# does not fail the whole flow if e.g. no Legal user has been invited yet.
_DISTRIBUTION_GROUPS: tuple[str, ...] = (
    "Delivery",
    "Finance",
    "Legal",
)


async def _distribution_recipients(
    session: AsyncSession, *, owner_id: uuid.UUID
) -> list[User]:
    """Owner + one representative from each configured governance group.

    Story: "account owner + delivery lead + finance leader + legal leader
    (all pulled from ``users`` matching group; guarded if configured
    recipients are missing)". We pick the first user in each group as
    the canonical addressee — a proper notification-setting join is
    Sprint 6 material.
    """

    seen: set[uuid.UUID] = set()
    out: list[User] = []

    owner = (
        await session.execute(select(User).where(User.id == owner_id))
    ).scalar_one_or_none()
    if owner is not None:
        seen.add(owner.id)
        out.append(owner)

    users = list((await session.execute(select(User))).scalars().all())
    for group in _DISTRIBUTION_GROUPS:
        for u in users:
            if group in (u.groups or []) and u.id not in seen:
                seen.add(u.id)
                out.append(u)
                break
    return out


def _distribution_email(package_id: uuid.UUID, upload: SignedSowUpload) -> tuple[str, str]:
    subject = f"Signed SOW released — package {package_id}"
    body = (
        f"The signed SOW for approval package {package_id} has been verified\n"
        f"and released.\n\n"
        f"S3 key: {upload.file_s3_key}\n"
        f"File hash: {upload.file_hash}\n"
        f"Verified at: {upload.verified_at.isoformat() if upload.verified_at else 'n/a'}\n"
    )
    return subject, body


def _term_end_from_pinned(pinned: SowVersion) -> date | None:
    """Read the confirmed ``term_end`` from the pinned sow_version fields."""

    raw = _field_value(pinned.extracted_fields, "term_end")
    return _to_date(raw)


async def _file_task(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    subject: str,
    category: str,
    due_date: date | None,
    actor_id: uuid.UUID,
    related_package_id: uuid.UUID,
) -> Task:
    """Create a task row + audit + queue an inbox notification.

    Kept in-file (rather than delegating to a task helper elsewhere) so
    the whole release flow lands in one transaction and the audit chain
    stays tight.
    """

    task = Task(
        id=uuid.uuid4(),
        owner_id=owner_id,
        subject=subject,
        category=category,
        status="assigned",
        due_date=due_date,
    )
    session.add(task)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="task.created",
        entity="task",
        entity_id=str(task.id),
        before=None,
        after={
            "owner_id": str(owner_id),
            "category": category,
            "subject": subject,
            "related_package_id": str(related_package_id),
        },
    )
    await queue_notification(
        session,
        user_id=owner_id,
        category="task_assigned",
        subject=subject,
        body_md=(
            f"You have a new `{category}` task for approval package "
            f"`{related_package_id}`."
        ),
        related_entity="approval_package",
        related_entity_id=str(related_package_id),
    )
    return task


async def release(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    upload_id: uuid.UUID,
    ses: SESClient,
) -> SignedSowUpload:
    """Distribute the signed SOW and move the package to ``released``.

    Preconditions (**T23 · three distinct events**, all server-enforced):
      1. Internal signoff — Delivery lead approved the package.
      2. Client execution — Upload's ``verify_status == "verified"``.
      3. Delivery acceptance — a ``delivery_acceptance`` row exists.

    Plus:
      - Approvals current (CEO conditions, expiry) via
        :func:`app.services.approval_workflow.require_signature_eligibility`.
      - Package not superseded.

    ``Opportunity.is_closed_won`` is **never** consulted — CRM stage does
    not authorise release. The regression test
    ``test_release_ignores_closed_won`` guards this contract.

    Side effects (all in one transaction):
      1. SES email to owner + Delivery + Finance + Legal leaders.
      2. ``kickoff`` + ``billing_setup`` tasks filed on the owner.
      3. ``renewal`` row opened two calendar months before ``term_end``.
      4. ``project`` row created (or linked, idempotent).
      5. ``approval_package.status`` → ``released``.
    """

    upload = await _load_upload(session, upload_id)
    package = await _load_package_or_error(session, upload.package_id)

    # T23 · three-event release gate. Delegate to services.handoff so
    # this module remains focused on the state-machine + side-effects;
    # the gate module is what the release-gate pytest exercises.
    from app.services.handoff import check_release_gate

    gate = await check_release_gate(session, package)
    if not gate.ok:
        # Audit the refusal *before* raising so the failed-release trail
        # is complete. Refusal is a business event.
        await append_audit(
            session,
            actor_id=actor_id,
            action="handoff.gate_refused",
            entity="approval_package",
            entity_id=str(package.id),
            before=None,
            after=gate.to_json(),
        )
        await session.commit()
        raise SignedSowError(
            status_code=409,
            detail={
                "error": "release_gate_not_met",
                "message": (
                    "release requires internal signoff + verified "
                    "executed document + delivery acceptance — CRM "
                    "Closed Won is not sufficient"
                ),
                "gate": gate.to_json(),
            },
        )

    pinned = await _load_sow_version(session, package.sow_version_id)
    if pinned.superseded_by is not None or pinned.discarded_at is not None:
        raise SignedSowError(
            status_code=409,
            detail=(
                "the pinned SOW version was superseded or discarded; stale "
                "economics cannot be activated — release the current version"
            ),
        )

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == package.opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise SignedSowError(status_code=404, detail="opportunity not found")
    await _require_signature_eligibility(session, package)
    owner_id = opp.owner_id or actor_id

    # 1. SES fan-out. A missing recipient is silently skipped — the log
    # entry in the audit row records the actual recipient set.
    recipients = await _distribution_recipients(session, owner_id=owner_id)
    subject, body = _distribution_email(package.id, upload)
    delivered: list[str] = []
    for user in recipients:
        try:
            await ses.send(to_address=user.email, subject=subject, body_text=body)
        except Exception:  # noqa: BLE001 — one bad address never blocks the release
            continue
        delivered.append(user.email)

    # 2. Kickoff + billing setup tasks (owned by the account owner).
    await _file_task(
        session,
        owner_id=owner_id,
        subject=f"Kickoff — {opp.hubspot_deal_id}",
        category="kickoff",
        due_date=None,
        actor_id=actor_id,
        related_package_id=package.id,
    )
    await _file_task(
        session,
        owner_id=owner_id,
        subject=f"Billing setup — {opp.hubspot_deal_id}",
        category="billing_setup",
        due_date=None,
        actor_id=actor_id,
        related_package_id=package.id,
    )

    # 3. Open the renewal record. ``term_end`` may be missing on a
    # non-fixed engagement; skip cleanly (audit records the reason).
    term_end = _term_end_from_pinned(pinned)
    renewal_row: Renewal | None = None
    if term_end is not None:
        renewal_row = Renewal(
            id=uuid.uuid4(),
            opportunity_id=opp.id,
            term_end=term_end,
            trigger_date=compute_alert_date(term_end),
            status="open",
        )
        session.add(renewal_row)
        await session.flush()
        await append_audit(
            session,
            actor_id=actor_id,
            action="renewal.opened",
            entity="renewal",
            entity_id=str(renewal_row.id),
            before=None,
            after={
                "opportunity_id": str(opp.id),
                "term_end": term_end.isoformat(),
                "trigger_date": renewal_row.trigger_date.isoformat(),
                "status": "open",
                "source": "signed_sow_release",
            },
        )

    # 4. Create-or-link the project row (T24 idempotency guard). Baseline
    # snapshot is frozen at this call; subsequent runs return the same
    # project row and audit `project.linked` instead of `project.created`.
    from app.services.project_lifecycle import create_or_link as project_create_or_link
    project, project_created = await project_create_or_link(
        session, actor_id=actor_id, package=package
    )

    # 4b. Amendment activation (S21-16, T14.04/T14.07). If this opportunity
    # already has a released, unsuperseded contract on a different SOW
    # version, this release *is* the activation: the earlier package and
    # its pinned version are superseded in this same transaction so every
    # signed read (outlook, coverage, rollups) switches to the amendment's
    # effective schedule, and the explicit overlap or gap between the two
    # terms is recorded rather than silently absorbed.
    prior_packages = (
        await session.scalars(
            select(ApprovalPackage).where(
                ApprovalPackage.opportunity_id == opp.id,
                ApprovalPackage.id != package.id,
                ApprovalPackage.status == "released",
                ApprovalPackage.superseded_by.is_(None),
                ApprovalPackage.sow_version_id != package.sow_version_id,
            )
        )
    ).all()
    amendment_start = _to_date(_field_value(pinned.extracted_fields, "term_start"))
    for prior in prior_packages:
        prior.superseded_by = package.id
        prior_version = (
            await _load_sow_version(session, prior.sow_version_id)
            if prior.sow_version_id
            else None
        )
        if (
            prior_version is not None
            and prior_version.superseded_by is None
            and prior_version.id != pinned.id
        ):
            prior_version.superseded_by = pinned.id
        original_end = (
            _term_end_from_pinned(prior_version) if prior_version is not None else None
        )
        overlap_days = gap_days = 0
        if original_end is not None and amendment_start is not None:
            delta = (original_end - amendment_start).days
            if delta >= 0:
                overlap_days = delta + 1  # inclusive calendar days double-covered
            elif delta < -1:
                gap_days = -delta - 1  # uncovered days between the terms
        await append_audit(
            session,
            actor_id=actor_id,
            action="amendment.activated",
            entity="approval_package",
            entity_id=str(package.id),
            before={
                "superseded_package_id": str(prior.id),
                "superseded_version_id": str(prior_version.id)
                if prior_version is not None
                else None,
            },
            after={
                "superseded_package_id": str(prior.id),
                "superseded_version_id": str(prior_version.id)
                if prior_version is not None
                else None,
                "overlap_days": overlap_days,
                "gap_days": gap_days,
                "original_term_end": original_end.isoformat()
                if original_end is not None
                else None,
                "amendment_term_start": amendment_start.isoformat()
                if amendment_start is not None
                else None,
                "amendment_term_end": term_end.isoformat()
                if term_end is not None
                else None,
                "project_id": str(project.id),
            },
        )

    # 5. Move the package to ``released`` + record the upload's release
    # timestamp.  ``mark_released`` audits ``package.released`` for us.
    upload.released_at = datetime.now(UTC)
    await append_audit(
        session,
        actor_id=actor_id,
        action="signed_sow.released",
        entity="signed_sow_upload",
        entity_id=str(upload.id),
        before={"released_at": None},
        after={
            "released_at": upload.released_at.isoformat(),
            "recipients": delivered,
            "renewal_id": str(renewal_row.id) if renewal_row else None,
            "project_id": str(project.id),
            "project_created": project_created,
        },
    )
    # Explicit handoff.gate_passed audit line — the three-event contract
    # deserves a named trail marker distinct from `signed_sow.released`.
    await append_audit(
        session,
        actor_id=actor_id,
        action="handoff.gate_passed",
        entity="approval_package",
        entity_id=str(package.id),
        before=None,
        after=gate.to_json(),
    )
    try:
        await mark_released(session, actor_id=actor_id, package=package)
    except ApprovalError as exc:
        raise SignedSowError(status_code=exc.status_code, detail=exc.detail) from exc

    await session.commit()
    await session.refresh(upload)
    return upload


# ---- serialisation -------------------------------------------------------


def serialize_upload(row: SignedSowUpload) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "package_id": str(row.package_id),
        "file_s3_key": row.file_s3_key,
        "file_hash": row.file_hash,
        "uploaded_by": str(row.uploaded_by),
        "uploaded_at": row.uploaded_at.isoformat() if row.uploaded_at else None,
        "verify_status": row.verify_status,
        "verify_reason": row.verify_reason,
        "signer_state": row.signer_state,
        "diff_json": row.diff_json,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "released_at": row.released_at.isoformat() if row.released_at else None,
    }


__all__ = [
    "SIGNER_STATES",
    "SignedSowError",
    "VERIFY_STATUSES",
    "compute_diff",
    "create_upload",
    "latest_upload_for",
    "mark_declined",
    "mark_expired",
    "release",
    "serialize_upload",
    "verify",
]
