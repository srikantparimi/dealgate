"""NDA/MSA tracking transitions. Legacy states remain readable without data rewrites.

Execution requires signed evidence and dates. Callers own the transaction and
paired audit event; no internal review or approval cycle is involved.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.client import Agreement

# --- states ---------------------------------------------------------------

# The database also retains legacy states for historical records.
ALLOWED_STATES: tuple[str, ...] = ("missing", "requested", "sent", "executed", "expired")

LEGACY_STATES = ("drafting", "under_review", "partially_signed", "terminated", "superseded")
_ALLOWED_SET = frozenset(ALLOWED_STATES)
ALLOWED_TRANSITIONS = {
    state: {"requested", "sent", "executed"} - {state}
    for state in ("missing", "requested", "sent", "drafting", "under_review", "partially_signed")
}
ALLOWED_TRANSITIONS.update(executed={"expired"}, expired=set(), terminated=set(), superseded=set())


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
        # reaching us).
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

    if to_state == "executed" and (not agreement.expiry or not agreement.effective_from or not agreement.evidence_s3_key):
        raise InvalidAgreementTransition(
            from_state=agreement.state,
            to_state=to_state,
            reason="signed evidence, effective_from and expiry are required for executed agreements",
        )
    if to_state == "executed" and agreement.expiry < agreement.effective_from:
        raise InvalidAgreementTransition(from_state=agreement.state, to_state=to_state,
                                         reason="expiry must not precede effective_from")

    agreement.state = to_state


__all__ = [
    "ALLOWED_STATES",
    "ALLOWED_TRANSITIONS",
    "InvalidAgreementTransition",
    "is_allowed",
    "transition",
]
