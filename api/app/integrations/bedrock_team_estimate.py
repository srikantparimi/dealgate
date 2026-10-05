"""Bedrock scope→team estimate (S22).

The model reads the SOW's own words (scope, deliverables, effort tables,
team statements) and emits a REQUIRED-EFFORT draft: FTE count, role
shapes and the exact quotes that support them. Rule 6: it is a draft
with sources, schema-validated, and a human confirms it in the editor.
Rule 2: it never prices anything — rates, costs and GM stay in the
Decimal engine; the estimate feeds ``gm.staffing_mix`` as the
``required_fte`` input only.

Failure modes mirror the extraction client: anything abnormal returns
``EstimateUnavailable`` so the panel falls back to manual FTE entry —
never a fabricated estimate.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("dealgate.bedrock_team_estimate")

_MODEL_ENV = "BEDROCK_SOW_MODEL_ID"
_DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"


@dataclass(frozen=True)
class RoleEstimate:
    role: str
    fte: str  # Decimal string — transported as text, never floats.
    location_hint: str | None
    evidence: str
    skills: tuple[str, ...] = ()
    seniority: str | None = None
    phase: str | None = None
    people: int | None = None  # headcount when stated; fte covers partial allocation
    allocation: str | None = None  # Decimal fraction string per person, when stated
    basis: str = "inferred"  # "stated" (quoted contractual fact) or "inferred"


@dataclass(frozen=True)
class TeamEstimate:
    required_fte: str  # Decimal string.
    duration_weeks: str | None
    roles: tuple[RoleEstimate, ...] = ()
    rationale: str = ""
    evidence: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()  # what the document does not say — gaps, not zeros
    coverage: str | None = None  # SLA/shift/on-call commitments found in scope


@dataclass(frozen=True)
class EstimateUnavailable:
    reason: str


def _tool_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["required_fte", "roles", "rationale", "evidence"],
        "properties": {
            "required_fte": {
                "type": "string",
                "description": "Total concurrent FTE the scope needs, as a decimal string like '2.5'.",
            },
            "duration_weeks": {
                "type": ["string", "null"],
                "description": "Engagement duration in weeks when the document states one, as a decimal string.",
            },
            "roles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["role", "fte", "evidence"],
                    "properties": {
                        "role": {"type": "string"},
                        "fte": {"type": "string"},
                        "location_hint": {"type": ["string", "null"]},
                        "evidence": {
                            "type": "string",
                            "description": "Verbatim quote from the document supporting this role.",
                        },
                        "skills": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Named skills/technologies the scope requires of this role.",
                        },
                        "seniority": {"type": ["string", "null"]},
                        "phase": {
                            "type": ["string", "null"],
                            "description": "Delivery phase or milestone this role serves, when the document phases the work.",
                        },
                        "people": {
                            "type": ["integer", "null"],
                            "description": "Headcount when stated; partial availability goes in allocation.",
                        },
                        "allocation": {
                            "type": ["string", "null"],
                            "description": "Per-person allocation as a decimal fraction string like '0.5', when stated.",
                        },
                        "basis": {
                            "type": "string",
                            "enum": ["stated", "inferred"],
                            "description": "'stated' only when the document itself names this role/effort; otherwise 'inferred'.",
                        },
                    },
                },
            },
            "rationale": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verbatim quotes supporting the FTE total (team size statements, person-week tables).",
            },
            "unknowns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "What the document does NOT state that a staffing plan needs (dates, rates, locations, coverage). Gaps, never guessed values.",
            },
            "coverage": {
                "type": ["string", "null"],
                "description": "SLA, shift or on-call coverage commitments found in the scope, verbatim where possible.",
            },
        },
    }


_PROMPT = """You are estimating delivery effort from a Statement of Work.
Read ONLY the text below. From its deliverables, milestones and service
commitments, emit the team the SCOPE requires — independent of any fee:
- required_fte: total concurrent full-time-equivalents (half steps allowed).
- duration_weeks when the document states a duration.
- roles: role shapes with skills, seniority, phase, people, per-person
  allocation and per-role FTE, each with a verbatim supporting quote.
  Mark basis "stated" only where the document itself names the role or
  effort; otherwise "inferred". Do not force every role to one
  full-time person; partial allocations are normal.
- coverage: any SLA/shift/on-call commitment the scope makes.
- unknowns: what the document does not say that a plan needs (dates,
  locations, coverage details). Gaps stay gaps — never guess values.
Prefer the document's own numbers (team size statements, person-week
effort tables: FTE = person-weeks / duration-weeks) over judgment, but
do not merely copy a stated headcount if the deliverables clearly need
more or less — then report both, with the difference in the rationale.
Never estimate price, rates, cost or margin, and never derive the team
from a fee. If the text truly supports no estimate, emit required_fte
"0" with the rationale saying why.

