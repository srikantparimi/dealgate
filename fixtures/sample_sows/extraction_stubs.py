"""Deterministic extraction stubs for the six sample SOWs (S9 wave 2).

For each fixture PDF under ``fixtures/sample_sows/``, this module returns
the canonical ``extracted_fields`` payload the real Bedrock/Textract
pipeline would produce. E2E specs seed the stub so the SOW-first
pipeline (:mod:`api.app.services.sow_confirmation`) can run without
depending on a real model.

The exported shape matches
:data:`api.app.integrations.bedrock_sow_extract.EXTRACTED_FIELDS` and is
accepted by :func:`api.app.integrations.bedrock_sow_extract.validate_extract`.

Every stub is a pure Python literal — no time-dependent value, no random
number, no environment lookup. Regenerate the PDFs from this same
module and the bytes are identical every run.

Also exports :data:`STAFFING_META` (headcount + primary role hints) so
the E2E specs can seed the resource_table extraction hints that
:mod:`api.app.services.auto_staffing` reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# --- per-fixture canned extractions ---------------------------------------
#
# Field values line up with `api.app.integrations.bedrock_sow_extract.EXTRACTED_FIELDS`.
# Extra keys (like `resource_table`, `monthly_fee`, `coverage_hours`,
# `primary_location`, `fte_hours_per_week`, `primary_role`,
# `primary_seniority`) are consumed by the classifier + auto-staffing
# feature extractors; they are stored on the SowVersion's extracted_fields
# via the same `PATCH .../fields/<name>` endpoint. They land as unknown
# to `validate_extract` — the E2E specs write them after the schema pass
# via a second seed step so both consumers see them.


FIXTURES: dict[str, dict[str, Any]] = {
    "01_staff_aug_us.pdf": {
        # Schema fields — validated by `validate_extract`.
        "fields": {
            "client_legal_name": {
                "value": "Contoso Data Services, LLC",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "contoso.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "Provide three named consultants (2 Senior Data Engineers, "
                    "1 Data Analyst) on the client's Data Platform team, "
                    "full-time, remote from US."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "324000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "hourly",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-01", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2026-12-31", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2026-12-01", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": ["Sprint reports", "Weekly status decks", "Runbook updates"],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "Client program lead sign-off on weekly timesheet.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "Client provides laptop images and VPN access day 1.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Travel unless pre-approved in writing.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Jordan Miles", "role": "Client program lead"},
                    {"name": "Sam Rivera", "role": "Delivery lead"},
                ],
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "staff_aug",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        # Auxiliary hints — patched onto extracted_fields after the
        # schema-validated pass so the classifier + auto-staff see them.
        "aux": {
            "resource_table": [
                {
                    "role": "Senior Data Engineer",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": "480",
                    "hourly_rate": "225",
                    "person_name": "Consultant A",
                },
                {
                    "role": "Senior Data Engineer",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": "480",
                    "hourly_rate": "225",
                    "person_name": "Consultant B",
                },
                {
                    "role": "Data Analyst",
                    "seniority": "Mid",
                    "location": "US",
                    "hours": "480",
                    "hourly_rate": "150",
                    "person_name": "Consultant C",
                },
            ],
            "primary_location": "US",
        },
        # Expected classifier outcome (for both the E2E assertions and the
        # generator's --validate self-check).
        "expected_engagement_type": "staff_aug",
        "expected_rule": "rule.multiple_named_roles",
    },
    "02_managed_service_india.pdf": {
        "fields": {
            "client_legal_name": {
                "value": "Fabrikam Operations Pvt Ltd",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "fabrikam.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "24x7 managed service for the client's data pipelines. "
                    "168 hours of weekly coverage across three shifts, "
                    "minimum 3 FTEs delivered from India. SLA: P1 response "
                    "under 15 minutes, restore under 4 hours."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "216000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "monthly_fee",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-01", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2027-09-30", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2027-07-31", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": ["Monthly SLA report", "Runbook maintenance", "On-call rota"],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "Monthly SLA report accepted by client operations.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "Client provides observability dashboards and PagerDuty rota.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "New feature build outside of runbook fixes.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Priya Ravi", "role": "Client operations lead"},
                    {"name": "Marco Lin", "role": "Managed services lead"},
                ],
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "managed_service",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        "aux": {
            "monthly_fee": "18000",
            "coverage_hours": "168",
            "primary_location": "India",
            "primary_role": "Support Engineer",
            "primary_seniority": "Mid",
            "fte_hours_per_week": "40",
        },
        "expected_engagement_type": "managed_service",
        "expected_rule": "rule.monthly_fee_plus_sla",
    },
    "03_fixed_price_mixed.pdf": {
        "fields": {
            "client_legal_name": {
                "value": "Northwind Traders, Inc.",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "northwind.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "Fixed-price data platform modernisation delivered by a "
                    "mixed US + India team. Six deliverables spanning "
                    "discovery, design, build, and cutover."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "250000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-01", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2027-03-31", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2027-01-31", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": [
                    "Discovery report",
                    "Target architecture",
                    "Data model",
                    "Ingestion pipelines",
                    "Cutover plan",
                    "Runbook",
                ],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [
                    {"name": "Discovery", "date": "2026-10-31"},
                    {"name": "Design", "date": "2026-11-30"},
                    {"name": "Build", "date": "2027-01-31"},
                    {"name": "Cutover", "date": "2027-03-15"},
                ],
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "UAT sign-off by client sponsor per milestone.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "Client provides AWS account and IAM access day 1.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Third-party tool licences.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Alex Chen", "role": "Client sponsor"},
                    {"name": "Riya Patel", "role": "Delivery lead"},
                ],
                "page_ref": 7,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        "aux": {
            "primary_location": "US",
        },
        "expected_engagement_type": "fixed_price",
        "expected_rule": "rule.fixed_price_deliverables",
    },
    "04_assessment_4week.pdf": {
        "fields": {
            "client_legal_name": {
                "value": "Adventure Works Group",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "adventure-works.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "Four-week data platform assessment. Three workshops with "
                    "the client's data leadership, US resources, deliverable "
                    "is a written recommendations report."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "40000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-05", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2026-11-02", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2026-10-26", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": [
                    "Workshop 1 notes",
                    "Workshop 2 notes",
                    "Workshop 3 notes",
                    "Recommendations report",
                ],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [
                    {"name": "Kickoff", "date": "2026-10-05"},
                    {"name": "Findings review", "date": "2026-10-26"},
                    {"name": "Final report", "date": "2026-11-02"},
                ],
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "Client sponsor signs off on the final recommendations report.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "Client leadership available for three 2-hour workshops.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Implementation work; separate SOW.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Dana Whitaker", "role": "Client sponsor"},
                    {"name": "Nikhil Rao", "role": "Assessment lead"},
                ],
                "page_ref": 7,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "assessment",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        "aux": {
            "primary_location": "US",
        },
        "expected_engagement_type": "assessment",
        # The classifier keys "assessment" off the *workshop* scope + short
        # term (2 months or less). Either `rule.assessment_short_term` or
        # `rule.assessment_workshop` is acceptable for this fixture.
        "expected_rule": "rule.assessment_short_term",
    },
    "05_tm_capped.pdf": {
        "fields": {
            "client_legal_name": {
                "value": "Tailspin Toys, LLC",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "tailspin.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "Time and materials engagement not to exceed USD 150,000. "
                    "US resources, rates listed below. Client approves "
                    "timesheets weekly."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "150000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "time_and_materials",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-01", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2027-03-31", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2027-01-31", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": ["Weekly timesheets", "Sprint demos", "Sprint reports"],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "Client program manager approves weekly timesheets.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": "T&M cap is not to exceed; hours logged in client system.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Anything outside the agreed sprint scope.",
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Casey Morgan", "role": "Client program manager"},
                    {"name": "Ivy Rhodes", "role": "T&M delivery lead"},
                ],
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "tm",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        "aux": {
            "resource_table": [
                {
                    "role": "Consultant",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": "600",
                    "hourly_rate": "225",
                },
                {
                    "role": "Consultant",
                    "seniority": "Mid",
                    "location": "US",
                    "hours": "400",
                    "hourly_rate": "175",
                },
            ],
            "primary_location": "US",
        },
        "expected_engagement_type": "tm",
        "expected_rule": "rule.time_and_materials",
    },
    "06_below_floor.pdf": {
        "fields": {
            "client_legal_name": {
                "value": "Wingtip Financial, Inc.",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "client_domain": {
                "value": "wingtip.example.com",
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "scope_summary": {
                "value": (
                    "Mixed fixed-fee engagement. Below-floor pricing for both "
                    "US and India components — will trigger a CEO exception."
                ),
                "page_ref": 1,
                "status": "unconfirmed",
            },
            "price": {"value": "145000.00", "page_ref": 2, "status": "unconfirmed"},
            "currency": {"value": "USD", "page_ref": 2, "status": "unconfirmed"},
            "billing_basis": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
            "term_start": {"value": "2026-10-01", "page_ref": 3, "status": "unconfirmed"},
            "term_end": {"value": "2027-03-31", "page_ref": 3, "status": "unconfirmed"},
            "notice_date": {"value": "2027-01-31", "page_ref": 3, "status": "unconfirmed"},
            "deliverables": {
                "value": [
                    "Discovery",
                    "Build increment 1",
                    "Build increment 2",
                    "Cutover",
                ],
                "page_ref": 4,
                "status": "unconfirmed",
            },
            "milestones": {
                "value": [
                    {"name": "Discovery", "date": "2026-10-31"},
                    {"name": "Build 1", "date": "2026-12-31"},
                    {"name": "Build 2", "date": "2027-02-15"},
                    {"name": "Cutover", "date": "2027-03-15"},
                ],
                "page_ref": 5,
                "status": "unconfirmed",
            },
            "acceptance_criteria": {
                "value": "Cutover acceptance test signed by client sponsor.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "assumptions": {
                "value": (
                    "Discounted rates reflect a strategic seed engagement; "
                    "renegotiated at renewal per policy."
                ),
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "exclusions": {
                "value": "Any change requests outside the four deliverables.",
                "page_ref": 6,
                "status": "unconfirmed",
            },
            "signatories": {
                "value": [
                    {"name": "Robin Vance", "role": "Client sponsor"},
                    {"name": "Sunil Iyer", "role": "Delivery lead"},
                ],
                "page_ref": 7,
                "status": "unconfirmed",
            },
            "engagement_type_suggested": {
                "value": "fixed_price",
                "page_ref": 2,
                "status": "unconfirmed",
            },
        },
        "aux": {
            "primary_location": "US",
        },
        "expected_engagement_type": "fixed_price",
        "expected_rule": "rule.fixed_price_deliverables",
    },
}


def load(name: str) -> dict[str, Any]:
    """Return the canonical extraction payload for one fixture PDF."""

    if name not in FIXTURES:
        raise KeyError(f"unknown fixture {name!r}; known: {sorted(FIXTURES)}")
    return FIXTURES[name]


def all_names() -> list[str]:
    return sorted(FIXTURES)


def export_json(dest: Path) -> None:
    """Serialise FIXTURES to JSON so the TS E2E layer can consume it."""

    dest.write_text(json.dumps(FIXTURES, indent=2, sort_keys=True) + "\n")


__all__ = ["FIXTURES", "all_names", "export_json", "load"]
