"""Bedrock-backed CEO exception brief drafter (S4 E7, Agent V wave 3).

The LLM assembles a structured brief for the CEO from the deterministic
inputs the human already computed: the approval package, its SOW
version, the GM model, and the active policy. It *never* invents a
number and it *never* writes the rationale — the ``rationale`` field is
left ``null`` and must be filled by the account owner (blueprint §6.6
"Finance and Delivery write recommendations, the account owner writes
rationale, the AI can tidy but not invent").

Two entry points are exposed:

- :func:`draft_brief` — the ``brief_json`` payload persisted onto
  ``ceo_exception.brief_json`` when a package enters
  ``pending_ceo_exception``.
- :func:`tidy_rationale` — takes a human-written rationale and returns
  a lightly-copyedited version. The service layer always stores both
  the raw and tidied text so audit can prove the human intent.

Two adapters are shipped:

- :class:`StubBedrock` — deterministic, used in tests + local dev.
- :class:`UnavailableAdviser` — always raises; used to prove the
  ``draft_brief`` caller degrades gracefully.

The default adapter is picked by ``DEALGATE_ENV``: stub in local/test,
stub in every other env until the real Bedrock wire lands.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

# Bumped whenever the prompt text or the returned brief schema changes.
PROMPT_VERSION = "ceo_brief.v1"

# Persisted with the row so future retunes stay auditable.
STUB_MODEL = "stub.ceo_brief.v1"


# --- brief schema (documented in-code; validation is best-effort) -----------

BRIEF_SCHEMA_KEYS = (
    "client",
    "scope",
    "team_summary",
    "revenue",
    "cost",
    "gm",
    "price_uplift",
    "gross_profit_shortfall_usd",
    "alternatives",
    "finance_recommendation",
    "delivery_recommendation",
    "rationale",  # always null out of the model
    "sources",
    "model",
    "prompt_version",
)


@dataclass(frozen=True)
class TidiedRationale:
    """Return type for :func:`tidy_rationale`.

    ``text`` is the cleaned-up wording. ``model`` / ``prompt_version``
    let the caller persist provenance next to the raw text so a reader
    can always tell which words came from the human vs the model.
    """

    text: str
    model: str = STUB_MODEL
    prompt_version: str = PROMPT_VERSION


class BriefDrafter(Protocol):
    """Anything that can turn structured deterministic inputs into a brief dict."""

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]: ...

    def tidy(self, rationale: str) -> str: ...


def _fmt(value: Decimal | int | float | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return format(value, "f")


def _dec(value: Decimal | int | float | str | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


class StubBedrock:
    """Deterministic stand-in for tests and local dev.

    Reads the deterministic numbers straight through — the "AI" only
    templates the labels. That's a deliberate strength: any future real
    adapter has the same contract (pass numbers through verbatim).
    """

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]:
        revenue = inputs.get("revenue") or {}
        cost = inputs.get("cost") or {}
        gm = inputs.get("gm") or {}
        uplift = inputs.get("price_uplift") or {}
        shortfall = inputs.get("gross_profit_shortfall_usd")
        alternatives = inputs.get("alternatives") or []
        return {
            "client": {
                "name": inputs.get("client_name") or "",
                "context": inputs.get("client_context") or "",
            },
            "scope": inputs.get("scope") or "",
            "team_summary": inputs.get("team_summary") or "",
            "revenue": {
                "us": _fmt(revenue.get("us")),
                "india": _fmt(revenue.get("india")),
                "blended": _fmt(revenue.get("blended")),
            },
            "cost": {
                "us": _fmt(cost.get("us")),
                "india": _fmt(cost.get("india")),
                "blended": _fmt(cost.get("blended")),
            },
            "gm": {
                "us": {
                    "value": _fmt((gm.get("us") or {}).get("value")),
                    "floor": _fmt((gm.get("us") or {}).get("floor")),
                    "passes": bool((gm.get("us") or {}).get("passes", True)),
                },
                "india": {
                    "value": _fmt((gm.get("india") or {}).get("value")),
                    "floor": _fmt((gm.get("india") or {}).get("floor")),
                    "passes": bool((gm.get("india") or {}).get("passes", True)),
                },
                "blended": {
                    "value": _fmt((gm.get("blended") or {}).get("value")),
                },
            },
            "price_uplift": {
                "us": _fmt(uplift.get("us")),
                "india": _fmt(uplift.get("india")),
            },
            "gross_profit_shortfall_usd": _fmt(shortfall),
            "alternatives": [str(a) for a in alternatives if a],
            "finance_recommendation": inputs.get("finance_recommendation") or "",
            "delivery_recommendation": inputs.get("delivery_recommendation") or "",
            # Rule: never written by the model. Owner fills this later.
            "rationale": None,
            "sources": list(inputs.get("sources") or ()),
            "model": STUB_MODEL,
            "prompt_version": PROMPT_VERSION,
        }

    def tidy(self, rationale: str) -> str:
        """Trim + collapse whitespace. Real Bedrock does light rewriting;
        the stub is a deterministic passthrough so tests stay stable."""

        return " ".join((rationale or "").split()).strip()


class UnavailableAdviser:
    """Adapter that always fails — exercises the graceful-degradation path."""

    def draft(self, inputs: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("bedrock ceo brief adapter unavailable")

    def tidy(self, rationale: str) -> str:
        raise RuntimeError("bedrock ceo brief adapter unavailable")


def _default_adapter() -> BriefDrafter:
    env = os.environ.get("DEALGATE_ENV", "local")
    if env in ("local", "test"):
        return StubBedrock()
    # Real Bedrock wire lands in a follow-up story; stub keeps the surface
    # functional in every env for now.
    return StubBedrock()


def draft_brief(
    inputs: dict[str, Any],
    *,
    adapter: BriefDrafter | None = None,
) -> dict[str, Any]:
    """Return the structured CEO brief.

    ``inputs`` must already carry every deterministic number the brief
    displays. The adapter is only asked to arrange them — never to
    compute or reword a value. If the adapter blows up, we still return
    a valid brief built from the raw inputs so the package can move
    forward (the CEO's ``pending_ceo_exception`` queue never depends on
    Bedrock's uptime).
    """

    ad = adapter or _default_adapter()
    try:
        brief = ad.draft(inputs)
    except Exception:
        brief = StubBedrock().draft(inputs)

    # Force the rationale null regardless of what the adapter returned —
    # this is the non-negotiable "AI cannot invent rationale" contract.
    brief["rationale"] = None
    # Stamp provenance so audit can always attribute wording.
    brief.setdefault("model", STUB_MODEL)
    brief.setdefault("prompt_version", PROMPT_VERSION)
    return brief


def tidy_rationale(
    text: str, *, adapter: BriefDrafter | None = None
) -> TidiedRationale:
    """Ask the adapter to lightly copyedit a human rationale.

    The raw text is stored verbatim by the caller; this only produces
    the tidied side. Returns the original string on adapter failure so
    callers can always render *something* to the user.
    """

    ad = adapter or _default_adapter()
    try:
        cleaned = ad.tidy(text)
    except Exception:
        cleaned = (text or "").strip()
    return TidiedRationale(text=cleaned or (text or "").strip())


__all__ = [
    "BRIEF_SCHEMA_KEYS",
    "BriefDrafter",
    "PROMPT_VERSION",
    "STUB_MODEL",
    "StubBedrock",
    "TidiedRationale",
    "UnavailableAdviser",
    "draft_brief",
    "tidy_rationale",
]
