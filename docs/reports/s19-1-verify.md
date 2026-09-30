# S19 slice 1 — verification report (first commit)

Per directive §Slice 1: verify data correctness **before** any data-model
or UI change. Findings drive the migration + mapper fix that lands in
this same slice; UI comes after the mirror agrees with HubSpot.

Portal: SmarTek21 HubSpot (id 48656168, US/Eastern). Mirror state: 656
opportunities with `source='hubspot' AND archived_at IS NULL`, image
`s18-2a-ae5fe36` on ECS rev 47 (matches origin/main at 0aa5549 after
CI's fresh build finishes and preserves the inline HubSpot secret env).

## 1 · Pipelines and stages

`GET /crm/v3/pipelines/deals` returns **one pipeline**:

| pipeline id | label | displayOrder | stages | archived |
|---|---|---:|---:|:---:|
| `710688094` | SmarTek21 Global Pipeline | 2 | 9 | no |

Stage table (source-of-truth for the mapper):

| stage id | label | displayOrder | isClosed | probability | archived |
|---|---|---:|:---:|---:|:---:|
| `1038193692` | 1-Initial Contact/Prospecting | 0 | false | 0.1 | no |
| `1038193693` | 2-Qualification | 1 | false | 0.2 | no |
| `1038193694` | 3-Requirement/Fit Gap Analysis | 2 | false | 0.3 | no |
| `1038193695` | 4-Proposal | 3 | false | 0.5 | no |
| `1038193696` | 5-Negotiation | 4 | false | 0.7 | no |
| `1038193697` | 6-Contracting/Drive Commitment | 5 | false | 0.9 | no |
| `1038553758` | **7-Closed Won** | 6 | **true** | 1.0 | no |
| `1038553759` | **8-Closed Lost** | 7 | **true** | 0.0 | no |
| `1182672128` | Hold | 8 | false | 0.1 | no |

**Every distinct stage id present in the mirror resolves to a stage in
this table.** No unknown-stage bug.

Mirror distribution across those 9 stages (all 656 rows):

| stage label | count | share |
|---|---:|---:|
| 8-Closed Lost | 297 | 45.3% |
| 7-Closed Won | 253 | 38.6% |
| 4-Proposal | 35 | 5.3% |
| 1-Initial Contact/Prospecting | 28 | 4.3% |
| 3-Requirement/Fit Gap Analysis | 21 | 3.2% |
| 2-Qualification | 9 | 1.4% |
| 6-Contracting/Drive Commitment | 8 | 1.2% |
| 5-Negotiation | 3 | 0.5% |
| Hold | 2 | 0.3% |
| **open (not-closed) total** | **106** | **16.2%** |
| **closed total** | **550** | **83.8%** |

The mirror is treating all 656 as "open" today (Pipeline filters on
`archived_at IS NULL` only). The `is_closed_won` / `is_closed_lost`
flags in the S19 data model are exactly what fix this.

## 2 · Top-3 clients — HubSpot vs mirror counts

Directive: "compare... the 3 clients with the most deals against HubSpot".

| client | HubSpot deals | mirror deals | match |
|---|---:|---:|:---:|
| Capitec Bank Limited | 44 | 44 | ✓ |
| Standard Bank of South Africa | 42 | 42 | ✓ |
| Momentum Group | 37 | 37 | ✓ |

**All three counts match exactly.**

## 3 · Sample diff — 12 deals

10 chosen at random from the mirror + Costco Travel `37027579541` and
`32824410491` by name per the directive's follow-up. Stage label
column shows what HubSpot's pipelines endpoint resolves; mirror shows
what §2a stored.

| deal id | HubSpot name | HS stage → label | Mirror stage_label | HS amount | Mirror amount | HS currency | Mirror currency | HS close | Mirror close | HS last_mod | Mirror last_seen | HS owner | Mirror owner | company assoc |
|---|---|---|---|---:|---:|---|---|---|---|---|---|---|---|---:|
| `63222237786` | Costco US Dev Team - 11 qty. | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 1200000 | 1200000.00 | USD | (not stored) | 2026-08-18 | 2026-08-18 | 2026-08-18 | 2026-09-29 05:59 | sreedhars@smartek21.com | sreedhars@smartek21.com | 1 unique |
| `39542828055` | TIH - Tyler Jade Renwal | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 77152 | 77152.00 | USD | (not stored) | 2025-08-28 | 2025-08-28 | 2026-09-22 | 2026-09-29 06:33 | (deactivated 76287123) | unassigned@dealgate.local (F2 sentinel) | 1 unique |
| `40664664940` | Road Accident Fund - PEN TESTING SERVICES | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 99 | 99.00 | USD | (not stored) | 2025-08-18 | 2025-08-18 | 2026-07-10 | 2026-09-29 06:33 | cesterhuizen@retrorabbit.co.za | cesterhuizen@retrorabbit.co.za | 1 unique |
| `61024775346` | Momentum - Renewal - GIAP Team (1 Month) | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 50050 | 50050.00 | USD | (not stored) | 2026-09-23 | 2026-09-23 | 2026-09-29 | 2026-09-29 06:33 | bvermaak@retrorabbit.co.za | bvermaak@retrorabbit.co.za | 1 unique |
| `44576823330` | Sound Hound- Help Desk | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 1135980 | 1135980.00 | USD | (not stored) | 2026-04-30 | 2026-04-30 | 2026-07-10 | 2026-09-29 06:33 | adill@smartek21.com | adill@smartek21.com | 1 unique |
| `35154488105` | Vizin - New Resource - L5 Dev | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 76773.05 | 76773.05 | USD | (not stored) | 2025-05-13 | 2025-05-13 | 2026-07-08 | 2026-09-29 06:33 | cesterhuizen@retrorabbit.co.za | cesterhuizen@retrorabbit.co.za | 1 unique |
| `58906023250` | Christus - Epic Prelude & RTE | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 64800 | 64800.00 | USD | (not stored) | 2026-06-04 | 2026-06-04 | 2026-07-11 | 2026-09-29 06:33 | brandonl@smartek21.com | brandonl@smartek21.com | 1 unique |
| `33479939602` | Capitec - IT Payment System - Dylan Pietersen | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 88617.84 | 88617.84 | USD | (not stored) | 2024-08-31 | 2024-08-31 | 2026-09-23 | 2026-09-29 06:33 | dnolte@retrorabbit.co.za | dnolte@retrorabbit.co.za | 1 unique |
| `38707766326` | Vitality Global - New Deal - Flutter dev | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 10000 | 10000.00 | USD | (not stored) | 2025-08-21 | 2025-08-21 | 2026-07-20 | 2026-09-29 06:33 | cesterhuizen@retrorabbit.co.za | cesterhuizen@retrorabbit.co.za | 1 unique |
| `36393408313` | Goosehead - SmartBox Call Monitoring | `1038553759` → **8-Closed Lost** | `1038553759` **(mapper bug)** | 99 | 99.00 | USD | (not stored) | 2026-08-05 | 2026-08-05 | 2026-08-05 | 2026-09-29 06:33 | (deactivated 76180375) | unassigned@dealgate.local (F2 sentinel) | 1 unique |
| **`37027579541`** | **Costco Travel** | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 35000000 | 35000000.00 | USD | (not stored) | 2025-08-29 | 2025-08-29 | 2026-08-10 | 2026-09-29 06:34 | sreedhars@smartek21.com | sreedhars@smartek21.com | 1 unique |
| **`32824410491`** | **Costco Travel** | `1038553758` → **7-Closed Won** | `1038553758` **(mapper bug)** | 29000000 | 29000000.00 | USD | (not stored) | 2023-09-01 | 2023-09-01 | 2026-08-10 | 2026-09-29 06:34 | sreedhars@smartek21.com | sreedhars@smartek21.com | 1 unique |

### 3.1 · Costco Travel resolution

Both are marked **7-Closed Won** in HubSpot (stage id `1038553758`).
They mirror as "open" today only because the mirror doesn't store the
closed-flag. Once the migration lands `is_closed_won`, Pipeline will
filter them out of the open counts automatically.

**Not stale CRM data** — HubSpot itself has them at 7-Closed Won,
authored by sreedhars@smartek21.com, last-modified 2026-08-10. The
2023 / 2025 close dates are honest historical dates on won deals.
No HubSpot cleanup needed on your side.

## 4 · Multi-company deals

Across all 656 deals, HubSpot returns each `deal_to_company`
association **twice** — once under `deal_to_company` (labeled/primary)
and once under `deal_to_company_unlabeled` (default). Deduping on
company id:

| bucket | count |
|---|---:|
| deals with **no** company | 2 |
| deals with exactly **1** unique company | 653 |
| deals with **>1** unique company | 1 |
| max unique companies on any deal | 3 |

The one multi-company deal:
- `48350247038` **EY SA - New - Website Design** (8-Closed Lost, $24,934, USD) — 3 unique company ids: `32914477398`, `33373156241`, `43986945657`.

The two no-company deals:
- `32387658902` **PriceLine** (8-Closed Lost, $2,000)
- `32790917642` **Edisen** (8-Closed Lost, $156,000)

**Primary-company decision (per directive §Slice 1 verify):** the
association returned first under `deal_to_company` (the labeled edge)
is the primary. In portals where `associationLabel` metadata is
present it wins; the `_unlabeled` type is HubSpot's automatic default
copy and never overrides.

## 5 · Currency mix

| currency | deal count | share |
|---|---:|---:|
| USD | 655 | 99.8% |
| (null / unset) | 1 | 0.2% |

The single null-currency row is `33440725130` **Momentum Group - RFP
for Business Process Automation** (8-Closed Lost, amount also null).

The mirror does not store currency today — column missing. Slice 1's
data model adds it.

## 6 · Bugs found → fixes required (all in scope for this slice)

### 6.1 · Mapper bug: `stage_label` stores the stage id
`services.hubspot_intake._upsert_opportunity` sets `stage_label` from
`props.get("dealstage_label") or stage`. HubSpot's CRM v3 deal read
does **not** return a `dealstage_label` property; the label lives on
the pipelines endpoint. So `stage_label` falls back to the numeric id
on every write.

**Fix (this slice):** load the pipeline stage table once at the start
of backfill / webhook processing and populate `stage_label` from the
resolved label. Cache the mapping.

### 6.2 · Data model gaps (directive §Slice 1)
Every ✗ in the sample diff maps to a column the directive already
specifies. Migration adds:

- `hubspot_pipeline_id`, `hubspot_stage_id`, `stage_order`,
  `is_closed_won`, `is_closed_lost` — kill the "everything looks open"
  behaviour.
- `currency` — track USD vs future mixed-currency portals.
- `hubspot_created_at`, `hubspot_last_activity_at`,
  `hubspot_last_modified_at` — Pipeline sort keys.
- `primary_client_id` — for multi-company deals.

Plus new tables: `hubspot_pipeline`, `hubspot_stage` (the mirror);
`next_action` (slice 2 UI, data model here); `sync_status`;
`user_preference`.

### 6.3 · Amount string-form difference
HubSpot returns `77152` as a bare integer string; the mirror stores
`77152.00` (Numeric(14,2)). Numeric equality holds; the difference is
cosmetic from `Decimal` formatting. No fix needed.

## 7 · Judgment calls for Kanna

**None** in this session — every mismatch found is either a mapper
bug or a data-model gap the S19 slice 1 spec already covers.
Continuing to the checklist + migration + mapper fix without a pause.

## 8 · Next commits on this branch

1. **docs/directives/s19-checklist.md** — one line per screen /
   endpoint / job / edge case, before any code.
2. **Migration + models** for §Slice 1 data model.
3. **Mapper fix** — pipeline mirror + stage label lookup; rerun
   backfill against staging.
4. **Post-fix verification** — re-report Costco Travel + top-5 with
   labels + closed flags resolved.
5. **Query service extensions** — `list_clients`, `list_opportunities`,
   `summary`, filters, ≤3-query guarantee.
6. **UI** — `/pipeline` toggle, summary bar, stage strip, tables,
   detail panel (read-only), "Create in HubSpot" header link, sync
   banner.
7. **Sync** — webhooks + SQS + reconcile + drift, per §Slice 1 Sync.
8. **Tests + smoke + click-through**.

## 9 · Post-fix verification (commit `8248afd`, rev 48)

Backfill counts on rerun after the mapper fix landed:

| counter | value |
|---|---:|
| deals_seen | 656 |
| deals_created | 0 |
| deals_updated | 656 |
| deals_unchanged | 0 |
| deals_archived | 0 |
| companies_matched | 656 |
| companies_created | 0 |
| owners_matched | 656 |
| owners_unassigned | 0 |
| multi_company_deals | 1 |
| errors | 0 |

Every row updated because the new columns (labels + closed flags +
currency + timestamps + pipeline id + primary client + secondary
companies) rewrote existing values.

### 9.1 · Costco Travel — resolved

| deal | is_closed_won | is_closed_lost | stage_label | stage_order |
|---|:---:|:---:|---|---:|
| `37027579541` | **true** | false | 7-Closed Won | 6 |
| `32824410491` | **true** | false | 7-Closed Won | 6 |

Both are now correctly flagged Closed Won. The Pipeline UI filter
`is_closed_won = false AND is_closed_lost = false` will drop them
from the open board automatically.

### 9.2 · Edge-case fixtures — all resolved

| deal | client | stage_label | is_closed | primary | secondary | currency |
|---|---|---|:---:|---|---:|---|
| `48350247038` **EY SA** | EY SA | 8-Closed Lost | lost | resolved | **2** | USD |
| `32387658902` **PriceLine (no company)** | Unknown company (deal 32387658902) | 8-Closed Lost | lost | sentinel | 0 | USD |
| `33440725130` **Momentum RFP (null amount)** | Momentum Group | 8-Closed Lost | lost | resolved | 0 | null |
| `33479939602` **Capitec sample** | Capitec Bank Limited | 7-Closed Won | won | resolved | 0 | USD |
| `63222237786` **Costco Dev Team** | Costco Travel | 7-Closed Won | won | resolved | 0 | USD |

### 9.3 · Portal summary in the mirror

| bucket | count | share |
|---|---:|---:|
| Closed Won | 253 | 38.6% |
| Closed Lost | 297 | 45.3% |
| Open | 106 | 16.2% |

Currency mix in the mirror **matches HubSpot exactly** (655 USD + 1
null).

## 10 · Bugs closed by this rerun

- 6.1 · stage_label mapper bug — closed. Labels now resolve via the mirror.
- 6.2 · data-model gaps — closed. All 10 new columns populated on every row.
- 6.3 · amount string-form cosmetic difference — no fix needed (still holds; Decimal formatting).
