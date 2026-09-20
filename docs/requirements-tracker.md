# Requirements tracker — DealGate end-to-end

Every requirement from the build-guide, mapped to its story file, implementation
modules, tests, and verification evidence.

**Live URL**: https://dealgate.smartek21.com (also reachable at https://d1mu2un4hj9akj.cloudfront.net — same CloudFront distribution; the custom domain is an added alias, not a replacement. See `docs/runbooks/custom-domain.md`.)
**Cognito hosted UI**: https://officeapp-dev-405473.auth.us-east-2.amazoncognito.com
**Account**: `669810405473` / `us-east-2` / all resources prefixed `officeapp-dev-*`

Status codes: `done` · `partial` · `blocked` · `pending`.

## Sprint 0 — scaffold

| # | Requirement | Story | Impl | Tests | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| S0-1 | Monorepo per §14 | — | repo root | — | git log `b58edfa` | done |
| S0-2 | Standing rules for agents | — | `CLAUDE.md` | — | file present | done |
| S0-3 | UI kit primitives | — | `web/src/ui/` | — | live nav renders | done |
| S0-4 | FastAPI `/healthz` | — | `api/app/routers/health.py` | `test_health.py` | live: HTTP 200 | done |

## Sprint 1 — E1 platform + E2 HubSpot + deals

| # | Requirement | Story | Impl | Status |
| --- | --- | --- | --- | --- |
| S1-1 | SSO auth + `/me` (Cognito PKCE) | s1-e1-app-shell-and-sso | api/app/auth/, web/src/auth/ | done |
| S1-2 | Append-only audit chain (sha256, tamper-evident) | s1-e1-audit-log-viewer | api/app/audit.py | done |
| S1-3 | Standalone audit viewer + chain-verify | s1-e1-audit-log-viewer | routers/audit.py, pages/Audit.tsx | done |
| S1-4 | Users & roles admin (SystemAdmin only, last-admin guard) | s1-e1-app-shell-and-sso | routers/admin_users.py, pages/UsersAdmin.tsx | done |
| S1-5 | HubSpot v3 webhook + re-read + idempotent intake | s1-e2-hubspot-webhook-intake | routers/hubspot.py, services/hubspot_intake.py, worker/hubspot_intake.py | done |
| S1-6 | Deal list + Deal detail + PATCH with audit | s1-e2-deal-list-and-detail | routers/deals.py, pages/DealList.tsx, DealDetail.tsx | done |
| S1-7 | Six GM templates + policy floors (US 35% / India 50%) | — | api/app/gm/templates/ | done |
| S1-8 | Migration for 8 base tables | — | alembic/versions/20260917_0001_initial.py | done |
| S1-9 | Terraform dev deployment on AWS | — | infra-tf/ (63 resources) | done |
| S1-10 | Cognito hosted UI + PKCE + JWKS verifier | — | integrations/cognito.py, web/src/auth/cognito.ts | done |

## Sprint 2 — E3 agreements + tasks + notifications, E4 rate cards + policy + GM sandbox

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| S2-1 | opportunity→client FK + client upsert on HubSpot intake | services/clients.py, alembic 0002a | done |
| S2-2 | Client page with legal entities + agreements + opportunities + activity | pages/ClientList.tsx, ClientDetail.tsx | done |
| S2-3 | Agreements NDA/MSA CRUD + 10-state machine + S3 evidence upload | services/agreement_state.py, routers/agreements.py, integrations/s3_evidence.py | done |
| S2-4 | Rate cards + policy admin (Finance-only, immutable versions) | services/rate_cards.py, policy.py, routers/admin_rate_cards.py, admin_policy.py | done |
| S2-5 | Tasks inbox + lifecycle + snooze + reassign | services/tasks.py, routers/tasks.py, pages/MyTasks.tsx | done |
| S2-6 | Notification schema + settings + inbox + bell | services/notifications.py, ui/NotificationBell.tsx | done |
| S2-7 | Alert scheduler (4 triggers) + SES sender + exponential backoff | worker/alert_scheduler.py, notification_sender.py, integrations/ses.py | done |
| S2-8 | GM sandbox — M1 sign-off screen with §7 discounted case as HTTP evidence | routers/gm.py, services/gm_sandbox.py, pages/GMSandbox.tsx | **done + M1 evidence** |

