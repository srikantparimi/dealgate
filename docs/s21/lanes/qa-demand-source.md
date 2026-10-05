# Independent Demand Source QA

Baseline: `eda73004cb367a08da277163349071fcfca9765e`, branch
`s21/qa-demand-publication`. Budget: 15 minutes. Only new
`api/tests/test_s21_demand_source_independent.py` and this report are owned.
Production and existing tests stayed read-only. Authoring preceded the lead's
serialized runtime grant; no other runtime was started by this worker.

## Evidence

One bounded run: **52 passed, 11 failed in 2.12s**, no skips or xfails. The 25
new independent cases contributed **14 passes / 11 failures**; all 38 existing
projection cases passed. No assertions were changed after execution.

Exact command, from this worktree:

```sh
env -u DEALGATE_POSTGRES_URL -u POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=api /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/pytest api/tests/test_s21_demand_source_independent.py api/tests/test_s21_demand_source.py -o addopts='' -q -p no:cacheprovider --tb=short --basetemp=/tmp/s21-qa-demand-source-independent
```

Tests construct their own typed commercial/calendar sources and literal date,
quantity and Decimal expectations. They do not import worker fixture builders,
patch feature functions, use a DB fixture, or contact providers. The direct
hybrid mismatch cases additionally assert the existing commercial engine's
`components.binding` rejection before challenging projection of that same
source; no monetary expectation is calculated from production output.
`git diff --check` passed. Lint was not run in this bounded runtime slot.

## Findings

1. **High: parent-child source binding is not validated during traversal.** A
   child and its assignment can consistently identify another source, obsolete
   source version, or another policy and still enter the parent projection.
   Six cases cover the three identities in direct and nested hybrids. The
   assignment-to-own-child check at `api/app/gm/demand_source.py:66` is not a
   substitute for checking against the enclosing source. Recursion at `:114`
   passes no parent context. The existing commercial invariant is in
   `api/app/gm/commercial.py:707`. This is a pure projection defect; these tests
   do not claim a demonstrated public API authorization bypass.
2. **Medium: staffing outside the confirmed package term is projected despite
   the commercial binding invariant.** A November 1-30 parent accepts a child
   beginning October 31 or ending December 1. Both inputs are first rejected
   with `components.binding` by the actual commercial engine, but projection
   raises no error. The check at `api/app/gm/demand_source.py:56` only validates
   each component's own period. Its `:87` intersection uses the child, never the
   parent. This does not require identical parent/child dates: a child dated
   November 10-20 is an explicit passing control. Commercial containment is
   already specified at `api/app/gm/commercial.py:710`, not invented by QA.
3. **Medium: absent source staffing evidence is hidden by manual capability
   evidence.** Empty source evidence and whitespace-only source evidence both
   return `missing=[]` after skills/level are enriched. Manual HR confirmation
   establishes skills, not provenance for the source-owned staffing count and
   dates. The independent expectation is an explicit
   `component:delivery:source_evidence` missing reason while retaining the known
   quantity. Evidence merging at `api/app/gm/demand_source.py:104` and the missing
   field list at `:107` never assess source evidence.
4. **Low: duplicate manual skill keys are accepted as canonical enrichment.**
   `skills=["python", "python"]` is accepted rather than rejected; the managed
   workforce validator already rejects duplicate skill keys. `_strings` at
   `api/app/gm/demand_source.py:18` checks shape/whitespace only, while `:77`
   forwards the duplicates. No headcount inflation is claimed for this case.

Failing node suffixes, each prefixed with
`api/tests/test_s21_demand_source_independent.py::`:

```text
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[False-source_id-other-source]
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[False-source_version-obsolete-version]
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[False-policy_version-other-policy]
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[True-source_id-other-source]
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[True-source_version-obsolete-version]
test_hybrid_cannot_publish_a_self_consistent_child_from_another_source_context[True-policy_version-other-policy]
test_child_staffing_outside_confirmed_package_term_is_not_published_as_complete[changes0]
test_child_staffing_outside_confirmed_package_term_is_not_published_as_complete[changes1]
test_manual_capability_evidence_does_not_replace_missing_source_staffing_evidence[evidence0]
test_manual_capability_evidence_does_not_replace_missing_source_staffing_evidence[evidence1]
test_duplicate_manual_skill_keys_are_rejected_as_noncanonical_enrichment
```

## Passing Controls and Limits

- Valid child-specific dates and mixed US/India timezones/currencies retain
  literal headcounts 2 and 5, without requiring financial pricing or FX.
- Manual skills, level and retained-person links each require evidence.
  Unsupported profile names reject instead of being relabeled.
- Zero allocation remains explicit zero with a missing allocation reason;
  unresolved location remains null. No staffing yields a missing component,
  not fabricated zero demand. Calendar coverage never invents service dates.
- Leap-day intersection preserves inclusive dates. Exact Decimal allocation and
  version-stable structured line identity are preserved. Mutating output lists
  does not mutate source staffing, enrichment, or subsequent projections.
- Projection output has an exact cost-free field allowlist even when source
  bill/cost rates and their versions are present.

No publication persistence, CAS, tenant/role enforcement, trusted-fixture scope,
consumer matching, sourcing drafts, source-event replay, API/UI, cloud or
staging behavior was tested. Nullable unknown quantity/allocation cannot be
constructed as a canonical `StaffingAssignment`; handling legacy/incomplete raw
sources remains a caller boundary. The lead reported an adapter that persists
zero allocation as unresolved null plus a missing reason; that adapter is not
in this pure projection acceptance surface and was not verified here.
T22/T23 and FC-07/FC-08 are not accepted by these unit results.
