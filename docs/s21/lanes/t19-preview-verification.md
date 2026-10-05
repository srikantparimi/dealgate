# T19 Independent Persisted Preview Verification

Worker branch s21/t19-preview-verification starts at integration63aa55e, in the
isolated dealgate-s21-actual-coverage worktree. Earlier1fa7e23 confirmation branch
preserved. Exclusive ownership: scripts/s21_preview_verify.py and this report.

Executed once against loopback API8210 with the exact actor from
/tmp/s21-preview-ab7182f1.json. Only twelve sequential GET /forecast/outlook
requests; no mutation, direct DB access, worker, provider or cloud calls.
The sole output is an explicitly requested new exclusive local JSON artifact.
Physical source IDs and versions come from the original seed receipt; monetary
expectations come from independent scripts/s21_preview_inputs.py source literals,
not receipt expected values, production calculators or returned API aggregates.

Command:

```sh
PYTHONDONTWRITEBYTECODE=1 /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python scripts/s21_preview_verify.py --output /tmp/s21-preview-verification-ab7182f1.json
```

Session25684 exited0, passed. Artifact records every request, response hash,
source watermark, scenario/account results and exact physical fixture IDs.

Verified all12 sources and six accounts, all15 months October2026-December2027,
five quarters and three scenarios. Every source monthly revenue AND cost is
checked against literal source values with explicit independent Decimal scenario
weights. Every row preserves original source version, account, opportunity and
lifecycle. No unresolved, pending, excluded or stale rows. Two-future-quarter
totals: committed174000, Expected666400, Upside894400; four-quarter totals:
committed174000, Expected916000, Upside1230400. Current month208500.

All six account Expected future totals: Company X196000, Harbor163200,
Northstar51600, Atlas230400, Cedar25200, Meridian0. Company X signed assessment
remains24000 with14000 cost; modernization remains a separate420000 potential
source, never signed. Confirmed staffing cost does not duplicate PeriodCost.

Scope: local authenticated persisted financial read proof only, before connected
edits. Seeded signed prerequisites are not a new approval/signature proof; local
auth/synthetic source facts are not live CRM or staging proof. This does not close
T19's remaining UI edit, recomputation and reload conditions. Lead owns them.
