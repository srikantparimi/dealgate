"""Engagement-type classifier (Sprint 9 wave 1).

Rules first (manifesto §2). When rules land unambiguously we return
``confidence=1.0`` with a ``rule_matched`` label so the audit stream can
trace the decision. When rules are ambiguous the classifier falls
through to :class:`BedrockClassifier` and returns the top two
candidates; the UI asks the human to pick.

Threshold: default ``0.85`` from ``CLASSIFIER_CONFIDENCE_THRESHOLD``.
Above → auto-select. Below → surface both candidates to the confirmation
screen.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.bedrock_classifier import (
    BedrockClassifier,
    Candidate,
    StubBedrockClassifier,
)
from app.services.provenance import value_of


CLASSIFIER_CONFIDENCE_THRESHOLD = float(
    os.environ.get("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.85")
)


@dataclass(frozen=True)
class ClassifierResult:
    """Structured output the confirmation endpoint consumes."""

    primary: Candidate
    secondary: Candidate | None = None
    rule_matched: str | None = None
    features: dict[str, Any] = field(default_factory=dict)

    @property
    def auto_confirm(self) -> bool:
        return self.primary.confidence >= CLASSIFIER_CONFIDENCE_THRESHOLD


# --- feature extraction ----------------------------------------------------


def _to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _scope_text(extracted: dict[str, Any]) -> str:
    parts: list[str] = []
    for name in ("scope_summary", "acceptance_criteria", "assumptions"):
        val = value_of(extracted.get(name))
        if isinstance(val, str) and val:
            parts.append(val)
    return " ".join(parts).lower()


def _extract_features(extracted: dict[str, Any]) -> dict[str, Any]:
    """Pull out the deterministic signals the rules key on."""

    billing_basis = value_of(extracted.get("billing_basis"))
    resource_table = value_of(extracted.get("resource_table")) or value_of(
        extracted.get("resources")
    )
    deliverables = value_of(extracted.get("deliverables")) or []
    milestones = value_of(extracted.get("milestones")) or []
    monthly_fee = _to_decimal(value_of(extracted.get("monthly_fee")))
    coverage_hours = _to_decimal(value_of(extracted.get("coverage_hours")))
    price = _to_decimal(value_of(extracted.get("price")))
    scope = _scope_text(extracted)

    features: dict[str, Any] = {
        "billing_basis": billing_basis,
        "has_resource_table": bool(resource_table),
        "resource_count": len(resource_table) if isinstance(resource_table, list) else 0,
        "deliverable_count": len(deliverables) if isinstance(deliverables, list) else 0,
        "milestone_count": len(milestones) if isinstance(milestones, list) else 0,
        "monthly_fee": monthly_fee,
        "coverage_hours": coverage_hours,
        "price": price,
        "scope_mentions_sla": bool(re.search(r"\bsla\b|service level", scope)),
        "scope_mentions_assessment": "assessment" in scope,
        "scope_mentions_workshop": "workshop" in scope,
        "scope_mentions_placement": "placement fee" in scope
        or "recruitment fee" in scope,
        "not_to_exceed": (
            isinstance(billing_basis, str) and "not to exceed" in billing_basis.lower()
        )
        or "not to exceed" in scope,
        "term_months": _term_months(extracted),
    }
    return features


def _term_months(extracted: dict[str, Any]) -> int | None:
    """Approximate months between term_start and term_end, if both present."""

    from datetime import date

    start_raw = value_of(extracted.get("term_start"))
    end_raw = value_of(extracted.get("term_end"))

    def _parse(d: Any) -> date | None:
        if isinstance(d, date):
            return d
        if not isinstance(d, str):
            return None
        try:
            return date.fromisoformat(d)
        except ValueError:
            return None

    s = _parse(start_raw)
    e = _parse(end_raw)
    if s is None or e is None:
        return None
    days = (e - s).days
    if days < 0:
        return None
    return max(1, round(days / 30))


# --- rules -----------------------------------------------------------------


def _apply_rules(features: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(engagement_type, rule_id)`` if a rule locks in, else None."""

    basis = (features["billing_basis"] or "").lower() if features["billing_basis"] else ""

    # Permanent placement — the manifesto's simplest signal.
    if features["scope_mentions_placement"] or basis == "placement_fee":
        return ("permanent_placement", "rule.placement_fee")

    # T&M / not-to-exceed.
    if basis in ("tm", "time_and_materials", "t&m") or features["not_to_exceed"]:
        return ("tm", "rule.time_and_materials")

    # Managed service: monthly fee + SLA / coverage hours.
    if (
        features["monthly_fee"] is not None
        and (features["scope_mentions_sla"] or features["coverage_hours"] is not None)
    ):
        return ("managed_service", "rule.monthly_fee_plus_sla")

    # Assessment: short-term (2–6 weeks) with workshop / assessment scope.
    term = features["term_months"]
    if (
        features["scope_mentions_assessment"]
        and (term is not None and 0 < term <= 2)
    ):
        return ("assessment", "rule.assessment_short_term")
    if features["scope_mentions_workshop"] and (term is not None and 0 < term <= 2):
        return ("assessment", "rule.assessment_workshop")

    # Staff aug / single resource: named roles with hourly/daily rates.
    if features["has_resource_table"] and features["resource_count"] > 0:
        if features["resource_count"] == 1:
            return ("single_resource", "rule.single_named_role")
        return ("staff_aug", "rule.multiple_named_roles")

    # Fixed price: fixed_price billing basis + deliverables/milestones.
    if basis in ("fixed_price", "fixed", "fixed_fee") and (
        features["deliverable_count"] > 0 or features["milestone_count"] > 0
    ):
        return ("fixed_price", "rule.fixed_price_deliverables")

    return None


# --- public API ------------------------------------------------------------


def classify(
    extracted_fields: dict[str, Any] | None,
    *,
    bedrock: BedrockClassifier | None = None,
) -> ClassifierResult:
    """Classify one SOW's extracted fields.

    ``bedrock`` defaults to :class:`StubBedrockClassifier` so callers
    without an adapter still get deterministic behaviour (the stub only
    fires when rules are ambiguous).
    """

    extracted_fields = extracted_fields or {}
    features = _extract_features(extracted_fields)

    matched = _apply_rules(features)
    if matched is not None:
        typ, rule_id = matched
        return ClassifierResult(
            primary=Candidate(type=typ, confidence=1.0),
            rule_matched=rule_id,
            features=features,
        )

    # Ambiguous → ask the model. Any adapter failure downgrades to a
    # deterministic default so the confirm page never blocks on Bedrock.
    ad = bedrock or StubBedrockClassifier()
    try:
        candidates = ad.classify(extracted_fields)
    except Exception:  # noqa: BLE001 — never block on classifier outage
        candidates = [
            Candidate(type="fixed_price", confidence=0.4),
            Candidate(type="tm", confidence=0.3),
        ]

    primary = candidates[0]
    secondary = candidates[1] if len(candidates) > 1 else None
    return ClassifierResult(
        primary=primary,
        secondary=secondary,
        rule_matched=None,
        features=features,
    )


__all__ = [
    "CLASSIFIER_CONFIDENCE_THRESHOLD",
    "Candidate",
    "ClassifierResult",
    "classify",
]
