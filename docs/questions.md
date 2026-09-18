# Open questions

The lead answers these before the sprint that depends on them starts. Do not
guess. Each question names the sprint it blocks.

## Blocks Sprint 1

- [ ] **HubSpot edition, private-app scopes, sandbox URL.** Which HubSpot
  edition is licensed? Sandbox for staging? What scopes should the private app
  have? (Design: build-guide §11.)
- [ ] **Identity provider.** Entra ID or Google Workspace? Group name per role
  (Marketing, Sales, Presales, Delivery, HR, Finance, Legal, CEO, SystemAdmin)?
  (Design: build-guide §3.)
- [ ] **Build-guide §10 mirror.** The repo copy of `docs/build-guide.md` only
  contains the section list — §10 (data model) columns are not yet mirrored
  from the Claude Doc. Sprint 1 migration implements the columns named in the
  story files plus minimal skeletons for `client`, `legal_entity`, `agreement`
  (see `api/alembic/versions/20260917_0001_initial.py`). Mirror §10 and confirm
  or flag columns to add / rename. (Design: build-guide §10.)
- [ ] **`audit_event` DB grants in infra.** Migration adds a length CHECK on
  `row_hash` but the real append-only guarantee (no UPDATE/DELETE for the app
  role) must be granted in CDK/psql, not the app migration. Who owns adding
  that to `infra/`? (Design: blueprint §12.)
- [ ] **Task-to-opportunity linkage.** `task` has no `opportunity_id` column in
  the S1 schema (see `api/app/models/task.py`). The HubSpot intake service
  currently records the linkage inside `audit_event.after` (`opportunity_id`,
  `kind="intake"`) and reuses that trail for idempotency checks. Should the
  next migration add a proper FK column on `task`, or is the audit-only
  linkage the intended shape through S1? (Story: s1-e2.)
- [ ] **HubSpot v3 signed URI.** The v3 signature includes the full HTTPS URL.
  Behind the ALB the app sees `http://` and the internal host; the router
  reads `HUBSPOT_WEBHOOK_URL` to reconstruct what HubSpot signed. Confirm
  the staging/prod public URL and whether ALB will preserve query strings
  verbatim. (Story: s1-e2.)
- [x] **Opportunity → client linkage.** Resolved in S2-E3
  (`20260918_0002a_client_link.py`): `opportunity.client_id` is now a
  nullable FK to `client(id)` and `client.hubspot_company_id` carries the
  HubSpot company id (unique). The intake worker upserts a client + default
  legal entity on every event and falls back to a synthetic
  `unknown:deal:<id>` client when HubSpot returns no company. Still open:
  which sprint flips `client_id` to NOT NULL — see the new Sprint 3 question
  below. (Design: build-guide §10, §6.2.)
- [ ] **Cognito JWKS refresh + clock-skew + token type.** The verifier in
  `api/app/auth/cognito.py` caches JWKS in-process for 24h and enforces
  `exp/iss` with PyJWT defaults (no leeway). Confirm the 24h TTL is
  acceptable given Cognito's key-rotation cadence and whether a `leeway`
  allowance is wanted for clock drift across ECS tasks. Also: should the
  API accept both ID and access tokens, or only ID tokens issued to the
  SPA client? Current code accepts both. (Design: build-guide §3.)

- [ ] **GitHub OIDC provider in the AWS account.** Does account
  `669810405473` already have an IAM OIDC provider for
  `token.actions.githubusercontent.com`? If yes, keep
  `create_github_oidc_provider = false` in `infra-tf/dev.tfvars`; if no, flip
  it to `true` for the first apply only and then flip back. Also confirm the
  final GitHub repo slug (default in Terraform is `smartek21/officeapp-dealgate`).
  (Infra: `infra-tf/modules/github_oidc`.)
- [ ] **Custom domain / ACM cert for dev.** Terraform currently exposes the
  API on the ALB DNS over HTTP:80 and the SPA on the default `.cloudfront.net`
  domain. Confirm we are OK running dev like that (Cognito hosted UI is on
  HTTPS regardless) and, if not, pick a subdomain + Route53 hosted zone so a
  follow-up module can add ACM + HTTPS listener + custom CloudFront domain +
  matching Cognito callback URLs. (Infra: `infra-tf/modules/api`, `web`, `auth`.)

## Blocks Sprint 2

- [ ] **Alembic revision id collisions in the S2 wave.** Two S2 migrations
  (`20260918_0002_client_link.py` and `20260918_0002_rate_cards_policy.py`)
  originally shipped with the same revision id `20260918_0002`, so
  `alembic upgrade head` refused to run. They were rebranched as `0002a` /
  `0002b` with the `tasks_notifications` migration acting as the merge
  point (`0002b -> 0003`) and the new agreements migration on top
  (`0003 -> 0004`). Ask: agree the wave convention going forward is
  "one revision per PR, id includes the story letter" so parallel work
  cannot collide again. (Infra: `api/alembic/`.)

- [ ] **Agreements S3 IAM.** The `officeapp-<env>-agreements-<account>`
  bucket is created by `infra-tf/modules/storage`. The API task role also
  needs `s3:PutObject` + `s3:GetObject` on `arn:aws:s3:::<bucket>/agreements/*`
  so the pre-signed URLs sign under a principal that has those permissions.
  Wire the policy into `modules/api` after this story is merged; feed the
  bucket name into the API task's env as `AGREEMENTS_BUCKET`. Object Lock
  lands in a later sprint per build-guide §12 — flag if the WORM retention
  window is needed sooner. (Infra: `infra-tf/modules/storage`.)

