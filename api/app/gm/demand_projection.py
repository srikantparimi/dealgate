"""Scoped presentation of an already globally allocated recruiting proposal."""
from decimal import Context, Decimal, Inexact, localcontext

from app.gm.engine import GM_PRECISION


def scoped_intervals(intervals, identities):
    selected, months = [], {}
    with localcontext(Context(prec=GM_PRECISION)) as context:
        context.traps[Inexact] = True
        for interval in intervals:
            rows = [row for row in interval["demands"] if row["id"] in identities]
            if not rows:
                continue
            selected.append({**interval, "demands": rows})
            month = interval["start"].replace(day=1)
            totals = {"peak_headcount": sum(row["quantity"] for row in rows),
                "peak_fte": sum((row["required_fte"] for row in rows), Decimal("0")),
                "gap_fte": sum((row["gap_fte"] for row in rows), Decimal("0"))}
            previous = months.setdefault(month, {"month": month, **totals})
            for key, value in totals.items():
                previous[key] = max(previous[key], value)
    return selected, list(months.values())
