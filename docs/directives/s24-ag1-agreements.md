# S24-AG1 — NDA & MSA (Agreements): upload, attach, one-time backfill, net-new warnings

Branch `feat/s24-ag1` from main (use the newest main; if the S23-PL2 Pipeline work is not merged yet, stop and tell Kanna, because this work edits the Pipeline workspace code PL2 rewrote). **Start only after Kanna has clicked and approved the prototype.**

Source of truth, in this order: (1) this file, (2) `docs/reference/openapi-agreements.yaml`, (3) `docs/reference/prototype/dealgate-agreements.html` (approved clickable prototype: behaviour, information and copy; open it in a browser and use both "Data" modes, all three "Viewing as" roles and both "HubSpot msa_type" modes). Build with the app's own component kit and tokens, not the prototype's CSS. Do not redesign. Any deviation goes in `docs/bugs/s24-ag1.md`.

The discovery report (S24-AG0, `/tmp/agreements-discovery-*.md`) is the factual base. Its numbers are staging aggregates at discovery time; re-read them before you compare, because the nightly sync moves them: 208 clients; 47 with a Closed Won deal; 32 with an SOW or engagement; 70 existing (9 are in both lists); 138 net new, of which 9 have deals only in stage 1, 21 have a deal in stage 2 or later, 108 have only Closed Lost deals or none; 41 clients with an open deal in stages 2 to 6 and no file (42 with Hold); the old "Agreement gaps" card shows 53; 0 agreement rows; both agreement tables empty.

## What Kanna decided (record these in `docs/questions.md` as answered, per CLAUDE.md rule 1, before you build)

1. **Documents.** He uploads the standard NDA and the standard MSA once and attaches them in bulk to **existing clients and to the clients currently in the pipeline past stage 1** (the same step; he added this after the prototype was first published). Those pipeline clients stay net new but show "Standard copy" and are no longer flagged. Any other net-new client brings its own copy, uploaded per client. **Any client at any time can be given its own updated copy** (for example a slightly changed MSA agreed for that client) with an optional note; it replaces the standard copy for that client only, and the earlier version stays in history. He can also mark a kind covered, remove it, or change a client's relationship by hand whenever something changes.
2. **Existing client.** A client the company has worked with before (so the NDA and MSA are already in place): HubSpot has a Closed Won deal for it, or DealGate has any SOW or engagement for it (including the 81 forecast-model engagements). Everyone else is net new. **Refinement for you to build and for Kanna to confirm in the click-through:** this is judged **as of a cutover date** (the first real batch run), and the result is stored. Without that, a net-new client's first Closed Won deal would turn it into "existing" and drop its warning at the moment it signs. After the cutover a later win or SOW never changes a client from net new to existing (see `components.Cutover` in the contract).
3. **Enforcement.** **Warn and flag only.** A net-new client past stage 1 with an NDA or MSA missing is flagged in the Pipeline, the Command Center and the client panel. Nothing is blocked anywhere.
4. **Backfill scope.** Every existing client plus every net-new client past stage 1 (requirement `required`), except clients whose deals are only in stage 1 and test data. The admin can include or leave out any client in the dry run.
5. **Who.** Legal and SystemAdmin upload, replace, detach, mark and change relationship. SystemAdmin alone runs and undoes batches and saves the HubSpot mapping. Every role can view and download (as today). Sales roles get no write controls.
6. **HubSpot `msa_type`.** DealGate is the source of truth and Kanna wants to be able to leave HubSpot one day. If HubSpot already knows an MSA is in place, use it as a hint that an admin maps to "covered"; an admin or Legal can always mark the status in DealGate by hand, and DealGate's record always wins. Marks made from HubSpot are stored in DealGate and stay if HubSpot is switched off.
7. **Defaults taken unless Kanna objects:** the e2e test client is excluded from the backfill; the two "Unknown company" placeholders count as net new and are only flagged; duplicate clients are flagged, never merged; the 58 forecast-model engagements on 18 clients with no HubSpot link keep the clients they have (two possible name matches are listed in your report for Kanna, not linked by you); the SOW upload's "NDA and MSA are signed" checkbox is left exactly as it is; NDA and MSA downloads are audited.

