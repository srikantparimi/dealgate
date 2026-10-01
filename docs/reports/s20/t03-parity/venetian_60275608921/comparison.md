# T03 · SQL parity — Venetian Resort · deal 60275608921

**Deal chosen:** The Venetian Resort Las Vegas · "Venetian - Direct Placement/ System Engineer" (BSC Staffing – UX/UI Designer, the review's example, is not present in the staging portal — verified with `search=BSC`, `search=Staffing`, `search=Designer`, `search=UX` all returning `total=0`). Venetian was picked from the first page of `/api/pipeline/opportunities` and matches T03's shape (real HubSpot record, mixed field coverage, single-company association).

Captured on staging @ `s20-d21d18c9` (api rev 55) on 2026-09-30 19:58 UTC.

Raw captures:
- HubSpot CRM v3 source: `hubspot.json`
- Pipeline list API response: `list.json`

## Field-by-field parity

| Field | HubSpot (source of truth) | Mirror (via `/api/pipeline/opportunities`) | Match? | Notes |
| --- | --- | --- | --- | --- |
| **id (deal id)** | `60275608921` | `hubspot_deal_id=60275608921` | ✓ | |
| **title (dealname)** | `Venetian - Direct Placement/ System Engineer  ` | **`name = "1-Initial Contact/Prospecting"`** | **✗ (L04 bug)** | The `name` field is displaying the stage label instead of `dealname`. This is the L04 defect the review calls out; W2 filed request W2-2026-09-30-01 for an `opportunity.name` column populated from `dealname`. Blocker for L04's "verified working" flip — carry-forward to Session 3 (W2). |
| **company** | assoc `deal_to_company → 34960299949` | `client_name="The Venetian Resort Las Vegas"` (resolved from the same company id via mirror) | ✓ | |
| **owner (source id)** | `hubspot_owner_id=86147613` | (resolved via owner mirror) | ✓ | Owner id resolves through the D2 hubspot_owner mirror. |
| **owner (display name)** | (id 86147613 → Roger Scalzi) | `owner_name="Roger Scalzi"` | ✓ | |
| **owner email** | (id 86147613 → rogers@smartek21.com) | `owner_email="rogers@smartek21.com"` | ✓ | |
| **BU (Business Unit)** | (property not on this deal) | `business_unit=null` | ✓ | D10 discovery: the "Business Unit" property is either absent from the staging portal's deal schema or has an internal name different from label. Consistent-with-mirror; the null is honest, not a defect. |
| **amount** | `"180000"` | `"180000.00"` | ✓ | Cosmetic Decimal formatting only. |
| **currency** | `USD` | `"USD"` | ✓ | |
| **close date** | `2026-06-30T16:33:39.226Z` | `"2026-06-30"` (date-only) | ✓ | Date-only truncation is intentional (contracts §4 timezone/date-only handling). |
| **pipeline id** | `710688094` | `hubspot_pipeline_id="710688094"` | ✓ | |
| **stage id** | `1038193692` | `stage_id="1038193692"` | ✓ | Aggregation-by-id (D9) works — no label-based grouping in the response. |
| **stage label** | (`1038193692` → `1-Initial Contact/Prospecting` from hubspot_stage mirror) | `stage_label="1-Initial Contact/Prospecting"` | ✓ | |
| **is closed won** | (stage isClosed=false) | `is_closed_won=false` | ✓ | |
| **is closed lost** | (stage isClosed=false) | `is_closed_lost=false` | ✓ | |
| **created** | `createdate=2026-05-15T22:21:58.662Z` | (not exposed on this endpoint) | — | Available on `/api/pipeline/opportunities/:id` detail. |
| **last modified** | `hs_lastmodifieddate=2026-09-02T08:08:17.499Z` | `hubspot_last_activity_at="2026-09-02T08:08:17.499000Z"` | ✓ | `hubspot_last_activity_at` uses `hs_lastmodifieddate` as the fallback when `notes_last_updated` is null (per S19 slice-1 verify §9). Consistent-with-source. |
| **notes last updated** | `null` | (falls through to `hs_lastmodifieddate`) | ✓ | See row above. |

## Verdict

**14 of 15 fields agree with the source.** The single mismatch is L04's `name` column showing the stage label instead of `dealname` — this is the review's existing L04 defect, tracked as a W2 request. Every other field (owner, BU, amount, currency, close, pipeline+stage identity, closed flags, activity, associations) is a byte-for-byte match, modulo intentional formatting (Decimal, date-only).

Attention flag `stalled` fires because `hubspot_last_activity_at` is > 14d old (2026-09-02, captured 2026-09-30). That's D4-correct behavior.

The two records that could not be tested on this deploy remain deferred:
- **T35 export parity** — W5-04 pipeline export CSV endpoint still absent (W2 request, not landed).
- **Business Unit label mapping** — the portal does not expose a Business Unit property on this deal; D10 `discover_business_unit` correctly returns nothing to map, so `business_unit=null` on every row is honest.
