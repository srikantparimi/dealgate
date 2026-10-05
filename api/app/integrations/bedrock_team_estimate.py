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


@dataclass(frozen=True)
class TeamEstimate:
    required_fte: str  # Decimal string.
    duration_weeks: str | None
    roles: tuple[RoleEstimate, ...] = ()
    rationale: str = ""
    evidence: tuple[str, ...] = ()


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
                    },
                },
            },
            "rationale": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Verbatim quotes supporting the FTE total (team size statements, person-week tables).",
            },
        },
    }


_PROMPT = """You are estimating delivery effort from a Statement of Work.
Read ONLY the text below. Emit the team the scope requires:
- required_fte: total concurrent full-time-equivalents (half steps allowed).
- duration_weeks when the document states a duration.
- roles: the role shapes with per-role FTE and a verbatim supporting quote.
Prefer the document's own numbers (team size statements, person-week
effort tables: FTE = person-weeks / duration-weeks) over judgment.
Never estimate price, rates, cost or margin. If the text truly supports
no estimate, emit required_fte "0" with the rationale saying why.

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
                RoleEstimate("ServiceNow Consultant", "2", "US", "2 full-time"),
                RoleEstimate("ServiceNow Consultant", "0.5", None, "1 half-time"),
            ),
            rationale="stub",
            evidence=("Team Size: 3 consultants (2 full-time, 1 half-time)",),
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
        roles = tuple(
            RoleEstimate(
                role=str(r["role"])[:128],
                fte=str(Decimal(str(r["fte"]))),
                location_hint=(str(r["location_hint"])[:32]
                               if r.get("location_hint") else None),
                evidence=str(r["evidence"])[:500],
            )
            for r in raw.get("roles", [])
        )
        return TeamEstimate(
            required_fte=str(fte),
            duration_weeks=str(Decimal(str(duration))) if duration is not None else None,
            roles=roles,
            rationale=str(raw.get("rationale", ""))[:2000],
            evidence=tuple(str(e)[:500] for e in raw.get("evidence", [])),
        )
    except (KeyError, InvalidOperation, TypeError, ArithmeticError):
        return EstimateUnavailable(reason="estimate payload failed schema validation")


def get_team_estimate() -> BedrockTeamEstimate | StubTeamEstimate:
    """FastAPI dependency; S3_STUB=1 (the offline convention) selects the stub."""
    if os.environ.get("S3_STUB") == "1":
        return StubTeamEstimate()
    return BedrockTeamEstimate()
