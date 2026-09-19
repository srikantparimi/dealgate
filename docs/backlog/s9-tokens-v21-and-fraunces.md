# S9 — Migrate design tokens to v2.1 + adopt Fraunces + one-accent rule

## Story
Adopt `docs/design/DealGate_Design_Tokens_v2.1.json` + the addendum. Wire
Fraunces (display, headline + H1 only) alongside Inter (UI). Enforce the
one-accent rule (violet primary; lime **only** inside the plum banner;
plum is banner + toast + tooltip only, never a page background). Introduce
the 22 px `StatusChip` dot+word, the 22×18 `FunctionMark` (D H F L), the
0–60% `FloorBar`, gate steps with a `hold` "Will trigger" state, and the
3 px left stripe for `blocked / at-risk / in-progress` cards.

## Deliverables
1. `web/tailwind.config.ts` — rebind every color / spacing / radius /
   typography value to `DealGate_Design_Tokens_v2.1.json`. Layout tokens:
   `sidebarPx: 224`, `headerPx: 56`, `pagePaddingPx: 24`, `rowPx.comfortable:
   44`, `rowPx.compact: 36`. Radii: `control 6 / chip 4 / card 12 / panel
   16 / avatar 999`. Breakpoints: `sixLaneBoard 1560`, `twoColumnCollapse
   1180`, `mobile 820`.
2. `web/src/index.css` — `:root` + `[data-theme=dark]` custom-property
   sheets rewritten from the v2.1 palette. Font stacks per the tokens
   file (Fraunces via `@fontsource/fraunces`, Inter via
   `@fontsource-variable/inter`).
3. `web/src/ui-v2/AppShell.tsx` — sidebar 224 px, header 56 px, plum
   banner surface only in the executive banner region.
4. **Refresh primitives** to match the v2.1 spec:
   - `StatusBadge` → 22 px height, 4 px radius, dot + word, 5 variants
     (`neutral / success / warning / danger / progress`).
   - New `FunctionMark` primitive — 22 × 18, letter D/H/F/L, 4 states.
     Always followed by "n/4 reviews" text.
   - New `FloorBar` — 10 px track, text-colored floor marker, danger fill
     below floor, chip like "Fails by 7.2 pts", 0–60 % scale.
   - New `GateSteps` — 6 clickable steps + `hold` state that reads "Will
     trigger" before its gate is reached.
   - Card stripe utility: 3 px left border on `blocked / at-risk /
     in-progress` cards.
5. **One-accent enforcement** — a lint check (or a `web/src/lib/tokens.ts`
   helper + a test) that scans components for any raw hex outside
   `tailwind.config.ts` and fails. Existing V2 pages must not carry raw
   hex values.
6. **Board layout breakpoints** — SOW board is 1 lane on mobile, 3 across
   below 1560 px, all 6 at ≥1560 px. Cards keep chips readable at every
   breakpoint.
7. **Chart primitive** — `BarChart` inline SVG, thin bars, 2 series max
   (`chartSeries1`, `chartSeries2`), floor as a text-colored line, red
   value label only where forecast is below floor.
8. Every existing V2 page keeps working (185 web tests preserved). Any
   test that hard-codes a v2.0 token colour is updated to the v2.1 value.

## Constraints
- No page rewrites in this story — only the token layer + primitives.
- No hex outside `tailwind.config.ts` and `index.css`.
- Both themes work.
- Reduced motion + focus rings preserved.

## Notes
Addendum §"Rules for the agents" 1–10 is the acceptance check.
