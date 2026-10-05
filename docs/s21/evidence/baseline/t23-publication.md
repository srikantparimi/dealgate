# T23 People Publication And Sourcing: Local Closure

Application23dffd923cb5435462fdc69e506f23cd9e171d68,2026-10-02 23:40UTC.
Strengthened admin88901 passed1/42.3s (39.1s test); Sales49160 passed1/10.2s
(7.7s test). Regression74987 passed44/13.17s, two existing lifecycle warnings,
no skips/xfails/retries. Independent QA agrees with the literal condition mapping.

[Browser](../../../../tests/e2e/local/s21-publication-boundaries.spec.ts),
[persisted proof](t23-publication-proof.json), [regression](t23-boundaries.xml),
[sourcing screen](t23-publication.png), [Sales screen](t23-sales-demand.png).

## Conditions

- T23.01/.02: actual publication and sourced draft/history, earlier S5 and
  connected94568 plus current browser on one PostgreSQL source.
- T23.03: API source revision Nov1->Dec1,US2->3,India5,Apr30end. Browser stale
  demand->republish->prepare/reload draft. Five exact months,8people/4FTE,
  2.5matched/1.5gap. US2people/1FTEgap and India1/0.5gap; October17/November1
  deadlines. Old version metadata, every demand_line and entire first draft
  remain unchanged. Original Nov2US/5India source independently asserted first.
- T23.04: existing94568 separate workers2/1/0 and replay0 establish no duplicated
  result; [mapping](connected-20261002-d.md). No new worker replay claimed here.
- T23.05: genuine Sales-only runtime, exact/megroups. Populated current demand
  and five-month allocation remain; financial inputs/named matches excluded.
  Fee187643.53,cost4317.29,bill293.17,costrate83.29 first confirmed in canonical
  PG inputs, absent from SalesAPI/UI. Recursive declared-field denylist and
  protected supply/history/sourcing403.44tests add other restricted roles and
  nested privacy cases; this is not a cost-empty fixture.
- T23.06: publication/draft reserve/hire/person_id/status extras422 with exact
  versions/audits/workforce counts unchanged. Successful planning also preserves
  workforce versions/intervals byte-equivalently. Absent reserve/hire routes
  return404/405; outputs not reservations. HR imports of observed reserved/hired
  commitments remain supported, not operational hiring commands.

Date/headcount edit is **API-authored**; current editor changes assumptions only.
Local auth adapter/synthetic data, not liveHR/Cognito/mail/staging. No whole
FC-07/08/10 promotion or broader source-event/financial acceptance inferred.

## Reproduction

From tests/e2e, fresh guarded fixture and matching Admin/HR/Delivery/e2e API:
```sh
S21_PUB_MANIFEST=/tmp/s21-pub-7084db58-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-publication-boundaries.spec.ts --grep 'T23 admin' --output test-results/s21-t23-admin-final --reporter=list
```
Stop ownedAPI; restart sameDB with DEALGATE_TEST_GROUPS=Sales,officeapp-e2e,
confirm/me200 exactgroups, then:
```sh
S21_PUB_MANIFEST=/tmp/s21-pub-7084db58-manifest.json npx playwright test --config playwright.s21-local.config.ts s21-publication-boundaries.spec.ts --grep 'T23 Sales-only' --output test-results/s21-t23-sales --reporter=list
```
From root:
```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api api/.venv/bin/pytest api/tests/test_s21_people_api.py api/tests/test_s21_sourcing_http.py api/tests/test_s21_sourcing_independent.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-t23-boundaries --junitxml=docs/s21/evidence/baseline/t23-boundaries.xml
```

## Isolation And History

Fixturea5642da integrated23dffd9 seeds source only. DBs
s21_pub_b46665b3836c473f9b04079e053fcc8f OID98872 and
s21_pub_7084db587194444889f4c8e1b7b2fe3f OID101109, owner s21, matching
owned-s21-t23:<suffix> comments, schema0061. Guard72095 refuses occupied target.
Owned APIs stopped/collected143; exactOID/owner/comment verified, DROPwithoutFORCE
succeeded for both, remaining0. Retained s21_journey unchanged/restored.
Manifests no longer reusable. Generated proofJSON is retained with this report.

13797 failed422 at malformed direct import: missing request_key/previous-batch
fields; zero imports/publications/drafts confirmed. Fixed request then56762
passed40.1s. QA strengthened Sales/immutable-line assertions, final88901 reran
on a fresh database. First failure retained in test-results/s21-t23-admin.
