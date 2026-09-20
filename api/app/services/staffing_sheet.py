"""Staffing sheet: xlsx template out, staffing lines in (S10-05).

The SOW-first flow assumes the SOW tells you who is on the engagement. Most
do not: a fixed-fee assessment names a price and a scope and leaves the
staffing to Delivery. Before this module the system filled that gap by
*inventing* a roster — three roles from a hardcoded list, a default hours
figure, a zero bill rate and today+90d dates — and then computed a gross
margin from it with nothing to say the numbers were made up.

That is now refused (see :mod:`app.services.auto_staffing`). This module is
the honest alternative: a human supplies the plan, either by typing it into
the grid or by uploading this sheet.

Deliberately not reusing ``legacy_import``'s Excel parser. That one is for
bulk-importing historical projects, so every row must repeat ``sow_ref``,
``client_name`` and ``engagement_type``. Here the SOW is already known, and
asking someone to retype it per row is the kind of re-entry the whole
sow-first principle exists to remove.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

__all__ = [
    "COLUMNS",
    "StaffingSheetError",
    "SheetRow",
    "build_template_xlsx",
    "parse_staffing_xlsx",
]

# Column order is the contract — it is what the template writes and what the
# parser reads back, matched by header name so a reordered sheet still works.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("role", "Role"),
    ("seniority", "Seniority"),
    ("location", "Location"),
    ("allocation_pct", "Allocation (0-1)"),
    ("hours_billable", "Billable hours"),
    ("hourly_bill_rate", "Bill rate / hour"),
    ("start_date", "Start (YYYY-MM-DD)"),
    ("end_date", "End (YYYY-MM-DD)"),
)

_REQUIRED = ("role", "seniority", "location", "hours_billable")

ALLOWED_LOCATIONS = ("US", "India")


class StaffingSheetError(Exception):
    """The sheet could not be read. Carries per-row detail for the UI."""

    def __init__(self, message: str, errors: list[dict[str, Any]] | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


@dataclass
class SheetRow:
    row_number: int
    role: str
    seniority: str
    location: str
    allocation_pct: Decimal
    hours_billable: Decimal
    hourly_bill_rate: Decimal
    start_date: date | None
    end_date: date | None

    def to_resource_line(self) -> dict[str, Any]:
        """Shape the delivery-model / GM payload expects."""

        out: dict[str, Any] = {
            "role": self.role,
            "seniority": self.seniority,
            "location": self.location,
            "allocation_pct": format(self.allocation_pct, "f"),
            "hours_billable": format(self.hours_billable, "f"),
            "hourly_bill_rate": format(self.hourly_bill_rate, "f"),
        }
        if self.start_date:
            out["start_date"] = self.start_date.isoformat()
        if self.end_date:
            out["end_date"] = self.end_date.isoformat()
        return out


def build_template_xlsx() -> bytes:
    """The blank sheet a reviewer downloads, fills in and uploads back."""

    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Staffing"

    for col, (_key, header) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)
        ws.column_dimensions[cell.column_letter].width = max(len(header) + 4, 14)

    # One example row, clearly marked, so the expected format is obvious
    # without a separate instructions document.
    example = ["Consultant", "Senior", "US", 1, 160, 225, "2026-08-25", "2026-09-30"]
    for col, value in enumerate(example, start=1):
        ws.cell(row=2, column=col, value=value)
    ws.cell(row=3, column=1, value="(delete the example row above before uploading)")

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _dec(value: Any, *, field: str, row: int, default: Decimal | None = None) -> Decimal:
    if value is None or value == "":
        if default is not None:
            return default
        raise StaffingSheetError(
            f"row {row}: {field} is required",
            [{"row": row, "field": field, "message": "required"}],
        )
    try:
        return Decimal(str(value).replace(",", "").replace("$", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise StaffingSheetError(
            f"row {row}: {field} is not a number ({value!r})",
            [{"row": row, "field": field, "message": f"not a number: {value!r}"}],
        ) from exc


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def parse_staffing_xlsx(xlsx_bytes: bytes) -> list[SheetRow]:
    """Parse an uploaded staffing sheet.

    All-or-nothing: any invalid row rejects the whole upload, with every
    problem listed at once rather than one per attempt.
    """

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover — openpyxl is a hard dep
        raise StaffingSheetError(f"openpyxl not installed: {exc}") from exc

    try:
        wb = load_workbook(BytesIO(xlsx_bytes), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise StaffingSheetError(
            "could not read the file as .xlsx — re-save it from Excel"
        ) from exc

    ws = wb["Staffing"] if "Staffing" in wb.sheetnames else wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise StaffingSheetError("the sheet is empty")

    header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    index: dict[str, int] = {}
    for key, label in COLUMNS:
        want = label.strip().lower()
        if want in header:
            index[key] = header.index(want)
        elif key in header:  # tolerate raw keys as headers
            index[key] = header.index(key)

    missing_cols = [label for key, label in COLUMNS if key in _REQUIRED and key not in index]
    if missing_cols:
        raise StaffingSheetError(
            f"the sheet is missing required column(s): {', '.join(missing_cols)}"
        )

    def cell(row: tuple[Any, ...], key: str) -> Any:
        pos = index.get(key)
        if pos is None or pos >= len(row):
            return None
        return row[pos]

    out: list[SheetRow] = []
    errors: list[dict[str, Any]] = []

    for n, raw in enumerate(rows[1:], start=2):
        if raw is None or all(c in (None, "") for c in raw):
            continue
        first = str(cell(raw, "role") or "").strip()
        if not first or first.startswith("("):
            continue  # the template's own hint line

        try:
            location = str(cell(raw, "location") or "").strip()
            if location not in ALLOWED_LOCATIONS:
                errors.append(
                    {
                        "row": n,
                        "field": "location",
                        "message": (
                            f"must be one of {', '.join(ALLOWED_LOCATIONS)}; "
                            f"got {location or 'blank'!r}"
                        ),
                    }
                )
                continue

            row_obj = SheetRow(
                row_number=n,
                role=first,
                seniority=str(cell(raw, "seniority") or "").strip(),
                location=location,
                allocation_pct=_dec(
                    cell(raw, "allocation_pct"),
                    field="allocation_pct",
                    row=n,
                    default=Decimal("1"),
                ),
                hours_billable=_dec(
                    cell(raw, "hours_billable"), field="hours_billable", row=n
                ),
                hourly_bill_rate=_dec(
                    cell(raw, "hourly_bill_rate"),
                    field="hourly_bill_rate",
                    row=n,
                    default=Decimal("0"),
                ),
                start_date=_date(cell(raw, "start_date")),
                end_date=_date(cell(raw, "end_date")),
            )
        except StaffingSheetError as exc:
            errors.extend(exc.errors or [{"row": n, "message": exc.message}])
            continue

        if not row_obj.seniority:
            errors.append({"row": n, "field": "seniority", "message": "required"})
            continue
        if row_obj.hours_billable <= 0:
            errors.append(
                {"row": n, "field": "hours_billable", "message": "must be greater than 0"}
            )
            continue
        out.append(row_obj)

    if errors:
        raise StaffingSheetError(
            f"{len(errors)} row(s) could not be read", errors
        )
    if not out:
        raise StaffingSheetError("no staffing rows found in the sheet")
    return out
