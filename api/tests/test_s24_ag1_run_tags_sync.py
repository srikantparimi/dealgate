"""S24-AG1 B2/T11 — the test-data name rule covers every run tag the leak gate knows (bug #106).

``agreement_status._RUN_TAG`` decides the ``test_data`` flag from a client's name; the leak gate
(scripts/check-test-data-clean.sh) fails a deploy on the same names. This reads each prefix list in the
gate script, expands every alternative into concrete names, and checks the rule flags each one, so a tag
added to the gate but not to the rule fails here.
"""

from __future__ import annotations

import pathlib
import re

from app.services.agreement_status import _RUN_TAG

GATE = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check-test-data-clean.sh"
_REGEX_BLOCK = re.compile(r'prefix_re = re\.compile\(\s*((?:r"[^"]*"\s*)+),\s*re\.IGNORECASE', re.S)


def _gate_patterns() -> list[str]:
    patterns = []
    for block in _REGEX_BLOCK.findall(GATE.read_text()):
        patterns.append("".join(re.findall(r'r"([^"]*)"', block)))
    return patterns


def _alternatives(pattern: str) -> list[str]:
    body = pattern
    assert body.startswith("^(?:") and body.endswith(")"), body
    return body[len("^(?:"):-1].split("|")


def _expand(alternative: str) -> list[str]:
    """Concrete strings for one alternative: character ranges such as [2-9] expand to each character."""
    out = [""]
    i = 0
    while i < len(alternative):
        ch = alternative[i]
        if ch == "\\":
            out = [o + alternative[i + 1] for o in out]
            i += 2
        elif ch == "[":
            end = alternative.index("]", i)
            first, last = alternative[i + 1], alternative[end - 1]
            out = [o + chr(c) for o in out for c in range(ord(first), ord(last) + 1)]
            i = end + 1
        else:
            out = [o + ch for o in out]
            i += 1
    return out


def test_the_gate_has_its_prefix_lists():
    patterns = _gate_patterns()
    assert len(patterns) >= 3  # clients, approvals, people and engagements
    assert len(set(patterns)) == 1, "the gate's copies of the prefix list differ from each other"


def test_every_gate_run_tag_is_test_data_by_name():
    missing = []
    for alternative in _alternatives(_gate_patterns()[0]):
        for prefix in _expand(alternative):
            name = f"{prefix}x"
            if not _RUN_TAG.match(name):
                missing.append(name)
    assert missing == []


def test_real_looking_names_are_not_run_tags():
    for name in ("Peppermill Casino", "Peppermill Casino's, LLC", "Smokehouse Grill", "S24e2e without a space",
                 "Lunavale e2e Services"):
        assert not _RUN_TAG.match(name), name
