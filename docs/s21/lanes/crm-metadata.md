# CRM Metadata Increment

Status: fixed and tested locally; not staging verified. Base `63ed085`, isolated
branch `s21/crm-metadata`. Owned service, new regression file and this report only.
Lead-owned model declaration and migration 0054 are unchanged.

## Behavior

- Validated property arrays, unique identities, required string fields and
  enumeration options. Malformed responses, forbidden access and transport
  errors persist `unavailable`, never `absent`, without storing exception text.
- Initial unobserved state remains schema-default `unknown`. Valid discovery
  persists `configured`, `absent`, or `ambiguous`; failed discovery persists
  `unavailable`. Checked and successful observation timestamps are distinct.
- Preserve S20 deal-first precedence, with company fallback only after a valid
  deal response containing no candidates. Multiple candidates within that
  object are ambiguous, not first-match selection. A bound company refresh
  does not depend on deal metadata access.
- A bound identity cannot silently change to a similarly named property.
  Removal or incompatible type is unavailable; identity, options, version and
  last-success time remain intact. Last-good evidence survives repeated errors.
- Canonical option ordering prevents provider array ordering from bumping a
  version. Changed labels/options/type/identity have version comparisons;
  normal discovery only changes labels/options for the existing identity.
- `DiscoveryResult` adds availability state/reason/version with defaults.
  The legacy getter returns only configured mappings, including refusing an
  unverified migrated `unknown` mapping until a successful refresh. Consumers
  requiring stale evidence must read the availability record, not that getter.
- Existing rows are locked during refresh; first-insert uniqueness conflicts
  and database failures propagate to the caller rather than masquerading as
  provider absence. Caller owns commit/rollback including sync-status writes.
- Material availability or metadata changes append hash-chained audit events
  in that transaction, with before/after state, version, identity/options,
  reason and discovery source. Scheduled discovery has no human actor.
  Unchanged refreshes do not generate configuration-change audit noise.

## Local Evidence

New tests were authored first. Initial focused run: **22 failures**, including
actual first-hit acceptance, malformed options acceptance, rebinding a missing
identity, missing availability persistence and missing version increments.
After the fix: **28 passed**, no skips, no retries (22 new plus six unchanged
S20 discovery tests). A lead-review follow-up added an audit regression first:
**1 failed** because zero audit events existed instead of four. After the
audit fix the combined focused run is **29 passed**, no skips/retries, including
hash-chain verification and rollback of both mapping and audit rows.
Tests use a provider transport fixture to test metadata
parsing and real SQLAlchemy writes in isolated in-memory SQLite; this is not
a live provider or integrated journey claim.

Exact successful command from this worktree:

```sh
env PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-metadata/api:/Users/srikanthparimi/OfficeApp/dealgate-s21-crm-metadata \
  /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest \
  api/tests/test_s21_metadata_availability.py api/tests/test_hubspot_property_discovery.py \
  -q -p no:cacheprovider --tb=short
```

Lead authorized read-only dependency reuse and the bounded test slot. No files
or dependencies in the QA worktree were changed, no cache/bytecode was written
there, and no shared database, provider, browser or cloud operations ran.

## Remaining Integration

S21-10/12 and CO07/08 remain incomplete overall: lead must connect explicit
availability reads/UI, source-value observation and owner identity, atomic
backfill and source metadata activation. An ambiguous portal needs authorized,
audited, expected-version selection against a fresh provider definition; no
selection entry point is added by this increment, and discovery does not
pretend ambiguity is resolved. PostgreSQL concurrent refresh/first-create and
real provider access scenarios remain independent verification gates.
