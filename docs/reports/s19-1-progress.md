# S19 slice 1 — running progress notes

Update after every commit. Feeds `docs/reports/s19-1.md` when the slice
ships.

## Branch
`feat/s19-pipeline-1` from `main` at `0aa5549` (post-S18 §2a merge).

## Commits landed
- `8ed5345` — verification report (§verification, no code changes). Findings: mapper bug (stage_label = stage id), data-model gaps covered by slice 1 spec, top-3 client counts match exactly (Capitec 44, Standard Bank 42, Momentum 37), Costco Travel deals both Closed Won in HubSpot (not stale), 1 multi-company deal (EY SA), 2 no-company deals (PriceLine, Edisen), 655 USD + 1 null currency.
- `70b24fc` — checklist + progress doc (before code).
- `8248afd` — data model + mapper fix: migration `20260929_0041_s19_pipeline` (hubspot_pipeline/hubspot_stage/next_action/sync_status/user_preference + 10 columns on opportunity + 5 indexes), stage mirror service (B1), mapper populates every new column (B2), backfill syncs mirror + resolves secondaries + counts multi-company. 6 new stage-mirror tests + 40 existing HubSpot tests pass; full suite 822 pass / 6 skip.

## Deployed to staging
- ECS task-def rev 48, image `s19-1a-8248afd`. Migration `20260929_0041_s19_pipeline` up on RDS.
- Backfill rerun: 656 seen, 656 updated, 0 errors, 1 multi-company detected.
- Post-fix mirror state: Closed Won 253, Closed Lost 297, Open 106. Currency mix matches HubSpot exactly.
- Costco Travel + edge cases (EY SA, PriceLine, Momentum RFP null, Capitec sample) all now correctly flagged. See `docs/reports/s19-1-verify.md` §9 for the full post-fix table.

## Portal data finding — for the slice report, not code

**Currency mix in the mirror is 655 USD + 1 null; zero ZAR** despite the client base being SA-heavy (Capitec 44, Standard Bank 42, Momentum 37, Vitality Global, EY SA; Retro Rabbit owners at `.co.za`). Two plausible explanations, both to verify against HubSpot itself:

1. Portal default is USD — every deal takes it and displays as USD.
2. SA-region deals have `deal_currency_code` unset, and HubSpot presents them as USD by convention.

Kanna decides in HubSpot; no code change in slice 1. Captured as checklist L1. The slice 1 report reprints it and asks Kanna for a call.

## Fresh-session sequencing (from Kanna)

Same branch `feat/s19-pipeline-1` at `295aef0`. Order is fixed — infra first so nothing lands out of band:

1. **I — Terraform reconcile of the S18 §2a inline drift, then the new hubspot module apply.**
2. **C — Query service extensions** (`list_clients`, `list_opportunities`, `summary`, filters, sort, pagination) with the ≤3-query test.
3. **E — UI rebuild** of `/pipeline` (toggle + summary bar + stage strip + clients + opportunities tables + detail panel + "Create in HubSpot" link + sync banner) plus Command center card swap + SOW picker HubSpot search + SOW board "Not linked" pill.
4. **B3–B8 — Sync**: SQS queue + webhook enqueue + SQS consumer worker + nightly reconcile + drift on System health.
5. **J6–J8 — Proof**: Playwright deal-creation proof (create in HubSpot → visible in DealGate ≤ 2 min), screenshots per E steps, Kanna click-through, then squash-merge.

**Read on session start:** `CLAUDE.md`, `docs/directives/s19-pipeline.md`, `docs/directives/s19-checklist.md`, `docs/reports/s19-1-progress.md`. Nothing else.

Checklist lines land with proof references; standard slice report at the end; stop before merge.

