# T17 Current Local Runtime

## Fresh Continuous Proof Runtime

2026-10-03 06:04UTC, application f74df880e8b1a718e0544accb8f9e1d32730d77c.
New owned DB `s21_t17_8d7c388a1eda40cfbe2a184eb00524ad`, marker
`owned-s21-t17:8d7c388a-1eda-40cf-be2a-184eb00524ad`; migration66180 and
seed62458 exited0. API8212 PID67824/session5667, Vite5212/session87713.
Receipt `/tmp/s21-t17-8d7c388a.json` and append-only `.operations.jsonl`.
Real storage prefix `verification/s21/8d7c388a1eda40cfbe2a184eb00524ad/`.
Grant077d27ff-2147-4d1d-95c1-4296aa458a6f expires14:00:24UTC.
Client0c6c2a52-329a-4fe4-b6b6-a92f525887fd, dealbd55ab45-63b1-4093-93b5-0ca8c6c45568.
Synthetic document `/tmp/s21-t17-8d7c388a-sow.docx`, SHA256
1a34d0c1872a930116f87429b5f8df72e4dd5126f2a00f2431319ef84ce01e65.
No business states preseeded; browser96337 is mutating this fixture. Never reseed
or blindly replay after interruption. API startup command below is identical to
the retained runtime except database/tenant/receipt names and `S21_T17_PORT=8212`.
Vite uses owner `t17-8d7c388a-owner@example.test`, proxy8212, port5212.
Browser command from tests/e2e:

```sh
env S21_T17_RECEIPT=/tmp/s21-t17-8d7c388a.json S21_T17_API_URL=http://127.0.0.1:8212 S21_T17_WEB_URL=http://127.0.0.1:5212 npx playwright test --config playwright.s21-local.config.ts local/s21-t17-connected.spec.ts --workers=1 --retries=0
```

Read `evidence/baseline/t17-8d7c388a-connected-browser.json`, operations receipt
and actual DB before recovering a stopped run. Local identity adapter/SES sink,
real S3/Bedrock: not deployed Cognito/email/staging proof.

## Retained Diagnostic Runtime

2026-10-03 05:47 UTC. Not staging. Integration branch feat/s21-forecast;
HEAD a612b717d4277cccf4588a96eb29b63fd283dbbf, application7cbdac7.
Route audit71535 passed1/4.7m; actual API isolation37013 passed8 checks.
Migration61217 completed0063 after graceful drain of old API51624.
Backup `/tmp/s21-t17-before-0063-a612b71.dump` retained on host and in DB
container (579 archive entries validated). Never replay seed or restore blindly.

## Owned State

- PostgreSQL in existing local container dealgate-s21-lead-db, literal127.0.0.1:55421.
- New database/tenant s21_t17_61d71c0b4bf7436d957723c632fe1aba, user/owner s21.
  Comment owned-s21-t17:61d71c0b-4bf7-436d-9577-23c632fe1aba. Migration73507
  originally completed0062; now0063. Seed90119 exited0 before browser mutations.
- Receipt `/tmp/s21-t17-61d71c0b.json`; append-only fsynced operations receipt
  `/tmp/s21-t17-61d71c0b.json.operations.jsonl`. Never rerun seed. Six registered
  named fixture identities plus normal nonfixture reader. Fixture expires12:01UTC.
  Client11ceb7d9-1693-49e8-9ab1-596a5d6e5941;
  deal0a66db62-3619-4762-a96e-afe1473864a9. Now one approved/signed/released SOW,
  projectaa26879a-826c-445f-9792-4a995039b409. Browser59018 uploaded NDA
  bf343bcd-ad81-4fa4-873b-ec381fab2597 (nowv2) and MSA
  9ddadfa2-bd3f-40b4-878a-89980c718b9e (v1). Three real objects recorded.
  Never rerun the zero-agreement upload test against this fixture.
- API8211 PID63663/session93220; Vite5211 PID44714/session93140.
  Prior API8210/PID32611 and Vite5210/PID22413 retained unchanged.
- Real S3 buckets officeapp-dev-sows-669810405473 and
  officeapp-dev-agreements-669810405473; every issued key is guarded under
  `verification/s21/61d71c0b4bf7436d957723c632fe1aba/` and recorded before PUT.
  Real Bedrock us-east-2, profile lm-arbiter-poc. Credentials remain in AWS profile,
  never copied here. Explicit local identity adapter/SES sink; not Cognito/inbox proof.
- Synthetic source `/tmp/s21-t17-61d71c0b-sow.docx`, SHA256
  7104c0fe8432aac30032689e0e8d89d6fe752bff0001b730826f08083561c0fc.
  Fixed subcontracted deliverable, October2026 US, revenue24000/cost10000/GM14000.
  No separate hourly workforce. Older unuploaded file without -sow suffix has a
  superseded client label; preserve but never upload it.

## Commands And Recovery

Run from integration root. Verify owned PID/listener before starting a duplicate.

```sh
env PYTHONPATH=api:scripts POSTGRES_URL=postgresql+asyncpg://s21@127.0.0.1:55421/s21_t17_61d71c0b4bf7436d957723c632fe1aba DEALGATE_ENV=local DEALGATE_TENANT_ID=s21_t17_61d71c0b4bf7436d957723c632fe1aba DEALGATE_REPORTING_TIMEZONE=America/Los_Angeles DEALGATE_REPORTING_CURRENCY=USD S21_T17_RECEIPT=/tmp/s21-t17-61d71c0b.json S21_T17_PROVIDER_CALLS=lead-authorized AWS_PROFILE=lm-arbiter-poc api/.venv/bin/python scripts/s21_t17_runtime.py serve
```

Frontend from web/:

```sh
env VITE_API_BASE_URL=/api VITE_TEST_USER=t17-61d71c0b-owner@example.test DEALGATE_DEV_API_URL=http://127.0.0.1:8211 npm run dev -- --host 127.0.0.1 --port 5211 --strictPort
```

Browser from tests/e2e/ (only while fixture still has zero SOWs; inspect receipts
and database after interruption, never replay mutations blindly):

```sh
npx playwright test --config playwright.s21-local.config.ts local/s21-t17-connected.spec.ts --workers=1 --retries=0
```

DO NOT run the zero-SOW test above against this mutated fixture. Core proof used
diagnostic continuations; repeat release49137 and route audit71535 now pass.
Remaining whole-scenario proof includes actual NDA/MSA presence/replacement,
fresh uninterrupted journey and exact deployed leak gate. Local adapter isolation
does not replace deployed Cognito verification.
Cleanup after proof must list/delete only exact recorded keys AND their versions;
do not delete a broad prefix, shared fixtures or any retained database.

## Diagnostic History

-60461 startup failed before listen: installed FastAPI lacks add_event_handler;
  on_event compatibility hook used;69953 startup succeeded.
-57446 read-only Pipeline failedfetch because initial Vite lacked VITE_API_BASE_URL.
  Owned43589 stopped after cwd/port verification;93140 uses same-origin /api.
-48132 reads actualPipeline1client/1deal;62393 navigates sameclient/deal, noSOW,
  uploadCTA visible. No feature mutations/provider calls in either browser probe.
-QA caught /tmp symlink comparison, bucket config mismatch and log symlink risk;
  fixed before relevant writes. Atomic final receipt write added after initial seed.
-Post-PUT uncertain DB-registration orphan recovery remains a separate production
  robustness gap. Real PG deletion/lock-wait races not yet verified; SQLite narrow
  ownership-change test is not claimed as PG concurrency evidence.
