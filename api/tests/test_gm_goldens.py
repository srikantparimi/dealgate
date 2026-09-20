"""The fifteen golden fixtures, run against the engine (GM directive).

Each `expected.json` was computed by hand and verified a second, independent
way before any of this code existed. A golden generated from the engine would
only prove the engine agrees with itself.
"""

from __future__ import annotations

import json
import pathlib
from decimal import Decimal, localcontext

import pytest

from app.gm.engine import (
    GM_PRECISION,
    DirectCost,
    ResourceInput,
    SowSpec,
    compute_gm,
)

FIXTURES = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "sows"


def _d(value) -> Decimal | None:
    return None if value in (None, "") else Decimal(str(value))


def _resources(raw: list[dict]) -> tuple[ResourceInput, ...]:
    out = []
    for r in raw:
        hours = r.get("hours")
        out.append(
            ResourceInput(
                role=r.get("role", "?"),
                seniority=r.get("seniority"),
                location=r.get("location"),
                billable_hours=_d(r.get("billable_hours", r.get("forecast_hours", hours))),
                paid_hours=_d(r.get("paid_hours", hours)),
                bill_rate=_d(r.get("bill_rate")),
                cost_rate=_d(r.get("cost_rate")),
                utilization=_d(r.get("utilization")) or Decimal("1"),
            )
        )
    return tuple(out)


def _spec(raw: dict) -> SowSpec:
    """Build an engine spec from a fixture's input.json."""

    alloc = raw.get("revenue_allocation") or {}
    fx = raw.get("fx") or {}
    guarantee = raw.get("refund_guarantee") or {}
    return SowSpec(
        engagement_type=raw["engagement_type"],
        resources=_resources(raw.get("resource_lines") or []),
        direct_costs=tuple(
            DirectCost(
                label=c["label"],
                amount=_d(c.get("amount")),
                location=c.get("location"),
                pass_through=bool(c.get("pass_through")),
            )
            for c in raw.get("direct_costs") or []
        ),
        contract_price=_d(raw.get("contract_price")),
        revenue_allocation={
            k: Decimal(v) for k, v in alloc.items() if k in ("US", "India")
        }
        or None,
        allocation_basis=alloc.get("basis", "cost_weighted"),
        not_to_exceed=_d(raw.get("not_to_exceed")),
        term_months=int(raw["term_months"]) if raw.get("term_months") else None,
        monthly_fee={k: Decimal(v) for k, v in (raw.get("monthly_fee") or {}).items()},
        monthly_team_cost={
            k: Decimal(v) for k, v in (raw.get("monthly_team_cost") or {}).items()
        },
        onboarding_fee=_d(raw.get("onboarding_fee")),
        ramp_months=int(raw.get("ramp_months") or 0),
        placement_fee=_d(raw.get("placement_fee")),
        recruiting_cost=_d(raw.get("recruiting_cost")),
        refund_reserve_pct=_d(guarantee.get("reserve_pct")),
        location=raw.get("location"),
        discounts=tuple(_d(d["pct"]) for d in raw.get("discounts") or []),
        fx_rate=_d(fx.get("rate")),
        fx_as_of=fx.get("as_of"),
        currency=raw.get("currency", "USD"),
        components=tuple(_spec(c) for c in raw.get("components") or []),
    )


def _cases() -> list[str]:
    return sorted(
        d.name
        for d in FIXTURES.iterdir()
        if d.is_dir() and (d / "expected.json").exists()
    )


# Fixture 15 is a document-check case: the engine is never reached, so it is
# asserted in the upload router tests, not here.
_ENGINE_CASES = [c for c in _cases() if not c.startswith("15-")]
# Fixture 14's amendment shape is asserted separately below.
_ENGINE_CASES = [c for c in _ENGINE_CASES if not c.startswith("14-")]


