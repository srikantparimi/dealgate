# Directive S16: cut the dead weight, simplify agreements, then HubSpot for real

From: Kanna Parimi, product owner. Commit as `docs/directives/s16-cleanup-hubspot.md`. Two phases, in order — S16a ships and merges before S16b starts. New standing rule first.

## CLAUDE.md rule 14 — branch discipline (adopt now)

All work happens on a feature branch. The branch deploys to staging, `scripts/deploy-smoke.sh` is green, the slice's own proof passes, and for user-facing slices the product owner has clicked through it — only then does it squash-merge to main. Main is always releasable. (This is what we already converged on; it's now written down.)

## S16a — Cleanup and simplification

**1. Delete the legacy pages, and their backends where nothing else uses them.**
Routes /tasks, /deals, /gm/sandbox and the Margin lab page. Procedure per page: grep the SPA for route references, grep the API for endpoints only that page calls, check staging access logs for the endpoint paths (last 30 days) — then delete route, components, nav entry, and orphaned endpoints/tables together. The GM **engine** is shared and stays untouched — only Margin-lab-specific endpoints and scenario storage go. Records are never deleted: anything historical those pages displayed stays in the DB and audit trail. List every deleted file and endpoint in the report.

**2. NDA & MSA: tracking, not approvals.**
These are standard documents — no approval workflow, no review ceremony. The register simplifies to per-client-legal-entity status tracking:

- States: missing → requested → sent for signature → executed (with file + dates) → expiring/expired. Owner and next-action per record stay.
- Remove any approve/reject routing on agreements; Legal owns the records, nobody "approves" them.
- The one behavior that matters: **when a new company appears (HubSpot or SOW upload), the first check is "do we have a signed NDA and MSA?"** If not, auto-create the "obtain NDA/MSA" task to the account owner, and the client row shows the gap. Executed NDA+MSA remains the gate for SOW *signature* (not for review) — that rule is unchanged.
- Uploading a signed NDA/MSA file: same extraction pipeline, filed against the legal entity, sets state to executed with dates. Done.

**3. Delivery & actuals → "Projects".**
Rebuild the page to exactly three things: running projects (signed/released SOWs), the resources tied to each (from the staffing baseline), and GM (approved vs forecast). Nothing else — strip the reconciliation panels, import status widgets, and anything the page currently shows beyond those three. The removed data stays in the API for later; this is a page simplification, not a data deletion.

**4. Navigation after the cut:** Command center, My work, Pipeline clients, AI discovery, NDA & MSA (simplified), SOW approvals, New SOW studio, Projects, Renewals, Signed handoff, Reporting, Settings. Legacy section gone entirely.

**Proof:** deleted routes 404 into a friendly redirect, nav shows the new list, NDA/MSA simplified register works on a fixture client, new-company-without-agreements creates the task, Projects page shows a released fixture SOW with resources and GM. Smoke green. Kanna clicks through before merge.

## S16b — HubSpot: pull the real pipeline

Goal: every deal in SmarTek21's HubSpot becomes a DealGate opportunity, and stays in sync.

**Kanna's one setup action:** create a HubSpot **private app** (Settings → Integrations → Private apps) with read scopes only — `crm.objects.deals.read`, `crm.objects.companies.read`, `crm.objects.owners.read`, plus webhook subscriptions — and paste the token to the agent, who stores it in Secrets Manager via Terraform. **Read-only for now:** no write-back to HubSpot from staging; the three governance write-back properties wait for production. This makes connecting the live portal safe.

**Build:**
1. Initial backfill: pull ALL deals with company and owner associations, paged; upsert by `hubspot_deal_id` (unique — already in the model); companies through the client resolver (live-records rule, archived-aware); owners mapped by email to DealGate users, unmatched → "Unassigned" with task. Idempotent — rerunning changes nothing.
2. Webhooks: deal create/update/delete → API Gateway (signature verified) → SQS → worker re-reads the deal from the API (never trusts the payload). Deleted/merged deals archive locally, never hard-delete.
3. Nightly reconciliation catches missed events; drift shows on System health, not silently.
4. On new company: the NDA/MSA check from S16a fires — this is the integration's first business value.
5. Pipeline clients page now shows real deals: HubSpot stage, owner, agreement status, next action, source = "HubSpot".

**Proof:** backfill run against the live portal with counts (deals pulled / clients created / matched / unassigned); create a test deal in HubSpot → appears in DealGate within 2 minutes with the NDA/MSA task; edit it → change syncs; rerun backfill → zero duplicates. Screenshots of Pipeline clients showing the real pipeline. Kanna verifies his own deals look right before merge.

**Out of scope for S16b:** write-back, HubSpot pipeline-rule enforcement, and the AI adviser's HubSpot note — all later slices. Report per phase, standard format.
