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
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import append_audit
from app.gm.core import gross_margin
from app.models.actual import ActualImportBatch, ActualPeriod, FinancialImportBatch, FinancialActual
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


class FinancialCoverageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sow_version_id: uuid.UUID
    schedule_row: int = Field(ge=0, strict=True)
    fraction_start: str
    fraction_end: str
    through_date: date
    basis_evidence: str = Field(min_length=1, max_length=2000, pattern=r"\S")

    @field_validator("basis_evidence")
    @classmethod
    def normalize_evidence(cls, value):
        return value.strip()

    @model_validator(mode="after")
    def explicit_interval(self):
        try:
            start, end = Decimal(self.fraction_start), Decimal(self.fraction_end)
        except InvalidOperation as exc:
            raise ValueError("Coverage fractions require exact decimals") from exc
        if not start.is_finite() or not end.is_finite() or not Decimal(0) <= start < end <= Decimal(1):
            raise ValueError("Coverage requires 0 <= start < end <= 1")
        return self


class FinancialRowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: uuid.UUID
    gm_model_id: uuid.UUID | None = None
    source_id: str = Field(min_length=1, max_length=255, pattern=r"\S")
    revision: int = Field(ge=1, strict=True)
    expected_previous_revision: int = Field(default=0, ge=0, strict=True)
    period_month: date
    measure: Literal["recognized_revenue", "billed", "cash_collected", "delivery_cost"]
    amount: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    source_date: date
    fx_rate: str | None = None
    fx_version: str | None = Field(default=None, max_length=128)
    fx_date: date | None = None
    reason: str = Field(min_length=1, max_length=2000, pattern=r"\S")
    coverage: FinancialCoverageInput | None = None

    @field_validator("amount", "fx_rate")
    @classmethod
    def finite_money(cls, value):
        if value is not None:
            try:
                amount = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("Expected a Decimal string") from exc
            if not amount.is_finite():
                raise ValueError("Financial facts must be finite")
        return value

    @field_validator("period_month")
    @classmethod
    def first_of_month(cls, value):
        if value.day != 1:
            raise ValueError("period_month must be the first day of its accounting month")
        return value


class FinancialImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_system: str = Field(min_length=1, max_length=128, pattern=r"\S")
    idempotency_key: uuid.UUID
    rows: list[FinancialRowInput] = Field(min_length=1, max_length=1000)


def _financial_scope():
    tenant = os.environ.get("DEALGATE_TENANT_ID")
    if not tenant:
        raise HTTPException(409, "Financial imports require an explicit tenant")
    return tenant, os.environ.get("DEALGATE_ENV", "local")


