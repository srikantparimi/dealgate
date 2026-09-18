"""Repo-level conftest.

Pytest collects conftests from the rootdir on up. Adding this file lets us
put the ``worker/`` sibling package on ``sys.path`` without editing
``tests/conftest.py`` (owned by other agents) or the API's ``pyproject``
(which intentionally publishes only the ``app*`` packages).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Ensure the scheduler ledger mapper is registered on Base.metadata before
# the `engine` fixture in tests/conftest.py runs `create_all`. Importing
# here keeps the models package untouched.
from app.scheduler.ledger import SchedulerFired  # noqa: E402, F401
