"""S6 legacy import service — bulk SOW upload + Excel resource import.

Owns the entire vertical for the "legacy: approval not evidenced" rollout
(blueprint §13). All money is ``Decimal`` (CLAUDE.md rule 2). Every
mutation writes an ``audit_event`` in the caller's transaction (rule 5).
Legacy ``sow_version`` rows **never** flip ``approval_evidenced`` to
``True`` — the rollout rule forbids backfilling fake approvals.

Public surface:

- :func:`create_batch` — creates the batch envelope, audits the open.
- :func:`bulk_upload_sows` — for each file in the payload, creates a
  synthetic ``Opportunity`` (governance_status='Legacy'), a ``Sow`` (linked
  to that opportunity + the batch + the client, tagged with ``sow_ref``)
  and a ``SowVersion`` (``legacy=True, approval_evidenced=False``).
- :func:`import_excel` — parses the uploaded ``.xlsx`` via openpyxl,
  validates every row per the template spec, then groups by ``sow_ref``
  and creates one ``GmModel`` + N ``ResourceLine`` rows per group.
  Rejects the whole file if any row is invalid (all-or-nothing).
- :func:`reconcile` — returns matched/unmatched SOWs, orphaned resource
  lines, per-project GM (using the pure ``app.gm`` library) and a
  below-floor list.
- :func:`approve_batch` — flips the batch to ``approved``, files tasks
  against unmatched or incomplete projects. Does NOT create approval
  records for any ``sow_version``.
- :func:`assert_not_legacy_for_approval` — TODO guard. The Sprint 3
  approvals endpoint lands later; this function is what it will call to
  return 403 when the caller tries to approve a legacy row.
"""

from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.core import gross_margin
from app.gm.policy import INDIA_FLOOR, US_FLOOR
from app.models.client import Client
from app.models.gm_model import GmModel, ResourceLine
from app.models.legacy import LegacyImportBatch
from app.models.opportunity import Opportunity
from app.models.sow import Sow, SowVersion
from app.models.task import Task


LEGACY_ROLES: tuple[str, ...] = ("Finance", "CEO", "SystemAdmin")


# ---- Excel template spec (kept in lock-step with docs/backlog/s6-legacy-excel-template.md).

TEMPLATE_COLUMNS: tuple[str, ...] = (
    "sow_ref",
    "client_name",
    "engagement_type",
    "role",
    "seniority",
    "location",
    "start_date",
    "end_date",
    "allocation_pct",
    "billable_hours",
    "hourly_bill_rate",
    "hourly_loaded_cost",
    "currency",
    "revenue_us",
    "revenue_india",
    "notes",
)

ALLOWED_LOCATIONS: frozenset[str] = frozenset({"US", "India"})
ALLOWED_ENGAGEMENT_TYPES: frozenset[str] = frozenset(
    {
        "staff_aug",
        "single_resource",
        "fixed_price",
        "assessment",
        "tm",
        "managed_service",
    }
)
_REVENUE_SPLIT_TYPES: frozenset[str] = frozenset(
    {"fixed_price", "assessment", "managed_service"}
)
ALLOWED_SENIORITY: frozenset[str] = frozenset({"junior", "mid", "senior", "principal"})


# ---- Errors --------------------------------------------------------------


class LegacyImportError(Exception):
    """Raised when a legacy import step fails validation."""

    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


# ---- Dataclass payloads --------------------------------------------------


@dataclass(frozen=True)
class SowUpload:
    s3_key: str
    filename: str
    sow_ref: str
    client_name: str | None = None


@dataclass
class ExcelRow:
    row_number: int  # 1-indexed spreadsheet row (header = 1)
    sow_ref: str
    client_name: str
    engagement_type: str
    role: str
    seniority: str
    location: str
    start_date: date
    end_date: date
    allocation_pct: Decimal
    billable_hours: Decimal
    hourly_bill_rate: Decimal
    hourly_loaded_cost: Decimal
    currency: str
    revenue_us: Decimal | None
    revenue_india: Decimal | None
    notes: str | None


