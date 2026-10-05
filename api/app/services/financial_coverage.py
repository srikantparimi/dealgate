"""Validate explicit coverage under the financial import's account locks."""

import os
from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models.actual import FinancialActual
from app.models.approval import ApprovalPackage
from app.models.signed_sow import SignedSowUpload
from app.services.commercial_models import SCHEDULE


async def validate_coverage_source(session, *, row, gm, tenant, environment):
    coverage = row.coverage
    if row.measure not in {"recognized_revenue", "delivery_cost"}:
        return ["Only recognized revenue or delivery cost can replace service forecast"]
    if gm is None:
        return ["Coverage requires an attached signed GM source"]
    signed = await signed_model_evidence(session, gm)
    if not signed or gm.sow_version_id != coverage.sow_version_id:
        return ["Coverage requires the exact signed GM and SOW version"]
    snapshot = gm.commercial_snapshot or {}
    if (snapshot.get("tenant_id"), snapshot.get("environment")) != (tenant, environment):
        return ["Coverage source is outside the financial tenant or environment"]
    try:
        schedule = SCHEDULE.validate_python(snapshot.get("schedule"))
        scheduled = schedule.rows[coverage.schedule_row]
    except (ValueError, TypeError, IndexError):
        return ["Coverage schedule row is unavailable"]
    if scheduled.month != row.period_month:
        return ["Coverage must match the signed service month"]
    material_gaps = [gap for gap in schedule.missing if row.measure == "delivery_cost" or
                     gap.field not in {"costs.amount", "costs_confirmed", "cost_basis"}]
    if schedule.status == "unsupported" or material_gaps or (row.measure == "delivery_cost" and scheduled.cost is None):
        return ["Coverage requires a complete signed service basis"]
    timezone = os.environ.get("DEALGATE_REPORTING_TIMEZONE")
    if not timezone:
        return ["Coverage requires an explicit reporting timezone"]
    cutoff = datetime.now(UTC).astimezone(ZoneInfo(timezone)).date()
    if (coverage.through_date.replace(day=1) != row.period_month or
            coverage.through_date > cutoff or coverage.through_date > row.source_date or row.source_date > cutoff):
        return ["Coverage cutoff must be in its service month and not after the source or reporting cutoff"]
    reporting_currency = os.environ.get("DEALGATE_REPORTING_CURRENCY")
    if not reporting_currency or gm.currency != reporting_currency:
        return ["Signed source reporting currency is unresolved"]
    if row.currency != reporting_currency and not (
        row.fx_rate and row.fx_version and row.fx_date and row.fx_date <= cutoff
    ):
        return ["Coverage actual reporting FX is unresolved"]
    return []


async def current_signed_evidence(session, package):
    if package.status in {"voided", "rejected"} or package.superseded_by is not None:
        return False
    latest = await session.scalar(select(SignedSowUpload).where(
        SignedSowUpload.package_id == package.id
    ).order_by(SignedSowUpload.uploaded_at.desc(), SignedSowUpload.id.desc()).limit(1))
    return latest.verify_status == "verified" if latest else package.status == "released"


async def signed_model_evidence(session, gm):
    packages = (await session.scalars(select(ApprovalPackage).where(
        ApprovalPackage.gm_model_id == gm.id, ApprovalPackage.sow_version_id == gm.sow_version_id,
        ApprovalPackage.status.notin_(("voided", "rejected")),
        ApprovalPackage.superseded_by.is_(None),
    ))).all()
    for package in packages:
        if await current_signed_evidence(session, package):
            return True
    return False


async def coverage_conflicts(session, prepared, *, tenant, environment):
    # Account locks held by the caller serialize different source systems too.
    stored = (await session.scalars(select(FinancialActual).where(
        FinancialActual.tenant_id == tenant, FinancialActual.environment == environment,
        FinancialActual.original_account_id.in_({row.original_account_id for row in prepared}),
    ).order_by(FinancialActual.revision.desc()))).all()
    current = {}
    for row in stored:
        current.setdefault((row.source_system, row.source_id), row)
    for row in prepared:
        current[(row.source_system, row.source_id)] = row
    errors = []
    for index, row in enumerate(prepared, 1):
        if not row.coverage:
            continue
        a = row.coverage
        for other in current.values():
            b = other.coverage
            if other is row or not b:
                continue
            if (row.original_account_id, row.original_gm_model_id, row.period_month, row.measure,
                a["sow_version_id"], a["schedule_row"]) != (
                other.original_account_id, other.original_gm_model_id, other.period_month, other.measure,
                b["sow_version_id"], b["schedule_row"]):
                continue
            if Decimal(a["fraction_start"]) < Decimal(b["fraction_end"]) and Decimal(b["fraction_start"]) < Decimal(a["fraction_end"]):
                errors.append((index, "Coverage overlaps another current actual source"))
                break
    return errors
