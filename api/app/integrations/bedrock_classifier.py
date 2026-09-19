"""Bedrock engagement-type classifier (Sprint 9 wave 1, story A/B).

The classifier lives here so the service layer stays offline-testable and
the real invoke_model wiring can land later without touching business
logic. Every candidate is validated against a tiny JSON schema before it
reaches the service (rule 6 — never persist raw model output).

Two adapters are shipped:

- :class:`BedrockClassifier` — real Bedrock caller stub (returns "unavailable").
- :class:`StubBedrockClassifier` — deterministic canned scores for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ENGAGEMENT_TYPES: tuple[str, ...] = (
    "staff_aug",
    "single_resource",
    "managed_service",
    "fixed_price",
    "assessment",
    "tm",
    "permanent_placement",
)

PROMPT_VERSION = "engagement_classify.v1"
MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"


@dataclass(frozen=True)
class Candidate:
    """One (type, confidence) pair the classifier proposes."""

    type: str
    confidence: float


def validate_candidates(raw: Any) -> list[Candidate]:
    """Validate the model payload and return sorted candidates.

    Rejects unknown types, non-numeric confidences and payloads that
    aren't a list of ``{type, confidence}`` objects.
    """

    if not isinstance(raw, list) or not raw:
        raise ValueError("candidates must be a non-empty list")
    out: list[Candidate] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"candidates[{i}] must be an object")
        typ = item.get("type")
        conf = item.get("confidence")
        if typ not in ENGAGEMENT_TYPES:
            raise ValueError(
                f"candidates[{i}].type must be one of {list(ENGAGEMENT_TYPES)}"
            )
        try:
            conf_val = float(conf)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"candidates[{i}].confidence must be numeric") from exc
        if not 0.0 <= conf_val <= 1.0:
            raise ValueError(f"candidates[{i}].confidence out of [0, 1]")
        out.append(Candidate(type=typ, confidence=conf_val))
    out.sort(key=lambda c: c.confidence, reverse=True)
    return out


class BedrockClassifier:
    """Real Bedrock caller — stubbed until model access is enabled."""

    def classify(self, extracted_fields: dict[str, Any]) -> list[Candidate]:
        # Deferred to the story that enables Bedrock model access. Until
        # then the service falls back to the top rule candidate.
        raise RuntimeError("bedrock classifier not yet implemented")


class StubBedrockClassifier(BedrockClassifier):
    """Deterministic classifier used by tests + offline dev.

    Returns fixed_price/tm 50/50 by default so the service's ambiguity
    branch is exercised. Override :attr:`canned` per test.
    """

    def __init__(
        self,
        *,
        canned: list[Candidate] | None = None,
        unavailable: bool = False,
    ) -> None:
        self.canned = canned or [
            Candidate(type="fixed_price", confidence=0.55),
            Candidate(type="tm", confidence=0.35),
        ]
        self.unavailable = unavailable
        self.calls: list[dict[str, Any]] = []

    def classify(self, extracted_fields: dict[str, Any]) -> list[Candidate]:
        self.calls.append(extracted_fields)
        if self.unavailable:
            raise RuntimeError("stub bedrock classifier unavailable")
        # Validate through the same schema real payloads take so a
        # bad stub cannot dodge the safety net.
        return validate_candidates(
            [{"type": c.type, "confidence": c.confidence} for c in self.canned]
        )


__all__ = [
    "Candidate",
    "ENGAGEMENT_TYPES",
    "MODEL_ID",
    "PROMPT_VERSION",
    "BedrockClassifier",
    "StubBedrockClassifier",
    "validate_candidates",
]
