# T09 Dedicated Filter Fixture

Authored only, **UNEXECUTED**. Branch `s21/pipeline-filter-fixture`, baseline
`bd188a3f5354eafda9bef9e77ef0ceafe905c5ad`. Worker owns only this report and
`scripts/s21_filter_fixture.py`; lead runs and verifies the real application.

## Guard And Boundary

The helper accepts only an already-migrated PostgreSQL database whose name is
`s21_filter_<32 lowercase hex>`, literal host127.0.0.1/port55421/user and owner s21,
trust-only psycopg URL without query options. Explicit local environment and
tenant exactly equal to that database are mandatory. No PG environment overrides,
alternate target argument, creation, migration, deletion, server startup, API
request or cloud/provider call exists. It never touches `s21_journey`.

It locks its business/mirror tables and refuses any existing row, reporting table
counts rather than appending duplicate fixtures on retry. Missing tables or an
invalid Alembic-head record also fail before insertion. All inserts use a single
transaction. The lead must inspect any failure; do not erase a database merely
to make this guard pass. A successful rerun intentionally refuses the nonempty DB.

These are explicitly **synthetic mirrored CRM records**, not real HubSpot data or
issued `sow_upload` fixture grants. Synthetic source IDs are never sent to a provider.
The local administrator has deterministic `uuid5(NAMESPACE_URL,
"dealgate:local:s21-filter-admin@example.test")`, SystemAdmin, and no officeapp-e2e
group, solely inside this dedicated synthetic database. This is not a live canary,
test-identity authorization proof, or staging acceptance.

## Declared Oracle

88 Deals, 22 populated clients with four Deals each, plus one empty client:

| Indices | Count | Owner | Stage | BU | Per Deal |
| --- | --- | --- | --- | --- | --- |
| 0-63 | 64 | A | Discovery | Consulting | USD1000 |
| 64-71 | 8 | B | Discovery | Consulting | USD2000 |
| 72-79 | 8 | A | Negotiation | Consulting | CAD3000 |
| 80-87 | 8 | A | Discovery | Delivery | USD4000 |

The triple selection has64 Deals/16 clients/USD64000, spanning25+25+14 rows.
All rows total USD112000 and CAD24000. Ten manifest cases specify exact Deal IDs,
client matching counts, literal independent currency sums and expected25-row
pages: all, each single axis, each pair, triple selection, stage-only saved view
and OwnerB+Negotiation zero intersection. They are derived from the authored
cohort ranges, never application filter/summary responses. Supported sort is
`client_name`, with UUID ascending ties independently reflected in manifest order.

Positive BU comes from `HubspotPropertyMapping` in
`api/app/services/hubspot_properties.py`: configured deal enumeration, version7,
observed values/timestamps matching the model pattern in
`api/tests/test_s21_crm_bu_readers.py`. No legacy BU fallback. Two owners have real
local User rows plus synthetic HubspotOwner metadata. One pipeline/two stage
definitions supply labels. SavedView has only Negotiation in `filter_json`, so
the browser can prove replacing rather than merging stale owner/BU filters.

Inserted tables: user, hubspot_owner, hubspot_pipeline, hubspot_stage,
hubspot_property_mapping, client, opportunity, saved_view. No SOW, GM, approval,
grant, task, project or audit authority is fabricated. Dates are fixed synthetic
source observations (2026-10-02T12:00Z), close date2026-12-15, not claimed freshness.

## Exact Invocation

Lead first creates and migrates a new appropriately named private DB. Substitute
its already-created 32-hex suffix below; this command does not create it:

```sh
DEALGATE_ENV=local \
DEALGATE_TENANT_ID=s21_filter_<32hex> \
S21_FILTER_DATABASE_URL=postgresql+psycopg://s21@127.0.0.1:55421/s21_filter_<32hex> \
PYTHONDONTWRITEBYTECODE=1 \
/Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python \
scripts/s21_filter_fixture.py > /tmp/s21-filter-manifest.json
```

Run from this worktree (or integrated repository). Replace placeholders before
shell execution; angle brackets are descriptive, not literal shell input.
The JSON output includes actor, database/tenant, row facts, IDs and independent
oracles. Capture exit status and stderr as well; an empty redirected file is not
proof of successful seed. No runtime/syntax/DB tests were authorized for this
authoring increment. Lead must execute, inspect manifest and complete browser,
export, persistence, response-race and cleanup evidence before T09 can close.