@dataclass
class ProjectGmSnapshot:
    sow_ref: str
    revenue_us: Decimal
    revenue_india: Decimal
    cost_us: Decimal
    cost_india: Decimal
    gm_us: Decimal | None
    gm_india: Decimal | None
    below_floor: bool
    failing: list[str]
    complete: bool


@dataclass
class ReconciliationReport:
    batch_id: uuid.UUID
    status: str
    matched: list[dict[str, Any]] = field(default_factory=list)
    unmatched_sows: list[dict[str, Any]] = field(default_factory=list)
    orphaned_resource_lines: list[dict[str, Any]] = field(default_factory=list)
    project_gm: list[ProjectGmSnapshot] = field(default_factory=list)
    below_floor: list[str] = field(default_factory=list)


# ---- Role gate -----------------------------------------------------------


def assert_role(user_groups: Iterable[str]) -> None:
    """Raise 403 unless the caller is Finance/CEO/SystemAdmin."""

    if not any(r in LEGACY_ROLES for r in user_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="legacy endpoints are Finance/CEO/SystemAdmin only",
        )


def assert_not_legacy_for_approval(sow_version: SowVersion) -> None:
    """Guard the future POST /approvals endpoint from backfilling fake approvals.

    Blueprint §13 rollout: "Import as 'legacy approval not evidenced' and let
    executives disposition them; do not backfill fake approvals." Call this
    from the approvals router (Sprint 3+) before creating an approval row.

    TODO(Sprint 3+): wire this into ``POST /approvals`` once that endpoint
    exists. The message text is intentional — it points reviewers at the
    rollout rule, not at an implementation detail.
    """

    if getattr(sow_version, "legacy", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "cannot create an approval for a legacy sow_version; "
                "blueprint §13 rollout: do not backfill fake approvals"
            ),
        )


# ---- Batch lifecycle -----------------------------------------------------


async def create_batch(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
) -> LegacyImportBatch:
    """Create a fresh batch envelope. Status starts at ``uploading``."""

    batch = LegacyImportBatch(
        id=uuid.uuid4(),
        uploaded_by=actor_id,
        sow_count=0,
        resource_line_count=0,
        errors=None,
        status="uploading",
    )
    session.add(batch)
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="legacy_batch.created",
        entity="legacy_import_batch",
        entity_id=str(batch.id),
        before=None,
        after={"status": batch.status},
    )
    await session.commit()
    await session.refresh(batch)
    return batch


async def load_batch(
    session: AsyncSession, batch_id: uuid.UUID
) -> LegacyImportBatch:
    row = (
        await session.execute(
            select(LegacyImportBatch).where(LegacyImportBatch.id == batch_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="batch not found"
        )
    return row


# ---- SOW bulk upload -----------------------------------------------------


async def bulk_upload_sows(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    batch: LegacyImportBatch,
    uploads: list[SowUpload],
) -> list[SowVersion]:
    """Register the uploaded PDFs as legacy Sow + SowVersion rows.

    Every version lands with ``legacy=True, approval_evidenced=False``. A
    synthetic ``Opportunity`` (``governance_status='Legacy'``,
    ``hubspot_deal_id='LEGACY-<uuid>'``) is created per file so the existing
    1:1 ``sow → opportunity`` invariant continues to hold.
    """

    if batch.status != "uploading":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"batch status is {batch.status!r}; cannot add SOWs",
        )

    versions: list[SowVersion] = []
    for u in uploads:
        client_id = await _find_or_create_client(session, u.client_name)
        opportunity = Opportunity(
            id=uuid.uuid4(),
            hubspot_deal_id=f"LEGACY-{uuid.uuid4().hex[:16]}",
            owner_id=actor_id,
            client_id=client_id,
            governance_status="Legacy",
        )
        session.add(opportunity)
        await session.flush()

        sow = Sow(
            id=uuid.uuid4(),
            opportunity_id=opportunity.id,
        )
        # Attach the legacy-only attributes.
        sow.sow_ref = u.sow_ref  # type: ignore[attr-defined]
        sow.client_id = client_id  # type: ignore[attr-defined]
        sow.filename = u.filename  # type: ignore[attr-defined]
        sow.legacy_batch_id = batch.id  # type: ignore[attr-defined]
        session.add(sow)
        await session.flush()

        version = SowVersion(
            id=uuid.uuid4(),
            sow_id=sow.id,
            uploaded_by=actor_id,
            file_s3_key=u.s3_key,
            file_hash=_synthetic_hash(u.s3_key),
            extract_status="manual_required",
        )
        version.legacy = True  # type: ignore[attr-defined]
        version.approval_evidenced = False  # type: ignore[attr-defined]
        session.add(version)
        await session.flush()

        await append_audit(
            session,
            actor_id=actor_id,
            action="sow.legacy_uploaded",
            entity="sow_version",
            entity_id=str(version.id),
            before=None,
            after={
                "sow_id": str(sow.id),
                "sow_ref": u.sow_ref,
                "filename": u.filename,
                "s3_key": u.s3_key,
                "legacy": True,
                "approval_evidenced": False,
                "batch_id": str(batch.id),
            },
        )
        versions.append(version)

    batch.sow_count = (batch.sow_count or 0) + len(versions)
    if batch.status == "uploading":
        batch.status = "reviewing"
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="legacy_batch.sows_added",
        entity="legacy_import_batch",
        entity_id=str(batch.id),
        before=None,
        after={"added": len(versions), "sow_count": batch.sow_count, "status": batch.status},
    )
    await session.commit()
    for v in versions:
        await session.refresh(v)
    await session.refresh(batch)
    return versions


