# T03 · SQL parity — real deal, field by field

Per review + directive §8:
> Verify BSC Staffing – UX/UI Designer (or nearest real deal) field by
> field: title, company, owner, BU, amount/currency, close, pipeline
> and stage.
>
> No unseen amount, owner or Business Unit value should be invented.

Any invented value is a defect — recorded in `docs/reports/s20/matrix.md`
against the affected capability + owner.

## Method

1. Pick a real deal name that appears in `services.hubspot_pipeline.list_opportunities`.
   Preference order:
   1. `BSC Staffing - UX/UI Designer` (review's example).
   2. Nearest match if the exact name isn't in the mirror tonight.
   3. Any deal with a non-null `owner`, `amount` and `hubspot_stage_id`.

   Candidate names harvested via
   `scripts/t03-parity.sh --list | head -20` — output logged below.

2. Run `scripts/t03-parity.sh "<name>"` which captures six blobs into
   `docs/reports/s20/t03-parity/<slug>/`:
   - `1-list.json` (list API row)
   - `2-hubspot.json` (HubSpot source of truth, read-only)
   - `3-mirror.json` (mirror row via /api/dev/mirror; W1 to add if missing)
   - `4-client.json` (client detail API)
   - `5-deal.json` (deal detail API)
   - `6-export.csv` (export endpoint; W2 to add if missing)

3. Copy each field's value into the table below. `—` = surface did
   not return the field. Any disagreement between surfaces is a
   defect; capture the discrepancy in the "notes" column.

## Chosen deal

- Deal name: **TBD — awaiting live capture tonight**
- HubSpot deal id: TBD
- Opportunity id (mirror UUID): TBD
- Client (company): TBD
- Capture command: `scripts/t03-parity.sh "<name>"`
- Capture output dir: `docs/reports/s20/t03-parity/<slug>/`
- Capture timestamp (UTC): TBD

## Field-by-field parity table

Column meaning:

| column | source |
| --- | --- |
| HubSpot | Read-only pull from `/crm/v3/objects/deals/{id}` |
| Mirror | Row in local `opportunity` (via `/api/dev/mirror`) |
| List | `/api/pipeline/opportunities?search=…` |
| Client | `/api/clients/{client_id}` (matching-deal section) |
| Deal | `/api/pipeline/opportunities/{opportunity_id}` |
| Export | `export.csv` row |

| Field | HubSpot | Mirror | List | Client | Deal | Export | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Title (dealname) | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Company (associated) | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Owner (name) | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Owner (email) | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Business Unit | TBD | TBD | TBD | TBD | TBD | TBD | not_run — depends on D10 discovery (W1) |
| Amount | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Currency | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Close date | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Pipeline (name + id) | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| Stage (name + id) | TBD | TBD | TBD | TBD | TBD | TBD | not_run — D9 pipeline_id + stage_id |
| is_closed_won | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| is_closed_lost | TBD | TBD | TBD | TBD | TBD | TBD | not_run |
| last_activity_at | TBD | TBD | TBD | TBD | TBD | TBD | not_run |

## Defects surfaced

- (none yet — waiting on live capture)

Any row whose values do not match across every surface where the field
is expected is logged here with:

```
- Field: <field>
  Divergence: <hubspot=…, mirror=…, list=…, etc.>
  Likely cause: <migration / stale mirror / display transform>
  Owner: <W1|W2|…>
  Next action: <requests.md entry, matrix.md entry>
```

## Log

- 2026-09-30 · W5 cycle 0 · skeleton committed; live capture pending
  W1's mirror surface (`/api/dev/mirror`) and W2's export endpoint
  landing on `integrate/s20`. In the meantime, `scripts/t03-parity.sh`
  will capture the four already-implemented surfaces (list, HubSpot,
  client detail, deal detail).