Also fix `docs/blueprint.md:14`, which still says a missing NDA or MSA blocks signature (S17 removed that and this decision confirms warn-only).

## Rules (they apply every time)

1. **No session token or time budget. Do not get stuck.** One bounded attempt per issue; if it does not yield, log it in `docs/bugs/s24-ag1.md` with what you tried and move on. Finish ALL fundamental code first (code-complete: every B and F item), then test (T items), then fix the logged bugs one by one, each recorded in the file. Efficient and quick.
2. **Anti-glossing.** Report **every** numbered item (D1-D17, S1-S19, B1-B15, F1-F12, T1-T14) by its number in exactly one of five states: **verified working / fixed and tested / missing / blocked / deferred**, each with proof (test name and result, request and response, screenshot path, or file:line). Only D and S items marked DEFERRED or REPORT ONLY below may use "deferred". A "complete" or "zero deferrals" summary may not replace the list. An item missing from your report counts as not done.
3. **Heartbeat.** One line at every step boundary and at least every 15 minutes while a long command runs: `AG1 · item · result · next`.
4. CLAUDE.md applies: rule 12 no infra via console or CLI, rule 14 branch → staging → smoke → Kanna's click → squash merge, rule 15 never a scripted-yes terraform, rule 17 parallel lanes, rule 18 any click-through finding becomes a failing Playwright test first. Test data stays under run tags and the leak gate. Never render a raw id. Never invent a number: a missing value shows its reason, never a zero. The HubSpot token is test-only and is never printed, logged, committed or reused.
5. **Never run a real (non-dry) batch against staging data, and never upload a real document there.** Staging holds the real client list. You prove the batch on a Postgres test database with fixtures (T5). Kanna uploads the standard documents and runs the one-time attach himself from the page after his click-through. A dry run on staging is allowed and expected (T2).
6. Deploy to staging exactly the way PL2 did: an image-only Terraform roll applied from a saved plan (show the plan summary first; if it contains anything other than the image, stop and ask), then `scripts/deploy-smoke.sh` (it only smoke-tests). Follow the existing practice for applying the database migration and report which it is. Never a scripted yes. Do not merge: Kanna clicks first.

## Design in one page

