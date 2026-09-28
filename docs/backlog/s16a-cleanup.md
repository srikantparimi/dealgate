# S16a acceptance

Source: `docs/directives/s16-cleanup-hubspot.md`. S16b does not start until
this phase ships, receives product-owner click-through, and merges.

1. Given an authenticated user, navigation contains the twelve S16 destinations
   permitted by their roles, no Legacy section and no Margin lab. Old tasks,
   deals and sandbox URLs show a friendly not-found view with a current-workspace
   link. Existing in-app links use current routes. Shared APIs and GM math remain.
2. Given Legal, the NDA/MSA register tracks missing, requested, sent for signature,
   executed, expiring and expired records per legal entity, with owner/next action.
   It has no approval or rejection columns/actions. A signed file uses the shared
   extraction path, pre-fills source-backed dates, and is filed as executed only
   after Legal confirms the extracted dates and signed evidence. Other roles
   may read but cannot mutate. Historical states/files/audits are retained.
3. Given a newly resolved company from SOW upload or HubSpot intake, missing NDA
   and MSA produce idempotent obtain-agreement tasks for its account owner.
   Replaying intake creates no duplicate tasks. Executing an agreement completes
   its gap task. Coverage never blocks functional review, but blocks signature.
4. Given a released SOW, Projects shows its client/project, frozen staffing
   resources and server-computed approved versus latest forecast GM. Drafts and
   unsigned SOWs are absent. No actuals-import/reconciliation controls appear;
   those APIs and historical data remain. Cost visibility matches existing roles.
5. Backend/unit/browser checks and deployed smoke pass. Staging proof and product
   owner click-through are recorded before merge, never inferred from local tests.

Manual fields: Legal's confirmation of signed evidence cannot be inferred from
AI output. Corrected dates require an explanation; agreement owner/next action
are operational assignments unavailable from the document. New-company task
owners are looked up from the opportunity, never guessed from extracted text.
