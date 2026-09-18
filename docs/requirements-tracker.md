# Requirements tracker

Every requirement from the blueprint / build-guide, mapped to its story file,
implementation module(s), tests, and verification evidence. Updated at the end
of each sprint wave.

Status codes: `done` · `partial` · `blocked` · `pending`.

## Sprint 0 — scaffold

| # | Requirement | Story | Impl | Tests | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S0-1 | Monorepo per §14 | — | repo root | — | git log b58edfa | done |
| S0-2 | Standing rules for agents | — | CLAUDE.md | — | file present | done |
| S0-3 | UI kit primitives (AppShell, StatusChip) | — | web/src/ui/ | web/src/__tests__ | vite build | done |
| S0-4 | FastAPI /healthz | — | api/app/routers/health.py | test_health.py | curl /healthz 200 | done |

## Sprint 1 — E1 platform, E2 HubSpot + deals

| # | Requirement | Story | Impl | Tests | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S1-1 | SSO auth + /me | s1-e1-app-shell-and-sso.md | api/app/auth/, api/app/routers/me.py | test_auth.py, test_cognito_auth.py | live Cognito login | done |
| S1-2 | Append-only audit chain, tamper-evident | s1-e1-audit-log-viewer.md | api/app/audit.py | test_audit.py | verify_chain returns ok | done |
| S1-3 | Standalone audit viewer + verify | s1-e1-audit-log-viewer.md | api/app/routers/audit.py, web/src/pages/Audit.tsx | test_audit_viewer.py, Audit.test.tsx | done |
| S1-4 | Users & roles admin (SystemAdmin-only) | s1-e1-app-shell-and-sso.md | api/app/routers/admin_users.py, web/src/pages/UsersAdmin.tsx | test_admin_users.py, UsersAdmin.test.tsx | done |
| S1-5 | HubSpot v3 webhook + re-read + idempotent intake | s1-e2-hubspot-webhook-intake.md | api/app/routers/hubspot.py, services/hubspot_intake.py, worker/hubspot_intake.py | test_hubspot_signature.py, test_hubspot_intake.py | done |
| S1-6 | Deal list + Deal detail + PATCH with audit | s1-e2-deal-list-and-detail.md | api/app/routers/deals.py, web/src/pages/DealList.tsx, DealDetail.tsx | test_deals.py, DealList.test.tsx, DealDetail.test.tsx | done |
| S1-7 | Six GM templates + policy floors + hypothesis | — | api/app/gm/templates/ | test_gm_*.py | 63 tests | done |
| S1-8 | 8-table Postgres schema + migration | — | api/alembic/versions/20260917_0001_initial.py | test_models.py | RDS in dev | done |
| S1-9 | Terraform dev deployment on AWS | — | infra-tf/ | manual apply, curl live | ~$80/mo running | done |
| S1-10 | Cognito hosted UI + PKCE | — | web/src/auth/cognito.ts | AuthProvider.test.tsx | login works end-to-end | done |

## Sprint 2 — E3 agreements + tasks + notifications, E4 rate cards + policy admin + GM sandbox

*Updated at end of each wave.*

## Sprint 3 — E5 SOW upload + AI extraction, E6 Delivery Model Builder + GM sheet, E11 adviser start

*Updated at end of each wave.*

## Sprint 4 — E7 approval packages + CEO exception + HubSpot write-back, E11 adviser finish

*Updated at end of each wave.*

## Sprint 5 — E8 signed SOW distribution, E9 renewals, E10 dashboards + client page

*Updated at end of each wave.*

## Sprint 6 — E9 forecast/actuals, E12 legacy SOW import, UAT

*Updated at end of each wave.*

## User-added scope

| # | Requirement | Task # | Story | Impl | Tests | Status |
| --- | --- | --- | --- | --- | --- | --- |
| X-1 | Bulk upload existing SOWs | 17 | s6-legacy-sow-import.md | pending | pending | pending |
| X-2 | Excel resource import per project | 18 | s6-legacy-excel-import.md | pending | pending | pending |
| X-3 | Compute current GM for legacy projects | 17 | (part of X-1) | pending | pending | pending |
| X-4 | SOW↔resources reconciliation screen | 19 | s6-legacy-reconciliation.md | pending | pending | pending |