@pytest.mark.parametrize("slug", _ENGINE_CASES)
def test_golden(slug: str):
    raw_in = json.loads((FIXTURES / slug / "input.json").read_text())
    exp = json.loads((FIXTURES / slug / "expected.json").read_text())

    result = compute_gm(_spec(raw_in))

    assert result.status == exp["status"], (
        f"{slug}: expected {exp['status']}, got {result.status} "
        f"({result.reason or ''})"
    )

    if exp["status"] == "incomplete":
        got = {(m.field, m.line) for m in result.missing}
        want = {(m["field"], m["line"]) for m in exp["missing"]}
        assert want <= got, f"{slug}: expected to name {want - got}"
        assert result.gm_blended is None
        return

    if exp.get("revenue_total") is not None:
        assert result.revenue_total == Decimal(exp["revenue_total"]), f"{slug}: revenue"
    if exp.get("cost_total") is not None:
        assert result.cost_total == Decimal(exp["cost_total"]), f"{slug}: cost"

    for key, loc in (("gm_us", "US"), ("gm_india", "India")):
        want = exp.get(key)
        got = result.gm_by_location.get(loc)
        if want is None:
            assert got is None, f"{slug}: {key} should be absent, got {got}"
        else:
            assert got == Decimal(want), f"{slug}: {key} expected {want}, got {got}"

    if exp.get("gm_blended") is not None:
        assert result.gm_blended == Decimal(exp["gm_blended"]), f"{slug}: blended"

    for key, loc in (("us_pass", "US"), ("india_pass", "India")):
        assert result.passes.get(loc) is exp.get(key), f"{slug}: {key}"

    if "requires_ceo" in exp and exp["requires_ceo"] is not None:
        assert result.requires_ceo is exp["requires_ceo"], f"{slug}: requires_ceo"


def test_every_fixture_is_covered():
    """Fifteen fixtures, none quietly skipped."""

    assert len(_cases()) == 15, _cases()


# --- fixture 14: an amendment is a new package, plus the delta -----------


def test_golden_14_amendment():
    """A scope addition is computed twice: the amended whole and the delta.

    Reporting only the whole understates how bad an addition is. Here the
    base passes at 36.67%, the addition on its own is 15%, and the amended
    whole lands under the floor — the delta is what makes that legible.
    """

    slug = "14-amendment-scope-addition"
    raw = json.loads((FIXTURES / slug / "input.json").read_text())
    exp = json.loads((FIXTURES / slug / "expected.json").read_text())

    add = raw["addition"]
    delta_spec = SowSpec(
        engagement_type=raw["engagement_type"],
        resources=_resources(add["resource_lines"]),
    )
    delta = compute_gm(delta_spec)

    assert delta.status == "ok"
    assert delta.revenue_total == Decimal(exp["delta"]["revenue_total"])
    assert delta.cost_total == Decimal(exp["delta"]["cost_total"])
    assert delta.gm_blended == Decimal(exp["delta"]["gm"])
    assert delta.passes["US"] is exp["delta"]["pass"]

    # The amended whole is base + addition, recomputed — not the two margins
    # averaged, which would be arithmetically meaningless.
    base = raw["base"]
    whole_rev = Decimal(base["revenue_total"]) + delta.revenue_total
    whole_cost = Decimal(base["cost_total"]) + delta.cost_total
    with localcontext() as ctx:
        ctx.prec = GM_PRECISION
        whole_gm = (whole_rev - whole_cost) / whole_rev

    assert whole_rev == Decimal(exp["amended_whole"]["revenue_total"])
    assert whole_cost == Decimal(exp["amended_whole"]["cost_total"])
    assert whole_gm == Decimal(exp["amended_whole"]["gm"])
    assert (whole_gm >= Decimal("0.35")) is exp["amended_whole"]["pass"]

    # The base passed on its own; the amendment is what breaks it.
    with localcontext() as ctx:
        ctx.prec = GM_PRECISION
        base_gm = (
            Decimal(base["revenue_total"]) - Decimal(base["cost_total"])
        ) / Decimal(base["revenue_total"])
    assert base_gm >= Decimal("0.35")
    assert whole_gm < Decimal("0.35")


def test_golden_15_is_rejected_before_the_engine():
    """A resume and a malformed file never reach the GM engine at all.

    Asserted here as a contract: the document check owns this, and the engine
    must not be asked to produce a margin for something that is not a SOW.
    """

    from app.services.document_text import UnreadableDocument, extract_document_text
    from app.services.document_type import classify_document

    exp = json.loads((FIXTURES / "15-rejected-not-a-sow" / "expected.json").read_text())
    assert exp["status"] == "rejected"

    resume = (FIXTURES.parent / "sample_sows" / "99_resume.pdf").read_bytes()
    assert classify_document(resume).type == exp["resume"]["detected_type"]

    with pytest.raises(UnreadableDocument):
        extract_document_text(b"PK\x03\x04 truncated")