def _synthetic_hash(s3_key: str) -> str:
    """Deterministic 64-char hex placeholder for legacy uploads.

    A real SHA-256 would need to stream the file from S3, which is out of
    scope for the pilot import. The value is unique per s3_key so the
    dedupe query in Agent P's extract worker won't collapse two files.
    """

    import hashlib

    return hashlib.sha256(f"legacy:{s3_key}".encode()).hexdigest()


async def _find_or_create_client(
    session: AsyncSession, name: str | None
) -> uuid.UUID | None:
    """Return an existing client id by name, or create a new row."""

    if not name:
        return None
    normalized = name.strip()
    if not normalized:
        return None
    row = (
        await session.execute(select(Client).where(Client.name == normalized))
    ).scalar_one_or_none()
    if row is not None:
        return row.id
    client = Client(id=uuid.uuid4(), name=normalized)
    session.add(client)
    await session.flush()
    return client.id


# ---- Excel import --------------------------------------------------------


async def import_excel(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    batch: LegacyImportBatch,
    xlsx_bytes: bytes,
) -> dict[str, Any]:
    """Parse + validate + persist resource lines from a template ``.xlsx``.

    All-or-nothing per file: any invalid row rejects the whole import and
    nothing is written (see :class:`LegacyImportError`). On success, one
    ``GmModel`` per distinct ``sow_ref`` is created and the rows attached.
    """

    rows = _parse_excel(xlsx_bytes)
    errors = _validate_rows(rows)
    if errors:
        # Persist the error report on the batch so the UI can render it.
        batch.errors = errors
        await session.flush()
        await session.commit()
        raise LegacyImportError("excel import failed validation", errors=errors)

    imported_lines: list[ResourceLine] = []
    models_by_ref: dict[str, GmModel] = {}
    grouped: dict[str, list[ExcelRow]] = {}
    for r in rows:
        grouped.setdefault(r.sow_ref, []).append(r)

    for sow_ref, group in grouped.items():
        sow = await _find_sow_by_ref(session, batch.id, sow_ref)
        gm = GmModel(
            id=uuid.uuid4(),
            engagement_type=group[0].engagement_type,
            currency=group[0].currency,
        )
        if sow is not None:
            gm.sow_id = sow.id
            gm.opportunity_id = sow.opportunity_id
        else:
            # No matching SOW yet — model still gets created so the numbers
            # are queryable; reconciliation surfaces the orphan.
            gm.opportunity_id = None
        session.add(gm)
        await session.flush()
        models_by_ref[sow_ref] = gm

        for r in group:
            line = ResourceLine(
                id=uuid.uuid4(),
                gm_model_id=gm.id,
                role=r.role,
                seniority=r.seniority,
                location=r.location,
                start_date=r.start_date,
                end_date=r.end_date,
                allocation_pct=r.allocation_pct,
                billable_hours=r.billable_hours,
                hourly_bill_rate=r.hourly_bill_rate,
                hourly_loaded_cost=r.hourly_loaded_cost,
                revenue_us=r.revenue_us,
                revenue_india=r.revenue_india,
                notes=r.notes,
                hourly_cost=r.hourly_loaded_cost,
            )
            session.add(line)
            imported_lines.append(line)

    batch.resource_line_count = (batch.resource_line_count or 0) + len(imported_lines)
    batch.errors = None
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="legacy_import.batched",
        entity="legacy_import_batch",
        entity_id=str(batch.id),
        before=None,
        after={
            "imported": len(imported_lines),
            "sow_refs": sorted(grouped.keys()),
        },
    )
    await session.commit()
    await session.refresh(batch)
    return {
        "imported": len(imported_lines),
        "sow_refs": sorted(grouped.keys()),
        "errors": [],
    }


