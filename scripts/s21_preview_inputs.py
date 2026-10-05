"""Accepted HTML preview facts, canonical model inputs and independent money oracles.

This module performs no API, database, file, worker or provider operations.
Unspecified staffing cost/calendar inputs are deliberately not invented.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal


PREVIEW_PATH = "docs/directives/references/DealGate_Forecast_Preview (1).html"
AS_OF = "2026-10-15T12:00:00Z"

# Monthly monetary literals are transcribed from the accepted terms; not outputs
# of commercial/forecast code. Milestone cost follows the HTML cost/value basis.
SOURCES = (
    dict(id="cx-assess", client="Company X", title="Modern workplace assessment", model="Fixed assignment",
         profile="fixed_assignment", start=0, lifecycle="signed", probability="1", revenue=("24000",), cost=("14000",),
         source="Signed assessment SOW · §2 Scope and §4 Fees",
         evidence="Four-week assessment, findings report and roadmap. A fixed assignment fee of $24,000 covers this engagement."),
    dict(id="harbor-service", client="Harbor Health", title="Managed cloud operations", model="Monthly retainer",
         profile="recurring_msp", start=0, lifecycle="signed", probability="1", revenue=("32000",)*3, cost=("21000",)*3,
         source="Signed MSP SOW · §3 Service term",
         evidence="Monthly service fee: $32,000. Current service term ends 31 December 2026. Renewal is subject to agreement."),
    dict(id="north-project", client="Northstar Retail", title="Customer platform delivery", model="Milestone",
         profile="milestone", start=0, lifecycle="signed", probability="1", revenue=("40000", "60000", "50000", "30000"),
         cost=("24000", "36000", "30000", "18000"), source="Signed project SOW · Appendix B",
         evidence="Four delivery milestones across October to January. Total contracted fees: $180,000."),
    dict(id="atlas-staff", client="Atlas Bank", title="Application engineering team", model="Staff augmentation",
         profile="calendar_staff_aug", start=0, lifecycle="signed", probability="1", revenue=("48000",)*6, cost=("28800",)*6,
         source="Signed staffing SOW · §5 Commercial terms",
         evidence="Six engineers at an agreed combined monthly fee of $48,000 through March 2027."),
    dict(id="cedar-points", client="Cedar Labs", title="Product backlog delivery", model="Story point",
         profile="unit", start=0, lifecycle="signed", probability="1", revenue=("42000",)*3, cost=("24000",)*3,
         source="Signed product SOW · §6 Unit pricing",
         evidence="$140 per accepted story point. Contracted minimum: 300 accepted points per month for October–December; credits apply if not delivered."),
    dict(id="meridian-fixed", client="Meridian Group", title="Data readiness assignment", model="Fixed assignment",
         profile="fixed_assignment", start=0, lifecycle="signed", probability="1", revenue=("22500",)*2, cost=("13500",)*2,
         source="Signed assignment SOW · §4 Fee",
         evidence="A fixed fee of $45,000 covers the defined eight-week data readiness assignment."),
    dict(id="cx-next", client="Company X", title="Workplace modernization", model="Fixed assignment",
         profile="fixed_assignment", start=1, lifecycle="needs_review", probability="0.70", revenue=("70000",)*6, cost=("35000",)*6,
         parent="cx-assess", source="Assessment findings · §5 Recommended roadmap",
         evidence="Recommended implementation team: one solution architect, one delivery lead, three cloud engineers, one QA engineer and one business analyst. Proposed delivery duration: six months.",
         probability_source="Illustrative CRM stage probability; not extraction confidence.",
         assumptions=("November start is proposed; customer confirmation pending.", "Fixed fee of $420,000 is an estimate, not an approved quote.")),
    dict(id="harbor-renew", client="Harbor Health", title="Cloud operations renewal", model="Monthly retainer",
         profile="recurring_msp", start=3, lifecycle="tentative", probability="0.85", revenue=("32000",)*12, cost=("21000",)*12,
         parent="harbor-service", source="MSP SOW · §3 and renewal planning note",
         evidence="Current term ends 31 December 2026. A 12-month continuation at the current monthly fee is the planning scenario; it has not been signed.",
         probability_source="Illustrative renewal probability."),
    dict(id="north-cross", client="Northstar Retail", title="Managed security coverage", model="Monthly retainer",
         profile="recurring_msp", start=2, lifecycle="needs_review", probability="0.40", revenue=("18000",)*4, cost=("10000",)*4,
         parent="north-project", source="Delivery findings · security gap summary",
         evidence="The delivery assessment identifies a gap in ongoing security monitoring. Managed security is a suggested service, not an obligation in the current SOW.",
         probability_source="Illustrative early-stage probability.", assumptions=("Service coverage and customer interest need validation.",)),
    dict(id="atlas-extend", client="Atlas Bank", title="Engineering team extension", model="Staff augmentation",
         profile="calendar_staff_aug", start=6, lifecycle="tentative", probability="0.60", revenue=("48000",)*6, cost=("28800",)*6,
         parent="atlas-staff", source="Staffing SOW · term end plus account plan",
         evidence="Current term ends 31 March 2027. A six-month extension with the existing team is a planning scenario. Rates and staffing mix remain to be agreed.",
         probability_source="Illustrative CRM probability."),
    dict(id="cedar-up", client="Cedar Labs", title="Product backlog expansion", model="Story point",
         profile="unit", start=3, lifecycle="tentative", probability="0.50", revenue=("16800",)*3, cost=("9000",)*3,
         parent="cedar-points", source="Product backlog review · next release",
         evidence="An additional 120 accepted story points per month at $140 per point is proposed for January–March. Resource cost is estimated independently of story points.",
         probability_source="Illustrative proposal probability."),
    dict(id="meridian-next", client="Meridian Group", title="Data quality improvement", model="Fixed assignment",
         profile="fixed_assignment", start=2, lifecycle="needs_review", probability="0.35", revenue=("30000",), cost=("18000",),
         parent="meridian-fixed", source="Readiness findings · next work package",
         evidence="Data quality remediation is a possible four-week follow-on assignment. The fixed fee, staffing and December start are illustrative planning assumptions.",
         probability_source="Illustrative early-stage probability.", assumptions=("Fixed fee and start date require a customer discussion.",)),
)

EXPECTED = {
    "months": ("2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01", "2027-05-01", "2027-06-01",
               "2027-07-01", "2027-08-01", "2027-09-01", "2027-10-01", "2027-11-01", "2027-12-01"),
    "committed": ("208500", "204500", "172000", "78000", "48000", "48000", "0", "0", "0", "0", "0", "0", "0", "0", "0"),
    "expected": ("208500", "253500", "238700", "169800", "139800", "139800", "105000", "56000", "56000", "56000", "56000", "56000", "27200", "27200", "27200"),
    "upside": ("208500", "274500", "290000", "214800", "184800", "184800", "150000", "80000", "80000", "80000", "80000", "80000", "32000", "32000", "32000"),
    "quarters": {"committed": ("585000", "174000", "0", "0", "0"), "expected": ("700700", "449400", "217000", "168000", "81600"),
                 "upside": ("773000", "584400", "310000", "240000", "96000")},
    "future": {"committed": "174000", "expected": "666400", "upside": "894400"},
    "future_four_quarters": {"committed": "174000", "expected": "916000", "upside": "1230400"},
    "account_future_expected": {"Company X": "196000", "Harbor Health": "163200", "Northstar Retail": "51600",
                                "Atlas Bank": "230400", "Cedar Labs": "25200", "Meridian Group": "0"},
}


def month_at(offset):
    index = 2026 * 12 + 9 + offset
    return date(index // 12, index % 12 + 1, 1)


def records(*, location, timezone):
    """Caller must explicitly label its synthetic financial location/timezone.

    HTML supplies service months, not a universal delivery geography/calendar.
    These dimensions must never be presented as inferred production facts.
    """
    from app.services.commercial_models import parse_component
    if location not in {"US", "India"} or not timezone:
        raise ValueError("Explicit synthetic preview location/timezone required")
    result = []
    for source in SOURCES:
        months = [month_at(source["start"] + index) for index in range(len(source["revenue"]))]
        start, last = months[0], months[-1]
        end = last.replace(day=monthrange(last.year, last.month)[1])
        identity = source["id"]
        inputs = dict(component_id=identity, version="1", source_id=f"preview:{identity}", source_version="1",
            workstream_id=identity, profile=source["profile"], profile_version="1", policy_version="preview-confirmed-fixture-v1",
            source_evidence=[source["source"], source["evidence"]], service_start=start.isoformat(), service_end=end.isoformat(),
            timezone=timezone, currency="USD", billing_cadence="monthly",
            cost_basis="Accepted preview total cost allocated by the preview service-value basis; not inferred hourly staffing cost",
            costs_confirmed=True, costs=[dict(source_id=f"{identity}:{month}", month=month.isoformat(), location=location, amount=cost)
                for month, cost in zip(months, source["cost"], strict=True)], staffing=[])
        unknowns = []
        if source["profile"] == "fixed_assignment":
            inputs["pricing"] = dict(total_fee=str(sum(map(Decimal, source["revenue"]))),
                allocations=[dict(month=month.isoformat(), location=location, weight="1") for month in months],
                allocation_basis="Accepted preview equal monthly service allocation", minor_unit="0.01")
        elif source["profile"] == "recurring_msp":
            inputs["pricing"] = dict(fees=[dict(location=location, amount=source["revenue"][0])],
                proration="full_month", included_scope=source["evidence"], adjustments=[], usage=[])
        elif source["profile"] == "milestone":
            inputs["pricing"] = dict(milestones=[dict(milestone_id=f"{identity}-{index+1}",
                planned_date=month.isoformat(), location=location, amount=amount,
                acceptance_conditions="Preview planned milestone only; actual acceptance conditions are not supplied",
                approved_invoice_ref=None, recognized_revenue_ref=None)
                for index, (month, amount) in enumerate(zip(months, source["revenue"], strict=True))])
        elif source["profile"] == "unit":
            quantity = "300" if identity == "cedar-points" else "120"
            inputs["pricing"] = dict(rate="140", unit="accepted_story_point", contractual_basis="billable_units",
                quantities=[dict(source_id=f"{identity}:{month}", month=month.isoformat(), location=location,
                                 quantity=quantity) for month in months])
        else:
            # Preserve the monthly staffing model, not an invented hourly contract.
            inputs["pricing"] = dict(rates=[dict(assignment_id="six-engineers", basis="monthly", rate="8000",
                version="accepted-preview-monthly-team-fee", proration="full_month", hours_per_day=None)])
            inputs["staffing"] = [dict(assignment_id="six-engineers", source_id=inputs["source_id"], source_version="1",
                component_id=identity, profile_version="1", policy_version=inputs["policy_version"], role="Engineer",
                location=location, timezone=timezone, currency="USD", quantity=6, allocation="1", calendar=None,
                bill_rate=None, cost_rate=None, rate_version=None, cost_version=None,
                start=start.isoformat(), end=end.isoformat())]
            unknowns = ["Preview has an agreed 48000 monthly team fee/28800 monthly team budget, not hourly rates.",
                        "Canonical staffing calculation requires confirmed calendar and loaded hourly cost/version; preview does not provide them."]
        parse_component(inputs)
        result.append({**source, "inputs": inputs, "unknowns": unknowns,
            "preview_lifecycle": {"signed": "committed", "tentative": "planned", "needs_review": "draft"}[source["lifecycle"]],
            "fixture_assumptions": [f"Explicit synthetic financial bucket {location}/{timezone}; HTML does not define all location allocations.",
                "Month-start milestone dates stand for named preview months, not evidenced acceptance days."]})
    return result


def preflight(items):
    """Fail closed on any incomplete source or mismatched monthly monetary fact."""
    from app.gm.commercial import calculate_component
    from app.services.commercial_models import parse_component
    errors = []
    for item in items:
        schedule = calculate_component(parse_component(item["inputs"]))
        if not schedule.complete:
            errors.append({"id": item["id"], "unknowns": item["unknowns"],
                           "missing": [gap.reason for gap in schedule.missing]})
            continue
        expected = [(month_at(item["start"] + index), Decimal(revenue), Decimal(cost))
                    for index, (revenue, cost) in enumerate(zip(item["revenue"], item["cost"], strict=True))]
        observed = [(row.month, row.revenue, row.cost) for row in schedule.rows]
        if observed != expected:
            errors.append({"id": item["id"], "reason": "Calculated rows differ from independent monthly literals"})
    if errors:
        raise ValueError(errors)
    return {"sources": len(items), "accounts": len({item["client"] for item in items}), "complete": True}
