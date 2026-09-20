"""Staffing sheet endpoints for the SOW-first flow (S10-05).

Two endpoints, both in service of one rule: a gross margin is only as good as
the staffing plan under it, and that plan has to come from a person when the
SOW does not carry one.

- ``GET  /sows/staffing-template.xlsx``            — the blank sheet.
- ``POST /sows/{opportunity_id}/staffing/import``  — upload it back.

Import **parses and returns**; it does not save. The rows land in the grid
where the reviewer can see the live gross margin before committing, because
uploading a spreadsheet should not silently become an approved cost basis.
Saving goes through the existing ``POST /delivery-model/{id}/versions``, which
already writes the immutable GM version and its audit row.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthUser, require_role
from app.db import get_session
from app.models.opportunity import Opportunity
from app.services.staffing_sheet import (
    StaffingSheetError,
    build_template_xlsx,
    parse_staffing_xlsx,
)

router = APIRouter(prefix="/sows", tags=["sows"])

# Whoever owns the delivery plan owns these. Finance and Legal can read the
# template but do not staff an engagement.
_STAFFING_ROLES: tuple[str, ...] = (
    "Sales",
    "SalesLeader",
    "Delivery",
    "Finance",
    "CEO",
    "SystemAdmin",
)

_XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_MAX_SHEET_BYTES = 5 * 1024 * 1024


@router.get("/staffing-template.xlsx")
async def staffing_template(
    _user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
) -> Response:
    """Download the blank staffing sheet."""

    return Response(
        content=build_template_xlsx(),
        media_type=_XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": 'attachment; filename="dealgate-staffing.xlsx"'
        },
    )


@router.post("/{opportunity_id}/staffing/import")
async def import_staffing(
    opportunity_id: uuid.UUID,
    file: UploadFile = File(...),
    _user: AuthUser = Depends(require_role(*_STAFFING_ROLES)),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Parse an uploaded staffing sheet into resource lines.

    Returns the parsed rows for review. Nothing is written — the reviewer sees
    the resulting gross margin first, then saves.
    """

    opp = (
        await session.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")

    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "the uploaded file is empty", "errors": []},
        )
    if len(payload) > _MAX_SHEET_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "message": f"sheet exceeds {_MAX_SHEET_BYTES // (1024 * 1024)}MB",
                "errors": [],
            },
        )

    try:
        rows = parse_staffing_xlsx(payload)
    except StaffingSheetError as exc:
        # Every problem at once — fixing one row at a time across repeated
        # uploads is the worst possible version of this.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": exc.message, "errors": exc.errors},
        ) from exc

    return {
        "resource_lines": [r.to_resource_line() for r in rows],
        "row_count": len(rows),
        "source": "sheet_upload",
    }
