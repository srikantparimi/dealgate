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
        "deliverable_count": _count_items(deliverables),
        "milestone_count": _count_items(milestones),
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
        # The model's normalised answer, or — for a version extracted before
        # that field existed — the basis recognised in the verbatim wording.
        "billing_basis_normalized": (
            value_of(extracted.get("billing_basis_normalized"))
            or _basis_from_prose(value_of(extracted.get("billing_basis")))
        ),
        # What the model concluded the engagement is, having read the whole
        # document. Used when no structural rule fires — a normalised answer
        # from something that read the prose beats a coin-flip default.
        "engagement_type_suggested": value_of(
            extracted.get("engagement_type_suggested")
        ),
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


def _count_items(value: Any) -> int:
    """Count list-shaped content whether it arrives as a list or as prose.

    The extractor is now asked for arrays, but SOWs are written in every
    format and a model will still sometimes return
    "Executive briefing; use case inventory; roadmap" as one string. Counting
    `len()` on that gave 0 — which is how a SOW with four deliverables and
    three milestones reached the fixed-price rule reporting neither.
    """

    if value is None:
        return 0
    if isinstance(value, (list, tuple)):
        return len([v for v in value if v not in (None, "")])
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return 0
        for sep in (";", "|", "\n"):
            if sep in text:
                return len([p for p in text.split(sep) if p.strip()])
        return 1
    return 0


# The classifier speaks "tm"; the extractor's vocabulary says
# "time_and_materials". One alias table rather than the two drifting apart.
_TYPE_ALIASES: dict[str, str] = {
    "time_and_materials": "tm",
    "t&m": "tm",
    "tm": "tm",
    "fixed_price": "fixed_price",
    "fixed_fee": "fixed_price",
    "managed_service": "managed_service",
    "staff_aug": "staff_aug",
    "single_resource": "single_resource",
    "assessment": "assessment",
    "permanent_placement": "permanent_placement",
}


# Phrases that identify a billing basis when no normalised value is present.
#
# The model normalises now, but versions extracted before that shipped have
# only the verbatim wording, and re-extracting an existing version is not
# something a reviewer should have to do to get their engagement type right.
# This is a safety net under the model, not a replacement for it: it matches
# phrases as they are actually written rather than comparing a sentence to an
# enum literal, which is what never worked.
_BASIS_PHRASES: tuple[tuple[str, str], ...] = (
    ("not to exceed", "not_to_exceed"),
    ("not-to-exceed", "not_to_exceed"),
    ("time and materials", "time_and_materials"),
    ("time & materials", "time_and_materials"),
    ("t&m", "time_and_materials"),
    ("fixed fee", "fixed_price"),
    ("fixed-fee", "fixed_price"),
    ("fixed price", "fixed_price"),
    ("firm fixed", "fixed_price"),
    ("lump sum", "fixed_price"),
    ("placement fee", "placement_fee"),
    ("recruitment fee", "placement_fee"),
    ("monthly fee", "monthly_fee"),
    ("per month", "monthly_fee"),
    ("monthly retainer", "monthly_fee"),
    ("per hour", "hourly"),
    ("hourly rate", "hourly"),
    ("per day", "daily"),
    ("day rate", "daily"),
)


def _basis_from_prose(text: str | None) -> str | None:
    """Recognise a billing basis in the wording a SOW actually uses.

    Order matters: "not to exceed" is checked before "fixed fee" because a
    capped T&M contract often mentions both, and the cap is the operative
    term.
    """

    if not isinstance(text, str) or not text.strip():
        return None
    lowered = text.lower()
    for phrase, basis in _BASIS_PHRASES:
        if phrase in lowered:
            return basis
    return None


def _canonical_type(value: str) -> str | None:
    """Map a model-supplied engagement type onto the library's vocabulary."""

    return _TYPE_ALIASES.get(value.strip().lower())


def _apply_rules(features: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(engagement_type, rule_id)`` if a rule locks in, else None."""

    # The NORMALISED basis, not the prose. `billing_basis` holds whatever
    # the SOW actually says — "a fixed fee of $50,000.00 for this engagement
    # (the \u201cFixed Fee\u201d)" — and comparing that to a literal like
    # "fixed_fee" with `in (...)` never matched anything a real document
    # produced. The model normalises; this reads the normalised value.
    basis = (features.get("billing_basis_normalized") or "").strip().lower()

    # Permanent placement — the manifesto's simplest signal.
    if features["scope_mentions_placement"] or basis == "placement_fee":
        return ("permanent_placement", "rule.placement_fee")

    # T&M / not-to-exceed.
    if basis in ("time_and_materials", "not_to_exceed") or features["not_to_exceed"]:
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
    if basis in ("fixed_price", "milestone") and (
        features["deliverable_count"] > 0 or features["milestone_count"] > 0
    ):
        return ("fixed_price", "rule.fixed_price_deliverables")

    if basis == "placement_fee":
        return ("permanent_placement", "rule.placement_fee_basis")

    if basis == "monthly_fee":
        return ("managed_service", "rule.monthly_fee_basis")

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

    # No structural rule fired. Before falling back to a guess, use what the
    # extractor already concluded from reading the whole document — it has
    # seen the prose, and a normalised answer from the thing that read it
    # beats a 0.4/0.3 default pair. Held below the auto-confirm threshold so
    # the reviewer still gets the two-candidate chooser rather than a silent
    # decision.
    suggested = features.get("engagement_type_suggested")
    if isinstance(suggested, str):
        normalised = _canonical_type(suggested)
        if normalised is not None:
            second = "fixed_price" if normalised != "fixed_price" else "tm"
            return ClassifierResult(
                primary=Candidate(type=normalised, confidence=0.75),
                secondary=Candidate(type=second, confidence=0.25),
                rule_matched=None,
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
