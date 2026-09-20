"""S11 — CI guard: `auto_staffing.py` must never fabricate a role name.

Kanna Parimi 20-Sep directive rule 3: "Kill the phantom roles for good.
Remove the template role list entirely (grep for `Architect`/`Engineer`
seeds in the studio code)."

The check runs against the module source (not the imported symbols) so a
future edit that reintroduces `Architect` / `Engineer` / `Consultant` /
`Analyst` as literal role names fails CI before it reaches staging.
"""

from __future__ import annotations

import pathlib
import re


AUTO_STAFFING = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "auto_staffing.py"
)


def test_no_phantom_role_names_in_auto_staffing():
    text = AUTO_STAFFING.read_text()
    # Strip comments — the file may name the deleted phrases while
    # explaining WHY they were removed. Only shipped literals count.
    code_only = re.sub(r"#.*", "", text)
    # Strip triple-quoted docstrings too.
    code_only = re.sub(r'"""[\s\S]*?"""', "", code_only)
    for name in ("Architect", "Engineer", "Consultant", "Analyst"):
        assert name not in code_only, (
            f"auto_staffing.py must not reference {name!r} as a role literal — "
            "CLAUDE.md rule 11 and the 20-Sep directive forbid phantom rosters"
        )
