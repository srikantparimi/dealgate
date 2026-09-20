"""`docs/gm-rules.md` must match the rule table the engine actually reads.

Finance signs off on that page. If a rule can change without the page
changing, the signature stops meaning anything — so the page is generated and
this test fails the build when it is stale.
"""

from __future__ import annotations

import pathlib
import sys

DOC = pathlib.Path(__file__).resolve().parents[2] / "docs" / "gm-rules.md"
GEN = pathlib.Path(__file__).resolve().parents[1] / "scripts_gen_gm_rules.py"


def _render() -> str:
    sys.path.insert(0, str(GEN.parent))
    import importlib.util

    spec = importlib.util.spec_from_file_location("_gen_gm_rules", GEN)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render()


def test_the_document_is_current():
    assert DOC.exists(), "docs/gm-rules.md is missing — run the generator"
    assert DOC.read_text() == _render(), (
        "docs/gm-rules.md is stale. A rule changed without the page Finance "
        "signed off on changing with it. Run: python api/scripts_gen_gm_rules.py"
    )


def test_every_rule_appears_on_the_page():
    from app.gm.engine import ENGINE_RULES

    text = DOC.read_text()
    for rule in ENGINE_RULES.values():
        assert rule.label in text, rule.label
        assert rule.revenue_rule in text, f"{rule.label}: revenue rule missing"
        assert rule.cost_rule in text, f"{rule.label}: cost rule missing"
        # The "never do" line is the part that stops a plausible wrong number,
        # so it is the part most worth having in front of Finance.
        assert rule.never_do in text, f"{rule.label}: 'never' missing"
