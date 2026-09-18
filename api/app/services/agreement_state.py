"""Agreement state machine (build-guide §6.2).

Ten states cover the NDA / MSA lifecycle from "we haven't started" to
"replaced by a newer version". The transition graph is intentionally strict:
Legal must move an agreement forward one step at a time so the audit trail
matches the paperwork.

`transition()` is the single mutation point. It:

- rejects moves that are not in `ALLOWED_TRANSITIONS` (422 via
  `InvalidAgreementTransition`);
- refuses to promote to ``executed`` without an ``expiry`` set — the alert
  scheduler needs the date and the blueprint requires it;
- mutates the ORM row in-place. The caller owns the transaction and the
  paired ``append_audit`` call (rule 5).

Keep the states / transitions in lock-step with the CHECK constraint in
`alembic/versions/20260918_0004_agreement_state.py`.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.client import Agreement

# --- states ---------------------------------------------------------------

# Order matches build-guide §6.2. Do not re-order — the migration CHECK
# constraint stores the same list and downstream reports assume this order.
ALLOWED_STATES: tuple[str, ...] = (
    "missing",
    "requested",
    "drafting",
    "under_review",
    "sent",
    "partially_signed",
    "executed",
    "expired",
    "terminated",
    "superseded",
)

_ALLOWED_SET: frozenset[str] = frozenset(ALLOWED_STATES)


# --- transitions ---------------------------------------------------------

# Forward path is linear from `missing` through `executed`. Terminal states
# (`expired`, `terminated`, `superseded`) are only reachable from `executed`.
# `superseded` may be reached from any live state so a re-signed agreement
# can retire the old row without waiting for it to expire.
#
# The wording of §6.2 is: Legal drives the lifecycle; the system enforces
# that a state cannot skip the review + signature stages.
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "missing": {"requested", "drafting"},
    "requested": {"drafting", "terminated"},
    "drafting": {"under_review", "sent", "terminated"},
    "under_review": {"drafting", "sent", "terminated"},
    "sent": {"partially_signed", "executed", "drafting", "terminated"},
    "partially_signed": {"executed", "terminated"},
    "executed": {"expired", "terminated", "superseded"},
    # Terminal states — no outgoing transitions. Legal must create a fresh
    # agreement row to replace an expired / terminated / superseded one.
    "expired": set(),
    "terminated": set(),
    "superseded": set(),
}


# --- errors ---------------------------------------------------------------


class InvalidAgreementTransition(Exception):
    """Raised when `transition()` receives an illegal move.

    Router code converts this into HTTP 422 with the message body — callers
    should not catch this and swallow it.
    """

    def __init__(self, *, from_state: str, to_state: str, reason: str | None = None):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        detail = f"cannot transition agreement from {from_state!r} to {to_state!r}"
        if reason:
            detail = f"{detail}: {reason}"
        super().__init__(detail)


# --- API ------------------------------------------------------------------


def is_allowed(from_state: str, to_state: str) -> bool:
    """Pure check — no side effects. Handy for UI hints and tests."""

    if to_state not in _ALLOWED_SET:
        return False
    if from_state == to_state:
        # No-op moves are not "transitions" — the router filters these before
        # reaching us, but return False so the graph stays a strict DAG.
        return False
    return to_state in ALLOWED_TRANSITIONS.get(from_state, set())


def transition(
    agreement: "Agreement",
    to_state: str,
    actor_id: uuid.UUID | None,
) -> None:
    """Apply `to_state` to `agreement`, validating against the state machine.

    Raises `InvalidAgreementTransition` on any illegal move (unknown state,
    forbidden edge, executed without expiry). Otherwise mutates the row's
    ``state`` attribute in-place — caller commits and audits.

    `actor_id` is accepted for future audit-inside-service refactors; today
    the router handles the audit write.
    """

    del actor_id  # noqa: F841 — reserved for a future audit hook.

    if to_state not in _ALLOWED_SET:
        raise InvalidAgreementTransition(
            from_state=agreement.state,
            to_state=to_state,
            reason=f"unknown state (allowed: {list(ALLOWED_STATES)})",
        )

    if not is_allowed(agreement.state, to_state):
        raise InvalidAgreementTransition(
            from_state=agreement.state,
            to_state=to_state,
        )

    if to_state == "executed" and agreement.expiry is None:
        raise InvalidAgreementTransition(
            from_state=agreement.state,
            to_state=to_state,
            reason="`expiry` must be set before marking an agreement executed",
        )

    agreement.state = to_state


__all__ = [
    "ALLOWED_STATES",
    "ALLOWED_TRANSITIONS",
    "InvalidAgreementTransition",
    "is_allowed",
    "transition",
]
