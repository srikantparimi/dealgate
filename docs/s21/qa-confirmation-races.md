# Independent Confirmation Race Proof

Authoring baseline: `8d4e5f43433758010fa5bd0f257bfcbaf2c50788`, isolated branch
`s21/qa-confirmation-races`. Owned additions are this report and
`scripts/s21_confirmation_races_pg.py`. Budget: approximately 20 minutes.
**Authored, not executed:** four concurrency cases; zero runtime cases run.
No Python/application imports, tests, database, migration, browser, installation
or cloud operation was performed by this QA authoring task. Application and
existing test files remain unchanged. Static diff checking is not a PG pass.

## Lead Run

After acquiring the serialized runtime slot, run from the integrated checkout
with the existing isolated API environment and loopback PostgreSQL server:

```sh
S21_CONFIRMATION_ADMIN_URL='postgresql+psycopg://s21@127.0.0.1:55421/postgres' PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api:. api/.venv/bin/python scripts/s21_confirmation_races_pg.py
```

The script imports safety helpers from the already validated
`s21_coverage_concurrency_pg.py`, without invoking its coverage proof. It retains
the guard/creation/migration/cleanup pattern with a distinct generated database
name `s21_confirmation_lock_<UUID hex>`. Only literal 127.0.0.1:55421/postgres,
the `s21` current/session identity and the psycopg admin driver are accepted;
URL query overrides, arguments and externally supplied target/drop names are
refused. Libpq PG environment overrides are removed. Application DSNs are set
to the new private database before application imports; environment is local.

The actual Alembic CLI upgrades that database, and its stored head must equal
the checkout's single migration head. Cleanup checks the exact generated name,
OID, owner and unpredictable marker. All tasks/sessions/engines close before
ordinary DROP; there is no FORCE, backend termination or shared database reset.
Ownership mismatch or an unexpected remaining connection fails visibly instead
of widening cleanup. PASS is printed only after successful exact-target cleanup.

## Four Independent Schedules

Each case uses distinct writer, contender and observer backend PIDs. Before
the writer commits, the observer requires the contender's exact application
name/PID, a Lock wait, an ungranted lock, the writer in `pg_blocking_pids`, and
a granted RowShareLock on `public.opportunity` while selecting that source.
This adapts the validated observer because the wide Opportunity SELECT may
truncate its trailing FOR UPDATE in `pg_stat_activity.query`; checking the
actual relation lock avoids depending on that suffix. It does not replace the
lock assertion with a sleep. Missing waits and early completion fail, without
retry. Observation and post-release completion each have 20-second deadlines;
database statements/locks have 30-second limits, proof 240 seconds, migration
300 seconds. A pending contender is cancelled and awaited before rollback.

1. **Scope completion versus replay.** Precache the original ORM version and
   parent in the contender. The writer runs actual same-document extraction,
   producing exactly one uncommitted price conflict while holding the source
   locks. Start actual `submit_confirmation`, observe its parent lock wait,
   then commit replay. Require 422 specifically naming `extraction_conflict:price`,
   one source version, no confirmation stamps/success audits and the complete
   retained conflict/evidence envelope.
2. **Legacy confirmation versus replay.** Same schedule using actual
   `submit_sow`. Require exactly `missing == ['extraction_conflict:price']`;
   missing unrelated fields cannot satisfy the assertion. One version, one
   committed failed-extract audit, no confirmation or resolution success audit.
3. **Ownership transfer versus conflict-review HTTP.** Begin with a valid price
   conflict and token, cache the old Sales owner's parent/version, then hold
   the parent lock with a replacement owner uncommitted. Start the actual POST
   route using that old owner. Observe the exact wait before committing the
   transfer; require 403, retained transferred ownership, unchanged values,
   unchanged conflict metadata and zero conflict-resolution/confirmation audits.
4. **New-version selection while confirmation waits.** Precache a fully scoped
   original version. Under the writer's parent lock, insert an honest ORM draft
   version 2 with a later timestamp, fresh extracted envelopes and missing
   currency. Prove its only scope blocker is currency. Start scope submission,
   observe the wait, commit the new version, and require the exact currency
   rejection. Neither version may be stamped; exactly those two version IDs
   must exist. This proves selection after the parent lock, not upload handling.

All seeds explicitly confirm every legacy field through the real service and
prove zero scope blockers before introducing the race. Literal assessment
dates, currency, scope, deliverables and signatories avoid unrelated gaps.
An assessment without staffing is valid for this scope-only boundary; financial
readiness is not asserted. Each race rereads persisted state in a fresh session,
checks exact source version identities, original setup audit counts and the
full audit hash chain. The adverse operation must never append a success audit.

## Provider And Fixture Boundaries

The existing synthetic DOCX bytes are parsed through the real document parser
and hashed by the real extraction service. `BoundaryProvider` supplies literal
synthetic extraction results; it is an external-provider boundary, not a mock
of extraction merge, locking, confirmation, authorization or an HTTP outcome.
The review request uses the real router with only authenticated-principal and
private-session dependencies injected into an in-process ASGI client. No live
Cognito, Bedrock, OCR, S3, HTTP server or staging accuracy claim follows.

The fourth case deliberately uses ORM version-2 insertion, agreed with the
lead, rather than hiding an unrelated creation defect. Static finding requiring
separate focused PG reproduction: baseline `sow_extract.create_sow_version`
constructs `SowVersion` without reserving an ordinal (`sow_extract.py:293`),
while `version_no` defaults to 1 and migration 0030 installs a unique
`(sow_id, version_no)` index. A second creation through that service appears
to collide. The lead's `12d9cd2` parent-lock change leaves the ordinal unchanged.
No test of that separate defect, upload API or all other version writers is
claimed here. Auto-GM transaction behavior is also outside these four schedules.

## Evidence Status

| Requirement slice | State | Evidence |
| --- | --- | --- |
| FC-09 / S21-18 / T16 / T24 replay and confirmation serialization | missing | Two authored real-PG schedules; lead execution required |
| FC-12 / T32 current owner authority at review commit | missing | Authored transfer/HTTP schedule; lead execution required |
| S21-03 / FC-09 current version selection | missing | Authored ORM insertion/selection schedule; upload writer boundary explicitly excluded |

The four static findings in the prior extraction review are not all covered:
UI token/draft rebinding and disputed nonempty currency have separate focused
test ownership. This proof does not establish whole requirements, all possible
interleavings, staging acceptance or permission to retire inherited xfails.
