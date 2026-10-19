"""S23-PL2 B7 / T2 (API half) — every metric equals the list its drill opens.

For each of the six metrics, across 106 filter combinations generated
deterministically (every value of every axis alone, then 40 seeded mixes) from
every filter axis (status, stage, deal owner incl.
none / former, account owner, business unit incl. unmapped, search, SOW state,
attention, missing information, every date field and preset, watching, group,
mine, tab, unmatched clients, client), applying the metric's ``drill`` to the
current filters returns a list whose length (or USD total) is the metric.
The shared seed makes every metric non-zero in many combinations: Hold, closed
won / lost, archived and missing owners, an unmapped and a missing region, a
deal with no amount and one in EUR, overdue / dated / undated next actions,
NDA / MSA on some clients, every SOW state incl. pending, and a deal with two
SOWs.
"""

from __future__ import annotations

import random
from collections import Counter
from decimal import Decimal

from tests import test_s23_pl2_workspace as shared

# Shared fixtures, bound as module globals so pytest finds them here.
api, engine, frozen_clock, seeded = shared.api, shared.engine, shared.frozen_clock, shared.seeded

AXES: dict[str, list] = {
    "status": ["open", "all", "won", "lost", "hold"],
    "stage": [[1], [2, 9], [7, 8], [3, 4, 5, 6], [9]],
    "owner": [["none"], ["former"], ["101"], ["102", "none"], ["104"]],
    "account_owner": [["101"], ["none"], ["102"]],
    "bu": [["ST21"], ["IT Avalon"], ["Retro Rabbit"], ["unmapped"], ["ST21", "unmapped"]],
    "q": ["acme", "bolt", "ben brook", "countersign", "delta", "zzz"],
    "sow": ["pending", "none", "draft", "signed", "changes_requested"],
    "attention": ["overdue", "past_close", "no_owner", "inactive", "pending_approval", "any"],
    "missing": ["owner", "close", "activity", "next_action", "nda", "msa", "agreements"],
    "date": [(field, preset) for field in ("close", "created", "activity")
             for preset in ("passed", "next7", "next30", "next90", "last7", "last30", "last90", "month",
                            "quarter", "custom")],
    "watching": [True],
    "group": ["viewer"],
    "mine": [True],
    "tab": ["clients"],
    "include_unmatched_clients": [True],
    "client": ["acme", "bolt", "delta"],
}


def combinations(seeded) -> list[dict]:
    """Every value of every axis alone (each date preset once), then 40 seeded mixes."""
    combos: list[dict] = [{}]
    for axis, values in AXES.items():
        # Ten date presets, each once, cycling through the three date fields.
        for value in values if axis != "date" else values[::3]:
            combos.append({axis: value})
    rng = random.Random(2323)
    for _ in range(40):
        combos.append({axis: rng.choice(values) for axis, values in AXES.items() if rng.random() < 0.3})
    return [to_params(combo, seeded) for combo in combos]


def to_params(combo: dict, seeded) -> dict:
    params: dict = {"page_size": 100}
    for axis, value in combo.items():
        if axis == "date":
            params["date_field"], params["date_preset"] = value
            if value[1] == "custom":
                params["date_from"], params["date_to"] = "2026-10-01", "2026-11-15"
        elif axis == "group":
            params["group"] = str(seeded.group)
        elif axis == "client":
            params["client"] = str(seeded.clients[value])
        elif isinstance(value, bool):
            params[axis] = "true" if value else "false"
        else:
            params[axis] = value
    return params


def apply_drill(params: dict, drill: dict) -> dict:
    out = {**params, "page": 1}
    for key, value in drill.items():
        if value is None:
            out.pop(key, None)
        else:
            out[key] = ("true" if value else "false") if isinstance(value, bool) else value
    return out


async def fetch(api, params: dict, cache: dict | None = None) -> dict:
    key = repr(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in params.items()))
    if cache is not None and key in cache:
        return cache[key]
    response = await api.get("/pipeline/workspace", params=params)
    assert response.status_code == 200, (params, response.text)
    if cache is not None:
        cache[key] = response.json()
    return response.json()


def usd_total(rows: list[dict]) -> Decimal:
    return sum((Decimal(row["amount"]) for row in rows if row["amount"] is not None and row["currency"] == "USD"),
               Decimal(0)).quantize(Decimal("0.01"))