SOW TEXT:
{text}
"""


class StubTeamEstimate:
    """Deterministic offline stub for tests and local dev."""

    def __init__(self, result: TeamEstimate | EstimateUnavailable | None = None):
        self.result = result or TeamEstimate(
            required_fte="2.5",
            duration_weeks="7",
            roles=(
                RoleEstimate(
                    "ServiceNow Consultant", "2", "US", "2 full-time",
                    skills=("ServiceNow",), people=2, allocation="1", basis="stated",
                ),
                RoleEstimate(
                    "ServiceNow Consultant", "0.5", None, "1 half-time",
                    skills=("ServiceNow",), people=1, allocation="0.5", basis="stated",
                ),
            ),
            rationale="stub",
            evidence=("Team Size: 3 consultants (2 full-time, 1 half-time)",),
            unknowns=("No shift or on-call coverage stated",),
        )
        self.calls: list[str] = []

    def estimate(self, text: str) -> TeamEstimate | EstimateUnavailable:
        self.calls.append(text)
        return self.result


class BedrockTeamEstimate:
    """Real Bedrock caller; sync by design, callers thread it off."""

    def __init__(self, *, client: Any | None = None) -> None:
        self._client = client

    def _runtime(self) -> Any:
        if self._client is not None:
            return self._client
        import boto3
        from botocore.config import Config

        return boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "us-east-2"),
            config=Config(read_timeout=60, retries={"max_attempts": 2}),
        )

    def estimate(self, text: str) -> TeamEstimate | EstimateUnavailable:
        from botocore.exceptions import BotoCoreError, ClientError

        model_id = os.environ.get(_MODEL_ENV, _DEFAULT_MODEL)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "tools": [{
                "name": "emit_team_estimate",
                "description": "Emit the team the scope requires.",
                "input_schema": _tool_schema(),
            }],
            "tool_choice": {"type": "tool", "name": "emit_team_estimate"},
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": _PROMPT.format(text=text[:24000])}],
            }],
        }
        try:
            resp = self._runtime().invoke_model(modelId=model_id, body=json.dumps(body))
            payload = json.loads(resp["body"].read())
        except (ClientError, BotoCoreError, TimeoutError) as exc:
            log.warning("bedrock team estimate failed: %s", exc)
            return EstimateUnavailable(reason="bedrock unavailable for team estimate")
        except json.JSONDecodeError:
            return EstimateUnavailable(reason="bedrock returned a non-JSON body")

        for block in payload.get("content", []) if isinstance(payload, dict) else []:
            if block.get("type") == "tool_use":
                return _validate(block.get("input"))
        return EstimateUnavailable(reason="bedrock emitted no tool payload")


def _validate(raw: Any) -> TeamEstimate | EstimateUnavailable:
    from decimal import Decimal, InvalidOperation

    if not isinstance(raw, dict):
        return EstimateUnavailable(reason="estimate payload was not an object")
    try:
        fte = Decimal(str(raw["required_fte"]))
        if fte < 0 or fte > 100:
            raise InvalidOperation
        duration = raw.get("duration_weeks")
        if duration is not None:
            Decimal(str(duration))
        def _role(r: dict[str, Any]) -> RoleEstimate:
            allocation = r.get("allocation")
            if allocation is not None:
                allocation = str(Decimal(str(allocation)))
            people = r.get("people")
            if people is not None:
                people = int(people)
                if people < 0 or people > 1000:
                    raise InvalidOperation
            return RoleEstimate(
                role=str(r["role"])[:128],
                fte=str(Decimal(str(r["fte"]))),
                location_hint=(str(r["location_hint"])[:32]
                               if r.get("location_hint") else None),
                evidence=str(r["evidence"])[:500],
                skills=tuple(str(s)[:64] for s in r.get("skills", []) or [])[:12],
                seniority=str(r["seniority"])[:64] if r.get("seniority") else None,
                phase=str(r["phase"])[:128] if r.get("phase") else None,
                people=people,
                allocation=allocation,
                basis="stated" if r.get("basis") == "stated" else "inferred",
            )

        roles = tuple(_role(r) for r in raw.get("roles", []))
        return TeamEstimate(
            required_fte=str(fte),
            duration_weeks=str(Decimal(str(duration))) if duration is not None else None,
            roles=roles,
            rationale=str(raw.get("rationale", ""))[:2000],
            evidence=tuple(str(e)[:500] for e in raw.get("evidence", [])),
            unknowns=tuple(str(u)[:300] for u in raw.get("unknowns", []) or [])[:20],
            coverage=str(raw["coverage"])[:500] if raw.get("coverage") else None,
        )
    except (KeyError, InvalidOperation, TypeError, ArithmeticError):
        return EstimateUnavailable(reason="estimate payload failed schema validation")


def get_team_estimate() -> BedrockTeamEstimate | StubTeamEstimate:
    """FastAPI dependency; S3_STUB=1 (the offline convention) selects the stub."""
    if os.environ.get("S3_STUB") == "1":
        return StubTeamEstimate()
    return BedrockTeamEstimate()
