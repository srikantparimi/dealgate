# Forecast Plan Source Provenance

Branch `s21/plan-source-provenance`, baseline `d44545b`. Bounded ownership:
`forecast_plans.list_plans`, new `test_s21_plan_source.py` and this report only.
Budget: 15 active minutes plus the lead-coordinated runtime wait.

Connected-browser finding: a server-issued local SOW-upload deal was labeled
Linked CRM deal merely because the plan had an internal opportunity UUID.
Tests are authored first, before production changes, with independent statuses:

- Nonblank persisted HubSpot deal ID: Linked HubSpot deal, even if the original
  record source was local before linkage. Neither name nor local UUID is proof.
- Known local source without external ID: Linked local deal.
- HubSpot/unknown source without usable external ID: Linked deal; CRM identity
  unavailable. Do not pretend a broken mirror is definitely local.
- No opportunity reference: Local forecast only.
- Missing/archived/mismatched-account referenced deal: Linked deal unavailable;
  return no navigable opportunity ID and no foreign identity metadata.

Existing source evidence, field shapes and permissions remain compatible. The
read path must never promote/create/update a CRM record. Authorization remains
upstream of source enrichment; fixture-account provenance continues to isolate
test data from business users. No extra source IDs are exposed.

Read-only UI review: `web/src/App.tsx` defines `/deals/:id`; both
`forecast/NextOpportunities.tsx` and `forecast/Overview.tsx` use the internal
opportunity UUID correctly for local and mirrored deals. Separately,
`forecast_plans.outlook` still constructs source_url from a bare opportunity ID
without checking availability. That dead-link/foreign-reference risk was sent
to the lead and is outside this narrow production ownership.

Schema limit: a historical deletion that already SET NULLs the plan's foreign
key is indistinguishable here from an always-unlinked plan. This pass cannot
invent deletion provenance. The retained source marker requirement needs its
existing deletion/source-history contract, not inference from a NULL field.

## Verification

Initial new-file run: **11 failed, 2 passed**. Failures were the incorrect source
statuses; existing owner/tenant and unlinked controls passed. Production now
uses `_plan_source_identity` from the scoped list path. It validates deal
availability/account and the exact fixture-issued deal grant before returning
a link. An additional assertion verifies an ungranted fixture sibling cannot
become a navigable plan source. No existing tests or assertions were modified.

Combined `test_s21_plan_source.py`, `test_s21_plan_assumptions.py` and
`test_s21_forecast_plans.py`: **32 passed**, two existing FastAPI deprecation
warnings, 22.77 seconds. No skips, xfails or retries. Explicit current-worktree
PYTHONPATH with a read-only dependency executable, disabled bytecode/cache and
unset DEALGATE_POSTGRES_URL ensured private SQLite fixtures only. No network,
CRM writes, migrations, provider or staging calls. Diff checks passed.

Status: fixed and tested locally. No staging or full FC-08 completion claim.

## Calculated Outlook Follow-Up

Lead expanded ownership to `outlook` source metadata assembly after the first
commit. Three additional independent cases create real persisted plans and
worker-produced schedules, then simulate missing, archived and foreign-account
deal references. All three failed first on the stale source URL assertion.

Outlook now reuses the same validated source-identity helper for plan source
metadata and constructs a URL only from the permitted live deal identity.
The source name, calculation metadata, assumptions and evidence remain intact.
Tests read through the Sales-role response redaction, asserting no cost field,
foreign source metadata or navigable invalid opportunity ID survives.

Final combined source/assumptions/plan regression: **35 passed**, two existing
deprecation warnings, 23.15 seconds; no skipped, retried or weakened tests.
All original test files remain unchanged. Same isolated SQLite/runtime controls
as above. The previously reported outlook destination gap is fixed locally;
source conversion, SET NULL deletion-history semantics and connected staging
verification remain outside this increment.
