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
