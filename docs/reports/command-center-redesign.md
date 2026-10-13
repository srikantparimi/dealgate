# Command Center redesign evidence

Status at 2026-10-13 01:27 PDT: **implemented and connected locally; staging
pending**. Authoritative branch `feat/command-center-redesign`, worktree
`/Users/srikanthparimi/OfficeApp/dealgate-command-center-redesign`. No merge to
`main` is permitted before product-owner acceptance.

| # | Acceptance condition | Local evidence | Staging |
|---|---|---|---|
| 1 | Stage 4 excluded; Stage 5+ included per ordered pipeline | Backend `test_stage5_is_resolved_per_pipeline_and_not_from_stage_ids`; connected Playwright sees Stage 5/6 and excludes Stage 4 | Pending |
| 2 | SOW state does not affect sales-stage eligibility | `test_sow_governance_does_not_change_sales_stage_eligibility` | Pending |
| 3 | Per-pipeline threshold; unknown/unlinked/unconfigured rows excluded; gaps explicit | `test_unknown_unlinked_lost_and_unconfigured_rows_are_explicit` | Pending |
| 4 | Server search, filters, paging and CSV use one eligible population | Backend search/paging/CSV test; connected BU/owner filters and CSV download; unique opportunity IDs asserted | Pending |
| 5 | Reset preserves visible Stage-5 constraint | UI unit and connected browser assertions | Pending |
| 6 | Other dashboard populations are not Stage-5-restricted | `test_overview_keeps_stage4_in_its_population_while_accounts_do_not`; connected open value includes Stage 4 | Pending |
| 7 | Actions and cards open owning records with return context | UI drawer destinations and connected deal-link assertion; router state carries `from` | Pending |
| 8 | Established financial/capacity services; missing data is unknown | Real forecast test independently verifies $90,000 - $26,400; missing-cost test; People allocation integration test; connected 62.5% GM | Pending |
| 9 | Independent loading/empty/error behavior | UI tests prove an overview failure keeps the table and a table failure keeps the overview; source gaps render explicitly | Pending |
| 10 | Responsive, keyboard-operable layout and focus-contained drawer | Connected 390px containment, desktop/mobile screenshots, named controls, Radix Sheet Escape test | Pending |

## Focused verification

```text
Ruff: clean
Backend: 12 passed
Frontend TypeScript: passed
Frontend related suites: 46 passed
Connected Playwright: 2 passed (14.9s)
```

Connected local data is isolated in `dealgate_command_center`. The guarded
fixture `scripts/command_center_fixture.py` refuses any other database and
contains only synthetic HubSpot-mirrored records. The observed eligible table
contains exactly Stage Five Account and Stage Six Account; Stage Four Account
remains in the broader business pulse and is absent from the table. Financial
evidence shows $90,000 committed revenue, 62.5% GM and $224,000 weighted
unsigned potential. Workforce values remain explicitly unknown in this fixture
because it intentionally has no current demand or supply publication; focused
service coverage proves current publications populate required, allocated and
uncovered FTE without frontend calculation.

Artifacts:

- `docs/evidence/command-center/command-center-desktop.png`
- `docs/evidence/command-center/command-center-mobile.png`
- `api/tests/test_command_center_accounts.py`
- `tests/e2e/local/command-center-redesign.spec.ts`

## Remaining release gates

1. Production build after the final local checkpoint.
2. Immutable API/worker image and reviewed Terraform-owned staging plan.
3. Staging migration/image/frontend/smoke and connected browser proof.
4. Product-owner click-through and explicit acceptance.
5. Only then merge to `main` and verify the resulting main-image deployment.
