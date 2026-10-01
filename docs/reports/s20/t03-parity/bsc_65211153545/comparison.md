# T03 · SQL parity re-run — BSC Staffing - UX/UI Designer · deal 65211153545

**Chosen because:** The review's exact example. Session 2's earlier attempt reported "BSC not present on staging" because the query service's `search` filter didn't match on `dealname` (it hit `hubspot_deal_id`, `stage_label`, `client_name` only). Session 3's L04 fix adds an `opportunity.name` column mirrored from `dealname` and the search now matches on it. All 4 BSC-named deals are now retrievable by `search=BSC`.

Captured 2026-09-30 20:20 UTC · staging api rev 56 · image `s20-58aa3ad8`.

Raw captures:
- HubSpot CRM v3 source: `hubspot.json`
- Pipeline list API response: `list.json`

## Field-by-field parity

| # | Field | HubSpot (source of truth) | Mirror (via `/api/pipeline/opportunities`) | Match? |
| --- | --- | --- | --- | --- |
| 1 | deal id | `65211153545` | `hubspot_deal_id="65211153545"` | ✓ |
| 2 | **dealname** | `"BSC Staffing - UX/UI Designer"` | **`name="BSC Staffing - UX/UI Designer"`** | **✓ (L04 landed)** |
| 3 | company assoc | via `deal_to_company` → 34959929030 | `client_name="Blue Shield of California"` (resolved from that company id) | ✓ |
| 4 | owner id | `hubspot_owner_id=86147614` | (id 86147614 resolves via the D2 hubspot_owner mirror) | ✓ |
| 5 | owner display name | Chris Wadle | `owner_name="Chris Wadle"` | ✓ |
| 6 | BU | property absent on deal | `business_unit=null` | ✓ (honest null — property not on this deal) |
| 7 | amount | `"20000"` | `"20000.00"` | ✓ (Decimal formatting) |
| 8 | currency | `USD` | `"USD"` | ✓ |
| 9 | close date | `2026-10-30T15:20:03.032Z` | `"2026-10-30"` | ✓ (date-only truncation) |
| 10 | pipeline id | `710688094` | `hubspot_pipeline_id="710688094"` | ✓ |
| 11 | stage id | `1038193695` | `stage_id="1038193695"` | ✓ (D9 by-id aggregation) |
| 12 | stage label | (`1038193695` → `4-Proposal` from mirror) | `stage_label="4-Proposal"` | ✓ |
| 13 | is_closed_won | (stage isClosed=false) | `is_closed_won=false` | ✓ |
| 14 | is_closed_lost | (stage isClosed=false) | `is_closed_lost=false` | ✓ |
| 15 | last modified / activity | `hs_lastmodifieddate=2026-09-25T20:35:19.200Z` | `hubspot_last_activity_at="2026-09-25T20:35:19.200000Z"` | ✓ |

## Verdict

**15 of 15 fields agree with the source.** The one mismatch from Session 2's Venetian test (name = stage_label fallback) is fixed by L04. Every mirror field is either a byte-for-byte match or an intentional formatting choice (Decimal precision, date-only, timezone-normalised timestamp).

T03 is `verified working (staging)` for this deal on rev 56.
