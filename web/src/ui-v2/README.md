# DealGate UI V2 (Sprint 8, Wave 1 foundation)

The DealGate V2 design system lives here. It sits alongside the legacy
primitives in `web/src/ui/*`; Wave 2+ agents migrate pages one at a time
and delete the old kit at the end of Sprint 8.

## Rules

1. **No business math in the browser.** Money and margin are formatted
   values only. All calculations live in `api/app/gm`. The primitives
   (`MoneyCell`, `MarginCell`, `Metric`) accept pre-formatted strings.
2. **No inline styles.** Every colour, spacing and radius flows through
   Tailwind classes bound to CSS custom properties in `src/index.css`.
   The `tokens.test.ts` guard enforces the token map.
3. **Always tokens, never hex.** If you need a colour Tailwind does not
   already expose, add the CSS variable first (both light and dark),
   register it in `tailwind.config.ts`, and update the tokens JSON.
4. **Text + icon on every status.** Colour is supplementary — see
   `StatusBadge`. Never rely on colour alone to convey policy state.
5. **Tabular numerals on every money/margin display.** Use the `.tnum`
   utility (built-in on `MoneyCell`, `MarginCell`, `Metric`).
6. **Reduced motion is respected globally.** All animated primitives use
   the `.transition-motion` utility which is silenced under
   `prefers-reduced-motion: reduce`.
7. **Server authority is never softened.** Hiding a nav item or disabling
   a button is a UX hint — the API still enforces the real gate.

## Primitives (`web/src/ui-v2/primitives/`)

| Primitive | When to use |
|---|---|
| `Button` | Every button. Variants: `primary` (one per region), `secondary`, `tertiary`, `destructive`, `ghost`, `hero` (reserved for the single executive-banner action). |
| `Input`, `Label` | Text inputs with labels above (spec §2). |
| `Switch`, `Checkbox` | Toggle preferences and multi-select rows. Never for policy switches. |
| `Badge` | Compact rectangular status marker. Prefer `StatusBadge` above it — badge tone alone is not accessible. |
| `Dialog` | Centred modal for a bounded action or confirmation (spec §4). |
| `Sheet` | Right-drawer for filters, notifications, quick task edits, resource rows. |
| `Popover` | Small floating panel; not for critical financial data. |
| `DropdownMenu` | Menus (profile, row actions). |
| `Tabs` | Section switching inside a page; used by `RecordTabs`. |
| `Tooltip` | Supplementary hints; never replaces essential guidance (spec §20). |
| `Command`, `CommandDialog` | `cmdk` wrapper — used by `GlobalSearch`. |
| `Toast`, `Toaster`, `useToast` | Non-financial confirmations. Never a substitute for an approval/signature success (spec §4). |

## Shell + shared components

| Component | Purpose |
|---|---|
| `AppShell` | The V2 frame — sidebar + header + main. Provides `PreferencesProvider`, `TooltipProvider`, `Toaster` at the root. |
| `PrimaryNavigation` | Grouped sidebar (Workspace, Growth, Commitments, Operations, Administration) from spec §3. Filters items by role. |
| `WorkspaceHeader` | 70px quiet header — breadcrumb left, search + notifications + profile right. |
| `GlobalSearch` | ⌘K / Ctrl+K command palette (spec §4). Wires to `getDeals`, `listClients` for now; server authorises. |
| `NotificationDrawer` | Right-sheet inbox with Unread/All tabs and filter chips; reuses S2 notifications API. |
| `ProfileMenu` | Name/role/workspace + My profile, Notification preferences, Appearance, Density, Help, Sign out. Persists to `localStorage`. |
| `PageHeader` | Working page header — 32/38 title with optional right-slot actions. |
| `RecordHeader` | Persistent workspace header for a SOW/opportunity (spec §8). |
| `RecordTabs` | Tab wrapper that keeps the router path in sync. |
| `Metric` | KPI tile — 30/36 tabular value, optional trend and basis. |
| `StatusBadge` | Named status marker — always text + icon; tone is supplementary. |
| `ReadinessChecklist` | Side-panel list explaining every blocked action (spec §8). |
| `EmptyState` | Honest "no records yet" + a permitted recovery. |
| `ErrorState` | Scoped "we couldn't load" panel — one failing module never hides the healthy ones. |
| `SourceFreshness` | Inline caption for integration-backed tables (source · as of · basis). |
| `MoneyCell`, `MarginCell` | Right-aligned tabular financial cells. Missing data renders "Unavailable" — never a fake zero. |

## Theme & density

`PreferencesProvider` reads / writes `localStorage`:

- `dealgate:v2:appearance` — `system` | `light` | `dark`
- `dealgate:v2:density` — `comfortable` | `compact`

The provider sets `data-theme` and `data-density` on `<html>` so all the
CSS custom properties in `src/index.css` re-evaluate. System appearance
tracks `prefers-color-scheme`.

## Files this wave did not touch

- `web/src/ui/*` — the legacy kit, still in use by every page today.
  Wave 2 migrates pages one at a time; do not delete these until the
  last import goes away.
- `web/src/pages/*` — no page in this wave was rewritten.
- `api/**`, `worker/**`, `infra-tf/**` — untouched.
- `web/src/auth/*` — untouched. The new `AppShell` reads
  `useAuth()` exactly like the legacy shell did.

## Adding a new primitive

1. Copy the shape from the canonical `shadcn/ui` docs.
2. Wire every colour through the `theme.extend.colors` tokens — no
   arbitrary hex, no `bg-[#…]`.
3. Add `focus-visible:outline-focus` on every interactive element.
4. Use `.transition-motion` for animation so reduced-motion silences it.
5. Add a small test under `web/src/__tests__/ui-v2/` covering keyboard
   behaviour and role visibility.
