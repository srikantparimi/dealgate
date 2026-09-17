# UI kit

Every page in DealGate assembles from these primitives so pages built by
different agents look like one product. Sprint 0 shipped the shell and the
status chip. Sprint 1 (S1-E2) adds table, empty state, error state, page
header and primary nav. Sprint 3 adds the approval card. See
`docs/build-guide.md` §13.

## Primitives

| File            | Purpose                                          |
| --------------- | ------------------------------------------------ |
| `AppShell.tsx`  | Frame: brand, primary nav slot, user info, body. |
| `StatusChip.tsx`| Governance / coverage state pill.                |
| `Nav.tsx`       | Primary nav links (uses `react-router-dom`).     |
| `PageHeader.tsx`| Title + subtitle + right-slot for actions.       |
| `Table.tsx`     | Generic `<Table columns rows onRowClick>`.       |
| `EmptyState.tsx`| Zero-row / empty panel placeholder.              |
| `ErrorState.tsx`| Fetch or mutation failure surface with retry.    |
| `DateRangePicker.tsx` | Since/until date input pair for filter bars. |
| `DiffCell.tsx`  | Collapsible before/after JSON diff for tables.   |
| `FilterBar.tsx` | Layout row for filter inputs; ships `Pager` for Prev/Next. |
| `Modal.tsx`     | Centered dialog with backdrop + Escape close.    |
| `Drawer.tsx`    | Right-anchored slide-out panel for edit surfaces.|

## Rules

- No business math in the browser. Format numbers here; compute nowhere.
- No API calls from primitives — pages compose primitives + a page-level
  data hook.
- Every primitive is exported with a stable prop shape; don't inline styles
  in pages.
