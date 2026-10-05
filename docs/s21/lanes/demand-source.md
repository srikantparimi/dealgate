# Cost-Free Staffing Projection

Scope: FC-07/T22 source projection only, on isolated branch
`s21/demand-source-projection` from `0c8880b`. No publication, authorization,
migration, API or UI ownership. This is not complete FC-07 or staging proof.

## Interface

`app.gm.demand_source.project_staffing(component, enrichments=None)` returns
`{"lines": [...], "missing": [...]}`. Lines contain only staffing identity,
capability, integer headcount, Decimal allocation, inclusive dates, canonical
commercial profile, explicit continuity IDs, evidence and missing reasons.
`delivery_model` means `PricingComponent.profile`; no inferred engagement
classification is introduced.

`line_key(component_id, assignment_id)` hashes structured JSON identity. It
excludes source version and commercial version, so publication revisions keep
stable continuity IDs. This key is scoped to its publication, not globally to
every SOW. Repeated component identity anywhere in a hybrid and repeated
assignment identity within a component reject. Distinct components may have
the same assignment name because the composite identity is unambiguous.

Bindings must match source ID/version, component, profile version, policy
version, currency and timezone. No financial completeness check is needed and
no financial fields enter the output. All six non-hybrid profiles and nested
hybrids use the same staffing projection; absent staffing remains missing.

Dates use the canonical calendar intersection of explicit assignment dates and
confirmed component service bounds. Missing assignment dates fall back only to
those bounds, never calendar coverage. Empty intersections return unknown dates
and a `service_period` missing reason. Zero allocation remains source zero with
an explicit missing reason; it is not converted to full allocation.

Enrichments are keyed by stable line key and allow only skills, level,
retained_person_ids and evidence. Manual values require written evidence.
Unknown lines/fields reject; retained IDs must be distinct and cannot exceed
headcount. Skills, level and people are never guessed. Source evidence is
preserved without mutating the immutable component. Missing field names are
line-local; top-level reasons include stable line identity, or component
identity when staffing is absent.

## Verification

Tests were authored first: the initial run failed collection because the
projection module did not exist. After implementation, 38 new cases exercise
literal two-US/five-India headcount (no probability weighting), all applicable
profiles, duplicate hybrid components and assignments, source bindings,
version-stable collision-safe keys, date intersection/absence, missing
capability, explicit continuity, and prohibited financial/source overrides.

Final command, with isolated source and read-only dependency executable:

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-demand-source/api
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_demand_source.py tests/test_s21_demand_allocation.py tests/test_s21_commercial_profiles.py -q -o addopts= -p no:cacheprovider
```

Result: **127 passed in 2.40s**, no skipped or xfailed cases. Runtime slot
released; no processes remain. No existing tests changed.

Remaining lead-owned proof: publication CAS, persistence/provenance, access and
fixture isolation, sourcing draft integration, real connected UI, full T22/T23
journeys, and staging validation. These unit results do not establish those
business outcomes.
