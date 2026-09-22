# Directive S13b: GM panel for Finance, cost-rate display, and miscellaneous costs

From: Kanna Parimi, product owner. 21 September 2026. Commit as `docs/directives/s13b-gm-panel.md`. Runs after s13a. The engine's math is now right — this slice is about showing it in a form Finance can read, displaying the rates the user entered, and adding the one input that has no home today: non-labor costs. Keep the floor bar and the overall panel structure — the product owner likes both. This changes display and adds direct-cost inputs; it does not change the calculation engine except to consume direct costs it already supports.

## Defect 1: the grid hides the rate the user entered

The Confirm grid shows `Rate 0.0000` for lines whose cost rate ($120/hr) was entered on the Staffing page. Wrong column for the engagement type:

- The grid's columns must mirror the Staffing page: on **fixed price**, show **Cost /hr** (the entered $120.00) and render the bill-rate column as `— fixed price` (it does not exist for this type; never show it as 0.0000).
- On staff aug / T&M, show both Bill rate and Cost /hr.
- A zero the user never typed must never render. `0.0000` in a rate column means the binding is wrong, not that the rate is zero.
- Allocation `100%` not `100.0000%`; hours `80` not `80.0000`.

## Defect 2: raw decimals in the GM panel

`US 0.4240000000`, `Blended 0.4240000000`, `Revenue 50000.00` are engine values leaked to the screen. Display rules (full precision stays internal; policy comparisons stay unrounded, as directed):

- Percentages: one decimal — `42.4%`. Points: one decimal — `+7.4 pts`.
- Money: `$50,000` (whole dollars; cents only where they exist).
- Tabular numerals everywhere.
- A geography with no resources reads `Not applicable — no India resources` in muted text, never `Unavailable` (that word is reserved for missing data on something that should exist).
- The summary chip must be consistent with the rows: if India is not applicable, the chip says `Passes US floor`, not `Passes both floors`.

## New capability: miscellaneous / direct costs

There is currently no place to enter non-labor costs. Add a **Direct costs** section under the staffing grid (Staffing page and mirrored on Confirm), line-item based:

| Field | Detail |
| --- | --- |
| Category | Travel, Meals & lodging, Software/licenses, Subcontractor, Equipment, Other (configurable list in Settings) |
| Description | Free text, short |
| Amount | Currency amount, or a % of revenue toggle (e.g. "2% of fee") — stored as the computed amount with its basis |
| Geography | US / India / split in proportion to labor cost (default: proportional) |
| Reimbursable? | **Yes** → pass-through: excluded from both revenue and delivery cost per Finance policy, shown in its own "Client-reimbursed (pass-through)" subtotal so it is visible but outside GM. **No** → delivery cost, enters the GM. This SOW is the example: it says travel and expenses are reimbursed by the client, so those lines are pass-through. |
| Provenance | manual / extracted (extractor should propose lines when the SOW states expense terms) |

Direct costs flow into the one GM engine as the direct-cost input it already supports (`gm-all-scenarios.md` cross-cutting rules). No client-side math.

## The panel, as Finance should read it

Right side of Staffing & GM, top to bottom (keep the floor bars):

```
GM summary                                    GM v4 · draft
Contract price                       $50,000
  Labor cost          $28,800   57.6% of price
  Direct costs         $1,000    2.0% of price
  Total delivery cost $29,800   59.6% of price
Gross profit          $20,200
Gross margin            40.4%

US · floor 35%                          40.4%
[====================|=====       ]  Passes by 5.4 pts
India                     Not applicable — no India resources
Blended                  40.4% · informational

Client-reimbursed (pass-through)   $2,300 · outside GM
```

(Numbers above are the current fixture with an illustrative $1,000 non-reimbursable direct cost and $2,300 reimbursable travel; the panel must compute, not copy, them.) Rules: the cost block always shows dollars **and** % of price side by side — that is the clarity Finance asked for; each geography row keeps the line/bar with the floor marker; mixed SOWs show US and India bars stacked as today; the same panel component renders on the Staffing page, the Confirm page, the approver's package view and the CEO brief, so every reviewer reads the identical presentation.

## Small fix in the same slice

The signatories "Internal" list renders raw UUIDs (visible in the current build). This is s13a defect 2 surfacing in another component — fix it from the same name-resolution helper, not a local patch.

## Definition of done

Browser-proven on staging, screenshots in `docs/reports/s13b.md`:

1. Peppermill fixture: Confirm grid shows Cost /hr $120.00, bill rate `— fixed price`, hours 80/160, allocation 100%.
2. GM panel shows the block above with formatted numbers; no raw decimal anywhere on the page (add a UI test asserting no `/0\.\d{6,}/` renders).
3. Add a $1,000 non-reimbursable "Software" direct cost → total cost and GM update live from the engine; add a reimbursable travel line → GM unchanged, pass-through subtotal appears.
4. India row reads "Not applicable"; chip reads "Passes US floor". A mixed fixture still shows both bars and both tests.
5. Direct costs round-trip through save, appear in the approver package and the exported GM (.xlsx), and are versioned with the GM model.
6. Signatories list shows names, not UUIDs.
7. Existing goldens untouched and green — this slice must not change any engine result except where direct costs are entered.
