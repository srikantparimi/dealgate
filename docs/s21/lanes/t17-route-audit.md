# T17 Read-Only Route Audit

Author-only, unexecuted. Branch s21/t17-route-audit from6ad2171 in isolated
dealgate-s21-actual-coverage. Own only new route spec and this report. Previous
sticky-header branch preserved. No tests, servers, DB/API/provider operations run.

Spec requires exact existing /tmp/s21-t17-61d71c0b.json, private database
s21_t17_61d71c0b4bf7436d957723c632fe1aba, API8211/UI5211 and released project
aa26879a-826c-445f-9792-4a995039b409 for deal0a66db62-3619-4762-a96e-afe1473864a9.
Only GET API requests, browser navigation and BEGIN READ ONLY SQL. Local identity
headers do not mock feature responses. No upload, submission, handoff replay or
business mutation is allowed. Runtime still provisions/synchronizes identity as
part of ordinary authenticated reads; this is not a database-read-only server.

T17.06: reconcile exact one deal/SOW/package/project and physical project ID;
open count from SQL vs filtered Pipeline list/summary/client rollup; client/deal
names; all eight workspace tabs keep one exact source title/version/readiness and
tab shell; no phantom SOW controls on direct denied pages. Read-only counts must
remain identical afterward. Sticky header gets computed opaque background,
56px offset and elementFromPoint ownership check while scrolled; screenshot.

T17.08: Pipeline/client/deal entry; direct-link and reload each of overview,
scope, staffing, approvals, documents, signature, handoff, activity; click tab
transitions and browser Back; verify same immutable source throughout. Normal
nonfixture SystemAdmin first proves valid role via /me and successful list APIs,
then fixture absence in lists, denial on exact API source routes and no source
identity/controls on direct browser routes. Either403 or404 is accepted only after
that role evidence; responses cannot disclose the fixture name.

Not a whole T17 closure: initial empty-deal path/core provider workflow belongs to
the prior connected spec; NDA/MSA semantics, repeated handoff events, exact AWS/
Cognito leak gate and staging remain separate. This inventory covers applicable
same-source workspace/client/deal routes, not every admin/legacy application route.
The parent must execute and reconcile failures honestly before promoting evidence.

Lead execution command from tests/e2e once its private runtime is ready:

```sh
npx playwright test --config playwright.s21-local.config.ts local/s21-t17-route-audit.spec.ts --workers=1
```

Harness is zero retries. Output JSON and screenshot are written only when run;
none exists as a result of authoring this artifact.

## API Contract Correction

Lead first execution42204 stopped at the authored source-title assumption before
browser navigation: this extracted document does not contain sow_title/title.
Authorized focused owner GETs on8211 confirmed workspaceTitle's existing fallback
is the literal fixture client name (legacy deal engagement_type is null). Revised
spec asserts independently authored fixture name plus exact source version,
opportunity, known document SHA256 and filename, rather than requiring invented
extraction fields. No assertions dropped.

Also corrected the detail API: actual DealDetail uses
/pipeline/opportunities/{id} for name and sow_count; legacy /deals/{id} supplies
workspace client_name/engagement_type and has neither former field. GET inspection
confirmed list totals1, client matching/open1, summary open1 and project provenance
shape. No browser/test rerun performed by worker; six selected API populations
read only. Parent retains runtime slot and will run the corrected audit.
