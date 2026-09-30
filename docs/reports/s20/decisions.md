# S20 · decisions log (autonomy = §0.7)

Every open choice tonight lands here, dated, with reversal notes. D1–D10
are fixed in the directive and not choices. This file grows as workers
integrate and the Lead applies patches.

Format: `## <id> · <one-line title> · <UTC timestamp> · <owner>` then:
- **Decision:** what was chosen.
- **Options considered:** the plausible alternatives.
- **Chosen because:** the reasoning.
- **How to reverse:** exact steps.

---

## D-ISO-01 · HubSpot token stays read-only for tonight · 2026-09-30 05:03 UTC · Lead

- **Decision:** Do not request `crm.objects.deals.write` for tonight's
  runs. Every worker treats HubSpot as read-only. J6 Playwright observer
  spec stays observer-mode; the S19 J6 team session tomorrow authors the
  deal in the HubSpot UI, not via the API.
- **Options considered:**
  1. Ask Kanna for a wider token overnight → violates autonomy, requires
     PO approval.
  2. Request a separate write-scoped token via a new private app → same,
     plus a token-rotation risk to the read-only path.
  3. Stay read-only tonight → **chosen**.
- **Chosen because:** The isolation guarantee (§5) is stronger with a
  read-only token. Every worker's tests already run against synthetic
  fixtures in staging RDS + Cognito; none need to mutate the portal.
- **How to reverse:** Kanna generates a private app with
  `crm.objects.deals.write`, drops the token into `dealgate/staging/
  hubspot_token_write` (separate secret). Nothing in code assumes this
  token exists; only the J6 creator path would use it.

## D-BRANCH-01 · integrate/s20 pushed to origin · 2026-09-30 05:00 UTC · Lead

- **Decision:** `integrate/s20` was pushed to origin so workers in
  separate worktrees can pull from a single collector branch.
- **Options considered:**
  1. Local-only integrate branch, cherry-pick from worker worktrees →
     works but doesn't preserve the "each worker has a real remote
     branch" review property.
  2. Push integrate/s20 + push each `s20/W*` when workers finish →
     **chosen**.
- **Chosen because:** Matches directive §2 ("workers in git worktrees on
  branch s20/W* off integrate/s20"). Kanna can inspect any worker's raw
  commits without asking the Lead to unpack them.
- **How to reverse:** `git push origin --delete integrate/s20 s20/W1
  s20/W2 …` after Kanna's click-through and (optionally) a squash-merge
  to main. Nothing is pinned to these refs long-term.

---

Workers append below this line as their scope surfaces choices.

## D-W3-01 · CEO exception field reads "Not required" when policy is met · 2026-09-30 07:30 UTC · W3

- **Decision:** When `floors.requires_ceo` is false (policy is met), the
  workspace and CommandCenter both render the string "Not required" for
  the CEO exception. Never blank, never "unavailable", never "Not
  applicable". When `requires_ceo` is true, render the full detail
  (business case, shortfall, limits, conditions, expiry, SOW/GM/policy
  versions) per T20.
- **Options considered:**
  1. Leave the row hidden when not required → user cannot tell whether
     the policy was checked or whether the check simply failed to render.
  2. "N/A" or "—" → same defect: no signal that the check ran.
  3. "Not required" — **chosen**.
- **Chosen because:** T20 in the review explicitly requires "Not
  required" as the wording (§"Additional acceptance checks for approvals
  and operations" T20). The status vocabulary in `contracts.md` §1
  reserves "Not applicable" for undefined behaviour; "Not required" is
  the specific, verified-negative answer.
- **How to reverse:** revert the wording change in
  `web/src/pages/v2/sow-workspace/readiness.ts` and `SignatureTab.tsx`
  and `CommandCenter.tsx`.

## D-W3-02 · SOW workspace renders an "Upload SOW" empty state when no SowVersion exists · 2026-09-30 07:35 UTC · W3

- **Decision:** `/sows/:id` — when `getCurrentSowVersion(id)` returns
  null, the page renders a bordered card ("No SOW draft for this deal
  yet") with an "Upload SOW" CTA that navigates to
  `/sows/new?opportunityId=<id>` and a "Back to deal" secondary link to
  `/deals/:id`. The full workspace shell (tabs, readiness, Delete SOW)
  is not rendered.
- **Options considered:**
  1. Auto-redirect to `/deals/:id` → the route is retired today and
     doesn't have a real deal page yet (W2's scope, requested in
     `requests.md`).
  2. Show the whole workspace shell with "No SOW draft uploaded yet"
     and a disabled Complete scope + enabled Delete SOW → this is the
     bug L09/L11 documents.
  3. Empty state card with Upload SOW + Back-to-deal — **chosen**.
- **Chosen because:** review §"Deal workspace" says a deal without a
  SOW must remain useful. The empty-state card is a bridge: it doesn't
  claim a SOW exists (no Delete), it names the primary action
  ("Upload SOW") and it offers a route back to the deal (or Pipeline
  when W2's page isn't ready). CLAUDE.md rule 11 forbids visible
  controls that don't work; Delete SOW on a non-existent SOW would be
  exactly that.
- **How to reverse:** revert the changes in `SowWorkspace.tsx` — the
  workspace shell renders again.

## D-W3-03 · Stub archive execution is deferred; dry-run manifest only · 2026-09-30 07:40 UTC · W3

- **Decision:** Tonight's stub-migration output is the dry-run manifest
  at `docs/reports/s20/stub-manifest.csv` (produced by
  `scripts/sow_stub_dry_run.py`). The archive itself does not run
  tonight. Lead + PO review the manifest tomorrow and decide whether to
  run the archive.
- **Options considered:**
  1. Execute the archive tonight after the dry run → directive §0 says
     "no merge to main tonight" and §6 explicitly says "Lead reviews the
     dry run before execution".
  2. Dry run + archive under a feature flag → adds surface area that
     will be re-decided tomorrow anyway.
  3. Dry run only, manifest committed — **chosen**.
- **Chosen because:** matches directive §6 step 5 ("archive proven-empty
  stubs") behind Lead approval. Rollback is trivial (no rows moved).
- **How to reverse:** N/A — nothing was archived. The script runs
  read-only.

## D-W3-04 · SignatureTab drops the NDA/MSA check row per D3 · 2026-09-30 07:45 UTC · W3

- **Decision:** Per contracts.md §D3, NDA/MSA are two independent facts
  (`on file` + `signed/verified`) and neither blocks review or
  submission. `require_signature_eligibility` in
  `services/approval_workflow.py` already does not gate on them
  (verified at line 255-256 "S17: NDA/MSA coverage no longer gates
  signature"). The SignatureTab check list drops the NDA/MSA row
  entirely — no explicit code check exists to preserve.
- **Options considered:**
  1. Keep the row as a status-only note → visually implies a check
     ran, contradicting D3.
  2. Move it into the record header as an information chip → already
     there (`SowWorkspace.tsx:221-226` renders the NDA/MSA marker
     status).
  3. Remove from the SignatureTab list — **chosen**.
- **Chosen because:** review L13 ("SOW's readiness says NDA/MSA is note
  only and nothing is blocked; Signature lists NDA/MSA among Held
  reasons") is the exact defect. The header already shows the
  marker; the check list should only list actual gating checks.
- **How to reverse:** re-add the row in `SignatureTab.tsx`.

