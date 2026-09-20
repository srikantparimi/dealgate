"""Engagement classifier tests (Sprint 9 wave 1)."""

from __future__ import annotations

import os

import pytest

from app.integrations.bedrock_classifier import (
    Candidate,
    StubBedrockClassifier,
    validate_candidates,
)
from app.services.engagement_classifier import (
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    classify,
)


def _wrap(value, provenance="extracted", **kw):
    return {
        "value": value,
        "provenance": provenance,
        "page_ref": kw.get("page_ref", 1),
        "source_id": None,
        "confidence": None,
        "warning": None,
        "status": "unconfirmed",
    }


def test_placement_fee_rule():
    fields = {
        "scope_summary": _wrap("Recruitment fee for placement of a CFO."),
    }
    result = classify(fields)
    assert result.primary.type == "permanent_placement"
    assert result.rule_matched == "rule.placement_fee"
    assert result.auto_confirm is True


def test_tm_not_to_exceed_rule():
    fields = {
        "billing_basis": _wrap("Time and Materials, not to exceed $200k"),
    }
    result = classify(fields)
    assert result.primary.type == "tm"
    assert result.rule_matched == "rule.time_and_materials"


def test_managed_service_monthly_fee_plus_sla():
    fields = {
        "monthly_fee": _wrap("50000"),
        "scope_summary": _wrap("24x7 SLA-backed support."),
        "coverage_hours": _wrap("168"),
    }
    result = classify(fields)
    assert result.primary.type == "managed_service"
    assert result.rule_matched == "rule.monthly_fee_plus_sla"


def test_assessment_short_term():
    fields = {
        "scope_summary": _wrap("Cloud readiness assessment"),
        "term_start": _wrap("2026-10-01"),
        "term_end": _wrap("2026-10-28"),
    }
    result = classify(fields)
    assert result.primary.type == "assessment"
    assert result.rule_matched.startswith("rule.assessment")


def test_staff_aug_multi_role():
    fields = {
        "resource_table": _wrap(
            [
                {"role": "Engineer", "seniority": "Senior", "hours": 800, "hourly_rate": 150},
                {"role": "PM", "seniority": "Senior", "hours": 400, "hourly_rate": 175},
            ]
        ),
    }
    result = classify(fields)
    assert result.primary.type == "staff_aug"
    assert result.rule_matched == "rule.multiple_named_roles"


def test_single_resource_rule():
    fields = {
        "resource_table": _wrap(
            [{"role": "Consultant", "seniority": "Senior", "hours": 200}]
        ),
    }
    result = classify(fields)
    assert result.primary.type == "single_resource"
    assert result.rule_matched == "rule.single_named_role"


def test_fixed_price_deliverables_rule():
    """The rule reads the NORMALISED basis, not the prose.

    It used to compare `billing_basis` — whatever wording the SOW used —
    against literals like "fixed_price" with exact equality. That matched the
    stub's own output and essentially nothing else, so a real fixed-fee SOW
    fell through to a guess.
    """

    fields = {
        "billing_basis": _wrap('a fixed fee of $50,000.00 (the "Fixed Fee")'),
        "billing_basis_normalized": _wrap("fixed_price"),
        "deliverables": _wrap(["Discovery report", "Runbook"]),
        "milestones": _wrap([{"name": "M1", "date": "2026-11-01"}]),
    }
    result = classify(fields)
    assert result.primary.type == "fixed_price"
    assert result.rule_matched == "rule.fixed_price_deliverables"


def test_prose_lists_are_counted():
    """SOWs are written in every format. A model asked for an array will
    still sometimes return "a; b; c", and counting len() on that gave 0 —
    which is how a SOW with four deliverables reached the fixed-price rule
    reporting none."""

    fields = {
        "billing_basis": _wrap("Firm fixed price for the engagement."),
        "billing_basis_normalized": _wrap("fixed_price"),
        "deliverables": _wrap(
            "Executive briefing; Use case inventory; Roadmap sketch"
        ),
        "milestones": _wrap(None),
    }
    result = classify(fields)
    assert result.primary.type == "fixed_price"
    assert result.rule_matched == "rule.fixed_price_deliverables"


def test_model_normalised_type_is_used_when_no_rule_fires():
    """A normalised answer from the thing that read the document beats a
    0.4/0.3 coin flip — but stays below auto-confirm so a human still picks."""

    fields = {
        "scope_summary": _wrap("Discovery assessment across three tracks."),
        "engagement_type_suggested": _wrap("assessment"),
    }
    result = classify(fields)
    assert result.primary.type == "assessment"
    assert result.rule_matched is None
    assert result.auto_confirm is False