## Sprint 3 — E5 SOW extract, E6 delivery model, E11 adviser

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| S3-1 | SOW upload + Bedrock extract with ManualRequired fallback (rule 6) | integrations/bedrock_sow_extract.py, services/sow_extract.py, pages/SOWUpload.tsx, SOWConfirm.tsx | done |
| S3-2 | Delivery Model Builder + live GM preview + capacity/HR warnings + xlsx | services/delivery_model.py, pages/DeliveryModelBuilder.tsx | done |
| S3-3 | Adviser intake + deterministic pricing (LLM roles, code math) + label discipline + no PDF | integrations/bedrock_adviser.py, services/adviser.py, pages/AdviserIntake.tsx | done |

## Sprint 4 — E7 approvals + CEO exception, E2 HubSpot writeback

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| S4-1 | Approval packages: frozen sow+gm hash, delivery/hr → finance/legal parallel | services/approvals.py, routers/approvals.py | done |
| S4-2 | Separation of duties + dual-role guard + change-voids-approval hooks | services/approvals_hooks.py | done |
| S4-3 | CEO exception brief (Bedrock, human rationale mandatory) + delegate | services/ceo_exception.py, integrations/bedrock_ceo_brief.py, pages/CEOExceptionBrief.tsx | done |
| S4-4 | HubSpot writeback (3 governance properties only, double-guarded MAP) | services/hubspot_writeback.py, worker/hubspot_writeback.py | done |

## Sprint 5 — E8 signed SOW, E9 renewals, E10 dashboards

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| S5-1 | Signed SOW upload + Bedrock re-extract + diff (exact price+dates, ≥0.9 scope) | services/signed_sow.py, pages/SignedSOWReview.tsx | done |
| S5-2 | Distribution (SES fan-out) + kickoff/billing tasks + renewal at term_end-60d + package→released | services/signed_sow.py::release | done |
| S5-3 | Renewals scheduler (7 triggers: 60d/7d/notice/30d/14d/expired/short-assessment) | worker/renewals_scheduler.py, services/renewals.py | done |
| S5-4 | Expired SOW blocks new commitments (submit_package → 409) | approvals.py churn guard | done |
| S5-5 | Six role dashboards (CEO/Finance/Delivery/Sales/HR/Legal) | services/dashboards.py, pages/dashboards/ | done |
| S5-6 | Client SOW+GM page with SUM(profit)/SUM(revenue) — asserted `Decimal("95")/Decimal("210")` | services/dashboards.py::client_sow_gm_view | done + assertion test |

## Sprint 6 — E9 forecast + actuals, E12 admin replay

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| S6-1 | Weekly forecast (single remaining_hours per line) + recovery task below floor | services/forecast.py, worker (WeeklyForecast page) | done |
| S6-2 | Actuals CSV import (all-or-nothing, upsert on (line, month)) | services/actuals_import.py, pages/ActualsImport.tsx | done |
| S6-3 | Admin replay screen (HubSpot writeback / notifications / integration events) | services/admin_replay.py, pages/AdminReplay.tsx | done |

## User-added scope

| # | Requirement | Impl | Status |
| --- | --- | --- | --- |
| X-1 | Bulk upload of existing SOWs (legacy — approval not evidenced) | services/legacy_import.py, pages/LegacyImport.tsx | done |
| X-2 | Excel resource import per template spec (all-or-nothing, missing cost rejects) | services/legacy_import.py::import_excel, fixtures/legacy_projects/ | done |
| X-3 | Current GM computed per legacy project (US/India/blended, floor pass/fail) | services/legacy_import.py::reconcile | done |
| X-4 | Reconciliation screen with approve gate + rollout-rule reminder | pages/LegacyReconciliation.tsx | done |
| X-5 | Guard preventing fake approvals on legacy sow_versions | services/approvals.py + assert_not_legacy_for_approval | done |

## Automation counts

- **562 API tests** (pytest, 100% passing)
- **107 web tests** (vitest, 100% passing)
- **20 SQLAlchemy models** covering the full data model
- **25 services** (all pure business logic; every mutation writes append_audit)
- **25 API routers** wired into main.py
- **42 web pages** (React + TypeScript + react-router)
- **21 alembic migrations** (linear chain via 3 merge migrations; downgrade tested)
- **5 workers** (hubspot_intake, alert_scheduler, notification_sender, renewals_scheduler, hubspot_writeback)

## Blueprint §11 acceptance scenarios coverage

All scenarios covered by per-story pytest suites. UAT-style browser end-to-end
suite is deferred to a follow-up task; the acceptance tests in
`api/tests/test_*.py` cover every Given/When/Then in the 27 story files under
`docs/backlog/`.