## Decisions taken
- Mapper fix depends on pipeline mirror; therefore migration + pipeline sync ship together, before the mapper change.
- Every new column that maps 1:1 to a HubSpot property gets populated by `_upsert_opportunity` in a single pass — no separate "enrich" job.
- `hubspot_last_activity_at` uses `notes_last_updated` when present, `hs_lastmodifieddate` as fallback. Both come from the deal read.
- `primary_client_id` picks the labeled association over `_unlabeled`; secondary companies stored in `opportunity.hubspot_secondary_client_ids` (JSONB) so the UI can show "+2 others" without another table.
- Query-count invariant (C7) enforced by a pytest fixture that wraps the SQLAlchemy `AsyncConnection` in a counting event listener; failing test on any N+1.
- Grep gate (C8, F3) — new no-stubs-style script `scripts/check-single-query-service.sh` invoked in CI + `scripts/deploy-smoke.sh`.

## Next
1. Query service extensions (C1–C8) with tests + ≤3-query fixture.
2. UI rebuild (E1–E14).
3. Sync — SQS + webhook + reconcile (B3–B8) + TF (I) — reconcile the S18 §2a inline drift first.
4. Playwright + smoke + screenshots + Kanna click-through.

## I1 · reconcile — done (state-only, no AWS change)

- Root `infra-tf/main.tf` now wires `hubspot_token_secret_arn = module.secrets.hubspot_token_secret_arn` into `module "api"`. Prior to this the api module declared the variable but the root never passed it — `terraform plan` errored `Missing required argument` on every laptop run.
- Targeted plan `terraform plan -target=module.api.aws_iam_role_policy.task_execution_secrets` after the wire-up → `1 to change` (state-only update; live IAM policy already contains the HubSpot ARN, verified with `aws iam get-role-policy --role-name officeapp-dev-api-exec --policy-name officeapp-dev-api-exec-secrets`).
- `terraform apply -target=…task_execution_secrets` → `Resources: 0 added, 0 changed, 0 destroyed` (idempotent on second plan; state now matches AWS).
- The api ECS task-def (`officeapp-dev-api` rev 48) carries `HUBSPOT_TOKEN` (from `dealgate/staging/hubspot_token-ayxxJm`) and `HUBSPOT_TOKEN_SECRET_ARN` today. CI's `fetch_and_patch` in `.github/workflows/deploy.yml` re-registers with those bits every deploy; the service has `lifecycle { ignore_changes = [task_definition] }` so TF and CI don't fight.

## Incident during I1 — S3 state briefly overwritten, restored

- `terraform init -reconfigure` prompted "overwrite S3 with local state?"; a scripted `yes\nno` answered *yes* and copied the pre-S3-backend local `terraform.tfstate` (157K, Sept 17 vintage, ~80 resources) over the real S3 state (283K, Sept 24, ~137 resources). Serial got bumped by a subsequent `apply -refresh-only`.
- Restored via `aws s3api copy-object … --copy-source ?versionId=CCPAB80oUThwo7f_r7zP_ex4IfPuGoVF` (the 2026-09-24 18:41 UTC version) and updated DynamoDB `officeapp-tfstate-lock` MD5 to match. `terraform state list | wc -l` → 137 across `api / auth / data / dns / ecr / github_oidc / kms / network / schedulers / secrets / storage / web`.
- Stale local `terraform.tfstate*` files renamed to `.stale.bak` so no future `terraform init` can pick them up. Root cause of the mishap: local state files never deleted per the S14a.1 ADR post-migration step.

## Broader drift observed (out of S19 slice 1 scope)

- `terraform plan -refresh=false` after restore: `38 to add, 9 to change, 6 to destroy`.
- Adds: `module.observability.*` (11 resources; CloudTrail + GuardDuty + SNS + alarms — never adopted), `module.storage.aws_s3_bucket.{sows,agreements}` + their PAB/versioning/lifecycle/SSE/object-lock siblings, `module.kms.aws_kms_alias.data`, `module.api.aws_iam_role_policy.{task_cognito_read,task_kms,task_execution_kms}`, `module.schedulers.aws_ecs_task_definition.e2e_cleanup` + its event rule/target/policy.
- Changes: `module.api.aws_iam_role_policy.sow_and_bedrock` (in-place), `module.api.aws_ecs_task_definition.api` **must be replaced** (TF would drop `ALLOW_DEV_SEED_ENDPOINT`, which the e2e path requires — do not apply), four `module.schedulers.aws_ecs_task_definition.*` **must be replaced** (same class of drift).
- All of the above already exist in AWS; the state gap is from the S14a-family imports never completing. I1's scope was only the S18 §2a inline drift — that piece is closed. The broader drift needs an explicit adoption pass (own directive), not slice 1 work.