async def import_financial(session, *, actor, body: FinancialImportInput):
    from app.models.client import Client
    from app.models.opportunity import Opportunity
    from app.services.test_fixtures import account_scope, is_test_user, user_allowed
    from sqlalchemy.exc import IntegrityError

    assert_role(actor.groups)
    tenant, environment = _financial_scope()
    key = f"{actor.id}:{body.idempotency_key}"
    payload = body.model_dump(mode="json")
    for row in payload["rows"]:
        if row.get("coverage") is None:
            row.pop("coverage", None)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        # Serialize replay by request, not User: identity synchronization must
        # not wait for account locks while holding the global audit-chain lock.
        identity = json.dumps(["financial-request", tenant, environment, body.source_system, key])
        lock = -(int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big") >> 1) - 1
        await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    existing = await session.scalar(select(FinancialImportBatch).where(
        FinancialImportBatch.tenant_id == tenant, FinancialImportBatch.environment == environment,
        FinancialImportBatch.source_system == body.source_system, FinancialImportBatch.request_key == key))
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "Import idempotency key already contains different inputs")
        for identity in {row.account_id for row in body.rows}:
            account = await session.get(Client, identity)
            if (account is not None and not user_allowed(actor, await account_scope(session, identity))) or (
                account is None and (existing.test_fixture or is_test_user(actor))
            ):
                raise HTTPException(403, "Import replay is outside current trusted scope")
        if existing.status == "failed":
            status = 409 if any(error.get("status_code") == 409 for error in existing.errors or []) else 422
            raise HTTPException(status, {"batch_id": str(existing.id), "errors": existing.errors})
        return existing
    # Source identity survives account deletion; account locks alone cannot serialize corrections.
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        from sqlalchemy import text
        for source_id in sorted({row.source_id for row in body.rows}):
            identity = json.dumps(["financial-source", tenant, environment, body.source_system, source_id])
            lock = -(int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big") >> 1) - 1
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    batch = FinancialImportBatch(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
        source_system=body.source_system, request_key=key, request_hash=digest, uploaded_by=actor.id,
        status="uploading", row_count=len(body.rows), errors=None, test_fixture=is_test_user(actor))
    session.add(batch)
    await session.flush()
    for account_id in sorted({row.account_id for row in body.rows}):
        await session.execute(select(Client.id).where(Client.id == account_id).with_for_update())
    errors, prepared, seen, conflict = [], [], set(), False
    for index, row in enumerate(body.rows, 1):
        def reject(message, status_code=422):
            errors.append({"row": index, "source_id": row.source_id, "error": message, "status_code": status_code})
        if row.source_id in seen:
            reject("Duplicate source row in batch")
        seen.add(row.source_id)
        prior = await session.scalar(select(FinancialActual).where(
            FinancialActual.tenant_id == tenant, FinancialActual.environment == environment,
            FinancialActual.source_system == body.source_system, FinancialActual.source_id == row.source_id
        ).order_by(FinancialActual.revision.desc()).limit(1))
        prior_revision = prior.revision if prior else 0
        if row.expected_previous_revision != prior_revision or row.revision != prior_revision + 1:
            reject("Source revision changed; refresh before correcting", 409)
            conflict = True
        if prior and (prior.original_account_id != row.account_id or prior.measure != row.measure):
            reject("Correction cannot move source identity to another account or measure")
        account = await session.get(Client, row.account_id)
        retained = prior and prior.account_id is None and not prior.test_fixture and not is_test_user(actor)
        if account is None and not retained:
            reject("Account unavailable")
        elif account is not None and not user_allowed(actor, await account_scope(session, account.id)):
            reject("Account is outside trusted import scope")
        gm = await session.get(GmModel, row.gm_model_id) if row.gm_model_id else None
        if row.gm_model_id:
            deal = await session.get(Opportunity, gm.opportunity_id) if gm else None
            retained_gm = prior and prior.gm_model_id is None and prior.original_gm_model_id == row.gm_model_id
            if not retained_gm and (gm is None or deal is None or deal.client_id != row.account_id):
                reject("GM source must belong to the same account")
            if gm and gm.commercial_snapshot and (
                gm.commercial_snapshot.get("tenant_id"), gm.commercial_snapshot.get("environment")
            ) != (tenant, environment):
                reject("GM source is outside the financial tenant or environment")
        if row.fx_rate is not None and (Decimal(row.fx_rate) <= 0 or not row.fx_version or not row.fx_version.strip() or not row.fx_date):
            reject("Reporting FX requires positive rate, version and date")
        if row.coverage:
            from app.services.financial_coverage import validate_coverage_source
            for message in await validate_coverage_source(session, row=row, gm=gm, tenant=tenant, environment=environment):
                reject(message)
        prepared.append(FinancialActual(id=uuid.uuid4(), tenant_id=tenant, environment=environment,
            source_system=body.source_system, source_id=row.source_id, revision=row.revision, batch_id=batch.id,
            account_id=account.id if account else None, original_account_id=row.account_id,
            gm_model_id=gm.id if gm else None, original_gm_model_id=row.gm_model_id,
            period_month=row.period_month, measure=row.measure, amount=Decimal(row.amount), currency=row.currency,
            source_date=row.source_date, fx_rate=Decimal(row.fx_rate) if row.fx_rate else None,
            fx_version=row.fx_version, fx_date=row.fx_date, reason=row.reason.strip(),
            coverage=row.coverage.model_dump(mode="json") if row.coverage else None,
            test_fixture=is_test_user(actor)))
    if any(row.coverage for row in prepared):
        from app.services.financial_coverage import coverage_conflicts
        for index, message in await coverage_conflicts(session, prepared, tenant=tenant, environment=environment):
            errors.append({"row": index, "source_id": prepared[index - 1].source_id,
                           "error": message, "status_code": 422})
    if errors:
        batch.status, batch.errors = "failed", errors
        await append_audit(session, actor_id=actor.id, action="actuals.financial_import_rejected",
            entity="financial_import_batch", entity_id=str(batch.id), before=None,
            after={"row_count": len(body.rows), "error_count": len(errors), "source_system": body.source_system})
        await session.commit()
        raise HTTPException(409 if conflict else 422, {"batch_id": str(batch.id), "errors": errors})
    session.add_all(prepared)
    batch.status = "committed"
    try:
        await append_audit(session, actor_id=actor.id, action="actuals.financial_imported",
            entity="financial_import_batch", entity_id=str(batch.id), before=None,
            after={"row_count": len(prepared), "source_system": body.source_system, "source_hash": digest})
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Concurrent financial source revision; refresh before import") from exc
    return batch


async def financial_records(session, *, actor, account_id=None, history=False):
    from app.services.test_fixtures import account_scope, is_test_user, user_allowed
    assert_role(actor.groups)
    tenant, environment = _financial_scope()
    query = select(FinancialActual).where(FinancialActual.tenant_id == tenant, FinancialActual.environment == environment)
    if account_id:
        query = query.where(FinancialActual.original_account_id == account_id)
    records = (await session.scalars(query.order_by(FinancialActual.source_system, FinancialActual.source_id,
                                                   FinancialActual.revision.desc()))).all()
    result, seen = [], set()
    for row in records:
        identity = (row.source_system, row.source_id)
        if identity in seen and not history:
            continue
        seen.add(identity)
        if row.account_id:
            if not user_allowed(actor, await account_scope(session, row.account_id)):
                continue
        elif row.test_fixture or is_test_user(actor):
            continue
        amount = format(row.amount, "f")
        if "." in amount:
            amount = amount.rstrip("0").rstrip(".")
        result.append({"id": str(row.id), "source_system": row.source_system, "source_id": row.source_id,
            "revision": row.revision, "batch_id": str(row.batch_id), "account_id": str(row.original_account_id),
            "gm_model_id": str(row.original_gm_model_id) if row.original_gm_model_id else None,
            "source_detached": row.account_id is None or (row.original_gm_model_id is not None and row.gm_model_id is None),
            "period_month": row.period_month.isoformat(), "measure": row.measure, "amount": amount,
            "currency": row.currency, "source_date": row.source_date.isoformat(), "reason": row.reason,
            "coverage": row.coverage,
            "fx_rate": str(row.fx_rate) if row.fx_rate is not None else None,
            "fx_version": row.fx_version, "fx_date": row.fx_date.isoformat() if row.fx_date else None})
    return result
