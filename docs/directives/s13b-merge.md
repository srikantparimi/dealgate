# Directive S13b-merge: integrate `feat/s13b-gm-panel` onto post-S13a `main`

From: Kanna Parimi, product owner. 21 September 2026. Runs after S13a
closure (`8328e5e`). Subject: branch `feat/s13b-gm-panel`, latest commit
`2095a24`, authored externally in worktree
`/Users/srikanthparimi/OfficeApp/dealgate-s13b`. Treat it as an external
contribution: integration and proof, not re-authorship.

## Execution order

1. **Rebase** `feat/s13b-gm-panel` onto `main` (post-`8328e5e`). Resolve
   conflicts with this policy:
   - **`main` wins** on infrastructure — `OwnerRef`, `client_resolver`,
     the deletion + archive paths, `ensure_user` Cognito hydration, the
     dev-seed endpoint, cleanup helpers.
   - **The branch wins** on the S13b feature UI — GM panel component,
     staffing/confirm grid columns, direct-cost section, signatories
     name resolution component.
2. **Directive-compliance review** of the full rebased diff, BEFORE
   running any test. Report findings per the checklist:
   - One GM engine — no client-side margin math (CLAUDE.md rule 2).
   - Reimbursable direct costs are pass-through (excluded from revenue
     AND delivery cost); non-reimbursable enters the GM.
   - Display rules: 1 decimal %, whole-dollar money, tabular numerals,
     "Not applicable — no India resources" copy, chip consistent with rows.
   - One shared panel component across Staffing / Confirm / approver
     package / CEO brief (CLAUDE.md §"Where things live" → `web/src/ui/`).
   - Direct costs versioned with the GM model (rule 4: immutable).
   - Every direct-cost field carries provenance (rule 10).
3. **Full regression gate** (post-review, pre-merge):
   - `pytest` — all suites including the S3+ GM goldens, byte-identity
     tests, no-phantom-seed grep, `test_deletion.py` +
     `test_client_resolver_normalisation.py` (including the archived-
     resolver regression).
   - `vitest` — full run; the pre-existing `StaffingGmSection`
     S13b-branch failure must be resolved (the branch owns this file).
   - `scripts/no-stubs.sh` clean.
   - Both Playwright specs (`19-two-store-consolidation-*` and
     `20-s13a-delete-and-archive`) green against staging after the
     API + web image deploy.
4. **Browser-prove S13b DoD** on staging (per `s13b-gm-panel.md` §DoD):
   - Confirm grid shows Cost /hr $120.00, bill rate `— fixed price`.
   - GM panel matches the ASCII block; no raw decimal renders (add a UI
     assertion for `/0\.\d{6,}/`).
   - Add a non-reimbursable direct cost → GM updates; add a reimbursable
     travel line → GM unchanged, pass-through subtotal appears.
   - India = "Not applicable"; chip = "Passes US floor".
   - Direct costs round-trip via save, show in the approver package and
     the exported XLSX, versioned with the GM model.
   - Signatories list shows names, not UUIDs.
   Screenshots to `docs/reports/s13b/`, report at `docs/reports/s13b.md`
   with a section "changes made to the external branch and why".
5. **Squash-merge** only after 1–4 are green, then delete the branch.
   **Partial = stop and name the blocker.** Do not merge a partial
   slice; the DoD is unforgiving.
