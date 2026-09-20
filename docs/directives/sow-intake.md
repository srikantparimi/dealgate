# Directive to the DealGate build agent: SOW intake and bulk import

From: Kanna Parimi, product owner. Date: 19 September 2026. This overrides any earlier story, estimate or "pilot" framing.

## Read this first

DealGate is a production system, not a pilot. Every screen that exists must work end to end in the browser against the real backend. A visible button that throws "not wired yet" is not partial progress; it is a defect that misleads the people testing the system. Do not ship one, do not leave one, do not describe one as "the right shape". Build the path or remove the button.

Your last report was accurate about the cause and wrong about the response. When you find that a feature is unwired, the answer is to wire it in the same story, not to write a paragraph about why it is sizable. The scope you described (one endpoint, a panel rewrite, tests) is a normal story. Do it.

## Defect 1: the upload button

`ready = Boolean(selected && file)` is the wrong contract. The SOW is the input. The client is read from the SOW, not chosen from a dropdown before upload. Requirements:

1. The only precondition for "Upload & extract" is a file. No client selection, no opportunity ID, no HubSpot deal.
2. After extraction the system resolves the client legal entity from the document: match against existing clients by legal name, domain and known aliases (fuzzy, with a confidence score). Match ≥ 0.85: link. Below: show the top three candidates plus "Create new client", pre-filled from the document. Never a blank search box as a gate.
3. If no opportunity exists for that client and scope, create one. Mark it `source = sow_upload`, `hubspot_deal_id = null`. The nightly HubSpot reconciliation job later links it by company and name, or raises a "not in HubSpot" task for the account owner. A missing HubSpot deal never blocks SOW processing.
4. A non-SOW file (a résumé, an invoice, a random PDF) must return a clear result: "This file does not look like a SOW. Detected: résumé." with the option to override. The document-type check is step zero of the pipeline. A grey button is not an error message.
5. The endpoint you described is required: `POST /sows/upload` → presign S3 → create `sow` + `sow_version` (file hash, uploader, timestamp) → enqueue extract → return `sow_id` and a job ID the UI polls. Follow with classify, rate-card resolution, staffing derivation, GM calculation and routing exactly as `docs/sow-first.md` specifies. The UI shows progress per step and lands on the confirmation screen.

## Defect 2: no way to load the contracts we already have

SmarTek21 has live contracts and SOWs today. A system that only governs new SOWs forces one set of deals outside and one inside, which is the situation we are trying to end. Build **Bulk SOW import** as a first-class screen under Settings & controls → Data imports, and link it from the SOW approvals board.

Requirements:

1. Drop many files or a ZIP. Each file becomes a job in a queue with its own status row: queued, extracting, classifying, matching client, deriving GM, needs review, imported, rejected, duplicate.
2. Every file runs the same pipeline as a single upload. No separate "legacy" code path. One pipeline, two entry points.
3. Dedupe on file hash first, then on client + title + term dates. A duplicate is logged and linked to the existing record, never silently dropped and never imported twice.
4. Imported SOWs carry `governance_status = legacy_not_evidenced`. Do not fabricate approvals. If the SOW is executed (signature page detected or user confirms), set execution state accordingly and create the renewal schedule, notice-deadline task and 30/14-day escalations from the term dates immediately. A SOW already inside its two-month window opens a renewal review on import.
5. Build the GM baseline for each imported SOW from the same derivation: client rate card (create a placeholder card flagged "unverified" if none), HR cost bands, staffing from the SOW. Where staffing cannot be derived, the GM sheet is `incomplete`, listed on the Finance dashboard as missing cost input. Never zero.
6. Create or link the client, legal entity, opportunity (`source = bulk_import`), and agreements (NDA/MSA if the file is one; the same importer accepts MSAs and NDAs and files them against the legal entity).
7. Persist an **import log** the user can open later: batch ID, who ran it, when, each file's name, hash, size, detected type, matched client, created or linked record IDs, confidence scores, warnings, errors, and a link to the record. Exportable as CSV. Re-running a batch is idempotent.
8. A "Needs review" queue lists every imported record with a `needs you` field, in the same confirmation screen used for single uploads. Reviewers clear them one by one; nothing else in the system waits for that.
9. Executive dashboards, client pages, renewals and reporting include imported SOWs from the moment they land, with a "legacy" chip. That is the point: one set of records.

## Definition of done for this work

All of the following pass as browser tests against the deployed staging environment, not mocks:

- Upload a résumé → rejected with the "not a SOW" message; no record created.
- Upload one SOW for a client that does not exist → client, legal entity, opportunity, SOW version, GM sheet and approval routing are created; the confirmation screen shows provenance on every field; no HubSpot deal required.
- Upload the same file again → flagged as a duplicate, linked, not re-created.
- Bulk import of the six fixture SOWs plus one MSA plus one duplicate → eight status rows, seven records, one duplicate; the MSA is filed against its legal entity; the log is complete and exportable.
- A fixture SOW expiring in 45 days → renewal review, weekly nudges and notice task exist immediately after import.
- Client page for an imported client shows the SOW with approved GM `incomplete` or calculated, renewal date, and the legacy chip.
- `grep -r "not wired" api/ web/ worker/` returns nothing. The same for `TODO: stub`, `throw new Error("Not implemented")` and equivalents. Add this grep to CI.

## How to report from now on

For each story: what a human can do in the browser on staging, in one sentence; the test file that proves it; what is not done, if anything, as a blocker with an owner. No "sizable but the right shape". No pilot language. If something needs a decision from me, ask the question in `docs/questions.md` and keep building everything that does not depend on it.
