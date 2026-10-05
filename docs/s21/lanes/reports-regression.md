# Reports Regression

Owner: worker `s21/forecast-ui`; only Reports page, its test and this report.
No runtime, schema, other source files or deployment changes.

Exact initial reproduction: Reports.test.tsx, 5 failed / 1 passed, 13.43 seconds.
The old fixture stubbed four API calls although Reports now loads twelve. The
eight unstubbed calls triggered genuine load errors. Two export tests also
assumed Portfolio remained the default; S20 changed the default to Pipeline.

The unit fixtures now cover every current typed response and explicitly click
Portfolio before asserting exports. Existing kind/format/filename, invoice and
cash caveat, unsourced labels and turnaround assertions remain intact. The tab
test additionally requires six tabs, selected Pipeline and rendered rollups.
No production error swallowing was added to make these tests pass.

New independent semantic test exposed a real production defect: forecast_gp
and actual_gp were rendered as forecast revenue and recognized revenue.
After fixture repairs, 8 passed / 1 failed precisely on the wrong 98765.43
revenue value. The page now keeps revenue values unavailable until bound to
an authoritative revenue/recognition source. Finance gross-profit metrics are
not changed. Added tests also preserve explicit 503 failures and permission-
denied unavailability rather than inventing zero-valued aggregates.
The explicit 403 assertion also reproduced misleading "endpoint did not
respond" copy. Nullable rollups now say "Unavailable or restricted"; the
existing exception handling remains unchanged. The final whole-file suite
runs all nine tests, including the original five failing behaviors.

Final validation: 9 passed, no skips/retries, 9.82 seconds;
`npx tsc --noEmit` and `git diff --check` passed. No browser/staging acceptance
is claimed by these unit tests.

Pre-existing issues outside this bounded ownership remain open: generic
report exports default to a console-only handler, global filters do not flow
to report requests, and fetched approval-turnaround aggregates are not passed
to the child view. These are not closed by the regression fixture repairs.
