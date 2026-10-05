# T40 Approval Card: Local Connected Pass

2026-10-02. Tested application **205d51aadec743eb613fdb3ceb184520eacb79bb**.
Browser99369 exit0: **1 passed (47.3s)**, test40.5s. No retries/skips.

From `tests/e2e`:
```sh
npx playwright test --config playwright.s21-local.config.ts s21-approval-card.spec.ts --workers=1 --output=test-results/s21-t40-205d51a
```

| Original condition | Verified local business outcome |
| --- | --- |
| T40.01 | Initial card/list0; mixed fixture includes two in-review packages and excludes approved, draft and another actor's restricted package. |
| T40.02 | Card2 links to the canonical in-review board with the same population revision; exact two package IDs appear, and remain after reload. |
| T40.03 | Each package has five distinct reviewer assignments; ten assignments still count as two packages. |
| T40.04 | Both included SOW packages belong to the same deal and remain two distinct cards. |

Additional assertions: page sizes1 return exact two IDs and stable total2 on
pages1/2/3, third page empty, identical population revision throughout. A stale
zero-state revision returns409; browser renders no mixed cards, explicit Reload
loads the current exact two and clears the error. [Card screenshot](t40-card.png)
and [destination screenshot](t40-list.png) inspected. The synthetic assignment
fixture has blocked role eligibility on some functions; no approval transition,
real roster/mail, or signature success is inferred from this population test.
Unrelated Command Center Pipeline-value unavailable state remains outside T40.

Real local Vite5210/API8210/PostgreSQL0061, unique test identity. Guarded
`scripts/s21_approval_card_fixture.py` creates declared mixed-state rows only
under exact server-issued local fixture grants. Feature HTTP responses are real;
browser interception only supplies the local identity header. Five reviewer
identities are first provisioned through owned fixture issuance; `/me` alone
does not persist users. All local fixtures remain expiry/provenance-scoped;
no S3 objects, external providers, notification worker or staging data touched.

## Fix And Regression Evidence

- f9c0e97 ->619bc3d: canonical newest-nonvoided/live/authorized per-SOW population;
  two SOWs count twice, reviewer multiplicity never enters count. Worker18pass.
- cb53eb8: card opens approvals rather than Pipeline; board honors in-review
  scope and reads all pages. Initial UI50241 three red ->65575 three pass.
- Independent [QA](../../lanes/qa-t40-closure.md) found same-count revision mixing
  and first30 preview starvation; both repaired, statically rechecked at205d51a.
- 1e74402 ->7c984ab: actor/scope/full-population revision fence. Six added red
  cases ->24pass. Lead affected62974 **47pass25.72s**,
  [XML](approval-card-snapshot-api.xml). Equal-count replacement specifically
  returns409, unchanged pages preserve revision, other viewer/scope cannot reuse.
- 205d51a: shared full-population loader, card/page token propagation, explicit
  refresh, later-page preview preservation. UI61712 **5pass5.15s**, including
  100 newer Delivery packages plus an older CEO package and revision mismatch.
  TypeScript55907 exit0. Existing React Router/DOM-nesting warnings recorded,
  not suppressed or treated as runtime assertion failures.

## History, Not Current Failures

68277 atcb53eb8 failed setup422 for unpersisted reviewer identities, before UI.
Corrected registration76427 then passed all original T40 assertions26.4s.
Final99369 reran after snapshot repairs and additionally proves stale recovery.
Retained runner outputs are in separate `test-results/s21-t40-cb53eb8`,
`s21-t40-registered`, and `s21-t40-205d51a` directories; no raw console log file
is claimed. Missing query-type/test-shape TypeScript errors93428 were corrected
before65058/55907 green runs.

T40 **passed locally**; CO-04 implementation complete with this bounded scope.
CO-04 verification remains in progress until combined staging evidence. No
engineering-ready release, operational acceptance, PO approval or main deployment
is implied. S21-09 has additional unrelated conditions still outstanding.
