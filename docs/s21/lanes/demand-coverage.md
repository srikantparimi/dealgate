# Explicit Staffing Slot Coverage

Isolated branch `s21/demand-coverage` from `07c36b8`. Own new pure
`demand_coverage.py`, independent literal tests and this report only. Existing
allocation engine, service, persistence and access controls remain lead-owned.

## Contract

`DemandCoverage(plan_id, project_id, plan_slots, project_slots, start, end)`
uses demand-line identities and zero-based integer slot tuples. Coverage and
application bounds are inclusive. Dates must be within both sources. There
must be one distinct project slot for each distinct mapped plan slot.

`validate_coverage(demands, coverages)` rejects unknown or duplicate demand
identities, same-source conversion, incomplete/different capability,
account/location/timezone/allocation mismatch, inactive/unselected plan demand,
and unselected or noncommitted project replacement. Skill equality is unordered.
Boolean, fractional, negative and out-of-range slots reject. Either endpoint
slot cannot be reused in simultaneously overlapping mappings; adjacent disjoint
inclusive windows may reuse the slot.

`apply_coverage(demands, coverages, start, end)` returns a tuple of residual
existing `Demand` values. The integration lead splits intervals at coverage
start and end-plus-one boundaries. A partial intersection is an explicit error,
not silently treated as full-interval conversion. Project demand remains full
and unchanged. Plan quantities are reduced only by explicitly mapped slots;
fully covered plan rows disappear only within covered intervals. Original slot
numbers are considered together before any residual quantity is constructed.
Call with the original source demands for each interval, never the previous
interval's residual. Service dates and IDs remain source-owned; the existing
engine continues to filter demand activity within the split interval.

Retained identities occupy the first named source slots. A covered retained
plan slot must map to the same named identity in the project slot; unnamed or
different project identities reject rather than infer continuity. A previously
unnamed plan slot may map to an explicitly named project slot. Residual plan
identities retain their order and stable `Demand.id` for continuity credits.

No money, financial fraction, probability multiplier or source inference is
used. This pure increment does not complete staffing conversion persistence,
CAS/audit, trust boundaries, connected workflows or staging verification.

Tests were authored first. Implementation proceeded during the integration
lead's serialized full-backend runtime, as instructed; no pre-implementation
red execution is claimed. Static review covers collecting all original slot
removals before rebuilding a residual and preserving immutable project objects.
After runtime was granted, the first focused execution passed: **62 passed in
1.77s** (46 new coverage cases and 16 unchanged pure allocation cases), no skips
or xfails. Runtime was released immediately; no processes remain.

```sh
cd /Users/srikanthparimi/OfficeApp/dealgate-s21-demand-coverage/api
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest tests/test_s21_demand_coverage.py tests/test_s21_demand_allocation.py -q -o addopts= -p no:cacheprovider --tb=short
```

Oracles cover literal seven rather than fourteen people at 70% probability;
partial dates/slots; unchanged project demand; source-copy safety; original-slot
numbering across simultaneous mappings; remaining named continuity; inclusive
boundary restoration; unknown, mismatched, inactive and incomplete sources;
overlapping endpoint reuse; invalid quantities, slots and date bounds. Existing
allocation tests were not changed. `git diff --check` passed.
