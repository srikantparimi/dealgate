# T05 Private Reviewer Planning Fixture

Worker authored only. Lead subsequently executed successfully96368/65311;
occupied-target refusal40419 passed, connected browser89032 passed and both
private databases were ownership-checked/dropped. See
[proof](../evidence/baseline/t05-reviewer-plan.md). Branch `s21/reviewer-plan-fixture`, baseafb0e5d.
Owns only `scripts/s21_reviewer_plan_fixture.py` and this report. No runtime,
dependency installation, provider, retained database or migration operation.

## Fixture And Safety

Requires explicit local environment, matching tenant and already-migrated private
database `s21_review_<32 lowercase hex>`, trust-only asyncpg user/owner s21 at
literal127.0.0.1:55421. Rejects PG overrides, URL options/password, alternate
targets and any existing business/group rows. Locks checked tables and verifies
actual connected database/user/owner and Alembic presence. Does not create,
comment, migrate, drop a database or start a server; only lead does those actions.
Services run inside savepoints under a single guarded outer seed transaction.
Failure must roll back the seed; successful retry refuses the now-nonempty tables.

Eight explicitly synthetic registered users have local-auth UUID5(email) IDs and
officeapp-e2e identity: owner/admin, Delivery primary/alternate, HR, Sales, Finance,
Legal and a nonmember. The nonmember belongs to the issued fixture's participants,
not approval groups and not ownership, so invalid reviewer selection and forbidden
submission test distinct boundaries. Delivery alternate also has HR role/membership,
with distinct defaults, enabling an actually eligible duplicate-person selection
to exercise separation of duties rather than only group-membership rejection.

Uses real `create_fixture` provenance and `save_group` services only in this empty
private database. One declared confirmed synthetic SOW is created without storage;
`file_s3_key` is empty and its hash identifies declared synthetic source text, not
uploaded bytes. GM is created through `create_gm_model_version`:100 US hours,
USD240 billed/hour, USD100 cost/hour, allocation1, zero contingency/warranty/direct
expenses. Independent expected revenue24000, cost10000, profit14000, above US35%
floor; no CEO required. No approval package, decision, assignment or task is seeded.

Manifest lists exact source versions, users/emails, function default/eligible IDs,
invalid UUID, baseline zero counts and expected real submission result after
choosing Delivery alternate: one package, five assignments, three active tasks
owned by alternate Delivery/HR/Sales, pending_delivery_hr. Other selection/submit
negatives expect422/403 with unchanged zero counts. Six reviewers remain distinct
people despite alternate eligibility in two functions. No mail delivery proof.
The independent five-assignment/three-task expectation matches
`approval_workflow.functions` and `active_functions` for routing policy2; table
names are `approval_package`, `approval_assignment` and `task`. The browser API
must use `DEALGATE_TEST_GROUPS=Sales,officeapp-e2e`, not SystemAdmin: otherwise
the local-auth override would invalidate the unauthorized-submit assertion.
Manifest top-level actor/unauthorized emails and IDs, opportunity ID, title/name,
reviewer IDs and Delivery alternative supplement the full eligible matrix.

## Invocation And Proof

Lead creates/comments/migrates a fresh database, then runs from repository root,
substituting the actual database name for `DB_NAME` below:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=DB_NAME \
S21_REVIEW_DATABASE_URL=postgresql+asyncpg://s21@127.0.0.1:55421/DB_NAME \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_reviewer_plan_fixture.py > /tmp/s21-reviewer-plan-manifest.json
```

No syntax or execution claim has been made. Lead must verify atomic seed, manifest,
real planned functions/eligible names, changed permitted choice, hostile API
requests with unchanged counts, real submit and reload frozen version/assignment/
task IDs. Current UI, server transitions and permission responses are never mocked.
T06 OOO/CEO, source extraction/storage, real mail/Cognito and staging remain separate.
Restore the lead API after the isolated browser run; never rewrite s21_journey groups.
