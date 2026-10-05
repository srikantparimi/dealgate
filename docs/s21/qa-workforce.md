# Independent Workforce Import QA

Baseline: `70d7d2a038f4408e2f8a4e6cb6308950106633f4`, branch
`s21/qa-workforce-import`. Budget: 15 minutes. Only this report and new
`api/tests/test_s21_workforce_independent.py` were added. Production, migration,
and existing tests stayed read-only. Test execution waited for the lead's
serialized runtime grant.

## Evidence

One bounded run on 2026-10-02: **35 passed, 5 failed in 9.33s**, zero skips and
zero xfails. The 26 new independent cases contributed **21 passes / 5 failures**;
all 14 existing import tests passed. No assertions were changed after execution.

Exact command from this worktree:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_workforce_independent.py api/tests/test_s21_people_imports.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-workforce-independent
```

Own fixtures use in-memory SQLite with `PRAGMA foreign_keys=ON`, real persisted
actors, actual validation models, and actual import/read/history services.
There are no feature/API/provider mocks. PostgreSQL environment variables were
unset, pytest cache and bytecode were disabled, and no DB server was accessed.
`git diff --check` passed; lint was not run in the bounded runtime slot.

## Findings

1. **Medium, backend-independent: availability serialization rounds exact
   allocation under ambient Decimal precision.** Importing `0.125`, then reading
   availability inside `localcontext(prec=2)`, returns `"0.12"` instead of
   `"0.125"`. The test changes no production function. The serializer calls
   `normalize()` before fixed-format output; normalization is arithmetic under
   the current context, not a lossless formatting operation. The normal default
   context can similarly round sufficiently long coefficients even when
   PostgreSQL stores the original exactly. Location:
   `api/app/services/people_planning.py:215`.
2. **Medium, SQLite-specific persistence parity: accepted exact fractions are
   silently truncated or become zero on the local service path.** Literal input
   `0.123456789012345678901` reads as `"0.123456789"`; positive
   `0.000000000001` reads as `"0"`. These are not display expectations derived
   from production: each oracle is the exact submitted Decimal string. The
   unconstrained `Numeric()` mapping uses SQLite's non-exact numeric behavior
   and the driver's default fractional return scale. This does **not** establish
   that PostgreSQL has the same storage defect. The lead separately reported
   exact 28-digit PG persistence; that proof was not rerun or counted here.
   Locations: `api/app/models/people_planning.py:89`,
   `api/app/services/people_planning.py:180`, `:215`.
3. **Medium: source observations accept numeric values without the required
   explicit timezone.** Integer `0` and float `1000000000.5` both pass
   `WorkforceImportInput` rather than raising validation errors. Pydantic's
   permissive datetime conversion gives these values a timezone before the
   after-validator sees them, bypassing the raw-input explicit-timezone
   requirement. This also leaves epoch-unit interpretation to coercion instead
   of a declared source contract. Locations:
   `api/app/services/people_planning.py:87`, `:99`.

Exact failing nodes, each prefixed with
`api/tests/test_s21_workforce_independent.py::`:

```text
test_exact_fraction_survives_managed_import_and_named_source_projection[0.123456789012345678901]
test_exact_fraction_survives_managed_import_and_named_source_projection[0.000000000001]
test_serialization_is_not_rounded_by_the_callers_decimal_context
test_source_observation_requires_explicit_timezone_not_numeric_epoch_coercion[0]
test_source_observation_requires_explicit_timezone_not_numeric_epoch_coercion[1000000000.5]
```

## Passing Controls

- Full-source replacement omits missing people; later reintroduction reuses the
  stable person ID. Three batches retain four historical person versions. A
  delayed identical first-request replay returns the first batch without making
  it current again. History pagination preserves the literal total of three.
- An explicit empty snapshot removes only that source's current roster and does
  not remove another source or historical versions. Named people retain the
  correct source and batch reference.
- Old source observation, old predecessor, conflicting request reuse, and future
  observation are rejected; after rollback the prior batch remains the sole
  current/history entry.
- Sales, Delivery, Finance, CEO and Legal are denied imports, named availability,
  and history. Real and test actors cannot read each other's supply/history.
  Identical source/request keys in another tenant or environment create isolated
  batches. These are trusted-principal service tests, not authentication proof.
- An invalid second person rejects the entire input before partial persistence.
  Float allocations, net-availability basis, requested test provenance, injected
  account scope, cost-rate fields and overlapping gross intervals are rejected.

## Boundaries Not Claimed

Workforce named supply is HR/SystemAdmin scoped at the tenant/environment level;
this contract does not make it account-filtered. Rejecting injected account IDs
does not prove downstream account-restricted demand projection. Current tests
do not exercise hostile authentication, real HTTP/router behavior, test identity
issuance, import-size limits/extreme exponents, PostgreSQL locking/CAS, migration
parity, worker replay, UI, or global demand consumption of imported commitments.
They do not prove immutability against arbitrary direct SQL mutation. Historical
retention here is through supported append-only import operations.

The lead's separate PG lock/CAS/migration proof is separate evidence, not an
independent run by this worker. No cloud, staging or whole-feature acceptance is
claimed. T22/T23 and FC-07/FC-08 remain broader than these boundary tests.

## Lead Remediation, 09:08 UTC

All 26 independent cases are unchanged. ExactNumeric retains PostgreSQL NUMERIC
and uses exact text only for local SQLite round trips; numeric range constraints
cast explicitly on the local representation. Serialization uses exact formatting
without ambient-context normalization. A before-coercion validator rejects epoch
numbers, preserving the explicit timezone contract. Allocation strings are
bounded and accept at most28 fractional places without rounding. HR availability
also returns the stable external person key for source reconstruction.

Combined independent/import/API/storage/new demand-schema selection: **67 passed
in23.75s**, zero skips/xfails; includes all five original failures and10 newly
authored demand schema cases. Log people-qa-schema-fixed.log. Renew PG parity and
connected import proof after this change before claiming those gates. Existing
PG proof on prior code preserved28digits and refused concurrent stale revisions.
