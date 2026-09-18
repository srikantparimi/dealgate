# S6 (user-added scope) — Excel template spec for legacy resource import

## Deliverable
Publish a canonical Excel template Finance can fill in. Ship at:
`/Users/srikanthparimi/OfficeApp/dealgate/fixtures/legacy_projects/template.xlsx`
with a sample filled sheet at `sample_client_a.xlsx` alongside.

## Columns (one row per resource-line)
| Column | Type | Required | Notes |
| --- | --- | --- | --- |
| sow_ref | string | yes | Matches uploaded SOW file's stem, e.g. `SOW-Client-A-2026-03` |
| client_name | string | yes | Legal name |
| engagement_type | enum | yes | One of: staff_aug, single_resource, fixed_price, assessment, tm, managed_service |
| role | string | yes | e.g. `Sr Data Engineer` |
| seniority | enum | yes | `junior, mid, senior, principal` |
| location | enum | yes | `US` or `India` (reject any other value) |
| start_date | date | yes | ISO YYYY-MM-DD |
| end_date | date | yes | Must be ≥ start_date |
| allocation_pct | decimal | yes | 0-100 |
| billable_hours | decimal | yes | For the period start→end |
| hourly_bill_rate | decimal | yes | USD, `NUMERIC(10,4)` |
| hourly_loaded_cost | decimal | yes | USD, `NUMERIC(10,4)`. Missing → reject entire file |
| currency | enum | yes | `USD` for pilot |
| revenue_us | decimal | conditional | Required for fixed_price / assessment / managed_service |
| revenue_india | decimal | conditional | Same |
| notes | string | no | Free text |

## Rules
- Any row with `location` outside `US/India` → whole file rejected with row number.
- Any row missing `hourly_loaded_cost` → whole file rejected (missing cost is never zero — §2 hard rule).
- `sum(revenue_us) + sum(revenue_india)` must equal total price for the project (validated after the SOW upload matches).
- Rejects are all-or-nothing per file (no partial state).

## Out of scope
- Automated FX conversion (currency is USD for pilot).
