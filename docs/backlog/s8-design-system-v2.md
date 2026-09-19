# S8 — Design system V2 (foundation)

## Story
Adopt the V2 design system from `docs/design/DealGate_UI_UX_Specification.md`
+ `DealGate_Design_Tokens.json`. Install Tailwind + shadcn/ui + Inter,
introduce the custom AppShell (194 px sidebar, 70 px header, dark plum
executive banner, violet primary, lime hero accent), rebuild the shared
primitives, wire theme (System/Light/Dark) and density (Comfortable/
Compact). Every existing page must still route, but they will be
rebuilt on top of the new primitives in Wave 2+.

## Deliverables
1. `web/tailwind.config.ts` with color / spacing / radius / typography
   tokens from `docs/design/DealGate_Design_Tokens.json`. Tabular numerals
   utility. Custom font-family Inter.
2. `web/src/index.css` — `@tailwind base/components/utilities` + a light
   CSS-variables sheet for light + dark tokens (root data-attr toggled).
3. Install: `tailwindcss`, `postcss`, `autoprefixer`, `@radix-ui/react-*`
   primitives used by shadcn/ui, `class-variance-authority`, `clsx`,
   `tailwind-merge`, `lucide-react`. Set up `shadcn` init and drop the
   canonical `Button`, `Input`, `Label`, `Dialog`, `Drawer` (Sheet),
   `Popover`, `DropdownMenu`, `Tabs`, `Tooltip`, `Command` (for Cmd+K),
   `Table`, `Toast`, `Badge`, `Checkbox`, `Switch`.
4. `web/src/ui-v2/` (parallel to `web/src/ui/` — old kept temporarily so
   Wave 2 can migrate incrementally):
   - `AppShell.tsx` + `PrimaryNavigation.tsx` (grouped: Workspace,
     Growth, Commitments, Operations, Administration).
   - `WorkspaceHeader.tsx` (breadcrumb left; search + notifications +
     profile right).
   - `GlobalSearch.tsx` (Cmd+K command dialog).
   - `NotificationDrawer.tsx` (right sheet: Unread/All, filters).
   - `ProfileMenu.tsx` (theme + density + sign out).
   - `PageHeader.tsx`, `RecordHeader.tsx`, `RecordTabs.tsx`, `Metric.tsx`,
     `StatusBadge.tsx`, `ReadinessChecklist.tsx`, `EmptyState.tsx`,
     `ErrorState.tsx`, `SourceFreshness.tsx`.
   - `MoneyCell.tsx`, `MarginCell.tsx` (tabular-nums, right-aligned).
   - Toast provider wired at root.
5. Theme + density stored in `sessionStorage`; System reads
   `prefers-color-scheme`; Reduced motion respected.
6. Update `web/src/main.tsx` and `App.tsx` to use the new AppShell and
   re-map every current route into the grouped nav from the spec §3.
7. Test-setup: existing vitest tests still pass. Add ~10 new tests for
   AppShell + GlobalSearch + ProfileMenu keyboard/a11y.

## Constraints
- DO NOT delete `web/src/ui/*` yet — pages currently import from there.
  Wave 2 agents will migrate.
- DO NOT touch any `api/**` code.
- DO NOT rewrite existing pages in this wave — only rewire routes into
  the new AppShell. The existing pages render as-is inside the new frame.
- No remote font CDN — bundle Inter via `@fontsource/inter`.
- Reduced motion + focus rings mandatory (WCAG 2.2 AA).

## Notes
- Blueprint §21 says preserve the existing app framework; this wave adds
  shadcn/ui without ripping the app apart.
- Old `web/src/ui/*` primitives get deleted at the end of Sprint 8 once
  every page has migrated.
