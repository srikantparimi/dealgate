# Command Center redesign evidence

Status at 2026-10-13 12:24 PDT: **owner-reported population defect fixed,
focused locally verified, and packaged in a reviewed staging plan awaiting
human approval**. The currently deployed candidate still contains the defect
described below. Authoritative branch
`feat/command-center-redesign`, worktree
`/Users/srikanthparimi/OfficeApp/dealgate-command-center-redesign`. No merge to
`main` is permitted before product-owner acceptance.

## Owner-reported closed-won defect

The deployed candidate treated every non-lost Stage-5-or-later HubSpot deal as
current work forever. That made an October 2025 Closed Won deal with no SOW or
active delivery appear in Accounts & engagements, Needs attention and the
Pipeline lifecycle count. The first incorrect boundary was
`list_command_accounts` / `build_command_overview` forcing
`include_closed=True, open_closed="any"` without a relevance rule. Weighted
potential also accumulated all open-deal amounts before checking the selected
financial period.

Fix `c606d763273ffa40379e4f4d39c8677e390045d5` keeps all open late-stage deals,
keeps current-period wins actionable, and keeps older wins only when a
non-closed engagement overlaps the selected period. Historical Closed Won rows
without that context are excluded from the account population, action queue,
lifecycle Pipeline count and recent activity. Potential revenue now includes
only open deals whose close date falls inside the selected financial period;
missing close dates remain incomplete instead of being assigned to a period.

| # | Acceptance condition | Local evidence | Staging |
|---|---|---|---|
| 1 | Stage 4 excluded; Stage 5+ included per ordered pipeline | Backend `test_stage5_is_resolved_per_pipeline_and_not_from_stage_ids`; connected Playwright sees Stage 5/6 and excludes Stage 4 | Deployed API/UI contract verified; owner-visible populated rows pending click-through because the staging test identity has no access to business accounts |
| 2 | SOW state does not affect sales-stage eligibility | `test_sow_governance_does_not_change_sales_stage_eligibility` | Deployed in API revision 109; populated owner-data assertion pending click-through |
| 3 | Per-pipeline threshold; unknown/unlinked/unconfigured rows excluded; gaps explicit | `test_unknown_unlinked_lost_and_unconfigured_rows_are_explicit` | Deployed and empty state verified; real pipeline rows/gaps pending owner click-through |
| 4 | Server search, filters, paging and CSV use one eligible population | Backend search/paging/CSV test; connected BU/owner filters and CSV download; unique opportunity IDs asserted | CSV and canonical API population pass through Cognito/CloudFront; populated paging/filter check pending owner data |
| 5 | Reset preserves visible Stage-5 constraint | UI unit and connected browser assertions | Verified on staging browser |
| 6 | Other dashboard populations are not Stage-5-restricted | `test_overview_keeps_stage4_in_its_population_while_accounts_do_not`; connected open value includes Stage 4 | Sections and independent endpoints verified on staging; populated owner values pending click-through |
| 7 | Actions and cards open owning records with return context | UI drawer destinations and connected deal-link assertion; router state carries `from` | Deployed; no authorized row exists for the bot to open, so owner click-through remains |
| 8 | Established financial/capacity services; missing data is unknown | Real forecast test independently verifies $90,000 - $26,400; missing-cost test; People allocation integration test; connected 62.5% GM | Correct unknown-source state verified on staging; populated owner financial/capacity values pending click-through |
| 9 | Independent loading/empty/error behavior | UI tests prove an overview failure keeps the table and a table failure keeps the overview; source gaps render explicitly | Settled empty state and source states verified on staging |
| 10 | Responsive, keyboard-operable layout and focus-contained drawer | Connected 390px containment, desktop/mobile screenshots, named controls, Radix Sheet Escape test | Desktop/mobile staging browser proof passed; populated drawer remains covered locally |
| 11 | Historical Closed Won rows do not dominate current work | `test_historical_closed_won_requires_current_delivery_context`; `test_overview_excludes_historical_wins_and_period_scopes_potential`; connected isolated API fixture contains one 2025 win and still returns only current Stage 5/6 rows | Pending deployment and owner re-check on the reported real record |

## Focused verification

```text
Ruff: clean
Changed backend: 11 passed
Frontend TypeScript: passed
Changed frontend: 5 passed
Production web build: passed
```

The prior connected Playwright evidence remains valid for the original
candidate. For this fix, the isolated API assertion passed with an actual 2025
Closed Won fixture present and excluded. The dev-browser run reached all
desktop business assertions but exceeded the unchanged 30-second budget during
the final Escape after a cold Vite transform; mobile passed. A production
preview attempt was stopped because production bundles correctly disable the
local test identity. Those unsuccessful approaches are preserved under
`tests/e2e/test-results/`; no timeout or assertion was weakened. The deployed
real-session check remains the required proof for this correction.

Connected local data is isolated in `dealgate_command_center`. The guarded
fixture `scripts/command_center_fixture.py` refuses any other database and
contains only synthetic HubSpot-mirrored records. The observed eligible table
contains exactly Stage Five Account and Stage Six Account; Stage Four Account
remains in the broader business pulse and is absent from the table. Financial
evidence shows $90,000 committed revenue, 62.5% GM and $224,000 weighted
unsigned potential. Workforce values remain explicitly unknown in this fixture
because it intentionally has no current demand or supply publication; focused
service coverage proves current publications populate required, allocated and
uncovered FTE without frontend calculation.

Artifacts:

- `docs/evidence/command-center/command-center-desktop.png`
- `docs/evidence/command-center/command-center-mobile.png`
- `api/tests/test_command_center_accounts.py`
- `tests/e2e/local/command-center-redesign.spec.ts`

## Staging candidate

