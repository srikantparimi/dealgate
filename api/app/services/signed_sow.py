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
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

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
from app.models.signed_sow import VERIFY_STATUSES, SignedSowUpload
from app.models.sow import SowVersion
from app.models.task import Task
from app.models.user import User
from app.services.approvals import ApprovalError, load_package, mark_released
from app.services.notifications import queue_notification


# ---- errors --------------------------------------------------------------


class SignedSowError(HTTPException):
    """Base error surfaced by the router as-is."""


# ---- diff engine ---------------------------------------------------------


# The four "material terms" the story locks against.
_MATERIAL_FIELDS: tuple[str, ...] = (
    "price",
    "term_start",
    "term_end",
    "scope_summary",
)

# Text similarity threshold for the scope diff. Below this the row lands
# blocked with the mismatch captured in ``diff_json``.
_SCOPE_SIMILARITY_THRESHOLD = 0.9

# The renewal is opened T-60d before the term_end date (build-guide §6.7).
_RENEWAL_LEAD_DAYS = 60


def _to_decimal(raw: Any) -> Decimal | None:
    """Best-effort ``Decimal`` cast for the price diff.

    ``None`` / empty / un-parseable values return ``None`` so the diff
    surfaces a "missing" mismatch rather than raising.
    """

    if raw is None:
        return None
    try:
        return Decimal(str(raw).strip())
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


def _diff_price(approved: Any, extracted: Any) -> dict[str, Any]:
    ap = _to_decimal(approved)
    ex = _to_decimal(extracted)
    match = ap is not None and ex is not None and ap == ex
    return {
        "field": "price",
        "approved": str(approved) if approved is not None else None,
        "extracted": str(extracted) if extracted is not None else None,
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
            _field_value(approved, "price"), _field_value(extracted, "price")
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
) -> SignedSowUpload:
    """Register a new signed-pdf upload against ``package_id``.

    Requires the package to be in status ``ready_to_sign``. A re-upload
    creates a fresh row and audits ``signed_sow.replaced`` on the
    previous row so the audit trail can reconstruct the sequence
    (rule 4: rows are set-once; a new version replaces).
    """

    package = await _load_package_or_error(session, package_id)
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
    package = await _load_package_or_error(session, upload.package_id)
    pinned = await _load_sow_version(session, package.sow_version_id)

    try:
        raw = bedrock.extract(file_bytes)
    except Exception as exc:  # noqa: BLE001 — LLM safety net
        raw = ManualRequired(reason=f"bedrock failed: {exc}")

    if isinstance(raw, ManualRequired):
        # No extract → we cannot verify. Block with a machine-readable
        # marker so the UI shows the "manual review" state.
        diff_payload: dict[str, Any] = {
            "fields": [],
            "match": False,
            "reason": raw.reason,
        }
        new_status = "blocked"
    elif isinstance(raw, ExtractedFields):
        extracted_map = raw.fields
        diff = compute_diff(pinned.extracted_fields, extracted_map)
        diff_payload = diff.to_json()
        new_status = "verified" if diff.all_match else "blocked"
    else:
        diff_payload = {
            "fields": [],
            "match": False,
            "reason": f"bedrock returned {type(raw).__name__}",
        }
        new_status = "blocked"

    before = {"verify_status": upload.verify_status}
    upload.verify_status = new_status
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
            "diff": diff_payload,
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

    Preconditions:
      - Upload's ``verify_status == "verified"`` (else 409).
      - Package is still ``ready_to_sign`` (else 409 via
        :func:`app.services.approvals.mark_released`).

    Side effects (all in one transaction):
      1. SES email to owner + Delivery + Finance + Legal leaders.
      2. ``kickoff`` + ``billing_setup`` tasks filed on the owner.
      3. ``renewal`` row opened with ``trigger_date = term_end - 60d``.
      4. ``approval_package.status`` → ``released``.
    """

    upload = await _load_upload(session, upload_id)
    if upload.verify_status != "verified":
        raise SignedSowError(
            status_code=409,
            detail=(
                f"upload is {upload.verify_status!r}; verify must succeed "
                "before release"
            ),
        )

    package = await _load_package_or_error(session, upload.package_id)
    pinned = await _load_sow_version(session, package.sow_version_id)

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
            trigger_date=term_end - timedelta(days=_RENEWAL_LEAD_DAYS),
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

    # 4. Move the package to ``released`` + record the upload's release
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
        },
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
        "diff_json": row.diff_json,
        "verified_at": row.verified_at.isoformat() if row.verified_at else None,
        "released_at": row.released_at.isoformat() if row.released_at else None,
    }


__all__ = [
    "SignedSowError",
    "VERIFY_STATUSES",
    "compute_diff",
    "create_upload",
    "latest_upload_for",
    "release",
    "serialize_upload",
    "verify",
]
