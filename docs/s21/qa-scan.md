# Independent Source Scan QA

Reviewed revision: `1c5b24514576c2f01a79ba5022afa11092bca884` on `s21/qa-scan`.
Scope: source adapter/backfill and migration 0055 lease protocol, with T43
checkpoint/resume and duplicate/out-of-order source behavior in view.
Production and existing tests were read-only. Only this report and
`api/tests/test_s21_scan_independent.py` were added.

## Evidence

One bounded run, 2026-10-02: **29 passed, 9 failed in 14.49s**, with zero skips
and zero xfails. The 21 new independent cases contributed **12 passes / 9
failures**; all 17 existing checkpoint/lease cases passed. Ruff reported
`All checks passed!`. No assertions were changed after execution.

From the QA worktree, the exact test command was:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_scan_independent.py api/tests/test_s21_backfill_checkpoint.py api/tests/test_s21_scan_lease.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-scan-independent
```

Lint command:

```sh
env PYTHONDONTWRITEBYTECODE=1 /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/ruff check --no-cache api/tests/test_s21_scan_independent.py
```

## Findings

Node names below have the prefix `api/tests/test_s21_scan_independent.py::`.

1. **High: finalization can archive and publish success under an obsolete BU
   mapping.** `test_mapping_change_during_provider_io_cannot_complete_old_context[archive_evidence]`
   changes the mapping/version during the archive-evidence fetch. The old scan
   archives one row and completes with zero errors. Page I/O has a matching green
   control, but finalization only checks the persisted lease, not the current
   mapping. Locations: `api/app/services/hubspot_backfill.py:191`, `:195`, `:213`;
   compare the page guard at `:386`.
2. **High: an equal-version live source response resurrects an authoritatively
   archived record.**
   `test_obsolete_source_response_cannot_resurrect_authoritatively_archived_deal[2026-10-02T01:00:00Z-False]`
   archives via explicit provider evidence, then processes a property-change
   event whose fetched live snapshot has the exact pre-archive source timestamp.
   `archived_at` is cleared. Older snapshots remain archived and a strictly newer
   snapshot restores successfully (both green controls). The test requires newer
   source evidence for restoration; it does not prohibit legitimate restores.
   Locations: `api/app/services/hubspot_intake.py:95`, `:461`, `:609`.
3. **Medium: a nonadjacent cursor cycle commits another page and fetches the
   previously visited cursor again.**
   `test_nonadjacent_cursor_cycle_stops_before_fetching_a_committed_cursor_again`
   produces next cursors A, B, A. Observed calls are `[None, A, B, A]`, not
   `[None, A, B]`, and logs report three committed creates. A fourth-fetch safety
   exception bounds this test; without that boundary the cycle is not detected by
   the implementation. The last committed checkpoint should remain B rather than
   advancing back to A. Locations: `api/app/services/hubspot_backfill.py:127`,
   `:379`, `:396`.
4. **Medium: malformed source IDs become persisted identities and a successful
   scan.** Four cases of
   `test_malformed_deal_identity_cannot_be_coerced_into_a_persisted_source` fail:
   `[True]`, `[identity1]` (dictionary), `[identity2]` (list), and `[   ]`
   (whitespace). Each reports one create, zero errors, and completed true. The
   missing-ID (`[None]`) control passes. Converting arbitrary truthy objects with
   `str()` is not source-identity validation. Locations:
   `api/app/services/hubspot_backfill.py:95`, `:113`.
5. **Medium: an archived-owner endpoint failure is reported as a complete healthy
   scan.** `test_archived_owner_fetch_failure_is_not_a_successful_complete_scan`
   injects an exception only for `archived=true`; production logs the exception
   but reports zero owner/backfill errors and completed true. Source review shows
   the owner mirror also writes successful freshness after swallowing that error.
   Locations: `api/app/services/hubspot_owners.py:208`, `:213`, `:247`;
   `api/app/services/hubspot_backfill.py:338`.
6. **Medium: metadata failure before lease acquisition is absent from persisted
   scan freshness.**
   `test_metadata_failure_persists_failed_freshness_without_advancing_prior_success`
   first completes a scan, then fails pipeline metadata. The returned error count
   correctly prevents completion, and previous success is preserved, but the
   persisted backfill `last_error` remains null. The attempt is not recorded by
   this path either: metadata failure occurs before acquiring a lease, while
   failure persistence is conditional on having one. Locations:
   `api/app/services/hubspot_backfill.py:328`, `:364`, `:409`.

## Passing Controls and Limits

- No archive on 404, missing evidence, wrong evidence identity, string `"true"`,
  or explicit false; exact identity plus boolean true is accepted.
- Mapping replacement during page I/O is rejected. An expired lease replaced
  during page I/O rejects the old writer without poisoning the new owner's state.
- Absent partial source fields preserve the known name, owner, currency and exact
  Decimal amount; explicit null owner/currency clears those fields.
- Existing tests cover same-generation resume, page rollback, immediate repeated
  cursor, malformed page shapes, lease context/generation/expiry, and stale cursor.

New tests invoke actual backfill, lease, persistence and intake functions, with
synthetic provider responses only at the external transport boundary. They use
private in-memory SQLite and no patched production functions. The direct mapping
and lease mutations are deterministic interleavings, not concurrent PG proof.
This run does not establish PostgreSQL row-lock behavior, live CRM responses,
HTTP authorization, full tenant isolation, crash recovery across processes, or
staging/feature acceptance. The lead's separate PG lock/rollback-resume evidence
was not rerun or counted here. T43 remains broader than these boundary tests.

## Lead Remediation, 2 Oct 08:14 UTC

All independent tests retained unchanged. Persisted page audits now fence cursor
cycles across restarts; deal IDs are validated before writes; partial owner fetch
failure cannot advance freshness; pre-lease failures record errors without
poisoning another lease; finalization locks and rechecks the BU mapping; archive
restoration requires a strictly newer source version.

First combined run: 81 passed, 1 failed; see original QA counts above for the
exact new independent subset.
The failure was an older restoration fixture without source version evidence.
It now supplies explicit initial and later restoration timestamps, retaining all
business assertions. No production fence or independent assertion was relaxed.
Second combined run: **82 passed in 33.12s**, no skips or xfails, command:

```sh
cd api
.venv/bin/pytest -o addopts='' -q tests/test_s21_scan_independent.py tests/test_s21_backfill_checkpoint.py tests/test_s21_scan_lease.py tests/test_hubspot_backfill.py tests/test_hubspot_backfill_scan_generation.py tests/test_s21_source_adapter.py tests/test_hubspot_owners_mirror.py
```

Logs: `docs/s21/evidence/baseline/scan-qa-fixed.log` (failure preserved) and
`scan-qa-fixed-v2.log`. PG and separate-process proofs still need rerunning;
this is local remediation, not staging acceptance.
