"""S18 §2 · staging is read-only against HubSpot.

Directive: no write-back to HubSpot in this slice. The write-back client
method stays on disk (services/hubspot_writeback.py stays put) but no
routed code path may invoke it. This test enforces that guarantee via
grep — if a future edit wires update_deal from a router or intake service,
this fails and the read-only claim is caught before deploy.

If write-back returns in a later slice, register the new call site here
and bump ``EXPECTED_CALL_SITES``.
"""

from __future__ import annotations

import pathlib
import re

# Only these files may reference `update_deal` — every one is dormant.
EXPECTED_CALL_SITES: set[str] = {
    "app/integrations/hubspot.py",        # the client method itself
    "app/services/hubspot_writeback.py",  # dormant service, not routed
}


def _repo_app_dir() -> pathlib.Path:
    # tests/ is one level below api/, and app/ is a sibling of tests.
    return pathlib.Path(__file__).resolve().parent.parent / "app"


def test_no_new_update_deal_call_sites():
    app_dir = _repo_app_dir()
    assert app_dir.is_dir(), f"expected {app_dir} to exist"

    pattern = re.compile(r"\bupdate_deal\b")
    found: set[str] = set()
    for path in app_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if pattern.search(text):
            rel = path.relative_to(app_dir.parent).as_posix()
            found.add(rel)

    new = found - EXPECTED_CALL_SITES
    dead = EXPECTED_CALL_SITES - found
    assert not new, (
        "New HubSpot write-back call sites detected; S18 §2 is read-only. "
        f"Add them to EXPECTED_CALL_SITES only after write-back is intended. Found: {new}"
    )
    assert not dead, (
        "EXPECTED_CALL_SITES references files that no longer mention "
        f"update_deal — drop them: {dead}"
    )
