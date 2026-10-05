# Independent Publication Service QA

Baseline: `656b0ac8e3f2b192f133dc158bbb8ab7b7426d85`, isolated branch
`s21/qa-publication-service`. Budget: 15 minutes. Only this report and new
`api/tests/test_s21_publication_independent.py` are owned. Production, existing
tests and migrations were read-only. Execution waited for the lead's runtime
grant; the slot was released immediately when pytest exited.

## Evidence

One bounded run: **33 passed, 4 failed, 2 warnings in 59.12s**, no skips or
xfails. New independent cases: **18 passed / 4 failed**. All 15 existing
publication cases passed. The warnings are existing FastAPI `on_event`
deprecations. No test assertions were changed after execution.

Exact command, from this worktree:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_publication_independent.py api/tests/test_s21_demand_publication.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-publication-independent
```

PostgreSQL variables were unset. Own in-memory SQLite fixtures enable foreign keys and persist real
actors/accounts. They call actual plan-save, managed-workforce-import,
publication and read services. One new case also calls the actual FastAPI router
over in-process HTTP, with only its DB dependency redirected to private SQLite
and the existing local authentication stub. No feature responses are mocked.

## Findings

1. **High: UUID aliases let one person claim two retained slots.** A valid
   imported workforce UUID is submitted once in canonical hyphenated form and
   once in hex form for a two-person assignment. Publication succeeds rather
   than rejecting the duplicate real identity. Projection checks distinct raw
   strings, then `_validate_continuity` silently collapses them into a UUID set
   and only compares that set with current supply. It never validates canonical
   distinctness within each demand line or canonicalizes the persisted links.
   Locations: `api/app/services/people_demand.py:42`, `:46`, `:59`, `:121`.
   This is within one quantity, not a claim that a person cannot cover two
   separate compatible half-time roles during later global matching.
2. **Medium: publication text can exceed its persisted schema.** A manual
   129-character level and a source-owned 129-character role both publish in
   SQLite rather than returning validation 422. Their columns are `String(128)`;
   PostgreSQL overflow is therefore a production-boundary risk, not an observed
   PG result from this worker. The service does not validate projected text
   lengths before inserting. Locations: input enrichment at
   `api/app/services/people_demand.py:25`, projection/insertion at `:98`, `:121`,
   and column limits at `api/app/models/people_demand.py:65`, `:67`.
3. **Medium, stored-data corruption boundary: source-hash drift is still
   labeled current.** After publishing a two-person source, the test explicitly
   injects stored component-input corruption changing quantity to seven while
   retaining the source version ID. Read returns `state="current"` instead of
   stale with no current lines. The recorded hash at
   `api/app/services/people_demand.py:109` is never checked by the freshness
   decision at `:156`. This is not an assertion that normal plan editing updates
   immutable versions in place; it tests fail-closed handling of detected
   identity/hash inconsistency. Normal append-only editing has a passing control.

Exact failing node suffixes, each prefixed with
`api/tests/test_s21_publication_independent.py::`:

```text
test_uuid_aliases_cannot_claim_two_retained_slots_for_one_workforce_person
test_publication_rejects_text_that_cannot_fit_its_persisted_schema[level]
test_publication_rejects_text_that_cannot_fit_its_persisted_schema[role]
test_same_version_source_hash_drift_is_not_reported_as_current_publication
```

## Passing Controls

- Replaying an old request after a new source version returns the original
  publication, with one publication audit, but does not restore current read
  freshness. Same-source enrichment appends history without mutating old lines.
- Allocation `0.123456789012345678901` round-trips exactly; headcount stays two.
  Stale source/publication CAS and cross-actor request-key reuse are rejected
  without new publication or line records.
- Historical-but-removed, foreign-tenant, and test-roster people cannot confer
  continuity in real demand. Foreign runtime tenant/environment cannot read or
  publish a known plan.
- HR/Admin receive named retained IDs; owned Sales, Delivery, Finance and CEO
  projections do not. No rate/cost/pricing fields enter the line projection.
- Incomplete source allocation remains unresolved null with an explicit reason,
  known headcount remains two, and missing location/skills/level remain visible.
  Current publication state does not claim complete staffing inputs.
- The actual HTTP router rejects a financial enrichment field with 422 and no
  persisted publication.

## Limits

No global capacity matching, reservation, hire, sourcing draft, retained-project
publication, live connector, browser or staging journey was exercised. The
UUID-alias finding concerns distinct retained identities, not allocation fairness
or future matching policy. No PostgreSQL locking/CAS/migration/downgrade proof
was rerun; the lead's separate proof is not counted as independent evidence.
Trusted fixture issuance/expiry, account deletion races, service crash recovery
and arbitrary SQL immutability enforcement were not retested in this increment.
Local auth does not prove live JWT authentication. These tests do not close
T22/T23 or FC-07/FC-08 acceptance. Lint was not run in the bounded runtime slot.
