# Directive S13a: delete and reset pipeline records, plus the three defects in this screenshot

From: Kanna Parimi, product owner. 21 September 2026. Commit as `docs/directives/s13a-delete-reset.md` first, then execute. Evidence: the Pipeline clients screen currently shows two Peppermill rows ("Peppermill Casino (S12 1789936428334)" and "Peppermill Casino's, LLC"), owners rendered as raw UUIDs, and stage labeled "HubSpot · from CRM" for records that came from SOW upload.

## 1. Delete, with governance rules — the main deliverable

The product owner must be able to remove a client, opportunity or SOW he created and start fresh with the same client and same SOW file. Delete is not one behavior; it depends on what the record has been through:

| Record state | Allowed action | Behavior |
| --- | --- | --- |
| No approvals recorded, no executed agreement, no signed SOW (drafts, test uploads, everything on this screenshot) | **Hard delete** | Row menu → Delete → confirmation naming what cascades. Removes the client/opportunity/SOW and its versions, GM models, staffing, tasks, blockers, and the uploaded files in S3. Writes one `audit_event` (actor, timestamp, record identity, counts of cascaded rows) — the audit trail records the deletion; nothing else survives. |
| Any approval recorded, or agreement/SOW executed | **Archive (void)**, never hard delete | Record leaves all default views and dashboards, keeps its history, shows an "Archived" chip in search and the client page. Unarchive is admin-only. The blueprint's append-only audit rule stands: approved and signed history is never destroyed. |
| Linked to a live HubSpot deal | Archive only, with a warning that the deal still exists in HubSpot | Hard-deleting it would just resurrect on the next sync. Archiving also writes the governance status back to HubSpot. |

Permissions: the record's owner and admins can delete drafts; only admins archive approved records. Every delete/archive is a server-side check, not a hidden button.

**The fresh-start requirement, spelled out:** after deleting the Peppermill records, re-uploading the exact same SOW file must work cleanly. That means the file-hash and client+title+dates dedupe checks run against **live records only**. A deleted record's hash must not trip the duplicate detector; an archived record's duplicate hit shows as an informational "matches archived SOW-xxxx" note, not a block. Add this as an explicit test: upload → hard delete → re-upload same file → succeeds with no duplicate flag.

Batch cleanup: on Settings → Data imports, a "Delete batch" action that hard-deletes everything a bulk-import or test batch created, same state rules per record, one confirmation listing counts.

## 2. Three defects visible in the same screenshot — fix in this slice

1. **Dedupe failed at creation.** "Peppermill Casino (S12 1789936428334)" and "Peppermill Casino's, LLC" are the same client; the second upload should have matched the first (or the e2e fixture should have been cleaned up — see 3). The client-matching threshold and alias handling from `docs/directives/sow-intake.md` §Defect 1 apparently isn't catching possessive/suffix variants. Add "Peppermill Casino's, LLC" vs "Peppermill Casino" as a matcher test case; normalize possessives, punctuation and entity suffixes (LLC, Inc, Corp) before scoring.
2. **Owner shows a raw UUID.** `Owner: 112b05a0-…` is a defect everywhere it appears. Render the user's display name and avatar; if the owner id resolves to no user, show "Unassigned" with the assignment task, never the UUID. Grep the UI for other places an id renders where a name belongs (approvers, audit rows, task owners).
3. **Provenance label is wrong.** These records came from SOW upload, not HubSpot, but the stage column says "HubSpot · from CRM". The source field exists (`source = sow_upload`); render it truthfully: "SOW upload", "Bulk import", "HubSpot". A wrong provenance label undermines the whole provenance system.

Also: e2e runs against staging must tag their records (`created_by = e2e` or a test-run batch id) and clean up after themselves using the new delete endpoint — S12's leftovers on this screen are how we found this gap.

## Definition of done

Browser-proven on staging, screenshots in `docs/reports/s13a.md`:

1. Delete both Peppermill rows from the portal (cascade confirmation shown), list is empty.
2. Re-upload the same Peppermill SOW → processes cleanly, one client, no duplicate flag, owner shows a name, source shows "SOW upload".
3. Upload the same file a second time without deleting → duplicate flag appears (dedupe still works on live records).
4. Approve a fixture package, then attempt delete → delete refused, archive offered; archived record keeps history and leaves default views.
5. Matcher test: "Peppermill Casino's, LLC" matches "Peppermill Casino" ≥ 0.85.
6. E2e suite run leaves zero residue rows on staging.
7. All existing tests still green; report in the standard format (screenshots, test IDs, files added/deleted).
