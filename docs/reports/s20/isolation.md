# S20 · staging isolation verification (Hour 0, Lead)

Per directive §5: every resource that would be written by tonight's workers
is confirmed to be a staging resource, or the resource is a hard block for
writes until confirmed.

Run: 2026-09-30 04:57 UTC (~ 21:57 Pacific, Sep 29).
Verifier: Lead (from AWS profile `lm-arbiter-poc`, account 669810405473,
region us-east-2).

## Resource inventory

| # | Resource | Identifier | Confirmed staging? | Evidence |
| --- | --- | --- | --- | --- |
| 1 | RDS Postgres | `officeapp-dev-db` @ `officeapp-dev-db.cnuuizqvet2v.us-east-2.rds.amazonaws.com` · DB `dealgate` · single-AZ · storage encrypted | ✓ | `aws rds describe-db-instances` matches TF module `data`; the name-prefix `officeapp-dev` is our staging convention (ADR 0001) |
| 2 | SQS queues | `officeapp-dev-hubspot-events` + `officeapp-dev-hubspot-events-dlq` | ✓ | `aws sqs list-queues --queue-name-prefix officeapp-dev` returns only these two; no `prod` prefixes exist on this account |
| 3 | S3 buckets touched by workers | `officeapp-dev-sows-669810405473`, `officeapp-dev-agreements-669810405473`, `officeapp-dev-audit-exports-669810405473`, `officeapp-dev-web-669810405473`, `officeapp-tfstate-669810405473` | ✓ | `aws s3 ls`; no `dealgate-prod-*` or similar |
| 4 | Cognito user pool | `us-east-2_VV03Ir8AF` · name `officeapp-dev-users` · domain `officeapp-dev-405473` | ✓ | Pool holds 4 tagged test users (`e2e-staging@…`, `srikanthp+ceo@…`, `srikanthp+approver-delivery@…`, `srikantp@…`); no production pool exists on this account |
| 5 | SES | `Enabled: true`, `ProductionAccessEnabled: false` (sandbox) | ✓ (sandbox) | `aws ses get-account-sending-enabled` + `aws sesv2 get-account`; only verified recipients receive |
| 6 | HubSpot token | `dealgate/staging/hubspot_token` (Secrets Manager); scopes = read-only | ✓ (read-only proved) | `GET /crm/v3/owners` → HTTP 200; `POST /crm/v3/objects/deals` → **HTTP 403** with `crm.objects.deals.write` scope missing (see §Findings below) |
| 7 | Test-data cleanup targeting | `worker/e2e_cleanup.py::_PREFIX_RE` matches `s1[2-9]-`, `S1[2-9] e2e `, `smoke `, `Peppermill Casino (smoke fixture)`, `S17 e2e `, `S17 delete-everywhere`, `Peppermill Casino's, LLC` (case-insensitive) with 24 h age gate | ✓ | Untagged clients (e.g. `74 Sky`, `Capitec Bank Limited`) cannot match; `_MIN_AGE = 24h` prevents in-flight-run collisions |
| 8 | ECR repo | `669810405473.dkr.ecr.us-east-2.amazonaws.com/officeapp-dev-api` | ✓ | The only api repo on this account; no `-prod` sibling |
| 9 | ECS cluster / services | `officeapp-dev-cluster`; api rev 51 running `s19-1-fbee5b8`; seven scheduler task-defs | ✓ | matches TF state |
| 10 | KMS CMK | `officeapp-dev` (alias); ARN `arn:aws:kms:us-east-2:669810405473:key/54e90f8b-…` | ✓ | referenced by every SSE resource above |

## Verdict

All ten resources confirmed staging. **No hard block on writes** from
isolation.

## Findings surfaced during isolation

**F1 (informational) · HubSpot token is missing `crm.objects.deals.write`.**
The probe POST to `/crm/v3/objects/deals` returned HTTP 403 with:
> requiredGranularScopes: ["crm.objects.deals.write", "crm.schemas.deals.write", "crm.obj…"]

This is *good* for read-safety tonight: no worker can accidentally mutate
the HubSpot portal. It also means tomorrow morning's J6 team session (from
S19 slice 1) cannot use `POST /crm/v3/objects/deals` from the Playwright
observer spec's creator path either — the deal has to be created by a
human in the HubSpot UI. Recorded in `decisions.md` under D-ISO-01 for
the morning report.

**F2 (informational) · single-AZ dev RDS.** The directive's A8 flags this
as a production-readiness item. Confirmed here; not a tonight block.

## Test-user tags

Cognito users authorized to hit staging tonight:
| Username | Email | Role groups |
| --- | --- | --- |
| `112b05a0-…` | `e2e-staging@smartek21.com` | SystemAdmin + every governance group (smoke bot) |
| `213b15a0-…` | `srikanthp+ceo@smartek21.com` | CEO, SystemAdmin |
| `b16b8540-…` | `srikanthp+approver-delivery@smartek21.com` | Delivery |
| `f1db1580-…` | `srikantp@smartek21.com` | SystemAdmin (Lead's PO account) |

Workers use `officeapp-dev-e2e-user` from Secrets Manager for staging
Playwright; `officeapp-dev-e2e-approvers` for the multi-role approval path.
No other Cognito users exist on this pool.