async def _find_sow_by_ref(
    session: AsyncSession, batch_id: uuid.UUID, sow_ref: str
) -> Sow | None:
    """Find a Sow in this batch with ``sow_ref`` (case-insensitive stem match)."""

    rows = list(
        (
            await session.execute(
                select(Sow).where(Sow.legacy_batch_id == batch_id)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row_ref = (getattr(row, "sow_ref", None) or "").strip()
        if _norm_ref(row_ref) == _norm_ref(sow_ref):
            return row
    return None


def _norm_ref(s: str) -> str:
    return s.strip().lower()


# ---- Excel parser --------------------------------------------------------


def _parse_excel(xlsx_bytes: bytes) -> list[ExcelRow]:
    """Read the first sheet, mapping header names to column indices.

    Missing required columns raise :class:`LegacyImportError` before any
    row is examined so the error report is precise.
    """

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover — openpyxl is a hard dep.
        raise LegacyImportError(f"openpyxl not installed: {exc}") from exc

    try:
        wb = load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    except Exception as exc:
        raise LegacyImportError(f"could not read workbook: {exc}") from exc

    ws = wb.active
    if ws is None:
        raise LegacyImportError("workbook has no active sheet")

    header_cells = list(next(ws.iter_rows(min_row=1, max_row=1, values_only=True)))
    header = {
        _norm_header(c): i
        for i, c in enumerate(header_cells)
        if c is not None and str(c).strip()
    }
    missing = [c for c in TEMPLATE_COLUMNS if c not in header]
    if missing:
        raise LegacyImportError(
            "missing required columns: " + ", ".join(missing),
            errors=[{"row": 1, "column": c, "error": "missing"} for c in missing],
        )

    parsed: list[ExcelRow] = []
    for idx, raw_row in enumerate(
        ws.iter_rows(min_row=2, values_only=True), start=2
    ):
        if _row_is_blank(raw_row):
            continue
        if _looks_like_note_row(raw_row, header):
            # The template ships with a merged instructional row at row 2 —
            # skip anything where only the first cell is populated with text
            # and every other required numeric column is empty.
            continue
        parsed.append(_row_to_dataclass(idx, raw_row, header))
    return parsed


def _looks_like_note_row(
    row: tuple[Any, ...], header: dict[str, int]
) -> bool:
    """Return True for the template's merged instructional / note row."""

    numeric_cols = (
        "allocation_pct",
        "billable_hours",
        "hourly_bill_rate",
        "hourly_loaded_cost",
    )
    for name in numeric_cols:
        if _cell(row, header, name) is not None:
            return False
    # Only text in the first cell → treat as a note.
    first = _cell(row, header, "sow_ref")
    return isinstance(first, str) and bool(first.strip())


def _norm_header(v: Any) -> str:
    return str(v).strip().lower().replace(" ", "_")


def _row_is_blank(row: tuple[Any, ...]) -> bool:
    return all(c is None or (isinstance(c, str) and not c.strip()) for c in row)


def _cell(row: tuple[Any, ...], header: dict[str, int], name: str) -> Any:
    idx = header.get(name)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _row_to_dataclass(
    row_number: int, row: tuple[Any, ...], header: dict[str, int]
) -> ExcelRow:
    """Convert cell values to typed fields; leave validation to the caller."""

    return ExcelRow(
        row_number=row_number,
        sow_ref=_str(_cell(row, header, "sow_ref")),
        client_name=_str(_cell(row, header, "client_name")),
        engagement_type=_str(_cell(row, header, "engagement_type")),
        role=_str(_cell(row, header, "role")),
        seniority=_str(_cell(row, header, "seniority")),
        location=_str(_cell(row, header, "location")),
        start_date=_date(_cell(row, header, "start_date")),
        end_date=_date(_cell(row, header, "end_date")),
        allocation_pct=_decimal(_cell(row, header, "allocation_pct")),
        billable_hours=_decimal(_cell(row, header, "billable_hours")),
        hourly_bill_rate=_decimal(_cell(row, header, "hourly_bill_rate")),
        hourly_loaded_cost=_maybe_decimal(_cell(row, header, "hourly_loaded_cost")),
        currency=_str(_cell(row, header, "currency")).upper(),
        revenue_us=_maybe_decimal(_cell(row, header, "revenue_us")),
        revenue_india=_maybe_decimal(_cell(row, header, "revenue_india")),
        notes=_maybe_str(_cell(row, header, "notes")),
    )


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _maybe_str(v: Any) -> str | None:
    s = _str(v)
    return s if s else None


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str) and _ISO_DATE_RE.match(v.strip()):
        return date.fromisoformat(v.strip())
    # Trigger a validation error downstream by returning a sentinel that
    # fails ``end_date >= start_date``.
    return date(1900, 1, 1)


def _decimal(v: Any) -> Decimal:
    d = _maybe_decimal(v)
    return d if d is not None else Decimal("NaN")


def _maybe_decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            return None
    return None


# ---- Validation ---------------------------------------------------------


def _validate_rows(rows: list[ExcelRow]) -> list[dict[str, Any]]:
    """Return a list of errors; empty means the file is acceptable."""

    errors: list[dict[str, Any]] = []
    if not rows:
        errors.append({"row": None, "error": "spreadsheet has no data rows"})
        return errors

    # per-project revenue totals for cross-row checks
    project_revenue: dict[str, Decimal] = {}
    project_types: dict[str, str] = {}

    for r in rows:
        row_errors = _validate_row(r)
        errors.extend(row_errors)
        if row_errors:
            continue
        rev = (r.revenue_us or Decimal("0")) + (r.revenue_india or Decimal("0"))
        project_revenue[r.sow_ref] = project_revenue.get(r.sow_ref, Decimal("0")) + rev
        prev_type = project_types.get(r.sow_ref)
        if prev_type is None:
            project_types[r.sow_ref] = r.engagement_type
        elif prev_type != r.engagement_type:
            errors.append(
                {
                    "row": r.row_number,
                    "column": "engagement_type",
                    "error": (
                        f"engagement_type {r.engagement_type!r} does not match earlier "
                        f"{prev_type!r} for sow_ref {r.sow_ref!r}"
                    ),
                }
            )
    return errors


def _validate_row(r: ExcelRow) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def bad(column: str, error: str) -> None:
        errors.append({"row": r.row_number, "column": column, "error": error})

    if not r.sow_ref:
        bad("sow_ref", "required")
    if not r.client_name:
        bad("client_name", "required")
    if r.engagement_type not in ALLOWED_ENGAGEMENT_TYPES:
        bad(
            "engagement_type",
            f"must be one of {sorted(ALLOWED_ENGAGEMENT_TYPES)}",
        )
    if not r.role:
        bad("role", "required")
    if r.seniority not in ALLOWED_SENIORITY:
        bad("seniority", f"must be one of {sorted(ALLOWED_SENIORITY)}")
    if r.location not in ALLOWED_LOCATIONS:
        # Template spec §Rules: whole file rejected with row number.
        bad(
            "location",
            f"must be one of {sorted(ALLOWED_LOCATIONS)}; got {r.location!r}",
        )
    if r.start_date == date(1900, 1, 1):
        bad("start_date", "must be YYYY-MM-DD")
    if r.end_date == date(1900, 1, 1):
        bad("end_date", "must be YYYY-MM-DD")
    if r.start_date != date(1900, 1, 1) and r.end_date != date(1900, 1, 1):
        if r.end_date < r.start_date:
            bad("end_date", "must be >= start_date")

    for name, value in (
        ("allocation_pct", r.allocation_pct),
        ("billable_hours", r.billable_hours),
        ("hourly_bill_rate", r.hourly_bill_rate),
    ):
        if not _is_finite(value):
            bad(name, "required numeric value")

    if r.hourly_loaded_cost is None:
        # Template spec §Rules: missing cost is never zero (§2). Reject file.
        bad("hourly_loaded_cost", "required (§2 hard rule: never treat as zero)")
    elif r.hourly_loaded_cost < 0:
        bad("hourly_loaded_cost", "must be non-negative")

    if r.currency != "USD":
        bad("currency", "USD only for pilot")

    if r.engagement_type in _REVENUE_SPLIT_TYPES:
        if r.revenue_us is None and r.revenue_india is None:
            bad(
                "revenue_us/revenue_india",
                f"engagement_type {r.engagement_type!r} requires at least one revenue value",
            )

    if r.allocation_pct is not None and _is_finite(r.allocation_pct):
        if r.allocation_pct < 0 or r.allocation_pct > Decimal("100"):
            bad("allocation_pct", "must be between 0 and 100")

    return errors


def _is_finite(value: Decimal | None) -> bool:
    if value is None:
        return False
    if value.is_nan():
        return False
    return True


# ---- Reconciliation -----------------------------------------------------


async def reconcile(
    session: AsyncSession, batch_id: uuid.UUID
) -> ReconciliationReport:
    """Compare uploaded SOWs against imported resource lines.

    Returns matched pairs, unmatched SOWs (uploaded but no rows), orphaned
    resource lines (grouped by sow_ref) and per-project GM. Below-floor
    projects are flagged using the default policy floors from ``app.gm``.
    """

    batch = await load_batch(session, batch_id)

    sow_rows = list(
        (
            await session.execute(
                select(Sow).where(Sow.legacy_batch_id == batch_id)
            )
        )
        .scalars()
        .all()
    )
    sow_by_ref: dict[str, Sow] = {}
    for row in sow_rows:
        ref = getattr(row, "sow_ref", None)
        if ref:
            sow_by_ref[_norm_ref(ref)] = row

    # Every gm_model attached to one of this batch's sows (via sow_id) OR
    # created with a sow_id=None (orphan). We take the latter as "attached
    # to the batch via the fact its resource lines were imported into it".
    sow_ids = [s.id for s in sow_rows]
    matched_models = []
    if sow_ids:
        matched_models = list(
            (
                await session.execute(
                    select(GmModel).where(GmModel.sow_id.in_(sow_ids))
                )
            )
            .scalars()
            .all()
        )
    orphan_models = list(
        (
            await session.execute(
                select(GmModel).where(GmModel.sow_id.is_(None))
            )
        )
        .scalars()
        .all()
    )

    per_model_lines = await _load_lines(session, [m.id for m in matched_models + orphan_models])

    matched_report: list[dict[str, Any]] = []
    project_gm: list[ProjectGmSnapshot] = []
    below_floor: list[str] = []
    matched_refs: set[str] = set()

    for model in matched_models:
        sow = next(s for s in sow_rows if s.id == model.sow_id)
        sow_ref = getattr(sow, "sow_ref", None) or "(no ref)"
        lines = per_model_lines.get(model.id, [])
        snapshot = _snapshot_gm(sow_ref, lines)
        project_gm.append(snapshot)
        if snapshot.below_floor:
            below_floor.append(sow_ref)
        matched_refs.add(_norm_ref(sow_ref))
        matched_report.append(
            {
                "sow_id": str(sow.id),
                "sow_ref": sow_ref,
                "filename": getattr(sow, "filename", None),
                "gm_model_id": str(model.id),
                "line_count": len(lines),
                "gm_us": _to_str(snapshot.gm_us),
                "gm_india": _to_str(snapshot.gm_india),
                "below_floor": snapshot.below_floor,
                "failing": snapshot.failing,
                "complete": snapshot.complete,
            }
        )

    unmatched_sows: list[dict[str, Any]] = []
    for row in sow_rows:
        ref = getattr(row, "sow_ref", None) or ""
        if _norm_ref(ref) in matched_refs:
            continue
        unmatched_sows.append(
            {
                "sow_id": str(row.id),
                "sow_ref": ref,
                "filename": getattr(row, "filename", None),
            }
        )

    orphaned: list[dict[str, Any]] = []
    for model in orphan_models:
        lines = per_model_lines.get(model.id, [])
        # We stored the sow_ref back-reference by importing lines; recover it
        # by looking at engagement_type + any distinguishing field. For the
        # pilot we surface the model id and let the UI flag "no matching SOW".
        orphaned.append(
            {
                "gm_model_id": str(model.id),
                "engagement_type": model.engagement_type,
                "line_count": len(lines),
            }
        )

    return ReconciliationReport(
        batch_id=batch.id,
        status=batch.status,
        matched=matched_report,
        unmatched_sows=unmatched_sows,
        orphaned_resource_lines=orphaned,
        project_gm=project_gm,
        below_floor=below_floor,
    )


async def _load_lines(
    session: AsyncSession, model_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ResourceLine]]:
    if not model_ids:
        return {}
    rows = list(
        (
            await session.execute(
                select(ResourceLine).where(ResourceLine.gm_model_id.in_(model_ids))
            )
        )
        .scalars()
        .all()
    )
    out: dict[uuid.UUID, list[ResourceLine]] = {}
    for r in rows:
        out.setdefault(r.gm_model_id, []).append(r)
    return out


def _snapshot_gm(sow_ref: str, lines: list[ResourceLine]) -> ProjectGmSnapshot:
    """Compute the per-component GM using the pure ``app.gm`` library."""

    revenue_us = Decimal("0")
    revenue_india = Decimal("0")
    cost_us = Decimal("0")
    cost_india = Decimal("0")
    for line in lines:
        # If the row carries explicit revenue splits (fixed-price / assessment /
        # managed-service) use those; otherwise treat the resource as staff-aug
        # / T&M and attribute revenue by location.
        rev_us = _decimal_or_zero(line.revenue_us)
        rev_in = _decimal_or_zero(line.revenue_india)
        if rev_us == 0 and rev_in == 0:
            derived = (
                _decimal_or_zero(line.billable_hours)
                * _decimal_or_zero(line.hourly_bill_rate)
                * _decimal_or_zero(line.allocation_pct)
                / Decimal("100")
            )
            if (line.location or "").lower() == "india":
                rev_in = derived
            else:
                rev_us = derived
        cost = (
            _decimal_or_zero(line.billable_hours)
            * _decimal_or_zero(line.hourly_loaded_cost)
            * _decimal_or_zero(line.allocation_pct)
            / Decimal("100")
        )
        revenue_us += rev_us
        revenue_india += rev_in
        if (line.location or "").lower() == "india":
            cost_india += cost
        else:
            cost_us += cost

    gm_us = gross_margin(revenue_us, cost_us) if revenue_us > 0 else None
    gm_in = gross_margin(revenue_india, cost_india) if revenue_india > 0 else None
    failing: list[str] = []
    if gm_us is not None and gm_us < US_FLOOR:
        failing.append("US")
    if gm_in is not None and gm_in < INDIA_FLOOR:
        failing.append("India")
    return ProjectGmSnapshot(
        sow_ref=sow_ref,
        revenue_us=revenue_us,
        revenue_india=revenue_india,
        cost_us=cost_us,
        cost_india=cost_india,
        gm_us=gm_us,
        gm_india=gm_in,
        below_floor=bool(failing),
        failing=failing,
        complete=len(lines) > 0,
    )


def _decimal_or_zero(v: Decimal | None) -> Decimal:
    return v if v is not None else Decimal("0")


def _to_str(v: Decimal | None) -> str | None:
    return str(v) if v is not None else None


# ---- Approval -----------------------------------------------------------


async def approve_batch(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    batch_id: uuid.UUID,
) -> ReconciliationReport:
    """Freeze the batch as ``approved`` and file follow-up tasks for mismatches.

    Does NOT create approval rows on any ``sow_version`` — the legacy
    rollout rule (§13) is that historical projects are dispositioned by
    executives, not backfilled with fake approvals.
    """

    batch = await load_batch(session, batch_id)
    if batch.status == "approved":
        return await reconcile(session, batch_id)
    if batch.status not in ("uploading", "reviewing"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"batch is {batch.status!r}; cannot approve",
        )

    report = await reconcile(session, batch_id)

    batch.status = "approved"
    batch.approved_by = actor_id
    batch.approved_at = datetime.now(UTC)
    await session.flush()

    # File follow-up tasks for every unmatched SOW so the account owner
    # sees a to-do. Owner defaults to the batch uploader (Finance) when the
    # legacy SOW's opportunity doesn't carry one.
    tasks_created = 0
    for row in report.unmatched_sows:
        subject = f"Legacy import: SOW {row['sow_ref']!r} has no resource lines"
        task_owner = await _resolve_owner_for_sow(session, uuid.UUID(row["sow_id"]))
        session.add(
            Task(
                id=uuid.uuid4(),
                owner_id=task_owner or actor_id,
                subject=subject[:255],
                due_date=(date.today() + timedelta(days=7)),
                escalation_level=0,
                status="assigned",
                category="intake",
            )
        )
        tasks_created += 1
    for snap in report.project_gm:
        if not snap.complete:
            session.add(
                Task(
                    id=uuid.uuid4(),
                    owner_id=actor_id,
                    subject=f"Legacy: {snap.sow_ref} imported without resource lines",
                    due_date=(date.today() + timedelta(days=7)),
                    escalation_level=0,
                    status="assigned",
                    category="intake",
                )
            )
            tasks_created += 1

    await append_audit(
        session,
        actor_id=actor_id,
        action="legacy_batch.approved",
        entity="legacy_import_batch",
        entity_id=str(batch.id),
        before={"status": "reviewing"},
        after={
            "status": "approved",
            "sow_count": batch.sow_count,
            "resource_line_count": batch.resource_line_count,
            "tasks_created": tasks_created,
        },
    )
    await session.commit()
    await session.refresh(batch)
    return await reconcile(session, batch_id)


async def _resolve_owner_for_sow(
    session: AsyncSession, sow_id: uuid.UUID
) -> uuid.UUID | None:
    sow = (
        await session.execute(select(Sow).where(Sow.id == sow_id))
    ).scalar_one_or_none()
    if sow is None or sow.opportunity_id is None:
        return None
    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == sow.opportunity_id)
        )
    ).scalar_one_or_none()
    return opp.owner_id if opp else None


# ---- Fixture helpers (used by the frontend template download endpoint) ----


def template_xlsx_path() -> Path:
    """Absolute path to the canonical template fixture."""

    root = Path(__file__).resolve().parents[3]
    return root / "fixtures" / "legacy_projects" / "template.xlsx"


__all__ = [
    "ALLOWED_LOCATIONS",
    "ALLOWED_ENGAGEMENT_TYPES",
    "LEGACY_ROLES",
    "LegacyImportError",
    "ProjectGmSnapshot",
    "ReconciliationReport",
    "SowUpload",
    "approve_batch",
    "assert_not_legacy_for_approval",
    "assert_role",
    "bulk_upload_sows",
    "create_batch",
    "import_excel",
    "load_batch",
    "reconcile",
    "template_xlsx_path",
]
