# Product owner click-through, 2026-10-01, staging rev 62–64

Screenshots taken by Kanna Parimi. Each maps to items in `docs/directives/s21-click-through-fixes.md`.
Rule 18: every item's Playwright test reproduces the path shown here and asserts on what is visible in the screenshot.

| file | screen | directive items |
| --- | --- | --- |
| 01-pipeline-clients-owner-filter.png | /pipeline, Owner = Adil Lalji, Status = Open; chips total 13 deals; Clients view lists all 187 with "Matching / total open 0", "Account owner Not set", "No owner" on every row; "Clear 2 filters" with no chips; `HS #…` under names | 9, 10, 11, 12 |
| 02-deal-page-shoot360.png | /deals/{id} "Shoot360 - Payment Integration": breadcrumb shows a UUID; Pipeline shows `710688094`; Business unit `—`; Next action and Latest comment are read-only text; Upload SOW present | 12, 13, 14 |
| 03-staffing-rates-hours-required.png | SOW studio Staffing & rates: Hours is a required typed field; row rejected without it; GM empty | 15 |
| 04-sow-overview-blanks.png | SOW workspace Overview (Liberty Mutual): "ID f2033a7a", "Owner Unassigned", "Term 10/12/2026 to April 12th", "Next action Not scheduled", "Commercial type Unknown" | 4 |
| 05-sow-header-scope-tab.png | Same workspace, Scope tab; no Back control in the studio flow | 3, 2 |
| 06-approvals-before-submit.png | Approvals tab before submit: "No reviews submitted", no routing shown, no editor; "Delete SOW" present | 5, 6, 1 |
| 07-approvals-after-submit-e2e-bot.png | Approvals after submit: "Finance · Queued for E2E Staging Bot"; "Legal: no eligible reviewer. Owner: SystemAdmin"; "Submitted by Unassigned"; raw hash `4019ee5ddac9`; button now "Archive SOW" | 7, 6, 1, 12 |
