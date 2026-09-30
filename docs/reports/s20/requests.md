# S20 · cross-worker requests (Lead routes)

Workers append a block here whenever they need a change on a file they
don't own (per `contracts.md` §6) — the Lead applies within the hour and
tags the responsible worker + a link to the requesting commit.

Format:
```
## <Wn>-<UTC>-<seq> · <one-line title>
Reason: <why>
File(s): <paths>
Change: <exact behavior/API>
Rollback: <how to undo>
Test: <acceptance>
Requested-in: <sha of requesting commit or `plan-only`>
```

---

(seeded empty; workers append during their runs)

## W3-2026-09-30-01 · sow.opportunity_id uniqueness relax
Reason: D1 fixed decision — many SOWs per deal. `Sow.opportunity_id` is
currently `unique=True` (`api/app/models/sow.py:30-32`), which forbids a
second SOW for a rebooked/renewal/added-scope engagement. The rollup
service W3 built (`services/sow_rollup.py`) is written to aggregate
multiple rows per deal; it collapses to one row today so it can ship
before the constraint is relaxed.
File(s): `api/app/models/sow.py`, new alembic revision from head.
Change:
  - Drop `unique=True` on `Sow.opportunity_id`.
  - Add composite index `ix_sow_opportunity_created` on
    `(opportunity_id, created_at)` — the rollup query is by deal, newest
    first.
  - Migration is backward-compatible (D5): existing rows are unaffected;
    dropping a uniqueness constraint never fails on populated data.
Rollback: recreate the unique constraint after archiving all-but-one SOW
per deal. Alembic `downgrade` recreates the unique index; if any deal
already has >1 SOW the downgrade fails visibly (which is the desired
signal — do not silently pick a winner).
Test: `api/tests/test_sow_rollup.py::test_many_sows_per_deal` (see W3
commit).
Requested-in: s20/W3 (planned as part of cycle 1)

## W3-2026-09-30-02 · deal detail page at /deals/:id
Reason: L09/L11 — a deal without a SOW currently redirects to
`/sows/:id`, rendering an empty SOW workspace shell with a disabled
"Complete scope" button and an enabled "Delete SOW" button. The review
requires a real deal detail page for tracking, comments, actions,
Upload SOW, and reporting. W3 owns SOW surfaces only; W2 owns
`web/src/pages/v2/deal*` per `contracts.md` §6.
File(s): W2 to create `web/src/pages/v2/DealDetail.tsx` and wire it into
`web/src/App.tsx` at `/deals/:id` (replacing the RetiredPage route).
Change:
  - Route `GET /deals/:id` renders client + deal identity, owner,
    stage, next action, latest comment, groups, and the SOW list or
    `Upload SOW` primary CTA per the review's Deal workspace row.
  - The rollup headline (D1) comes from
    `services.sow_rollup.compute_headline(opportunity_id)` — W3 ships
    the service; W2 consumes it in the deal page.
  - Upload SOW navigates to `/sows/new?opportunityId=<id>` with the
    client_id pre-bound (T11).
Rollback: revert the App.tsx route; RetiredPage catches `/deals/:id`
again. The rollup service and deal API stay in place.
Test: W5's Playwright T10 (deal with no SOW) exercises this end-to-end.
Requested-in: s20/W3 (cycle 1) — non-blocking for W3 shipping the SOW
workspace repairs; W3 patches the SowWorkspace to render an honest
empty-state until W2 lands the page.

## W3-2026-09-30-03 · sow_upload_job columns for pre-bound client + deal
Reason: T11/T37 — the review requires `POST /sows/upload` to accept
(and require) both `client_id` and `opportunity_id` (deal), persist both
before extraction, and preserve the file + entered corrections on
extraction failure. `SowUploadJob.opportunity_id` already exists as a
nullable FK set by the pipeline post-match; add `bound_client_id` and
`bound_opportunity_id` capturing the *pre-upload* binding the human
declared, so a picker step is skipped and the confirm page can prove the
binding is human-authoritative (not a fuzzy match).
File(s): `api/app/models/sow_upload_job.py`, new alembic revision.
Change:
  - Add nullable columns `bound_client_id: UUID | None` (FK client.id)
    and `bound_opportunity_id: UUID | None` (FK opportunity.id) to
    `sow_upload_job`.
  - When both are provided at upload time, the pipeline skips the
    client-match step and creates the SOW version under
    `bound_opportunity_id` directly. Uniqueness on
    `(bound_opportunity_id, file_hash)` is not enforced tonight — D1
    lets many SOWs share a deal.
  - Backward-compatible: existing callers can still omit both fields
    and hit the fuzzy-match/picker path.
Rollback: drop the two columns. Existing rows written since deploy
lose their explicit binding but the rest of the row survives; the
pipeline's post-match `opportunity_id` still records the resolved
binding.
Test: `api/tests/test_sow_upload_binding.py` (W3 will write it against
the current schema and re-run after the migration lands).
Requested-in: s20/W3 (cycle 1) — W3 ships the *router* accepting the
two fields and stashing them on the job's `needs_pick_payload` in the
interim; once the columns land the router writes them directly.

