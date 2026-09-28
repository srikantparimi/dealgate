"""Agreement state machine — every edge, every rejection.

Guarantees:

- Every edge listed in `ALLOWED_TRANSITIONS` is reachable via `transition()`.
- Every combination *not* in `ALLOWED_TRANSITIONS` raises
  `InvalidAgreementTransition` (excluding `state == state` no-ops).
- `executed` requires `expiry`.
- Unknown target states are rejected.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models.client import Agreement
from app.services.agreement_state import (
    ALLOWED_STATES,
    ALLOWED_TRANSITIONS,
    InvalidAgreementTransition,
    is_allowed,
    transition,
)


def _fresh(state: str, *, with_expiry: bool = True) -> Agreement:
    return Agreement(
        legal_entity_id=None,  # not needed for state-machine unit tests
        kind="NDA",
        state=state,
        expiry=date.today() + timedelta(days=365) if with_expiry else None,
        effective_from=date.today(),
        evidence_s3_key="agreements/fixture/signed.pdf",
    )


def _all_edges():
    for from_state, targets in ALLOWED_TRANSITIONS.items():
        for to_state in targets:
            yield from_state, to_state


def _all_forbidden_pairs():
    """Every (from, to) pair that is not an allowed edge and not a no-op."""

    for from_state in ALLOWED_STATES:
        for to_state in ALLOWED_STATES:
            if from_state == to_state:
                continue
            if to_state in ALLOWED_TRANSITIONS.get(from_state, set()):
                continue
            yield from_state, to_state


@pytest.mark.parametrize("from_state,to_state", list(_all_edges()))
def test_every_allowed_edge_transitions(from_state: str, to_state: str) -> None:
    agreement = _fresh(from_state)
    transition(agreement, to_state, actor_id=None)
    assert agreement.state == to_state


@pytest.mark.parametrize("from_state,to_state", list(_all_forbidden_pairs()))
def test_every_forbidden_edge_rejected(from_state: str, to_state: str) -> None:
    agreement = _fresh(from_state)
    with pytest.raises(InvalidAgreementTransition) as exc_info:
        transition(agreement, to_state, actor_id=None)
    err = exc_info.value
    assert err.from_state == from_state
    assert err.to_state == to_state
    # Row stays put on rejection.
    assert agreement.state == from_state


def test_transition_to_unknown_state_rejected() -> None:
    agreement = _fresh("drafting")
    with pytest.raises(InvalidAgreementTransition) as exc_info:
        transition(agreement, "flabbergasted", actor_id=None)
    assert "unknown state" in str(exc_info.value)


def test_executed_requires_expiry() -> None:
    agreement = _fresh("sent", with_expiry=False)
    with pytest.raises(InvalidAgreementTransition) as exc_info:
        transition(agreement, "executed", actor_id=None)
    assert "expiry" in str(exc_info.value)
    assert agreement.state == "sent"


def test_executed_allowed_when_expiry_present() -> None:
    agreement = _fresh("sent", with_expiry=True)
    transition(agreement, "executed", actor_id=None)
    assert agreement.state == "executed"


def test_is_allowed_pure_check_matches_transition() -> None:
    for from_state in ALLOWED_STATES:
        for to_state in ALLOWED_STATES:
            expected = (
                from_state != to_state
                and to_state in ALLOWED_TRANSITIONS.get(from_state, set())
            )
            assert is_allowed(from_state, to_state) is expected


def test_terminal_states_have_no_outgoing_edges() -> None:
    for terminal in ("expired", "terminated", "superseded"):
        assert ALLOWED_TRANSITIONS[terminal] == set()
        agreement = _fresh(terminal)
        for target in ALLOWED_STATES:
            if target == terminal:
                continue
            with pytest.raises(InvalidAgreementTransition):
                transition(agreement, target, actor_id=None)
