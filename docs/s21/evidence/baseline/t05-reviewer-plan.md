# T05 Reviewer Planning: Local Pass

Application a5ee76d9622a8b0008b867cb7c4361a4ca78f6b7.
Browser89032: one passed,22.3s total/19.6s test,2026-10-02 22:58 UTC.
Focused UI96515:26 passed/3 files/9.82s; TypeScript89235 exit0.
Independent read-only QA confirmed all four literal conditions are asserted.

Command from tests/e2e (requires fresh isolated fixture and matching API):
```sh
S21_REVIEW_MANIFEST=/tmp/s21-review-6619630c-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-reviewer-plan.spec.ts --output test-results/s21-t05-repair --reporter=list
```
Test: [connected assertions](../../../../tests/e2e/local/s21-reviewer-plan.spec.ts).
Screenshot: [submitted review stream](t05-reviewer-plan.png).

- T05.01: direct Approvals entry without earlier selections; exactly five
  functions, exact eligible names/default IDs, source SOW/GM versions1.
- T05.02: permitted alternate Delivery selection; real POST201; reload shows
  selected reviewer. Independent PostgreSQL query confirms one pending_delivery_hr
  package, exact frozen source IDs, five selected assignments, three assigned
  tasks owned by Delivery alternate/HR/Sales. Above-floor CEO absent.
- T05.03: nonexistent reviewer422, zero packages/assignments/tasks afterward.
- T05.04: nonmember/submitter/duplicate eligible person selections422;
  unauthorized nonowner submission403; zero rows after each refusal.

No mocked feature responses. Local Sales identity adapter, real API/PostgreSQL0061.
Declared synthetic confirmed source, not upload/extraction/S3 proof. No real
roster/dated OOO/email/Cognito/staging claim; S21-05 remains partial.
Fixture author379ffdf integrated186b126. Private second DB
s21_review_6619630cf37f4ccdb8e781ac597d457a, OID94402, owner s21,
comment owned-s21-t05:6619630cf37f4ccdb8e781ac597d457a. Seed65311 exit0.
First DB OID92167, s21_review_49911fb40df345cf8e1c74a7e7c6a0e5,
matching owned-s21-t05 comment. Guard40419 correctly refuses occupied seed.
Cleanup status is recorded in the handoff; manifests are not reusable fixtures.

## History

UI3708 missing heading; fixed42422. Host stale-route race35657 reproduced,
37364/96515 green after route guard. Browser78936 failed after successful
submission because exact name-only locator did not match full visible heading.
Screenshot confirmed selected reviewer; corrected to exact scoped full Delivery
heading and reran on a new database. No retry/skip/assertion weakening.
First failure artifacts tests/e2e/test-results/s21-t05; pass artifacts
tests/e2e/test-results/s21-t05-repair. These local ignored artifacts are secondary
to this committed report, test and screenshot.
