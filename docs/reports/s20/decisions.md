# S20 · decisions log (autonomy = §0.7)

Every open choice tonight lands here, dated, with reversal notes. D1–D10
are fixed in the directive and not choices. This file grows as workers
integrate and the Lead applies patches.

Format: `## <id> · <one-line title> · <UTC timestamp> · <owner>` then:
- **Decision:** what was chosen.
- **Options considered:** the plausible alternatives.
- **Chosen because:** the reasoning.
- **How to reverse:** exact steps.

---

## D-ISO-01 · HubSpot token stays read-only for tonight · 2026-09-30 05:03 UTC · Lead

- **Decision:** Do not request `crm.objects.deals.write` for tonight's
  runs. Every worker treats HubSpot as read-only. J6 Playwright observer
  spec stays observer-mode; the S19 J6 team session tomorrow authors the
  deal in the HubSpot UI, not via the API.
- **Options considered:**
  1. Ask Kanna for a wider token overnight → violates autonomy, requires
     PO approval.
  2. Request a separate write-scoped token via a new private app → same,
     plus a token-rotation risk to the read-only path.
  3. Stay read-only tonight → **chosen**.
- **Chosen because:** The isolation guarantee (§5) is stronger with a
  read-only token. Every worker's tests already run against synthetic
  fixtures in staging RDS + Cognito; none need to mutate the portal.
- **How to reverse:** Kanna generates a private app with
  `crm.objects.deals.write`, drops the token into `dealgate/staging/
  hubspot_token_write` (separate secret). Nothing in code assumes this
  token exists; only the J6 creator path would use it.

## D-BRANCH-01 · integrate/s20 pushed to origin · 2026-09-30 05:00 UTC · Lead

- **Decision:** `integrate/s20` was pushed to origin so workers in
  separate worktrees can pull from a single collector branch.
- **Options considered:**
  1. Local-only integrate branch, cherry-pick from worker worktrees →
     works but doesn't preserve the "each worker has a real remote
     branch" review property.
  2. Push integrate/s20 + push each `s20/W*` when workers finish →
     **chosen**.
- **Chosen because:** Matches directive §2 ("workers in git worktrees on
  branch s20/W* off integrate/s20"). Kanna can inspect any worker's raw
  commits without asking the Lead to unpack them.
- **How to reverse:** `git push origin --delete integrate/s20 s20/W1
  s20/W2 …` after Kanna's click-through and (optionally) a squash-merge
  to main. Nothing is pinned to these refs long-term.

---

Workers append below this line as their scope surfaces choices.

## D-COG-01 · Multi-role Cognito approvers TF partition deferred · 2026-09-30 05:22 UTC · Lead

- **Decision:** Do not stand up 5 new Cognito users + `officeapp-dev-e2e-approvers` Secrets Manager JSON tonight. T27 (permissions uniform across surfaces) + T44 (12-step full journey with role hand-offs) stay `xfail` with reason "multi-role users pending TF slice"; every other test in the harness runs against the fallback smoke-bot user.
- **Options considered:**
  1. Create the users via `aws cognito-idp admin-create-user` + `admin-add-user-to-group` + `admin-set-user-password`, drop the JSON into Secrets Manager via `aws secretsmanager put-secret-value` — a rule-12 violation (Cognito state not in TF); reversible via delete but fights the same policy S20 is trying to reinforce.
  2. Write the TF module tonight in `infra-tf/modules/e2e-approvers/` and apply → adds ~30 min of TF work + a broader-drift apply during D5's controlled window; the approvers are not on the S20 critical path, and the Lead's D5 tonight already carries a 38-add/9-change/6-destroy drift context (`docs/directives/s20-terraform-drift.md`). Adding another module tonight compounds the risk profile.
  3. Defer to a dedicated multi-role TF slice + fall back to SystemAdmin smoke bot with a WARN → **chosen**.
- **Chosen because:** The smoke bot has every governance group (see `isolation.md` §Test-user tags), so functional coverage of the *state machine* still runs. What we lose is proof that role gating rejects the wrong role — which is a real gap and is captured in the matrix as `missing` with next action = "spin up TF slice S20-01a". Zero effect on the truthfulness of the morning matrix: T27 + T44 are marked `blocked` (multi-role approver secret) with owner Lead + next action.
- **How to reverse:** Write `infra-tf/modules/e2e-approvers/` per `requests.md::W5-02`, `terraform apply`, populate secret, run `tests/e2e/fixtures/multi-role-auth.ts` — `mintRoleTokens("delivery")` starts returning a Delivery-tagged token instead of the SystemAdmin fallback, xfails flip to real assertions.

## D-INT-01 · W5 integrates first because non-conflicting · 2026-09-30 05:20 UTC · Lead

- **Decision:** Merge W5 into `integrate/s20` immediately on receipt, before waiting for the other six workers.
- **Options considered:**
  1. Batch-integrate all workers at the end → matches the directive's ~2h cadence but leaves the harness sitting in a branch nobody else can see; W2/W3 don't get a chance to see the T-skeletons growing.
  2. Serialize alphabetically → arbitrary.
  3. Integrate as workers return, with priority for non-conflicting scopes (W5, W6) → **chosen**.
- **Chosen because:** W5's ownership is `tests/**` + `scripts/**` (non-deploy) + `docs/reports/s20/matrix.md, tests.md`. Zero overlap with any other worker's files. Merging W5 first surfaces the test scaffolding to the rest of the pipeline (Lead can now inspect what will need to flip from xfail to real) without delaying anyone. The directive says "every ~2 hours" — I read that as a maximum interval, not a mandatory batching.
- **How to reverse:** `git revert 5852098` on `integrate/s20`; W5's work stays on `origin/s20/W5` untouched.

