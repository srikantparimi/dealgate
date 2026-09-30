# S20 · cross-worker requests (Lead routes)

Workers append a block here whenever they need a change on a file they
don't own (per `contracts.md` §6) — the Lead applies within the hour and
tags the responsible worker + a link to the requesting commit.

Format:
```
## <Wn>-<UTC>-<seq> · <one-line title>
Reason: <why>
File(s): <paths>
Change: <exact behavior/API>
Rollback: <how to undo>
Test: <acceptance>
Requested-in: <sha of requesting commit or `plan-only`>
```

---

(seeded empty; workers append during their runs)

## W5-2026-09-30-01 · add S20 fixture prefixes to e2e cleanup regex

Reason: T44 full-journey + T32 event-injection tag their fixtures with
`S20 e2e ` (deal / client / SOW names) and `s20-injection` (SQS message
`test_marker`). `worker/e2e_cleanup.py::_PREFIX_RE` currently only knows
about S12–S17 prefixes; a scheduled tick will leave S20 residue behind
after 24h.

File(s): `worker/e2e_cleanup.py`
Change: extend `_PREFIX_RE` to also match `^(S20 e2e |s20-)`
(case-insensitive). Same 24h age gate stays.
Rollback: revert the regex diff; residue is harmless (name prefix
alone doesn't affect production data — isolation.md §7 confirms).
Test: `api/tests/test_s20_security_boundaries.py::test_e2e_cleanup_regex_does_not_match_real_clients`
still passes for the real names (`74 Sky`, `Capitec Bank Limited`,
`BSC Staffing - UX/UI Designer`, `Sky Group`, `3M Company`).
Requested-in: (this commit)
Owner: **W1** (owns `worker/`).

## W5-2026-09-30-02 · terraform apply for multi-role Cognito approvers

Reason: `tests/e2e/fixtures/multi-role-auth.ts` needs a Secrets Manager
entry `officeapp-dev-e2e-approvers` mapping role slots (submitter /
delivery / hr / finance / legal / ceo) to Cognito creds. Without it,
every role falls back to the SystemAdmin smoke bot and T27
(permissions uniform) + T44 (multi-role e2e) cannot verify role
partitioning tonight.

File(s): `infra-tf/modules/e2e-approvers/*` (new), `infra-tf/staging.tf` include.
Change:
- Create 5 new Cognito users (submitter, delivery, hr, finance,
  legal, ceo — the last already exists but confirm group membership).
- Put creds into `officeapp-dev-e2e-approvers` secret as JSON:
  `{ "submitter": {...}, "delivery": {...}, ... }`.
- Add each to the appropriate `cognito:groups` (Delivery / HR /
  Finance / Legal / CEO / Sales).
Rollback: `terraform destroy` on the module.
Test: `mintRoleTokens("delivery")` returns tokens whose
`cognito:groups` claim contains `"Delivery"` (asserted at test-suite
start).
Requested-in: (this commit)
Owner: **Lead** (Terraform, plus records D-ISO-02 in decisions.md).

## W5-2026-09-30-03 · read-only mirror endpoint for T03 parity

Reason: T03 SQL parity captures 6 surfaces (source, mirror, list,
client, deal, export). The mirror row (raw `opportunity` table with
timestamps) is only reachable today via a psql connection; we need
a read-only HTTP surface so the T03 harness runs from a laptop.

File(s): `api/app/routers/dev.py` (already exists), a new
`GET /api/dev/mirror/opportunities/{id}`.
Change: return the full `Opportunity` row + joined `HubspotStage`
label as JSON. Gate behind `require_role("SystemAdmin")` and
`DEALGATE_ENV in {"dev","staging"}` (mirrors existing dev-router
policy).
Rollback: delete the route.
Test: `scripts/t03-parity.sh` step 3 no longer records `(endpoint
not exposed)`; the captured JSON has non-null `hubspot_deal_id`,
`hubspot_stage_id`, `stage_label`.
Requested-in: (this commit)
Owner: **W1**.

## W5-2026-09-30-04 · pipeline export CSV endpoint

Reason: T03 step 6 (export parity) + T35
(test_export_returns_full_filtered_set) both need a public
`GET /api/pipeline/opportunities/export.csv` that returns the same
row set the list API would return (same filter, permission-checked,
same aggregate contract per contract §4).

File(s): `api/app/routers/pipeline.py`.
Change: add `GET /export.csv`; body is CSV with one row per matching
opportunity; columns match `OpportunityRow` fields; permissions
identical to list.
Rollback: delete the route.
Test: `api/tests/test_s20_pagination_vs_totals.py::test_export_returns_full_filtered_set`;
CSV row count equals list `total`, not `page_size`.
Requested-in: (this commit)
Owner: **W2**.
