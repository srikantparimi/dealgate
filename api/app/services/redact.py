"""Role-aware cost-field redaction (S7 B).

Blueprint §3: "Sales cannot see individual salary or contractor cost."
Endpoint-level role gates already keep Sales users out of the delivery
model builder and Finance dashboards. This module closes the gap where a
Sales user can read a container (deal detail, client detail, adviser
estimate) that happens to embed a cost field.

Contract:

- :data:`COST_FIELDS` is the single source of truth. Any new cost-shaped
  key that lands in a response must be added here (and the redact call
  covers it automatically).
- :data:`ROLES_ALLOWED_COST` is the whitelist. Users with any of these
  roles keep every cost field verbatim; everyone else gets the same
  payload with those keys removed.
- :func:`redact_costs` is a pure deep-walk that returns a new object with
  the keys stripped — it never mutates the input. Lists preserve order.

Every endpoint that returns a payload carrying cost fields pipes the
serialized dict through :func:`redact_costs` right before returning.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


COST_FIELDS: frozenset[str] = frozenset(
    {
        "hourly_cost",
        "cost_low",
        "cost_base",
        "cost_high",
        "cost_us",
        "cost_india",
        "actual_cost",
        "hourly_loaded_cost",
        "loaded_cost",
    }
)

# Governance roles that see raw cost fields.
ROLES_ALLOWED_COST: frozenset[str] = frozenset(
    {"Delivery", "HR", "Finance", "CEO", "SystemAdmin"}
)


def _has_cost_access(user_groups: Iterable[str]) -> bool:
    """True when the user carries at least one cost-allowed role."""

    return any(role in ROLES_ALLOWED_COST for role in user_groups)


def redact_costs(payload: Any, user_groups: set[str] | frozenset[str] | Iterable[str]) -> Any:
    """Return a copy of ``payload`` with cost fields removed for non-privileged callers.

    Handles nested dicts + lists to any depth. Non-dict, non-list values
    are returned unchanged. When the caller has cost access, ``payload``
    is returned as-is (no copy — the caller owns the payload).

    Never mutates the input. New containers are allocated so the caller
    can round-trip the original response elsewhere (e.g. an audit log)
    without side effects.
    """

    if _has_cost_access(user_groups):
        return payload
    return _walk_and_strip(payload)


def _walk_and_strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: _walk_and_strip(v)
            for k, v in value.items()
            if k not in COST_FIELDS
        }
    if isinstance(value, list):
        return [_walk_and_strip(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_walk_and_strip(item) for item in value)
    return value


__all__ = [
    "COST_FIELDS",
    "ROLES_ALLOWED_COST",
    "redact_costs",
]