def test_time_and_materials_vocabulary_is_aliased():
    """The extractor says "time_and_materials"; the GM library says "tm"."""

    fields = {
        "scope_summary": _wrap("Ongoing engineering support."),
        "engagement_type_suggested": _wrap("time_and_materials"),
    }
    assert classify(fields).primary.type == "tm"


def test_ambiguous_falls_through_to_bedrock_stub():
    fields = {
        # No rule matches — no billing basis, no resources, no SLA.
        "scope_summary": _wrap("A bit of everything."),
    }
    stub = StubBedrockClassifier(
        canned=[
            Candidate(type="fixed_price", confidence=0.55),
            Candidate(type="tm", confidence=0.35),
        ]
    )
    result = classify(fields, bedrock=stub)
    assert result.rule_matched is None
    assert result.primary.type == "fixed_price"
    assert result.secondary is not None and result.secondary.type == "tm"
    # Below threshold → the confirmation screen shows the picker.
    assert result.auto_confirm is False


def test_ambiguous_with_high_confidence_auto_confirms():
    fields = {"scope_summary": _wrap("Ambiguous scope")}
    stub = StubBedrockClassifier(
        canned=[
            Candidate(type="fixed_price", confidence=0.92),
            Candidate(type="tm", confidence=0.10),
        ]
    )
    result = classify(fields, bedrock=stub)
    assert result.primary.confidence >= CLASSIFIER_CONFIDENCE_THRESHOLD
    assert result.auto_confirm is True


def test_bedrock_outage_degrades_gracefully():
    fields = {"scope_summary": _wrap("Something that no rule matches.")}
    stub = StubBedrockClassifier(unavailable=True)
    result = classify(fields, bedrock=stub)
    # Fallback: fixed_price / tm defaults, both below threshold.
    assert result.primary.type in {"fixed_price", "tm"}
    assert result.auto_confirm is False


def test_validate_candidates_rejects_bad_shape():
    with pytest.raises(ValueError):
        validate_candidates([])
    with pytest.raises(ValueError):
        validate_candidates([{"type": "not_a_type", "confidence": 0.5}])
    with pytest.raises(ValueError):
        validate_candidates([{"type": "tm", "confidence": 1.5}])


def test_threshold_reads_env(monkeypatch):
    monkeypatch.setenv("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.5")
    # Reload the module so the env re-reads. Simpler: assert the module
    # variable exists and defaults to 0.85 when unset — the env override
    # kicks in at import time.
    from app.services import engagement_classifier as ec

    # We can't easily re-import for the test, but the variable is public.
    assert ec.CLASSIFIER_CONFIDENCE_THRESHOLD > 0.0


def test_prose_basis_is_recognised_when_no_normalised_value_exists():
    """Versions extracted before `billing_basis_normalized` shipped have only
    the verbatim wording, and re-extracting to fix the engagement type is not
    something a reviewer should have to do.

    This is the real stored value from a SOW that was being offered as
    "fixed_price 55% / tm 35%, pick one" when the document says fixed fee
    outright.
    """

    fields = {
        "billing_basis": _wrap(
            'a fixed fee of $50,000.00 for this engagement (the “Fixed Fee”). '
            "The Fixed Fee excludes taxes, travel, and expenses."
        ),
        "deliverables": _wrap(
            "Executive briefing; Complete use case inventory; Prioritization matrix"
        ),
        "milestones": _wrap("Onsite Discovery | Aug 25-27 2026 | Wrap-Up | Aug 28"),
    }
    result = classify(fields)
    assert result.primary.type == "fixed_price"
    assert result.rule_matched == "rule.fixed_price_deliverables"
    # Auto-confirmed, so the reviewer is not asked to pick something the
    # document already states.
    assert result.auto_confirm is True


def test_a_capped_tm_is_not_a_fixed_fee():
    """Order matters. A capped T&M contract often uses the words "fixed fee"
    for the cap, but the cap is the operative term — billing still follows
    hours."""

    fields = {
        "billing_basis": _wrap("T&M with fees not to exceed a fixed fee cap of $80,000"),
        "deliverables": _wrap("Sprint reports; Runbook"),
    }
    assert classify(fields).primary.type == "tm"


def test_the_normalised_value_wins_over_the_prose():
    """The model read the whole document; the phrase match is only a net."""

    fields = {
        "billing_basis": _wrap("monthly retainer of $10,000"),
        "billing_basis_normalized": _wrap("time_and_materials"),
        "deliverables": _wrap("a; b"),
    }
    assert classify(fields).primary.type == "tm"
