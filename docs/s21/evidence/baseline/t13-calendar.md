# T13 Calendar: Current Bounded Proof

Tested tree00371d2dd43d1de9dfd7885de17c59a52d569430, application
bde6d29507ca1a7d91c1c757f4365fe81a2faa8c exposes already-persisted calendar
quantities and daily exceptions. No browser financial calculation added.
T13 PASSED LOCALLY; S21-15 remains partial. No staging deployment.
Final browser41842 passes1/37.3s; current independent oracle78 passes; UI20 passes.
Tested working files committed unchanged afterward, not a claim of rerunning.

## Independent Expectations

QA read-only review derived Oct16-31 2026:11 weekdays, one paid nonbillable
holiday per location. US3 people at25%, USD120 bill/33 cost:60 scheduled/billable,
66 paid hours,7200 revenue,2178 cost,69.75% GM. India2 people at50%,USD80 bill/40
cost:80 scheduled/billable,88 paid,6400 revenue,3520 cost,45% GM (below50% floor).
US holidayOct23 gives0/0/6 hours; IndiaOct26 gives0/0/8. Aggregate13600 revenue,
5698 cost. Separate child timezones preserved in a hybrid root.

## Checks And History

- UI68458: new saved-details assertion failed (missing accessible region).
- UI67465: all20 CommercialEditorIndependent cases pass22.07s after display fix.
- Typecheck57180 exits0.
- Browser40617:37s failure after correct money/save/reload on assumed row order.
  API canonical India-first; assertion now sorts exact identity/value tuples.
  No production ordering requirement or weaker value assertion introduced.
- Browser78838:33.7s; all API hours/holiday/margin-floor assertions pass. UI
  disclosure enumeration ran before reload finished, leaving details closed.
  Await visible details before enumerating; no timeout increase or retry.
- Browser22213 passes1/44.1s with that identified readiness repair. Screenshot
  inspected: saved quantities/day exceptions render; full page is long because
  each editable child and saved schedule is retained. No hidden financial math.
- Browser48880 failed8.7s: isolated missing calendar/cost assertions passed;
  short-coverage fixture wrongly put an Oct26 override outside Oct25 coverage.
  Parser correctly rejects that invalid structure. Use Oct27 coverage end,
  still shorter than Oct31 term, so the intended unresolved-coverage path runs.
  Output s21-t13-missing retained; corrected run uses s21-t13-coverage.
- Browser24672 passes1/44.4s including isolated missing inputs and mobile width.
- API58708 passes78/2.254s, zero skips/failures, t13-calendar-api.xml. Includes
  current ten-person monthly oracle, partial periods and missing-input matrix.
- Independent read-only QA finds no display defect; suggests explicit visible
  hours and saved-unknown assertions.52350 passes saved-unknown but failed34.6s
  because role=cell included header cells. Scope to tbody, preserving exact
  three numeric values; final output s21-t13-final.
- Browser41842 passes1/37.3s, including exact visible hours and persisted unknown
  values before correction. No retries/skips. Screenshots t13-calendar.png,
  t13-details.png and t13-mobile.png inspected. Wide tables scroll within the
  mobile container; whole-page width assertion passes. Fixed workspace chrome
  appears in tall element captures; screenshots alone are not assertion proof.

Commands from web:
`npx vitest run src/__tests__/v2/CommercialEditorIndependent.test.tsx`
and `npx tsc --noEmit`.
Browser from tests/e2e:
`npx playwright test --config playwright.s21-local.config.ts s21-calendar.spec.ts --workers=1 --output=test-results/s21-t13-final`.
Earlier output directories `s21-t13-first` and `s21-t13-order` retain traces.

## Scope And Remaining Conditions

Real browser/API/PostgreSQL0061, local issued identities; existing guarded
source-fixture helper declares seeded SOW evidence, never live extraction.
Owned issued fixtures retained under provenance/expiry; no S3/provider/cloud
mutation and no cleanup claim. API205d51a unchanged; Vite serves bde6d29 UI.

All literal T13 clauses have local evidence: current ten-person/monthly oracle,
partial mixed-location browser/API persistence, holiday details, isolated missing
inputs and no mandatory aggregate-hours input. Full S21-15 retains calendar
registry/seeding, broader downstream/staging and frozen-version conditions.
