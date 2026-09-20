"""Auto-staffing tests (Sprint 9 wave 1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.auto_staffing import (
    DEFAULT_FTE_HOURS_PER_WEEK,
    lines_to_payload_dicts,
    staff,
)


def _wrap(value, **kw):
    return {
        "value": value,
        "provenance": "extracted",
        "page_ref": kw.get("page_ref", 1),
        "source_id": None,
        "confidence": None,
        "warning": None,
        "status": "unconfirmed",
    }


@pytest.mark.asyncio
async def test_staff_aug_reads_resource_table():
    fields = {
        "resource_table": _wrap(
            [
                {
                    "role": "Engineer",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": 800,
                    "hourly_rate": 150,
                },
                {
                    "role": "PM",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": 400,
                    "hourly_rate": 175,
                },
            ]
        ),
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2026-12-31"),
    }
    result = await staff("staff_aug", fields)
    assert len(result.lines) == 2
    assert all(line.provenance == "extracted" for line in result.lines)
    assert result.lines[0].role == "Engineer"


@pytest.mark.asyncio
async def test_single_resource_uses_same_path():
    fields = {
        "resource_table": _wrap(
            [{"role": "Consultant", "seniority": "Senior", "hours": 200, "hourly_rate": 200}]
        ),
    }
    result = await staff("single_resource", fields)
    assert len(result.lines) == 1
    assert result.lines[0].provenance == "extracted"


@pytest.mark.asyncio
async def test_managed_service_headcount_from_coverage():
    fields = {
        "coverage_hours": _wrap("168"),  # 24x7 = 168 h/week
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2027-03-31"),
    }
    result = await staff("managed_service", fields)
    # 168 / 40 = 4.2 → 5 FTE (ceil).
    assert len(result.lines) == 5
    assert all(line.provenance == "calculated" for line in result.lines)
    assert any("coverage=" in n for n in result.notes)


@pytest.mark.asyncio
async def test_managed_service_no_coverage_warns():
    result = await staff("managed_service", {})
    assert result.lines == []
    assert any("coverage_hours missing" in n for n in result.notes)


@pytest.mark.asyncio
async def test_tm_uses_forecast_utilization_when_no_table():
    fields = {
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2026-12-31"),
    }
    result = await staff("tm", fields)
    assert len(result.lines) == 1
    assert result.lines[0].provenance == "defaulted"
    # 13 weeks × 40h × 0.75 = 390h
    assert result.lines[0].hours_billable > Decimal("300")


@pytest.mark.asyncio
async def test_tm_marks_resource_table_as_defaulted():
    fields = {
        "resource_table": _wrap(
            [{"role": "Consultant", "seniority": "Senior", "hours": 500, "hourly_rate": 200}]
        ),
    }
    result = await staff("tm", fields)
    # T&M downgrades extracted rows to "defaulted" — the cap is what
    # enforces the commitment, not the hours line.
    assert result.lines[0].provenance == "defaulted"


@pytest.mark.asyncio
async def test_fixed_price_looks_up_past_sows():
    fields = {
        "scope_summary": _wrap("Modernise loan origination platform."),
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2027-03-31"),
    }

    async def _past_search(_q: str):
        return [
            {
                "sow_version_id": "11111111-1111-1111-1111-111111111111",
                "chunk_text": "similar past project",
                "score": 0.91,
            }
        ]

    result = await staff("fixed_price", fields, past_sow_search=_past_search)
    assert len(result.lines) == 3
    assert all(line.provenance == "looked_up" for line in result.lines)
    assert "11111111-1111-1111-1111-111111111111" in result.sources


@pytest.mark.asyncio
async def test_fixed_price_proposes_nothing_when_no_past_sows():
    """No evidence, no proposal.

    This previously asserted the opposite: that a novel fixed-price scope
    produced three `defaulted` lines from a hardcoded roster, at a default
    hours figure and a ZERO bill rate, dated today+90d. A gross margin was
    then computed from those numbers with an empty `warnings` list, so
    nothing told Finance the inputs were invented. CLAUDE.md rule 6 wants a
    draft *with sources*; a guess with no source is a fabrication.
    """

    fields = {"scope_summary": _wrap("Novel scope with no history.")}

    async def _past_search(_q: str):
        return []

    result = await staff("fixed_price", fields, past_sow_search=_past_search)
    assert result.lines == []
    assert any("must be entered or uploaded" in n for n in result.notes)


@pytest.mark.asyncio
async def test_assessment_short_roster_only_with_a_cited_past_sow():
    """A roster is proposed only when a real approved SOW backs it."""

    fields = {
        "scope_summary": _wrap("Cloud readiness assessment."),
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2026-10-28"),
    }

    # No retrieval available → nothing proposed.
    bare = await staff("assessment", fields)
    assert bare.lines == []

    async def _past_search(_q: str):
        return [{"sow_version_id": "11111111-1111-1111-1111-111111111111"}]

    result = await staff("assessment", fields, past_sow_search=_past_search)
    assert len(result.lines) == 3
    # Every proposed line cites the SOW it came from.
    assert all(line.provenance == "looked_up" for line in result.lines)
    assert all(line.source_id for line in result.lines)
    # 4-week assessment: hours cap at 4 weeks × 40 = 160
    assert all(
        line.hours_billable <= DEFAULT_FTE_HOURS_PER_WEEK * Decimal("4")
        for line in result.lines
    )


@pytest.mark.asyncio
async def test_permanent_placement_no_lines():
    result = await staff("permanent_placement", {})
    assert result.lines == []


@pytest.mark.asyncio
async def test_unknown_type_raises():
    with pytest.raises(ValueError):
        await staff("nonsense", {})


@pytest.mark.asyncio
async def test_lines_to_payload_dicts_shape():
    fields = {
        "resource_table": _wrap(
            [{"role": "R", "seniority": "S", "location": "US", "hours": 100, "hourly_rate": 100}]
        ),
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2026-12-31"),
    }
    result = await staff("staff_aug", fields)
    dicts = lines_to_payload_dicts(result.lines)
    assert dicts[0]["role"] == "R"
    assert "start_date" in dicts[0]
    # ISO-formatted date so parse_resource_line accepts it.
    assert dicts[0]["start_date"].count("-") == 2
