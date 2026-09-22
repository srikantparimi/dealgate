"""Expense terms remain proposals until a reviewer saves the GM version."""

from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedDirectCost(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: str = Field(min_length=1, max_length=32)
    note: str = Field(min_length=1, max_length=500)
    basis: Literal["amount", "percent_revenue"]
    basis_value: str | None
    location: Literal["US", "India", "proportional"]
    reimbursable: bool
    page_ref: int = Field(ge=1)


def _decimal_text(raw: str | None, *, percent: bool) -> str | None:
    if raw is None:
        return None
    value = raw.strip().removesuffix("%").strip() if percent else raw.strip()
    if not percent:
        value = value.removeprefix("USD").strip().removeprefix("$").replace(",", "")
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0:
        return None
    return format(number, "f")


def propose_direct_costs(extracted_fields: dict | None) -> list[dict]:
    entry = (extracted_fields or {}).get("direct_costs") or {}
    values = entry.get("value") if isinstance(entry, dict) else None
    if not isinstance(values, list):
        return []
    proposals = []
    for value in values:
        line = ExtractedDirectCost.model_validate(value)
        basis_value = _decimal_text(line.basis_value, percent=line.basis == "percent_revenue")
        proposals.append({
            "category": line.category,
            "note": line.note,
            "basis": line.basis,
            "basis_value": basis_value,
            "amount": basis_value if line.basis == "amount" else None,
            "location": line.location,
            "reimbursable": line.reimbursable,
            "provenance": "extracted",
            "source_ref": f"SOW p. {line.page_ref}",
        })
    return proposals