async def test_every_metric_equals_the_list_its_drill_opens(api, seeded):
    combos = combinations(seeded)
    assert len(combos) == 106
    nonzero: Counter[str] = Counter()
    for params in combos:
        cache: dict = {}

        async def get(api, request: dict, _cache: dict = cache) -> dict:  # noqa: ANN001
            return await fetch(api, request, _cache)

        body = await get(api, params)
        metrics = body["metrics"]
        context = f"filters={params}"

        open_list = await get(api, apply_drill(params, metrics["open_deals"]["drill"]))
        assert open_list["page"]["total_rows"] == metrics["open_deals"]["value"], context
        assert open_list["tab_counts"]["deals"] == metrics["open_deals"]["value"], context
        assert len({row["client"]["id"] for row in open_list["rows"] if row["client"]["id"]}) == \
            metrics["open_deals"]["accounts"], context

        value_list = await get(api, apply_drill(params, metrics["open_value_usd"]["drill"]))
        assert value_list["page"]["total_value_usd"] == metrics["open_value_usd"]["value"], context
        assert str(usd_total(value_list["rows"])) == metrics["open_value_usd"]["value"], context
        assert value_list["page"]["total_rows"] == metrics["open_value_usd"]["deals"], context
        assert sum(1 for row in value_list["rows"] if row["stage_id"] == 9) == \
            metrics["open_value_usd"]["includes_on_hold"], context

        closing = await get(api, apply_drill(params, metrics["closing_this_month"]["drill"]))
        assert closing["page"]["total_rows"] == metrics["closing_this_month"]["value"], context
        assert closing["page"]["total_value_usd"] == metrics["closing_this_month"]["value_usd"], context

        overdue = await get(api, apply_drill(params, metrics["overdue_next_actions"]["drill"]))
        assert overdue["page"]["total_rows"] == metrics["overdue_next_actions"]["value"], context
        assert all("action_overdue" in row["flags"] for row in overdue["rows"]), context
        denominator = await get(api, apply_drill(params, {"tab": "deals", "status": "open", "attention": None}))
        with_action = {row["id"] for row in denominator["rows"] if row["next_action"]}
        assert len(with_action) == metrics["overdue_next_actions"]["with_next_action"], context
        # Pre-merge review R3: the overdue deals are always among "the deals with a next action".
        assert {row["id"] for row in overdue["rows"]} <= with_action, context

        pending = await get(api, apply_drill(params, metrics["pending_approvals"]["drill"]))
        assert pending["page"]["total_rows"] == metrics["pending_approvals"]["value"], context
        assert {row["sow_state"] for row in pending["rows"]} <= {
            "in_review_delivery_hr", "in_review_finance_legal", "ceo_exception"}, context

        gaps = await get(api, apply_drill(params, metrics["agreement_gap_clients"]["drill"]))
        assert gaps["page"]["total_rows"] == metrics["agreement_gap_clients"]["value"], context
        assert gaps["tab_counts"]["clients"] == metrics["agreement_gap_clients"]["value"], context
        # S24-AG1 B10: every listed client needs attention: net new, past stage 1, NDA or MSA missing.
        assert all("missing" in (row["agreements"]["nda_state"], row["agreements"]["msa_state"])
                   for row in gaps["rows"]), context
        assert all(not (row["agreements"]["nda_on_file"] and row["agreements"]["msa_on_file"])
                   for row in gaps["rows"]), context
        total = await get(api, apply_drill(params, {**metrics["agreement_gap_clients"]["drill"], "missing": None}))
        assert total["page"]["total_rows"] == metrics["agreement_gap_clients"]["clients_total"], context

        for name, metric in metrics.items():
            if metric["value"] not in (0, "0.00"):
                nonzero[name] += 1
    # The population makes every metric non-zero in many combinations.
    assert all(nonzero[name] >= 10 for name in (
        "open_deals", "open_value_usd", "closing_this_month", "overdue_next_actions", "pending_approvals",
        "agreement_gap_clients")), nonzero


async def test_a_drill_keeps_the_stage_selection(api, seeded):
    # The prototype clears the stage on a card click; then the list would not equal the card.
    get = fetch
    body = await get(api, {"stage": [1, 2], "status": "all"})
    assert body["metrics"]["open_deals"]["value"] == 5  # d01, d10, d02, d12, d15
    drilled = await get(api, apply_drill({"stage": [1, 2], "status": "all"},
                                         body["metrics"]["open_deals"]["drill"]))
    assert drilled["page"]["total_rows"] == 5
