# T39 Watching: Local Connected Pass

Recorded 2026-10-02 19:35 UTC. Tested application revision
`941953ab65d3621224906a5bdbe554fd09daa9aa`; later `3573130`/`3109012`
only add condition reports. Session46207 exited0: **1 passed (1.3m)**.
Persistent runner result: `tests/e2e/test-results/s21-t39-941953a/.last-run.json`
has status passed and no failed tests. Console output was not saved as a raw log.

From `tests/e2e`:
```sh
npx playwright test --config playwright.s21-local.config.ts s21-watching.spec.ts --workers=1 --output=test-results/s21-t39-941953a
```

The original T39 assertions all pass through real browser, API and PostgreSQL:

| Condition | Verified outcome |
| --- | --- |
| T39.01 | Empty Command Center Watching card0; destination Opportunities(0); API exact empty set. |
| T39.02 | Same deal belongs to three private groups; browser star produces count1; combined group/watch API returns exactly one deal. |
| T39.03 | Card1 opens destination with exactly one visible row whose ID equals the watched deal, not merely a formatted count. |
| T39.04 | Browser unstar persists; API exact empty set/count0, card0 and destination0 with no deal rows. |
| T39.05 | Another actor's fixture cannot be watched or retrieved (404); it is absent from exact API population and browser rows. |

Actor `s21-t39-24c90843-e223-4979-9e5a-e0086c55fb55@example.test`;
authorized deal `7bd5882a-157f-4dce-b00e-e53cf244fd5c`.
Identity headers use the local adapter; request interception only adds identity,
never substitutes feature responses. API8210, Vite5210, retained local
`s21_journey` PostgreSQL0061. This is not Cognito or staging proof.
Finally removes the watch and archives all three owned groups; issued local
fixture rows remain under their provenance/expiry controls. No cloud objects.

Screenshots inspected: [card1](t39-watching-one.png),
[destination1](t39-watching-list.png), [destination0](t39-watching-empty.png).
They supplement assertions, not replace them: the destination1 row is below
the captured viewport; destination0 captures a transient loading label.
The card screenshot also shows an unrelated Pipeline summary unavailable state;
this pass does not certify the whole Command Center or Pipeline financial totals.

## Fixes And Historical Failure

`9f23cb4` scopes watch identities/access and counts distinct matching deals;
`941953a` prefilters candidate fixture grants before full latest-grant validation.
Affected API run53674: **54 passed (31.65s)**,
[XML](watching-api.xml). Existing invalid-grant cases remain enforced.
Browser6428 at9f23cb4 failed initial readiness; instrumentation62174 reproduced
12 irrelevant grant checks. The candidate filter fixes that diagnosed cost.
No retries or assertion timeout increases were used to obtain the pass.
Earlier failed trace is retained locally at
`tests/e2e/test-results/s21-t39-9f23cb4`; it is history, not the current T39 result.

T39 is **passed locally**. Combined staging verification and product-owner
acceptance remain outstanding. S21-09/S21-14/DG-01 retain other unmet conditions;
this scenario does not close those parent requirements.
