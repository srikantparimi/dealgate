"""Generate the S6 legacy-import template + sample xlsx fixtures.

Run once at build time (``python fixtures/legacy_projects/_build.py``); the
outputs are checked in. Keeping this script alongside the fixtures makes
regeneration a one-liner if the template columns change (Task #18).

The columns and enums are read from ``app.services.legacy_import`` so this
script is the single source of truth for what a valid template looks like.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent

COLUMNS: tuple[str, ...] = (
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

FORMAT_NOTE = (
    "Formats: dates YYYY-MM-DD; allocation_pct 0-100; "
    "location one of {US, India}; engagement_type one of "
    "{staff_aug, single_resource, fixed_price, assessment, tm, managed_service}; "
    "seniority one of {junior, mid, senior, principal}; currency USD. "
    "hourly_loaded_cost is required (never treat missing as zero — §2)."
)


def _write_header(ws) -> None:
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="E5E7EB")
    for i, name in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=i, value=name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    note_cell = ws.cell(row=2, column=1, value=FORMAT_NOTE)
    note_cell.font = Font(italic=True, color="6B7280")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(COLUMNS))
    note_cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[2].height = 44

    for i, name in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(name) + 4)


def build_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Resources"
    _write_header(ws)
    wb.save(path)


def build_sample(path: Path) -> None:
    """Sample fixture for tests: three resources across US + India.

    Numbers picked so the hand-computed GM assertion in
    ``tests/test_legacy_gm_computation.py`` is trivial:

    * US Senior Data Engineer: 100h * $200 bill - 100h * $120 cost
      = $20,000 revenue, $12,000 cost -> GM 40%.
    * India Mid Backend: 100h * $80 bill - 100h * $30 cost
      = $8,000 revenue, $3,000 cost -> GM 62.5%.
    * India Junior QA: 50h * $50 bill - 50h * $20 cost
      = $2,500 revenue, $1,000 cost -> GM 60%.

    India component: 10,500 revenue, 4,000 cost -> GM 61.9047%.
    US component: 20,000 revenue, 12,000 cost -> GM 40%.
    """

    wb = Workbook()
    ws = wb.active
    ws.title = "Resources"
    _write_header(ws)

    rows = [
        {
            "sow_ref": "SOW-Client-A-2026-03",
            "client_name": "Acme Widgets, Inc.",
            "engagement_type": "staff_aug",
            "role": "Sr Data Engineer",
            "seniority": "senior",
            "location": "US",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "allocation_pct": 100,
            "billable_hours": 100,
            "hourly_bill_rate": 200,
            "hourly_loaded_cost": 120,
            "currency": "USD",
            "revenue_us": None,
            "revenue_india": None,
            "notes": "Sample line — 40% GM by hand.",
        },
        {
            "sow_ref": "SOW-Client-A-2026-03",
            "client_name": "Acme Widgets, Inc.",
            "engagement_type": "staff_aug",
            "role": "Backend Engineer",
            "seniority": "mid",
            "location": "India",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "allocation_pct": 100,
            "billable_hours": 100,
            "hourly_bill_rate": 80,
            "hourly_loaded_cost": 30,
            "currency": "USD",
            "revenue_us": None,
            "revenue_india": None,
            "notes": "Sample line — 62.5% GM by hand.",
        },
        {
            "sow_ref": "SOW-Client-A-2026-03",
            "client_name": "Acme Widgets, Inc.",
            "engagement_type": "staff_aug",
            "role": "QA Engineer",
            "seniority": "junior",
            "location": "India",
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "allocation_pct": 100,
            "billable_hours": 50,
            "hourly_bill_rate": 50,
            "hourly_loaded_cost": 20,
            "currency": "USD",
            "revenue_us": None,
            "revenue_india": None,
            "notes": "Sample line — 60% GM by hand.",
        },
    ]

    for r, row in enumerate(rows, start=3):
        for c, name in enumerate(COLUMNS, start=1):
            v = row.get(name)
            if isinstance(v, Decimal):
                v = float(v)
            ws.cell(row=r, column=c, value=v)

    wb.save(path)


if __name__ == "__main__":
    build_template(HERE / "template.xlsx")
    build_sample(HERE / "sample_client_a.xlsx")
    print("wrote:", HERE / "template.xlsx")
    print("wrote:", HERE / "sample_client_a.xlsx")
