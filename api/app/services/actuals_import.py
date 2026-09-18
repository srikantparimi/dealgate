"""S6 E9 actuals CSV import service.

Owns the vertical for the month-end actuals rollout (story
``docs/backlog/s6-actuals-import.md``, blueprint §9 pilot).

Public surface:

- :func:`import_csv` — parse + validate + upsert. All-or-nothing per
  file. Any row-level error (unknown resource_line_id, unparseable,
  missing actual_cost per §2) rejects the whole file and the batch is
  persisted as ``failed`` with the error report.
- :func:`actual_gm_for` — aggregate actual GM for a
  (gm_model_id, period_month). Sum-of-cost / sum-of-revenue, never the
  mean of per-line percentages.

All money is ``Decimal`` (CLAUDE.md rule 2). Every write goes through
:func:`app.audit.append_audit` in the caller's transaction (rule 5).
The CSV parser uses the standard-library ``csv`` module — no new deps
per the story constraints.
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.core import gross_margin
from app.models.actual import ActualImportBatch, ActualPeriod
from app.models.gm_model import GmModel, ResourceLine


ACTUALS_ROLES: tuple[str, ...] = ("Finance", "SystemAdmin")


REQUIRED_COLUMNS: tuple[str, ...] = (
    "sow_ref",
    "resource_line_id",
    "period_month",
    "actual_hours",
    "actual_cost",
    "actual_revenue",
)


# ---- Errors --------------------------------------------------------------


class ActualsImportError(Exception):
    """Raised when a CSV import fails validation. Whole-file reject."""

    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


# ---- Dataclass payloads --------------------------------------------------


@dataclass
class CsvRow:
    row_number: int  # 1-indexed spreadsheet row (header = 1)
    sow_ref: str
    resource_line_id: str
    period_month: str  # raw YYYY-MM as parsed from CSV
    actual_hours: str
    actual_cost: str
    actual_revenue: str


@dataclass(frozen=True)
class ActualGmSnapshot:
    revenue: Decimal
    cost_us: Decimal
    cost_india: Decimal
    gm_us: Decimal | None
    gm_india: Decimal | None


# ---- Role gate -----------------------------------------------------------


def assert_role(user_groups: Iterable[str]) -> None:
    """Raise 403 unless the caller is Finance/SystemAdmin."""

    if not any(r in ACTUALS_ROLES for r in user_groups):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="actuals endpoints are Finance/SystemAdmin only",
        )


# ---- Public API ----------------------------------------------------------


async def import_csv(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    csv_bytes: bytes,
) -> ActualImportBatch:
    """Parse, validate and (on success) upsert one CSV of actuals.

    All-or-nothing per file. On any validation error the batch is
    persisted with ``status='failed'`` and :class:`ActualsImportError` is
    raised (the caller returns 422 with the report). On success, one
    ``actual_period`` row per input row is upserted keyed on
    (resource_line_id, period_month); the batch is marked ``committed``.
    """

    # Batch is created up-front so the error report has a persistent home.
    batch = ActualImportBatch(
        id=uuid.uuid4(),
        uploaded_by=actor_id,
        row_count=0,
        errors=None,
        status="uploading",
    )
    session.add(batch)
    await session.flush()

    try:
        parsed = _parse_csv(csv_bytes)
    except ActualsImportError as exc:
        batch.status = "failed"
        batch.errors = exc.errors
        batch.row_count = 0
        await session.flush()
        await append_audit(
            session,
            actor_id=actor_id,
            action="actuals.import_rejected",
            entity="actual_import_batch",
            entity_id=str(batch.id),
            before=None,
            after={"status": "failed", "reason": exc.message},
        )
        await session.commit()
        await session.refresh(batch)
        raise

    # Load resource_line context so we can validate ids + resolve gm_model_id.
    line_ids: list[uuid.UUID] = []
    row_errors: list[dict[str, Any]] = []
    for r in parsed:
        try:
            line_ids.append(uuid.UUID(r.resource_line_id))
        except (ValueError, AttributeError):
            row_errors.append(
                {
                    "row": r.row_number,
                    "column": "resource_line_id",
                    "error": f"not a valid UUID: {r.resource_line_id!r}",
                }
            )

    lines_by_id: dict[uuid.UUID, ResourceLine] = {}
    if line_ids:
        rows = list(
            (
                await session.execute(
                    select(ResourceLine).where(ResourceLine.id.in_(line_ids))
                )
            )
            .scalars()
            .all()
        )
        lines_by_id = {row.id: row for row in rows}

    row_errors.extend(_validate_rows(parsed, lines_by_id))
    if row_errors:
        batch.status = "failed"
        batch.errors = row_errors
        batch.row_count = len(parsed)
        await session.flush()
        await append_audit(
            session,
            actor_id=actor_id,
            action="actuals.import_rejected",
            entity="actual_import_batch",
            entity_id=str(batch.id),
            before=None,
            after={
                "status": "failed",
                "row_count": len(parsed),
                "error_count": len(row_errors),
            },
        )
        await session.commit()
        await session.refresh(batch)
        raise ActualsImportError(
            "actuals import failed validation", errors=row_errors
        )

    # Happy path: mark validated, then upsert every row.
    batch.status = "validated"
    batch.row_count = len(parsed)
    batch.errors = None
    await session.flush()

    upserted = 0
    for r in parsed:
        line_id = uuid.UUID(r.resource_line_id)
        line = lines_by_id[line_id]
        period_month = _parse_period(r.period_month)
        existing = (
            await session.execute(
                select(ActualPeriod).where(
                    ActualPeriod.resource_line_id == line_id,
                    ActualPeriod.period_month == period_month,
                )
            )
        ).scalar_one_or_none()

        hours = Decimal(r.actual_hours)
        cost = Decimal(r.actual_cost)
        revenue = Decimal(r.actual_revenue)

        if existing is None:
            row = ActualPeriod(
                id=uuid.uuid4(),
                gm_model_id=line.gm_model_id,
                resource_line_id=line_id,
                period_month=period_month,
                actual_hours=hours,
                actual_cost=cost,
                actual_revenue=revenue,
                imported_by=actor_id,
                batch_id=batch.id,
            )
            session.add(row)
        else:
            existing.gm_model_id = line.gm_model_id
            existing.actual_hours = hours
            existing.actual_cost = cost
            existing.actual_revenue = revenue
            existing.imported_by = actor_id
            existing.batch_id = batch.id
        upserted += 1

    batch.status = "committed"
    await session.flush()
    await append_audit(
        session,
        actor_id=actor_id,
        action="actuals.imported",
        entity="actual_import_batch",
        entity_id=str(batch.id),
        before=None,
        after={
            "status": "committed",
            "row_count": upserted,
        },
    )
    await session.commit()
    await session.refresh(batch)
    return batch


async def actual_gm_for(
    session: AsyncSession,
    *,
    gm_model_id: uuid.UUID,
    period_month: date,
) -> ActualGmSnapshot:
    """Aggregate actual GM for a (gm_model_id, period_month).

    Uses the pure :func:`app.gm.core.gross_margin` on the aggregated
    sums — sum(revenue), sum(cost) — never the mean of per-line
    percentages (story rule + blueprint §9).
    """

    rows = list(
        (
            await session.execute(
                select(ActualPeriod, ResourceLine)
                .join(ResourceLine, ResourceLine.id == ActualPeriod.resource_line_id)
                .where(
                    ActualPeriod.gm_model_id == gm_model_id,
                    ActualPeriod.period_month == period_month,
                )
            )
        ).all()
    )

    revenue = Decimal("0")
    cost_us = Decimal("0")
    cost_india = Decimal("0")
    revenue_us = Decimal("0")
    revenue_india = Decimal("0")
    for actual, line in rows:
        revenue += Decimal(actual.actual_revenue or 0)
        location = (line.location or "").lower()
        if location == "india":
            cost_india += Decimal(actual.actual_cost or 0)
            revenue_india += Decimal(actual.actual_revenue or 0)
        else:
            cost_us += Decimal(actual.actual_cost or 0)
            revenue_us += Decimal(actual.actual_revenue or 0)

    gm_us = gross_margin(revenue_us, cost_us) if revenue_us > 0 else None
    gm_in = gross_margin(revenue_india, cost_india) if revenue_india > 0 else None
    return ActualGmSnapshot(
        revenue=revenue,
        cost_us=cost_us,
        cost_india=cost_india,
        gm_us=gm_us,
        gm_india=gm_in,
    )


# ---- CSV parser ----------------------------------------------------------


def _parse_csv(csv_bytes: bytes) -> list[CsvRow]:
    """Parse the uploaded CSV into typed row dataclasses.

    Missing required columns raise :class:`ActualsImportError` before any
    row is examined so the error report is precise (mirrors the legacy
    Excel importer's contract).
    """

    try:
        text = csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ActualsImportError(
            f"csv is not utf-8: {exc}",
            errors=[{"row": None, "error": "csv encoding must be utf-8"}],
        ) from exc

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ActualsImportError(
            "csv has no header row",
            errors=[{"row": None, "error": "csv has no header row"}],
        ) from exc

    header_map = {_norm(name): idx for idx, name in enumerate(header)}
    missing = [c for c in REQUIRED_COLUMNS if c not in header_map]
    if missing:
        raise ActualsImportError(
            "missing required columns: " + ", ".join(missing),
            errors=[
                {"row": 1, "column": c, "error": "missing"} for c in missing
            ],
        )

    rows: list[CsvRow] = []
    for idx, raw_row in enumerate(reader, start=2):
        if not raw_row or all((c is None or not str(c).strip()) for c in raw_row):
            continue
        rows.append(
            CsvRow(
                row_number=idx,
                sow_ref=_cell(raw_row, header_map, "sow_ref"),
                resource_line_id=_cell(raw_row, header_map, "resource_line_id"),
                period_month=_cell(raw_row, header_map, "period_month"),
                actual_hours=_cell(raw_row, header_map, "actual_hours"),
                actual_cost=_cell(raw_row, header_map, "actual_cost"),
                actual_revenue=_cell(raw_row, header_map, "actual_revenue"),
            )
        )
    return rows


def _norm(v: str) -> str:
    return v.strip().lower().replace(" ", "_")


def _cell(row: list[str], header: dict[str, int], name: str) -> str:
    idx = header.get(name)
    if idx is None or idx >= len(row):
        return ""
    val = row[idx]
    return "" if val is None else str(val).strip()


# ---- Validation ---------------------------------------------------------


def _validate_rows(
    rows: list[CsvRow], lines_by_id: dict[uuid.UUID, ResourceLine]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    if not rows:
        errors.append({"row": None, "error": "csv has no data rows"})
        return errors

    for r in rows:
        row_errors = _validate_row(r, lines_by_id)
        errors.extend(row_errors)
    return errors


def _validate_row(
    r: CsvRow, lines_by_id: dict[uuid.UUID, ResourceLine]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []

    def bad(column: str, error: str) -> None:
        errors.append({"row": r.row_number, "column": column, "error": error})

    if not r.sow_ref:
        bad("sow_ref", "required")

    # resource_line_id must be a UUID we already know about.
    line: ResourceLine | None = None
    try:
        line_uuid = uuid.UUID(r.resource_line_id)
    except (ValueError, AttributeError):
        # The caller already recorded a UUID-parse error; skip lookup.
        line_uuid = None
    if line_uuid is not None:
        line = lines_by_id.get(line_uuid)
        if line is None:
            bad(
                "resource_line_id",
                f"unknown resource_line_id: {r.resource_line_id!r}",
            )

    if not r.period_month:
        bad("period_month", "required (YYYY-MM)")
    else:
        try:
            _parse_period(r.period_month)
        except ValueError as exc:
            bad("period_month", str(exc))

    # §2 hard rule: missing actual_cost rejects the whole file. Zero is
    # a legitimate value (write-off / off-project week), empty is not.
    if r.actual_cost == "":
        bad(
            "actual_cost",
            "required (§2 hard rule: missing cost is never treated as zero)",
        )
    else:
        cost = _maybe_decimal(r.actual_cost)
        if cost is None:
            bad("actual_cost", f"not a number: {r.actual_cost!r}")
        elif cost < 0:
            bad("actual_cost", "must be non-negative")

    for column, raw in (
        ("actual_hours", r.actual_hours),
        ("actual_revenue", r.actual_revenue),
    ):
        if raw == "":
            bad(column, "required")
            continue
        val = _maybe_decimal(raw)
        if val is None:
            bad(column, f"not a number: {raw!r}")
        elif val < 0:
            bad(column, "must be non-negative")

    return errors


def _maybe_decimal(v: str) -> Decimal | None:
    s = (v or "").strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_period(v: str) -> date:
    """Parse ``YYYY-MM`` into the first-of-month date used at rest."""

    s = (v or "").strip()
    if len(s) != 7 or s[4] != "-":
        raise ValueError(f"must be YYYY-MM: got {v!r}")
    try:
        year = int(s[0:4])
        month = int(s[5:7])
    except ValueError as exc:
        raise ValueError(f"must be YYYY-MM: got {v!r}") from exc
    if not (1 <= month <= 12):
        raise ValueError(f"month out of range in {v!r}")
    return date(year, month, 1)


__all__ = [
    "ACTUALS_ROLES",
    "ActualGmSnapshot",
    "ActualsImportError",
    "actual_gm_for",
    "assert_role",
    "import_csv",
]
