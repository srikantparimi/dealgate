# S10-03 — Design cleanup to v2.1 prototype

## Story

The v2.1 prototype (`DealGate_Prototype_v2.1.html`) and the addendum are
authoritative. The current build has drifted; the following surfaces
must match the prototype exactly.

Visual conformance only. No new features. No copy changes beyond what
the prototype specifies.

## Scope (must match the prototype byte for byte where noted)

### Command Center (`web/src/pages/v2/CommandCenter.tsx`)

- Executive banner: plum background (`--plum`), Fraunces headline
  `500 40px/1.05`, italic em `--lime`. Two decorative circles
  (`::before` + `::after`) in `--plum-line`. Metrics grid uses
  `--plum-2` cards with `--plum-line` borders. Two alert metrics use
  `--lime` value color.
- Priority signals: `.sig` cards with icon tile (bad / warn / prog fill),
  title with an inline `StatusBadge`, description, meta line
  (owner / age / version).
- Pipeline client readiness table: exact columns and styling as
  prototype `#readiness` block.
- Lanes preview: three lanes shown from the SOW board.
- Delivery economics chart: SVG bars (series 1 `--s1`, series 2
  `--s2`), floor lines, hover tooltip.

### SOW board (`web/src/pages/v2/SowBoard.tsx`)

- Six lanes at ≥1560px, three lanes below. `.bl` cards, `.sow` cards
  with:
  - GM chip (ok / warn / bad)
  - NDA + MSA chip pair
  - FunctionMark row (D / H / F / L, 22×18px, per addendum)
  - Left stripe `stripe-bad` / `stripe-warn` / `stripe-prog` per state
- Card owner + next-action + age line at the foot.

### Staffing & GM (`web/src/pages/v2/SowWorkspace.tsx` → Staffing/GM tab)

- Gate steps use the prototype `.steps` component with `.step.done`,
  `.step.now`, `.step.hold` states. `hold` state uses `--bad-fill`
  background + `--bad` foreground.
- Three geography cards (US / India / Combined) with FloorBar geometry
  matching prototype (`.floorbar` track 10px, fill `--ok` or `--bad`,
  mark line + label).
- Staffing grid columns and cell styles per prototype.

### CEO Exception (`web/src/pages/v2/CEOExceptionDecision.tsx`)

- Two-column layout: case card left, sticky decision card right.
- Four metric cards on top; the "Price increase to reach policy" card
  has `stripe-bad` left border and `--bad` value color.
- Component table matches prototype styling.
- Conditions editor cards + rationale textarea + four decision buttons
  (Approve with conditions / Approve exception / Request changes /
  Decline) in the sticky sidebar.

### Global primitives

- `StatusBadge` — 22px dot+word, five variants: `ok / warn / bad / prog / plain`.
  Match the prototype `.chip` colors exactly.
- `FunctionMark` — 22×18px letter tile, four variants: `ok / bad / prog / neutral`.
- `FloorBar` — 10px track, 4px overshoot for the mark line, label
  positioning matches prototype `.mark::after`.
- `GateSteps` — inline flex, one border, `.done / .now / .hold` states.
- `CardStripe` — 3px left border, three tones (bad / warn / prog).
- Fraunces (display) is applied to h1 on page headers and the banner
  headline only. All other headings stay Inter.
- Density toggle: comfortable (row 44) / compact (row 36) via
  `data-density` on `<html>`. Setting persists in localStorage.

## Tests

- `web/src/__tests__/v2/design-tokens.test.tsx` — asserts computed
  styles on a rendered `StatusBadge`, `FunctionMark`, `FloorBar`,
  `GateSteps` match the token values.
- Visual comparison notes: an addendum `docs/design/v2.1-conformance.md`
  lists each surface and its prototype line-range for the next reviewer.

## Definition of done

- The Command Center, SOW board, Staffing & GM, CEO Exception screens
  on staging visually match the v2.1 prototype (side-by-side inspection
  by a human).
- No token overrides; only tokens from `DealGate_Design_Tokens_v2.1.json`
  are used.