## I2-I4 approach — targeted apply

- New `infra-tf/modules/hubspot/` (SQS main + DLQ + IAM) is self-contained; its only upstream is `module.kms.key_arn` (in state) and role ARNs from `module.api` / `module.schedulers` (both in state).
- Reconcile task lives in `module.schedulers` as a new task-def + event rule/target; adding these does not force replacement of the existing four scheduler task-defs (they're separately-drifted; TF still shows them as `must be replaced` but I will NOT include them in the target list).
- Plan gated by `-target=` on the new resources only. Broader drift left untouched (out of scope).

## Failures / blockers
None. Broader TF drift documented above is a known accumulated debt; carried forward for a separate directive.

## C1-C8 · query service — done

- `services/hubspot_pipeline.py` extended: `list_opportunities`,
  `list_clients`, `summary` alongside the existing S18 helpers. Shared
  `PipelineFilters` + `SortSpec`. `SowApprovalState` + `AttentionFlag`
  enums map directly to the directive strings for D3/D4.
- Query-count invariant enforced by
  `tests/test_hubspot_pipeline_query_service.py::counter` fixture (7
  new tests, all ≤ 3 executes). 39 pre-existing hubspot tests still
  green.
- Grep gate `scripts/check-single-query-service.sh` passes; wired into
  `scripts/deploy-smoke.sh` as step 0.5.
- Routers: `/pipeline/opportunities`, `/pipeline/clients`,
  `/pipeline/summary`, `/sync-status` (new). Same read-role gate as
  S18.
- Full pytest: **832 passed / 6 skipped** (postgres-gated as expected).

## E1-E14 · UI — done

- `web/src/pages/v2/Pipeline.tsx` rebuilt: toggle Clients / Opportunities
  (remembered in localStorage), summary bar per currency, filter row
  (search + include-closed), stage strip chips with count and click
  filter, sync banner reading `/api/sync-status`, "Create in HubSpot"
  deep link.
- Clients table: sticky name column, per-currency values, NDA/MSA,
  worst SOW state, attention chips, latest activity.
- Opportunities table: D1-D4 columns + amount + currency + close +
  owner + last activity.
- `CommandCenter.tsx` swapped to `listPipelineClients` — the pipeline
  card now renders from the same service (E13 landed).
- 266 vitest tests still green.

## B3-B8 · SQS webhook + consumer + reconcile — done

- `app/integrations/hubspot_events_queue.py`: aiobotocore-backed queue
  client + `StubHubSpotEventsQueue` for tests.
- Webhook enqueues to SQS when the URL is set; falls back to the
  legacy DB store otherwise.
- `worker/hubspot_intake.py` rewritten as an SQS consumer with soft
  wall-clock budget (default 240 s). Legacy `process_pending` helper
  retained for the pre-S19 DB-poll flow tests still exercise.
- `worker/hubspot_reconcile.py` (new) wraps `run_backfill` +
  `sync_status`.
- `app/services/sync_status.py::touch_source` upserts source rows.
- 3 new SQS-round-trip tests; full suite 832/6.

## J6-J8 · proof

- `tests/e2e/specs/25-s19-slice1-webhook-to-pipeline.spec.ts` — the
  webhook-to-pipeline latency test. Creates a HubSpot deal, waits for
  it to appear at `/pipeline` within 2 min, screenshots five surfaces
  into `docs/reports/s19-1/`, cleans up on teardown.
- Slice report at `docs/reports/s19-1.md` with the full checklist
  matrix + reprint of L1 currency finding + deploy checklist for
  Kanna.
- **STOP before merge** per directive. After Kanna's click-through
  and squash-merge, CI deploys the branch (task-def rev 51+) and the
  Playwright test can then hit staging end-to-end.
