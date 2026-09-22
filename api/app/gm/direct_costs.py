"""Direct-cost bases and Finance totals; all arithmetic stays in the GM library."""

from decimal import Decimal
from typing import Any

from app.gm.types import TemplateResult


def resolve_direct_costs(lines: list[Any], labor: TemplateResult) -> tuple[list[dict], list[Decimal], Decimal]:
    costs: list[dict] = []
    amounts: list[Decimal] = []
    pass_through = Decimal("0")
    for line in lines:
        value = line.basis_value if line.basis_value is not None else line.amount
        amount = labor.revenue_total * value / Decimal("100") if line.basis == "percent_revenue" else value
        amounts.append(amount)
        if line.reimbursable:
            pass_through += amount
            continue
        if amount == 0:
            continue
        if line.location == "proportional":
            if not labor.complete or labor.cost_total <= 0:
                raise ValueError("proportional direct costs require complete, positive labor costs; choose US or India")
            us = amount * labor.cost_us / labor.cost_total
            portions = (("US", us), ("India", amount - us))
        else:
            portions = ((line.location, amount),)
        for location, portion in portions:
            if portion:
                costs.append({"category": line.category, "amount": format(portion, "f"),
                              "location": location, "note": line.note or ""})
    return costs, amounts, pass_through


def finance_summary(result: TemplateResult, labor: TemplateResult, pass_through: Decimal) -> dict:
    revenue = result.revenue_total
    direct = result.cost_total - labor.cost_total
    complete = result.complete and labor.complete
    return {
        "revenue": revenue, "labor_cost": labor.cost_total if complete else None, "direct_cost": direct,
        "total_delivery_cost": result.cost_total if complete else None,
        "gross_profit": revenue - result.cost_total if complete else None,
        "labor_pct": labor.cost_total / revenue if complete and revenue > 0 else None,
        "direct_pct": direct / revenue if revenue > 0 else None,
        "total_cost_pct": result.cost_total / revenue if complete and revenue > 0 else None,
        "pass_through": pass_through,
    }


def floor_delta(margin: Decimal | None, floor: Decimal) -> Decimal | None:
    return margin - floor if margin is not None else None
