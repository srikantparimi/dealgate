# DealGate design addendum v2.1

19 September 2026 · Applies on top of `DealGate_UI_UX_Specification.md` (rev 2). Where this addendum and the spec differ, this addendum wins for visual and styling decisions. Business rules, routes, screen inventory and acceptance journeys in the spec are unchanged.

Reference: the clickable prototype (DealGate Workspace artifact) shows the command center, pipeline clients, SOW approvals board, Staffing & GM and CEO exception in light and dark. Match it.

## What changed and why

| Area | v2.0 | v2.1 | Why |
|---|---|---|---|
| Accents | Violet primary, lime hero, plum banner, plus semantic colors all competing | One accent (violet). Lime only on the one hero button inside the plum banner. Plum only as the executive banner, toast and tooltip surface. | Three saturated accents on one screen made nothing stand out. Executives should see one thing first. |
| Typography | Inter everywhere | Fraunces (serif) for the banner headline and page H1 only; Inter for all UI; tabular numerals on every numeric column | The spec asked for "editorial typography" but the tokens had no display face. One serif at two sizes gives the executive tone without slowing down tables. |
| Type scale | Page heading 32px, KPI 28–32px, body 14px | 40 banner / 28 H1 / 26 metric / 15 section / 14 body / 13 table / 12 secondary / 11 label | Fewer steps, clearer hierarchy. Metric values are 26px so four fit in the banner without wrapping. |
| Radius | 9 / 16 / 18 / 20 | 6 controls, 4 chips, 12 cards, 16 panels and banner | Four near-identical radii read as inconsistency. |
| Elevation | "None on routine panels" but no rule for what separates things | Borders separate; shadows float. Cards use a 1px border, never a shadow. Only menus, tooltips and dialogs get a shadow. | Keeps the canvas flat so the plum banner and status colors carry the attention. |
| Severity | Status only in chips | 3px left stripe (danger / warning / primary) on blocked, at-risk and in-progress cards and metric tiles | Board cards scan at a glance without reading the chips. |
| Status chips | Text on a fill | Dot + text on a fill, 22px, 4px radius; five variants: neutral, success, warning, danger, progress | Dot survives grayscale and color-blindness; the word is always there. |
| Function reviews | "Four functional review markers" unspecified | `D H F L` marks, 22×18, four states, always followed by "n/4 reviews" | A fixed glyph row is faster to scan than four chips. |
| Geography test | Numbers only | Floor bar: 0–60% track, text-colored floor marker with label, fill turns danger below floor, chip says "Fails by 7.2 pts" | The gap to policy is the decision; the bar shows it in one glance. |
| Gate progress | Six clickable steps | Same, with a `hold` state that says "Will trigger" for the CEO gate before the package reaches it | Sales sees the consequence while building the GM, not after submitting. |
| Header | 70px | 56px | A quiet header should not take 8% of a laptop screen. |
| Sidebar | 194px | 224px | Labels like "Delivery & actuals" and "Settings & controls" no longer truncate. |
| Rows | 52 / 40 | 44 / 36 | Denser tables without shrinking type; density is still a user preference. |
| Dark theme | Same plum banner on a dark canvas | Plum lifts to #2A2440 with a visible border; primary lightens to #A38BEA with dark text on it; chart series re-stepped | A banner the same color as the canvas disappears; violet buttons with white text fail contrast on dark. |
| Chart | Unspecified | Thin bars, two validated series, floor as a text-colored line, red value label only where forecast is below floor, hover tooltip, table view on request | Follows the data-viz rules: one axis, color follows the entity, status color reserved for a state. |
| Board | Six lanes at 1024px in two rows | Six lanes at ≥1560px, three per row below, one on mobile | Six lanes at laptop width squeezed cards to 190px and clipped chips. |

## Rules for the agents

1. Bind `DealGate_Design_Tokens_v2.1.json` to the Tailwind theme (or CSS variables). No hex codes in components.
2. Every color has a light and a dark value. Never define a color only inside a dark-mode block. Test both themes on every PR.
3. Google Fonts for Fraunces and Inter with `display=swap` and real fallback stacks; if fonts are blocked in production, the page must still lay out correctly.
4. `font-variant-numeric: tabular-nums` on every cell that holds money, percentages, counts or dates.
5. Status is never color alone: chip = dot + word; function mark = letter + state; floor bar = fill + marker + chip text.
6. One primary button per page or decision region. Lime is not a primary button; it exists only inside the plum banner.
7. Cards: 1px border, 12px radius, no shadow. Stripe only for blocked / at-risk / in-progress.
8. Loading states use skeletons of the same geometry. Never show a zero while data loads; show "Unavailable" or "Not validated" as the spec says.
9. Contrast: the tokens file lists computed ratios for the pairs that matter. Re-run the check whenever a token changes; `textMuted` (4.87:1 on surface, 4.49:1 on canvas) is for 12px+ secondary text only.
10. Mobile: sidebar becomes a horizontal chip row under the header; the banner stacks; the board is one column; wide tables and the chart scroll inside their own container, never the page.

## Not changed

Margin floors, approval order, CEO authority, agreement lifecycle states, routes, the screen inventory, the acceptance journeys and the R01–R28 coverage map are exactly as in the spec and the governance blueprint.