The current fix candidate is application commit
`c606d763273ffa40379e4f4d39c8677e390045d5`, packaged as immutable image
`officeapp-dev-api:ccfix-c606d76` with ECR digest
`sha256:c84f1f49a62b5b2b3d7e859cf26926ea11dab97a655f3e4b0a74bccf1d69f980`.
The matching production SPA build contains `assets/index-BPc0sdEg.js` and
`assets/index-CZ_B4MrY.css`.

The saved whole-root plan is `/tmp/ccfix-c606d76.tfplan`: **12 to add, 14 to
change, 12 to destroy**. It contains only the expected application-image
rollout: eleven ECS task-definition replacements plus the migration trigger,
the API service reference, nine EventBridge task references and four RunTask
policies. Every task image moves from `cc-eac3ee1f` to `ccfix-c606d76`. No RDS,
S3, Cognito, SES, KMS, VPC, security-group, CloudFront or DNS resource changes
are present. The API task also shows only AWS-provider normalization of omitted
empty arrays and `hostPort` defaulting to `containerPort`; its environment and
secret references are unchanged. There is no new migration file, so the
migration task is expected to confirm head `20261013_0067_import_key`.

| Artifact | SHA-256 |
|---|---|
| `/tmp/ccfix-c606d76.tfplan` | `945741933d94bd7ca9c28beb53946ddc6db65891efc9ea3f6296f62595a51524` |
| `/tmp/ccfix-c606d76.plan.txt` | `491c47a9b18968b17e52991f03ebd828ea9ba279edf8ecce48da900bc59dfa62` |
| `/tmp/ccfix-c606d76.plan.json` | `2a790fa475612f32a914914e593ee00e74afa04b5e3fbcdbb0af4eb99ed0b440` |

This plan has **not** been applied. Required human action: approve this exact
staging Terraform plan. The authorized apply command after approval is:

```bash
cd /Users/srikanthparimi/OfficeApp/dealgate-command-center-redesign
env AWS_PROFILE=lm-arbiter-poc AWS_REGION=us-east-2 \
  terraform -chdir=infra-tf apply /tmp/ccfix-c606d76.tfplan
```

### Previous deployed candidate

The identifiers below describe the **previous candidate and do not contain
`c606d76`**. They are retained as deployment history, not current-fix evidence.

Application revision: `eac3ee1faec7a55209a37907a6332c29b2d7714b`.

- API and worker image:
  `669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api:cc-eac3ee1f`
- ECR digest:
  `sha256:30421cd6b245a98b41de3cf4defe0a1ed52e9c93660e41913b7c3c2dc0f97cdf`
- Exact SPA assets: `assets/index-ezj6RfOC.js` and
  `assets/index-CZ_B4MrY.css`
- Saved Terraform plan: `/tmp/cc-eac3ee1f.tfplan`
- Plan result: `12 to add, 14 to change, 12 to destroy`
- Plan SHA-256:
  `18f777d8aa273e454eec783ad504418392f5f28e8479b9528cc3663ac1d1ed49`
- Human-readable plan SHA-256:
  `b73cbd2094a9ba7e33ef760e394526e439a16a690febc1b3498208fc74c43272`
- JSON plan SHA-256:
  `cfcce2e3dd5b9c51f155ec1881cf06a9c502e44fc53777553fe77c50ea84285a`

Plan review found only the expected application-image rollout: 12 ECS task
definition replacements, the ECS API service reference, nine EventBridge task
references, four run-task IAM policies and the migration trigger. Every task
moves from `s22p5main-3598e3bf` to `cc-eac3ee1f`; container environments and
secret references are unchanged. The plan contains no RDS, S3, Cognito, SES,
KMS, VPC, security-group, CloudFront or DNS changes and no business-data
mutation. Migration execution is retained but the application has no new
migration file, so it is expected to confirm the existing head
`20261013_0067_import_key`.

## Staging verification

- Approved plan applied exactly: `12 added, 14 changed, 12 destroyed`.
- Migration task `officeapp-dev-api-migrate:47` succeeded and retained head
  `20261013_0067_import_key`.
- API service is stable at `officeapp-dev-api:109`, running image digest
  `sha256:30421cd6b245a98b41de3cf4defe0a1ed52e9c93660e41913b7c3c2dc0f97cdf`.
- All nine scheduler families and the migration family resolve to image tag
  `cc-eac3ee1f`.
- SPA publish serves `assets/index-ezj6RfOC.js` and
  `assets/index-CZ_B4MrY.css`; CloudFront invalidation
  `I9MYXPKZC97AFCOKXFVSB7E1XH` completed.
- Deploy smoke `smoke 20261013T183350Z` passed upload, extraction, listing,
  teardown and the final zero-leak gate.
- Deployed Command Center Playwright: 2 passed, plus a focused desktop
  evidence recapture: 1 passed. It verifies Cognito, CloudFront, API 200s,
  the exact Stage-5 label, unique opaque row IDs when present, navigation,
  settled empty state, filters/reset, CSV headers and mobile containment.
- Post-apply Terraform detailed-exitcode is 0: **No changes**.
- Staging screenshots:
  `docs/evidence/command-center/command-center-staging-desktop.png` and
  `command-center-staging-mobile.png`.

The test identity is intentionally isolated from product-owner business
accounts, so it currently receives zero eligible rows. The server-issued
fixture endpoint cannot be converted into a mirrored HubSpot row: its runtime
scope explicitly rejects any fixture with a HubSpot company/deal identifier.
Populated real-account proof therefore remains a product-owner click-through,
not a skipped or weakened automation assertion.

## Remaining release gates

1. Product-owner real-data click-through and explicit acceptance.
2. Only then merge to `main` and verify the resulting main-image deployment.
