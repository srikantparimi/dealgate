# S20 · progress log for W3 (owned by W3)

**Scope reminder:** see `docs/directives/s20-overnight.md` §2, and
`docs/reports/s20/contracts.md` §6 for file ownership.

Update after every commit on `s20/W3`.

Sections:
- **Decisions / notes:** what was decided while working.
- **Files touched:** paths (owned + patches requested via requests.md).
- **Proven:** tests passing, evidence links.
- **Next:** what would come after the current step.
- **Blockers:** hard block only (per §9). Everything else keeps moving.

---

## Cycle 0 · spawn · 2026-09-30T06:31:31Z

Not started yet.

## Cycle 1 · orient · 2026-09-30T07:00Z

**Findings from reading the code before touching anything:**

1. **L09/L11 "auto-creation of empty SOW workspaces"** is *not* a server
   auto-creation defect. The three call sites that construct a `Sow` row
   (`sow_extract._load_or_create_sow`, `sow_upload_job_service:390`,
   `sow_upload_pipeline:355`) all sit inside an explicit upload path. The
   HubSpot intake / backfill never touches `Sow`. The empty workspace is a
   **UI/routing defect**: `web/src/pages/v2/RetiredPage.tsx:11` retires
   `/deals/:id` and forwards to `/sows/:id`, so any deal without a SOW
   presents the SOW workspace shell with a disabled "Complete scope" and
   an enabled "Delete SOW" — see `SowWorkspace.tsx:257-283`. Fix path:
   render an empty-state at `/sows/:id` when no `SowVersion` exists (no
   Delete, no disabled Complete), plus request W2 to build a real
   `/deals/:id` deal detail page in `requests.md`. In the meantime the
   RetiredPage sends to `/pipeline` when a deal has no SOW so the user
   isn't stranded in a phantom SOW workspace.

2. **`Sow.opportunity_id` is `unique=True`** (see `models/sow.py:30-32`).
   D1 says "many SOWs per deal". Migration request landed in
   `requests.md` — Lead applies. Rollup helper (`services/sow_rollup.py`)
   built to be forward-compatible with multi-SOW: today it collapses to
   at-most-one row per deal; after the migration it aggregates every SOW.

3. **`ApprovalPackage.package_hash` already exists** (`models/approval.py:65`).
   The stale-tab refusal (T19) needs the decide endpoint to require
   `package_hash` in the body and 409 when mismatched. No migration
   needed.

4. **Material-change → invalidation is already wired** via
   `approvals_hooks.on_sow_version_created` and `on_gm_model_created`
   (called from `sow_extract.create_sow_version:318` and
   `delivery_model.py:844`). T21 covered by existing code; regression
   test added for evidence.

5. **NDA/MSA are NOT server-side signature gates** — verified in
   `approval_workflow.require_signature_eligibility:255` ("S17: NDA/MSA
   coverage no longer gates signature"). Per D3 the SignatureTab check
   list drops the NDA/MSA row (readiness note stays; it's client-scoped
   context, not a workspace check).

6. **Readiness rendered twice**: `SowWorkspace.tsx:311-329` renders a
   Readiness aside AND `OverviewTab.tsx:128` renders a
   `ReadinessChecklist`. Removing the OverviewTab copy is D1 §L10.

**Files touched this cycle:**
- `docs/reports/s20/requests.md` — three requests to Lead (see below).
- `docs/reports/s20/decisions.md` — CEO exception "Not required" wording,
  and CTA state machine choice.

**Next:** priority-order execution:
1. Empty SOW workspace state (L09/L11) + RetiredPage fix.
2. Upload binding (T11/T37) — accept `client_id` + `opportunity_id`.
3. Dedupe readiness (L10).
4. Rollup service (D1) + stale-hash refusal (T19).
5. Stub migration dry run.
6. Deletion by state (D6) + CEO exception "Not required" (T20).

**Blockers:** none.