- [ ] **Agreements state machine wording (Legal).** The S2 code encodes the
  transition graph in `app/services/agreement_state.ALLOWED_TRANSITIONS`
  drawn from build-guide §6.2. Confirm Legal is happy with the specific
  edges chosen — most notably that `superseded` is only reachable from
  `executed` and that `sent -> drafting` is allowed for a re-work loop.
  Docs mirror lives in the file docstring; blueprint §6.2 is silent on the
  precise DAG. (Design: build-guide §6.2.)

- [ ] **GM definition (Finance).** What is inside `delivery_cost`? Burden,
  bench, tools, travel, subcontractors, PM overhead — in or out? (Design: §7.)
- [ ] **Mixed fixed-fee allocation (Finance).** How is one fee split between US
  and India work — by work package, by hours, by an approved method? (Design: §7.)
  Current `fixed_price` template takes `revenue_us` / `revenue_india` as
  explicit inputs and validates only that they sum to `total_price`.
- [ ] **Rate cards v1 (Finance + HR).** Planning cost bands by role, seniority
  and location. FX convention (fixed at SOW date? monthly?). (Design: §7.)
- [ ] **Alert channel.** Teams or Slack, plus email? Webhook URL for the
  incoming channel. (Design: §9.)
- [ ] **PBU (paid-but-unbilled) time in staff-aug (Delivery + Finance).** The
  §7 line "PBU time" currently modeled as extra hours per resource that add
  to cost at `hourly_cost` and add zero revenue (holidays, ramp, absorbed
  PTO). Confirm this is the intended shape, and whether replacement
  obligation should add a bench-cost reserve rather than being a policy
  flag only. (Design: §7 staff aug.)
- [ ] **T&M cap treatment (Finance).** Current `tm` template scores GM at
  forecast hours; when a revenue cap is set below forecast, revenue is
  clipped to the cap while cost stays at forecast. Confirm this is the
  expected pessimistic view for approvals. (Design: §7 T&M.)
- [ ] **Managed service term basis (Finance).** GM computed over the full
  contracted term (`monthly_fee * term_months`) vs. steady-state month.
  Current library uses full term. (Design: §7 managed service.)

## Blocks Sprint 3

- [x] **Bedrock (Claude) model access for SOW extraction (S3-E5).** Story
  s3-e5 depends on Claude via Bedrock in the dev account and region.
  Verified 2026-09-17 via `aws bedrock list-foundation-models --region us-east-2
  --by-provider anthropic` — 13 Anthropic models listed, including
  `anthropic.claude-sonnet-4-20250514-v1:0`. The extract module
  (`api/app/integrations/bedrock_sow_extract.py`) currently ships with a
  `StubBedrock` for tests and a `BedrockSowExtract` placeholder that
  returns `ManualRequired`; the real `invoke_model` call lands in
  Sprint 3 wave 2. Confirm the exact model id + region the API task role
  should be granted `bedrock:InvokeModel` on before wave 2. (Design:
  build-guide §6.3, story s3-e5.)
- [ ] **Opportunity.client_id NOT NULL cutover.** S2-E3 landed the FK as
  nullable so historical rows (pre-intake-refactor) do not block the
  migration. The intake worker now sets it on every event, and the
  "Unknown company (deal <id>)" fallback means new rows are never
  unassociated. When Sprint 3 backfills historical opportunities from
  HubSpot associations, flip the column to NOT NULL and add a CHECK that
  no `unknown:deal:*` client is left over (i.e. every deal has a real
  HubSpot company id). Owner: this story (S2-E3) left the seam; Sprint 3
  runbook should carry the flip. (Design: build-guide §6.2.)
- [ ] **Client-owned mutation surface.** S2-E3 exposes only read endpoints
  on `/clients`. Sprint 3 needs to decide whether Sales-leader can rename
  a client / re-point its HubSpot company id, or if that stays SystemAdmin
  only (matches build-guide §3 read/write matrix). (Design: build-guide §3.)

## Blocks Sprint 4

- [ ] **CEO delegate policy and approval SLAs.** Named delegate window,
  business-day SLAs per approver role. (Design: §3, §4.)

## Blocks Sprint 6 / rollout

- [ ] **E-signature tool.** Manual upload for pilot; which tool afterwards
  (DocuSign, Adobe Sign, other)? Authorized signatories list. (Design: §6.7.)
- [ ] **Source for actuals.** Timesheets + cost system. CSV import for pilot;
  integration target after. (Design: §9.)
- [ ] **Executive sponsor and process owner.** Named owner of rate cards,
  approver changes, and failed integrations after go-live.

## Blocks first deploy

- [ ] **ECS migrate task family.** `.github/workflows/deploy.yml` assumes a
  standalone Fargate task family `officeapp-dev-api-migrate` exists in ECS
  alongside the service task `officeapp-dev-api`. Terraform (Agent G) needs
  to register both (same image, different command / entrypoint). Confirm
  the exact family names before the first deploy — or supply overrides. The
  workflow also expects `ECS_PRIVATE_SUBNETS` and `ECS_TASK_SECURITY_GROUPS`
  repo secrets for the one-off task's networking. (Design: build-guide §8.)
- [ ] **Cognito app-client redirect / logout URIs per env.** The deploy
  workflow pipes `VITE_COGNITO_REDIRECT_URI` and `VITE_COGNITO_LOGOUT_URI`
  from repo secrets, but per-env values (dev/staging/prod) need to be
  registered on the Cognito app client's allowed URL lists before the
  hosted-UI flow will complete. Owner: Agent G. (Design: build-guide §3.)

## Ambient

- [ ] **Search API for the adviser.** Tavily vs Brave — verify pricing and
  data-residency. (Design: §5, §11.)
- [ ] **Bedrock model access.** Which Claude models are enabled in the AWS
  account and region?
