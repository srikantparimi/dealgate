# T23 Publication Boundary Fixture

Worker authored only. Lead seeds64563/14361 passed; admin88901/Sales49160 passed,
occupied guard72095 refused; both private DBs dropped with absence0.
[Current proof](../evidence/baseline/t23-publication.md). Base188adf3; owns only this report and
scripts/s21_publication_boundary_fixture.py. No runtime, tests, installation,
database, migrations or provider operations performed.

Self-contained seed requires explicit local environment, matching tenant,
trust-only asyncpg s21 user/owner at literal127.0.0.1:55421 and database
s21_pub_<32 lowercase hex>. Rejects PG overrides, URL options/password,
unmigrated or populated target; validates actual connected identity, locks
tables and uses an outer transaction with savepoint-isolated service commits.
Lead alone creates/comments/migrates/runs/drops the private database.

Real create_fixture and save_plan issue one authorized synthetic account/deal
and tentative70% plan. Actor local-test has SystemAdmin,HR,Delivery,officeapp-e2e;
its same identity will later read as Sales,officeapp-e2e via the lead's isolated
local-auth runtime switch. No publication, workforce import, sourcing rules,
drafts or matching outcomes are seeded. save_plan's ordinary pending forecast
job remains unexecuted.

Initial canonical source:2 US/5 India half-time roles, Nov1 2026-Apr30 2027;
US America/New_York, India Asia/Kolkata. Six-person roster remains a manifest
payload for real UI import: US capacity1, four India0.5, one India0.25.
Independent oracle:7 heads/3.5 required FTE/2.5 matched/1 gap.

Nonvacuous financial sentinels are explicit canonical data, not text hidden in
staffing evidence: each child's fixed fee187643.53, each monthly PeriodCost4317.29,
assignment bill_rate293.17 and cost_rate83.29, with rate/source versions. Financial
calculation is not this fixture's acceptance claim. Browser/API proof must first
verify these exist in the authorized source, then verify restricted nonempty
People responses omit their field paths and values. Do not merely test an empty
response or assume cost-free labels prove data redaction.

Manifest exposes all T22 stable keys plus sentinels, financial_sentinels paths,
plan_request, original_inputs, bound_inputs, revised_inputs and revision_body.
revision_body is ready for POST /forecast/plans/{plan_id}/versions with initial
expected_version_id and fresh idempotency key; account/deal identity is preserved.
It changes start to Dec1 and US quantity to3, retaining Apr30 end; all component,
assignment and calendar bounds/source bindings remain coherent. This source edit
is API-authored because current UI edits assumptions only.

Revised independent oracle per December-April interval:8 heads/4 required FTE/
2.5 matched/1.5 gap. US gap2 people/1FTE, India gap1/0.5FTE. With explicit rules
US45/India30 calendar days, sourcing dates are Oct17/Nov1. Old publication and
draft snapshots must remain immutable. publication_body carries exact initial
source CAS, null previous publication CAS and evidence-backed capability keys;
republish must replace both CAS values with the observed current versions.

Lead invocation from repository root, replacing DB_NAME:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=DB_NAME \
S21_PUB_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/DB_NAME \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_publication_boundary_fixture.py > /tmp/s21-publication-boundary-manifest.json
```

Remaining lead proof: real publication/import/draft, stale-to-republish browser
flow after real source revision, immutable history, restricted nonempty reads,
forbidden planning mutation extras with unchanged audits/versions/workforce.
Observed reserved/hired HR import commitments remain supported snapshots, not
operational hire commands. No script execution or scenario/staging closure is
claimed by this authored artifact.
