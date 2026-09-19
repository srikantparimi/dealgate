"""Bedrock-backed opportunity adviser (S3 E11).

The LLM proposes a team (roles + seniority + location + hours + allocation)
and a short scope interpretation with a confidence + reasons. That's it —
never a number the client will see. Deterministic pricing math is applied
by :mod:`app.services.adviser` using the published rate cards.

Every response is validated against :data:`TEAM_SCHEMA` or
:data:`QUESTIONS_SCHEMA`. Free-form text never escapes this module — an
unclassifiable response is coerced into a ClarifyingQuestions payload that
tells the user to talk to Presales (CLAUDE.md rule 6).

The default :class:`StubBedrock` is deterministic and covers a handful of
canned scenarios so tests and local dev don't touch the real Bedrock API.
Wire the real client in production by passing your own adapter into
:func:`propose_team`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

# ---------------------------------------------------------------------------
# Public types

# Bumped whenever the prompt text or model contract changes. Persisted with
# every ``adviser_estimate`` row so future retuning stays auditable.
PROMPT_VERSION = "adviser.v1"

# Model identifier we record when the stub answers (tests + local dev).
# Real Bedrock calls should overwrite this on the returned payload.
STUB_MODEL = "stub.adviser.v1"


# --- JSON schemas ----------------------------------------------------------

# Structured team payload — the ONLY shape the adviser will ever emit for a
# successful proposal. `role`/`seniority`/`location`/`hours`/`allocation_pct`
# are the fields the deterministic pricing service consumes.
TEAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "kind",
        "scope",
        "team",
        "confidence",
        "reasons",
    ],
    "properties": {
        "kind": {"const": "team"},
        "scope": {"type": "string", "minLength": 1},
        "team": {
            "type": "array",
            "minItems": 3,
            "items": {
                "type": "object",
                "required": ["role", "seniority", "location", "hours", "allocation_pct"],
                "properties": {
                    "role": {"type": "string", "minLength": 1},
                    "seniority": {"type": "string", "minLength": 1},
                    "location": {"enum": ["US", "India"]},
                    "hours": {"type": "number"},
                    "allocation_pct": {"type": "number"},
                },
            },
        },
        "confidence": {"enum": ["low", "medium", "high"]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
}

QUESTIONS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["kind", "questions"],
    "properties": {
        "kind": {"const": "questions"},
        "questions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
        },
        "note": {"type": "string"},
    },
}


# --- dataclasses ------------------------------------------------------------


@dataclass(frozen=True)
class TeamMember:
    role: str
    seniority: str
    location: str  # "US" | "India"
    hours: float
    allocation_pct: float


@dataclass(frozen=True)
class StructuredTeam:
    scope: str
    team: tuple[TeamMember, ...]
    confidence: str  # "low" | "medium" | "high"
    reasons: tuple[str, ...]
    sources: tuple[dict[str, Any], ...] = ()
    model: str = STUB_MODEL
    prompt_version: str = PROMPT_VERSION

    @property
    def kind(self) -> str:
        return "team"


@dataclass(frozen=True)
class ClarifyingQuestions:
    questions: tuple[str, ...]
    note: str = ""
    sources: tuple[dict[str, Any], ...] = ()
    model: str = STUB_MODEL
    prompt_version: str = PROMPT_VERSION

    @property
    def kind(self) -> str:
        return "questions"


ProposeResult = StructuredTeam | ClarifyingQuestions


# --- validation -------------------------------------------------------------


class SchemaValidationError(ValueError):
    """Raised when a Bedrock payload doesn't match the promised schema.

    Callers translate this to a :class:`ClarifyingQuestions` payload so the
    adviser never leaks a free-form model response to the UI (rule 6).
    """


def _validate(payload: Any, schema: dict[str, Any], path: str = "$") -> None:
    """Tiny JSON-schema subset. Enough to enforce our two shapes without a
    heavy dependency; every rejection is a labelled path so a developer can
    debug the drift quickly."""

    stype = schema.get("type")
    const = schema.get("const")
    enum = schema.get("enum")
    if const is not None:
        if payload != const:
            raise SchemaValidationError(f"{path}: expected const {const!r}, got {payload!r}")
        return
    if enum is not None:
        if payload not in enum:
            raise SchemaValidationError(f"{path}: {payload!r} not in {enum!r}")
        return
    if stype == "object":
        if not isinstance(payload, dict):
            raise SchemaValidationError(f"{path}: expected object")
        for req in schema.get("required", []):
            if req not in payload:
                raise SchemaValidationError(f"{path}.{req}: required")
        for k, sub in (schema.get("properties") or {}).items():
            if k in payload:
                _validate(payload[k], sub, f"{path}.{k}")
        return
    if stype == "array":
        if not isinstance(payload, list):
            raise SchemaValidationError(f"{path}: expected array")
        min_items = schema.get("minItems")
        if min_items is not None and len(payload) < min_items:
            raise SchemaValidationError(f"{path}: needs >= {min_items} items")
        item_schema = schema.get("items")
        if item_schema is not None:
            for i, item in enumerate(payload):
                _validate(item, item_schema, f"{path}[{i}]")
        return
    if stype == "string":
        if not isinstance(payload, str):
            raise SchemaValidationError(f"{path}: expected string")
        min_len = schema.get("minLength")
        if min_len is not None and len(payload) < min_len:
            raise SchemaValidationError(f"{path}: minLength {min_len}")
        return
    if stype == "number":
        # Reject bool since bool is a subclass of int in Python.
        if isinstance(payload, bool) or not isinstance(payload, (int, float)):
            raise SchemaValidationError(f"{path}: expected number")
        return


def _coerce_team(payload: dict[str, Any]) -> StructuredTeam:
    _validate(payload, TEAM_SCHEMA)
    members = tuple(
        TeamMember(
            role=str(m["role"]),
            seniority=str(m["seniority"]),
            location=str(m["location"]),
            hours=float(m["hours"]),
            allocation_pct=float(m["allocation_pct"]),
        )
        for m in payload["team"]
    )
    return StructuredTeam(
        scope=str(payload["scope"]),
        team=members,
        confidence=str(payload["confidence"]),
        reasons=tuple(str(r) for r in payload["reasons"]),
        sources=tuple(payload.get("sources") or ()),
        model=str(payload.get("model") or STUB_MODEL),
        prompt_version=str(payload.get("prompt_version") or PROMPT_VERSION),
    )


def _coerce_questions(payload: dict[str, Any]) -> ClarifyingQuestions:
    _validate(payload, QUESTIONS_SCHEMA)
    return ClarifyingQuestions(
        questions=tuple(str(q) for q in payload["questions"]),
        note=str(payload.get("note") or ""),
        sources=tuple(payload.get("sources") or ()),
        model=str(payload.get("model") or STUB_MODEL),
        prompt_version=str(payload.get("prompt_version") or PROMPT_VERSION),
    )


# --- adapters ---------------------------------------------------------------


class Adviser(Protocol):
    """Anything that can turn intake inputs into a validated payload dict.

    Real implementations wrap boto3's bedrock-runtime client; the stub just
    branches on inputs. Keep the return shape as a raw dict so the caller
    can re-validate.
    """

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]: ...


# Number of substantive facts the stub demands before it will draft a team.
# Thin intakes fall through to clarifying questions per the acceptance test.
_THIN_INTAKE_KEYS = ("problem", "functions", "users_count", "systems")
_THIN_INTAKE_MIN_SIGNAL = 2


def _tokens(text: str | None) -> int:
    if not text:
        return 0
    return len([t for t in re.split(r"\W+", text) if t])


class StubBedrock:
    """Deterministic in-process stand-in for tests + local dev.

    - "Thin" intakes (missing problem detail, no functions/users/systems)
      return clarifying questions.
    - Everything else emits a canned 4-person team so the deterministic
      pricing path always has something to chew on.
    """

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]:
        signal = 0
        if _tokens(inputs.get("problem")) >= 8:
            signal += 1
        for k in ("functions", "users_count", "systems", "geography", "timeline"):
            val = inputs.get(k)
            if val is None:
                continue
            if isinstance(val, (list, dict, str)) and len(val) > 0:
                signal += 1
            elif isinstance(val, (int, float)) and val > 0:
                signal += 1
        if signal < _THIN_INTAKE_MIN_SIGNAL:
            return {
                "kind": "questions",
                "questions": [
                    "What business outcome does the client want in the first 90 days?",
                    "Which existing systems must this integrate with?",
                    "How many end users, and in which geographies?",
                ],
                "note": (
                    "Not enough signal to draft a team; please add a fuller "
                    "problem statement or talk to Presales."
                ),
                "model": STUB_MODEL,
                "prompt_version": PROMPT_VERSION,
            }
        return {
            "kind": "team",
            "scope": (
                "Discovery + implementation of the described capability, "
                "with change management for the named user base."
            ),
            "team": [
                {
                    "role": "Solution Architect",
                    "seniority": "Senior",
                    "location": "US",
                    "hours": 120.0,
                    "allocation_pct": 0.5,
                },
                {
                    "role": "Engineer",
                    "seniority": "Senior",
                    "location": "India",
                    "hours": 480.0,
                    "allocation_pct": 1.0,
                },
                {
                    "role": "Engineer",
                    "seniority": "Mid",
                    "location": "India",
                    "hours": 480.0,
                    "allocation_pct": 1.0,
                },
                {
                    "role": "Project Manager",
                    "seniority": "Mid",
                    "location": "US",
                    "hours": 120.0,
                    "allocation_pct": 0.4,
                },
            ],
            "confidence": "medium",
            "reasons": [
                "Team shape is typical for the described functions + user count.",
                "Hours assume a 12-week baseline; adjust once Presales confirms.",
            ],
            "model": STUB_MODEL,
            "prompt_version": PROMPT_VERSION,
        }


class UnavailableAdviser:
    """Adapter that always fails — used when Bedrock is misconfigured.

    Returning a ``ClarifyingQuestions`` payload from ``propose_team`` for
    this branch keeps the API contract stable even when the model layer is
    down for maintenance.
    """

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("bedrock adviser unavailable")


# --- public entry -----------------------------------------------------------


def _default_adapter() -> Adviser:
    """Pick an adapter based on env: stub in local/dev, real in staging/prod.

    Sprint 3 wave 1 wires the stub; the real Bedrock adapter lands with the
    fuller adviser in Sprint 4. The env-gated fallback here keeps the API
    endpoint working end-to-end without changing call sites.
    """

    env = os.environ.get("DEALGATE_ENV", "local")
    if env in ("local", "test"):
        return StubBedrock()
    # No real backend yet — return a stub so the surface stays functional.
    # Replace with a boto3-backed adapter when the Bedrock story lands.
    return StubBedrock()


def _invoke_draft(
    adapter: Adviser,
    inputs: dict[str, Any],
    extra_kwargs: dict[str, Any],
) -> dict[str, Any]:
    """Call ``adapter.draft(inputs, **extra)`` if the adapter accepts extra
    kwargs; otherwise fall back to the single-arg contract.

    Keeps adapters written against the old signature (StubBedrock) working
    unchanged while letting the real Bedrock adapter opt into
    ``public_research`` without a breaking API change.
    """

    if not extra_kwargs:
        return adapter.draft(inputs)
    try:
        return adapter.draft(inputs, **extra_kwargs)  # type: ignore[call-arg]
    except TypeError:
        return adapter.draft(inputs)


def propose_team(
    inputs: dict[str, Any],
    *,
    adapter: Adviser | None = None,
    public_research: list[dict[str, Any]] | None = None,
    retrieved: dict[str, Any] | None = None,
) -> ProposeResult:
    """Draft either a structured team or clarifying questions.

    - Always validates the adapter's payload against the JSON schemas.
    - On schema failure, or any adapter exception, returns a
      ``ClarifyingQuestions`` payload pointing the user at Presales. This is
      the "AI drafts, humans confirm" contract (rule 6).
    - A team with fewer than 3 roles fails validation and falls back to
      clarifying questions (acceptance test).

    ``public_research`` is an optional list of ``{url, title, snippet}``
    citations from :mod:`app.integrations.tavily`. The real Bedrock adapter
    injects these into the system prompt so the LLM can ground its scope
    interpretation in publicly-known facts about the client. The stub
    ignores them so existing tests keep their canned output; the parameter
    is still forwarded on adapters that opt in via a keyword argument.

    ``retrieved`` is an optional dict with two lists — ``past_sows`` and
    ``capabilities`` — populated by the pgvector retrieval pipeline
    (:mod:`app.services.embeddings`). Same "opt-in via adapter kwarg"
    contract: the stub ignores it; the real Bedrock adapter injects the
    top matches into the system prompt so the LLM's team proposal is
    grounded in what DealGate has actually delivered.
    """

    ad = adapter or _default_adapter()
    # Forward extras to adapters that accept them. StubBedrock deliberately
    # ignores unknown kwargs so tests keep their canned output.
    draft_kwargs: dict[str, Any] = {}
    if public_research is not None:
        draft_kwargs["public_research"] = public_research
    if retrieved is not None:
        draft_kwargs["retrieved"] = retrieved
    try:
        raw = _invoke_draft(ad, inputs, draft_kwargs)
    except Exception:
        return ClarifyingQuestions(
            questions=(
                "The adviser service is not available right now. "
                "Please talk to Presales to draft this estimate manually.",
            ),
            note="bedrock adapter unavailable",
            model=STUB_MODEL,
            prompt_version=PROMPT_VERSION,
        )

    if not isinstance(raw, dict) or "kind" not in raw:
        return ClarifyingQuestions(
            questions=(
                "Please add more detail about the problem, "
                "then re-run — or talk to Presales.",
            ),
            note="adapter returned an unstructured payload",
        )

    try:
        if raw["kind"] == "team":
            return _coerce_team(raw)
        if raw["kind"] == "questions":
            return _coerce_questions(raw)
    except SchemaValidationError:
        # Too few roles, missing fields, whatever — fall through to questions.
        pass

    return ClarifyingQuestions(
        questions=(
            "The draft team was too thin to price. "
            "Please add functions, systems and user count — or talk to Presales.",
        ),
        note="draft failed schema validation",
    )


__all__ = [
    "Adviser",
    "ClarifyingQuestions",
    "PROMPT_VERSION",
    "ProposeResult",
    "STUB_MODEL",
    "SchemaValidationError",
    "StructuredTeam",
    "StubBedrock",
    "TEAM_SCHEMA",
    "QUESTIONS_SCHEMA",
    "TeamMember",
    "UnavailableAdviser",
    "propose_team",
]
