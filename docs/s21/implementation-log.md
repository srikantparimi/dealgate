# Tested Increments

## S21-07 / S21F:T07,T32: Trusted Fixture Boundaries

Lead-owned files: services/test_fixtures.py, approval_routing.py, approval_workflow.py, notifications.py; routers/dev_seed.py; worker/notification_sender.py; test_approval_routing.py and test_s21_test_isolation.py. This adds no schema or deployment change.

Baseline exact regression: `tests/test_approval_routing.py::test_s21_forged_client_name_never_authorizes_test_reviewers` failed because renaming a real client to an e2e prefix selected the test Finance user. The pre-existing test expecting that unsafe behavior was replaced by a stronger v3 refusal assertion, not skipped.

Implementation: only a server-issued, append-only provenance event created atomically with a NEW fixture account/deal can authorize test reviewers. Issuance requires enabled non-production fixture endpoint, test+SystemAdmin actor, explicit tenant, bounded validity and a roster of test identities. It cannot adopt an existing client or create an approved state/SOW. Routing, task creation, decisions, outbox enqueue and sender dispatch recheck scope. Wrong environment/tenant, missing tenant, expired grant, undeclared reviewer and ordinary client-name prefixes never authorize test reviewers; expired fixtures never fall back to business recipients.

Focused execution: `pytest tests/test_approval_routing.py tests/test_s21_test_isolation.py tests/test_notification_sender.py tests/test_notifications.py -q`: **44 passed, exit 0**, no skips/retries. Actual SQLAlchemy service paths and outbox worker, with only SES isolated to its existing test sink. SQLite fixture DB, NOT deployed PostgreSQL/storage/browser proof. Ruff targeted check and git diff --check pass. [Run log](evidence/baseline/isolation-tests.log).

Remaining S21-07: live contamination enumeration, pending cancellation + completed-decision invalidation/re-review, trusted cleanup consumer integration, PostgreSQL/HTTP/browser/staging evidence. The full requirement remains missing until these are implemented/proved. Do not label this increment full S21-07 acceptance.

Integration decisions: reuse existing append-only audit storage for trusted issuance, rather than a second mutable user-editable tag column. If profiling requires a dedicated indexed provenance projection, lead will add it with an ordered migration; immutable issuance stays the authority. Reviewer eligibility and Cognito grouping must still be independently verified on staging.

## S21F-01 Integration and Independent QA

Commercial commit dcda0ace integrated as e041387: immutable calendar/version references, inclusive overlap, dated overrides, scheduled/billable/paid quantities, explicit uncovered dates, Decimal context and quantity/allocation applied once. Production calendar engine is not used to construct independent expectations. The pure hourly adapter feeds existing GM authority; fixed/MSP profiles, persisted configuration, cost-only schedules and UI are NOT delivered by this increment. 31 new calendar tests pass; worker GM regression was 142 passed plus 12 pre-existing xfails.

First full execution of the initial containment tree: 1165 collected, 1005 passed, four failed, six skipped, 150 pre-existing xfailed, 452.79 seconds. [Original JUnit](evidence/baseline/pytest-checkpoint.xml) preserves each node and skip/xfail reason. Five skips required Postgres and one required explicit live Bedrock opt-in. The 150 old skeleton/dependency xfails are not completed acceptance. The four failures involved two legacy client-less CEO flows, a missing owner User and randomly fabricated signed-SOW parent references. dea73ca fixes business scope and strengthens fixtures without weakening assertions. Intermediate targeted failure and subsequent 34-pass fixture regression are retained.

Independent QA 47c9c51, integrated as 0ffcb9b, supplied 13 tests: nine passed; four exposed CEO, legacy task routing and task-linked reminder queue/dispatch bypasses. Original findings remain [unchanged](qa/first-increment.md). Fix bd22cb776584ea4abd10e9b8c473b9f1de2325e2 resolves these paths and filters administrative routing fallbacks. Task containment resolves authoritative assignment/audit parent, never editable body text. CEO fixtures now persist the authenticated User rather than relying on a nonexistent database identity.

Final affected-file execution: **130 passed, zero failed/skipped/xfail**, 33.74 seconds. [JUnit](evidence/baseline/final-targeted.xml), [log](evidence/baseline/final-targeted-corrected.log). Initial command typo referenced nonexistent test_gm_calendar.py, collected no tests/exit4, and is preserved as final-targeted.log; corrected filename is test_s21_calendar_schedule.py. This is command correction, not a retry of flaky feature assertions. Ruff for changed service/test files and git diff --check pass.

Independent QA recheck on exact bd22cb7: unchanged same 13 tests, 13 collected/executed/passed, zero failures/skips/xfails/not-run, 6.19 seconds. QA-owned venv/basetemp, integration imports verified, no source edits, no cache writes to integration, local SQLite and SES sink only. No residual defect observed within those bounded checks; full T07/T13 and staging remain unverified.

Real isolated PostgreSQL final check: **5 passed**, 12.84 seconds, zero skips: concurrent approval decision, immutable audit trigger and three migration-parity tests. [JUnit](evidence/baseline/postgres-final.xml), [log](evidence/baseline/postgres-final.log). All baseline migrations applied to the owned empty database, single head 20260930_0047_w6_watch. Not a representative backup/restore or full browser/storage journey. Full combined pytest rerun remains required after this checkpoint.