Every client has a **relationship** (`existing` or `net_new`, stored, with a basis), a **requirement** (net-new only: `required` when it has an open or on-hold deal at stage 2 to 6, or a Closed Won deal, or an SOW/engagement created after the cutover; `later` when its open deals are all stage 1; otherwise `none`), and for each of NDA and MSA a **state**: `client` (the client's own file), `standard` (a standard copy attached), `covered` (marked, no file), `missing` (net new, requirement required, nothing held), `due_later`, `not_needed`, or `existing_none` (existing, nothing attached). **Needs attention** = net new, requirement required, and either kind missing. One shared service computes all of this for the Agreements page, the Pipeline, the Command Center and the client panel. The exact definitions are in the contract; the prototype shows them.

A standard copy is **one stored object**; each client's agreement row points at it (`source=standard`, with the standard version and batch id). A **client copy** (`source=client`, state `client`) is the client's own object: a client copy, or a version updated for that client, with an optional note. Uploading a client copy over a standard copy replaces it for that client only and keeps the earlier state in history; later uploads add versions.

## Disposition of the discovery findings (AG0 items)

| # | Finding | Disposition |
|---|---|---|
| D1 | `/agreements` page: one register table, client-side search, no status/sort/pagination; 12 endpoints | **BUILT:** B3, F1, F8. The old register stays as the Documents tab (download, replace, history); its search placeholder now says what it searches. |
| D2 | Model: `agreement` + `agreement_file_version`; only state is "on file"; no requested/signed/expiry | **BUILT:** B1, B2. Requested, awaiting signature and expiry stay **CUT** (S17 removed them on purpose). |
| D3 | Upload only via API multipart; 25 MiB; PDF/DOCX; type check trusts the browser; KMS bucket; presigned download 300 s | **BUILT:** B5. Stay with API uploads. Browser-direct upload and an in-app viewer are **CUT**. |
| D4 | One file cannot be attached to many clients | **BUILT:** B4, B6, B7 (shared object, one row per client). |
| D5 | Only Legal and SystemAdmin write; all ten roles view and download | **KEPT** with server enforcement and two SystemAdmin-only actions: B11. |
| D6 | Nine client-creation paths; HubSpot paths run with no user; bulk and legacy imports have no hook and no audit row | **BUILT:** B8 (one hook, all paths; add the missing audit rows). |
| D7 | Consumers: Pipeline tags, Missing filter, gaps card, CSV, on-file strips, SOW note; nothing blocks | **BUILT:** B10, F6, F7. Nothing is made to block. |
| D8 | 208 clients; 70 existing; 138 net new | **Expected.** Reproduced by T2. |
| D9 | 58 forecast-model engagements sit on 18 clients with no HubSpot link; 14 of 18 have no HubSpot name match | **REPORT ONLY.** They count as existing through the SOW/engagement rule and are not misclassified. List the 2 possible name matches in your report without linking them. |
| D10 | 8 duplicate-name groups over 18 clients | **BUILT** as a flag only: B2 (`possible_duplicate`), F3. No merge (**DEFERRED**). |
| D11 | Gaps card 53 vs SQL 41 (42 with Hold) | **BUILT:** B10 redefines the card to net new, past stage 1, NDA or MSA missing. Explain on staging how 53, 41 and the new number relate (T2). |
| D12 | `FileDropzone.tsx` exists unused; no byte progress; no viewer | **BUILT:** F2 adopts `FileDropzone`. Viewer **CUT**. |
| D13 | Audit log is an append-only hash chain with one global lock; forecast import is the bulk precedent; no batch id or undo for agreements | **BUILT:** B7 (chunked commits, batch id, undo). |
| D14 | Header-only type check; doubled extension; no length cap; names rendered escaped | **BUILT:** B5, F2, T3. |
| D15 | Terraform: bucket and KMS exist; API uploads need no change | **REPORT ONLY.** No Terraform change in this directive. If you think one is needed, stop and ask. |
| D16 | Agreement tests run only on SQLite with a fake S3; 8 rule tests are placeholders; leak gate blind to agreements | **BUILT:** T4, T5, T10, T11. |
| D17 | HubSpot `msa_type` exists in the saved schema, never requested or stored | **BUILT:** B9, F5, T8. |

## Disposition of the "Surprises"

| # | Finding | Disposition |
|---|---|---|
| S1 | Blueprint says a missing NDA/MSA blocks signature | **BUILT:** B14 (doc fix plus the `docs/questions.md` entry). |
| S2 | "On file" cannot tell a standard copy from a client copy | **BUILT:** B1, B2 (`source`, the seven states). |
| S3 | `msa_type` unused | **BUILT:** B9. |
| S4 | SOW upload checkbox "NDA and MSA are signed" is not linked to a file | **DEFERRED.** Left exactly as is. Report how many SOW versions have it ticked. |
| S5 | 21 of 70 existing clients have no HubSpot deals, so Pipeline cannot show them | **Expected.** The Agreements page is client-based and lists them. |
| S6 | Duplicates are built in (sync matches company id only; SOW "create new" never checks the name; no merge) | **BUILT** as flag only (D10). Do not change sync or SOW matching here. |
| S7 | Two "Unknown company (deal …)" placeholders count as net new | **BUILT:** flag `unknown_company`, no other change. |
| S8 | Gaps card measures something else; missing NDA/MSA is not a "needs attention" flag | **BUILT:** B10 (the card), B3 (needs attention). |
| S9 | Uploader is required; backfill and HubSpot hooks must credit a real user | **BUILT:** B7 (the admin who ran it), B9 (the admin who last saved the mapping). No system user is invented. |
| S10 | Orphan S3 objects (file stored before the row; no sweeper; proof scripts write to the staging bucket) | **BUILT:** B5 (compensating delete), B13 (read-only orphan report). Do not delete the 3 existing orphans under `verification/s21/…`; report them. |
| S11 | Test data in the client list (e2e created one through SOW "create new"); it counts as existing; the leak gate cannot see it | **BUILT:** B2 (`test_data` flag), T11. **Report the leftover client; do not delete it.** |
| S12 | Every role including Marketing can download every NDA/MSA; downloads are not audited | **BUILT:** downloads audited (B11). Role access stays as today (**Kanna's call later**). |
| S13 | CloudFront to ALB is plain HTTP; the ALB accepts port 80 from anywhere | **REPORT ONLY.** Already known from AG0. No change here. |
| S14 | Browser uploads and viewer need CORS; the upload-link signer falls back to fake AWS keys on ECS; the legacy import's browser upload fails CORS | **BUILT:** B13 (the signer fails loudly instead of using fake keys, only if that code is in an agreements path; otherwise report). CORS and legacy import **REPORT ONLY**. |
| S15 | NDA/MSA files uploaded through SOW paths are misfiled or dropped; the rate-card MSA import never reads its file | **REPORT ONLY.** List where each happens (file:line). No change. |
| S16 | No batch or import-key column; the (client, kind) index is missing from the model; the audit lock forces chunked commits; 30 s and 60 s timeouts | **BUILT:** B1 (index in model and migration), B7. |
| S17 | HubSpot attach at pull time is limited (clients arrive via the nightly sync at 04:00 UTC; workers lack bucket access) | **BUILT** differently: no file attach from HubSpot. The relationship hook runs at creation (B8) and the mapping applies after each sync (B9). |
| S18 | CI e2e uploads fail with 502 | **BUILT or logged:** T9 (one bounded attempt; if it does not yield, log it and carry on). |
| S19 | A single test upload on staging hides the card's "no agreement files uploaded yet" note | **Expected.** The new cards do not depend on that note. |

## Backend items

**B1. Data model and migration.** Add: `standard_agreement` (id, kind, version_no, file_key, filename, size, sha256, uploaded_by NOT NULL, uploaded_at; unique kind+version); on `agreement`: `source` (`client`|`standard`, default `client`), `standard_agreement_id` nullable, `batch_id` nullable; `agreement_mark` (client_id, kind, reason, note, marked_on, marked_by NOT NULL, source `dealgate`|`hubspot`, hubspot_value, created_at, removed_at, removed_by; at most one active mark per client and kind); `agreement_batch` (label such as AG-0001, status, kinds, created_by NOT NULL, created_at, target_count, done_count, attached_count, skipped_count, error, undone_at, undone_by, idempotency_key unique); on `client`: `relationship`, `relationship_basis`, `relationship_set_by`, `relationship_set_at`; `agreements_settings` (singleton: cutover_date, set_by, set_at); on the HubSpot deal: nullable `hubspot_msa_type` text (max 200); `agreement_hubspot_map` (value, action, updated_by, updated_at). Put the **(client_id, kind) uniqueness** on active agreements in the **model code** as well as the migration (AG0 found it missing from the model, so an auto-migration would drop it). Reversible migration; run the up and down on Postgres. Existing rows (none today) keep `source=signed`.

**B2. One shared service `agreement_status`.** Pure functions plus one query layer returning, for any client set: relationship, basis, requirement, nda and msa state, needs_attention, furthest open stage (Hold counts as open at its stage), business units with regions (US is never shown without its BU), deal counts, and flags `possible_duplicate` (lower-case, strip punctuation and possessives, strip trailing legal suffixes llc, inc, ltd, corp, co, company, then compare), `test_data` (created by a test identity or a run-tagged client; if no reliable stored signal exists, say so in your report and propose one, do not guess silently), `unknown_company` (the "Unknown company (deal …)" placeholder), `no_hubspot_link`. Before the cutover is set the relationship is computed live and flagged provisional; after it, the stored value is used. Used by B3, B6, B10 and the Command Center. No other code computes these.

**B3. Workspace, export, documents, activity.** `GET /api/agreements/workspace`, `/export`, `/documents`, `/activity` per the contract. Six cards computed over all clients; each `drill`, applied to the filters, returns a list whose length equals the card value. One request per page view; measure queries and latency before and after (T13).

**B4. Standard documents.** `GET /api/agreements/standard`, `POST /api/agreements/standard/{kind}` (next version), `GET .../download`. Objects live under `agreements/standard/{KIND}/`. A new version never touches attached copies. Uploader is the calling user.

**B5. File rules on every agreement upload** (standard, client copy, replace, the existing `POST /agreements` and `/replace`): extension PDF or DOCX; at most 25 MiB; not empty; first bytes match (`%PDF-`; `PK` 03 04 for docx); sanitised stored name with exactly one extension and at most 80 characters of base; original name kept for display only. The object is written first and **deleted again if the row cannot be committed**. No virus scanning (record as a known gap in your report).

**B6. Per-client endpoints.** Panel detail, client-copy upload (route `/client-copy`, optional note), attach-standard (409 if the client already holds the kind), mark (reason, date not in the future, note) and unmark (soft), detach (a client copy follows the existing deletion job; a standard attachment removes only the row, and the shared object stays because other rows use it, as `deletion_storage.py:13-25` already guarantees), relationship, download (audited). All per the contract.

**B7. Batch: dry run, job, undo.** `POST /api/agreements/batches` per the contract. Dry run is the default and changes nothing; it returns every existing client, and with `include_net_new_past_stage_1` every net-new client whose requirement is `required`, as a target or an exclusion with a reason (`stage_1_only`: all open deals are stage 1 and no Closed Won deal; `test_data`). The real run is a **background job**: the request returns 202 within seconds, the browser polls. Commit **every 25 clients** and write the audit rows in that same transaction (the audit log serialises on one lock, so one long transaction would stall every other writer). Idempotent per (client, kind): a client that holds the kind (file or mark) is skipped and counted. A second run while one is running returns 409. A killed job resumes by re-running without creating duplicates. The first real run sets the cutover date (America/Los_Angeles calendar date) and stamps every client's relationship, once, never moved. Net-new clients that receive a copy stay net new. Every agreement row created carries the batch id and the **admin who ran it** as uploader. `confirm` must equal `ATTACH ` plus the target count or the request is refused. **Undo** removes only rows with this batch id whose source is still `standard`; client copies and marks made since are untouched; the standard files, the cutover and every relationship stay. Use the existing durable job pattern (deletion jobs, forecast import or the HubSpot reconcile, whichever survives a task restart) and say which in your report. If none does, add a CLI that does the same work and tell Kanna.

**B8. Client-creation hook.** One function sets the default relationship when a client is created: before the cutover, nothing is stamped; after it, `net_new` unless the client's HubSpot company already has a Closed Won deal dated on or before the cutover (then `existing`, basis `closed_won`). Call it from all nine creation paths in AG0 item 6 (HubSpot sync, the "Unknown company" placeholder, `POST /clients`, forecast-model and workbook imports, SOW studio "create new", bulk SOW import, legacy import, test fixtures). Where a path writes no audit row today (bulk and legacy imports), add one. Never changes an existing client's relationship.

**B9. HubSpot `msa_type`.** Add the property to the deal sync's requested properties and store the raw value on the deal. If the token's scopes do not allow it, mark this item **blocked** with the exact error and carry on; do not change HubSpot app settings. A client's hint is the value on its most recently modified deal that has one. `GET /api/agreements/hubspot-values`, `PUT .../hubspot-mapping` and `POST .../hubspot-mapping/apply` (dry run by default), SystemAdmin only. Apply marks the MSA covered only for clients that hold nothing for the MSA; each mark has source `hubspot`, the value found, and credits the admin who last saved the mapping. The nightly sync runs the same apply after each successful sync, only for mapped values. A hint is never a state by itself. Marks stay if HubSpot is switched off.

**B10. Pipeline and Command Center on the shared service.** In the PL2 workspace response, add `nda_state` and `msa_state` to deal and client rows and keep `nda_on_file` and `msa_on_file` (true only for `client` and `standard`). Redefine the metric `agreement_gap_clients` as the Needs-attention count and its `drill`; the `missing=nda|msa|agreements` filters mean state `missing`. The Pipeline client panel and the deal page strip use the same states and copy. The Command Center gets one tile, "Net-new clients past stage 1 without an NDA or MSA", that opens the Agreements page filtered to Needs attention. Update `docs/reference/openapi-pipeline.yaml` for the added fields. On staging the Pipeline card must equal the Agreements card.

**B11. Permissions and audit, enforced on the server.** Writers: Legal, SystemAdmin (upload, replace, detach, mark, relationship). SystemAdmin only: run and undo batches, save and apply the HubSpot mapping. All roles: view, download. Every write, every download (who, which client, which kind, which file) and every export is an audit row; `GET /api/agreements/activity` reads them. The page shows the lock; the API returns 403 regardless.

**B12. Flags only.** Expose the duplicate names, test-data and placeholder flags. No merge, no deletion, no change to sync or SOW matching.

**B13. Safety and housekeeping.** The agreements upload-link signer must fail loudly outside tests instead of falling back to fake AWS keys (only if that code is in an agreements path; otherwise report where it is). A read-only command lists objects under `agreements/` with no database row older than 24 hours; run it on staging and report the result (3 are expected under `verification/s21/…`); it deletes nothing.

**B14. Docs.** Fix `docs/blueprint.md:14`. Add the entry to `docs/questions.md` with Kanna's answers from the top of this file. Update any doc that describes agreement states.

**B15. Activity source.** The activity feed reads the audit log (no second event store) and covers: standard uploaded, client copy uploaded or replaced, standard attached, detached, marked, mark removed, relationship changed, batch run, batch undone, HubSpot applied, downloaded, exported.

## Frontend items

**F1. The page.** Header (Export view, HubSpot hints, Attach standard copies…, Upload document), the cutover line, six clickable cards, the two standard-document panels, tabs Clients / Documents / Activity with counts, filters (relationship, status, stage, business unit, search, sort), filter chips, pagination 25/50/100, and every empty state in the prototype. Write controls the caller may not use are locked with a reason, not hidden. Business unit is always shown with its region.

**F2. Upload dialog.** An optional note about the version (client copies only). Adopt the existing `FileDropzone` component. Same checks as the server before sending (type, size, empty, first bytes), the same messages as the prototype, a "stored as" line, the replace notice, the standard-version note, and progress (real byte progress if the upload layer supports it, otherwise an honest indeterminate bar; say which). File names are always rendered escaped.

**F3. Client panel (one shared component).** Used on the Agreements page and in the Pipeline client panel. NDA and MSA cards with: download, upload client copy or replace, upload a client copy ("Upload client copy", "Replace with client copy" over a standard copy, "Upload new version" over a client copy), attach standard copy (for a client holding nothing), mark covered, remove, history; change relationship; the duplicate-names line; the warning note for a net-new client past stage 1. The prototype's "Prototype: close its deal Won" button is a prototype control and is **not** built.

**F4. Attach standard copies (SystemAdmin only).** The three steps from the prototype, backed by the server: dry run, a tickable list (existing clients and net-new clients in the pipeline past stage 1 start ticked, labelled; stage-1-only clients and test data start unticked with their reason), the counts including how many are net new, typed confirm, job progress by polling (reopening the dialog shows a running batch), the done state, and the undo dialog whose count comes from the server. Closing and reopening never starts a second batch.

**F5. HubSpot hints dialog.** "Not stored yet" state, the values with client counts, the mapping, the dry-run count before applying, apply. SystemAdmin edits; others read.

**F6. Pipeline.** The NDA and MSA tags show the seven states with the prototype's wording (the label for state `client` is "Client copy"); the Missing filter and the Agreement-gaps card use the new definition and wording.

**F7. Command Center tile** (B10).

**F8. Documents tab.** The old register kept: client, type, file, source (Client copy or Standard vN with its batch), uploader, date, download, and the existing replace and history. Search placeholder "Search by client, type, file name or uploader".

**F9. Activity tab.** Reads B15; the empty state from the prototype.

**F10. Export view.** Downloads the CSV from `/api/agreements/export`; formula neutralisation as in every export.

**F11. After creating a client by hand** (the Clients create form and the SOW studio "create new client"), offer "Add the NDA and MSA now (optional)", which opens the upload dialog for that client. Clients pulled from HubSpot appear on the page by themselves; there is nothing to click.

**F12. Quality.** Never render a raw id. Escape every dynamic value (T9 uses a hostile client name). Works at 375 px with no horizontal overflow, in light and dark, keyboard focus visible, Escape closes dialogs and restores focus, the page is inert behind a dialog.

## Tests

**T1.** Table-driven classification: relationship × requirement × state, including the cutover cases (a net-new client's first Closed Won deal stays net new and stays flagged; a client created after the cutover whose company has an earlier win starts existing; Hold counts as open; stage-1-only; manual override; test data).
**T2.** Staging dry run: report the counts for clients, existing (with its two parts), net new (stage-1-only, past stage 1, none), needs attention, backfill targets and exclusions, and explain how the old card's 53, the SQL 41 (42 with Hold) and the new number relate. Re-read, do not copy the numbers at the top of this file.
**T3.** Upload rules (a note longer than 200 characters is refused; a client copy over a standard copy replaces it for that client only and the other holders keep it): text file named .pdf, fake .docx, empty, 26 MiB, `x.pdf.pdf`, hostile name with markup, over-length name, path characters, key shape, and no orphan object when the row cannot be committed.
**T4.** Shared object (Postgres): one standard key across many clients; detaching one client keeps the object; undo leaves other users of the object alone.
**T5.** Batch (Postgres, fixtures only, never staging): dry run changes nothing; with `include_net_new_past_stage_1` it targets exactly the net-new clients whose requirement is `required` and they stay net new with state `standard`; idempotent re-run; commits every 25; kill mid-run then resume gives no duplicates; a concurrent second batch gets 409; wrong confirm phrase refused; uploader is the running admin; undo touches only that batch's `standard` rows; client copies and marks made since are untouched; cutover set once; audit rows present.
**T6.** Permission matrix across all ten roles for view, download, upload, replace, detach, mark, relationship, batch run and undo, mapping save and apply. 403 from the server, not only a locked button.
**T7.** Download, export and every write produce audit rows; CSV formula guard.
**T8.** HubSpot (fixtures, no real token): the value is stored, apply fills only empty clients, never overwrites a record, credits the right user, runs after a sync, and leaves the sync-run record unchanged.
**T9.** Playwright: upload with a real file (and each rejection), client-panel actions, the attach dialog against a seeded test database or the dry run on staging, Sales lock, Legal cannot run a batch, Pipeline tags and card, hostile-name escaping, 375 px. Rule 18 applies. For the CI upload 502 (S18): one bounded attempt, then log it.
**T10.** Replace the 8 placeholder NDA/MSA rule tests with real tests of warn-only behaviour, including that SOW approval and signing proceed with no agreement on file.
**T11.** Leak gate: test uploads are keyed under a run-tagged prefix; the gate checks the bucket prefix and the client list and fails on leftovers. Report the one leaked e2e client; do not delete it.
**T12.** The Pipeline workspace and the Agreements workspace report the same Needs-attention number on staging; every card equals the list it opens.
**T13.** Queries and latency per call for the workspace, panel and batch dry run before and after; workspace 8 queries or fewer; a 67-client batch finishes in under 60 seconds in the test database.
**T14.** Accessibility pass on the page and the three dialogs (focus order, labels, contrast in both themes).

## Report format

Per item: `ID · state · proof`. Then a short list of every deviation from the prototype or the contract, every blocked item with the exact error, the leaked-client and orphan-object findings, the 2 possible forecast-client name matches, and how many SOW versions have the "NDA and MSA are signed" box ticked. Do not merge.
