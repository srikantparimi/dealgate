# T11 Tracking Boundaries

Branch `s21/tracking-boundaries`, baseline225a81d. Worker owns tracking routers,
comment/action services, the new shared access/CAS helper and focused tests.
Lead owns UI, real browser, independent PostgreSQL concurrency and integration.

## Implemented Boundary

Tracking now uses the actual Pipeline Deal page authority: Pipeline reader roles,
canonical source population and exact validated fixture grants. Ordinary Sales
can read mirrored business Deals; legacy `/deals` additionally uses owner/reviewer
restrictions and is not the current page authority. Ordinary ungranted sow_upload
records remain outside this read population, matching the existing Pipeline page.
No task assignment grants new Deal visibility. Existing author/creator/assignee/
leader mutation rules remain necessary in addition to underlying read access.

Direct reads/mutations, global action lists and client timelines are scoped;
client timelines no longer truncate source Deals at200. Action choices use
registered User IDs with reader rights and matching business/fixture scope, not
CRM owner facets. Foreign fixture participants and unissued siblings are excluded.

Rows expose opaque revision and can_edit; comments also expose can_delete and
resolved author_name. Lists expose can_create; scoped action lists return
assignees:[{id,name}], while global lists expose no unscoped directory. PATCH
requires expected_revision (428 absent,409 stale). Comment DELETE uses If-Match,
accepting raw or HTTP-quoted returned revision. Authorization precedes token
comparison/disclosure. CRM notes remain read-only with existing409 explanation.

Revision hashes row facts plus that entity's append-only audit count, under a
row lock and populate_existing reread. Every mutation appends audit before the
response token is generated. Pin/unpin and same-value ABA cannot reuse a token;
the design does not rely on timestamp uniqueness or add a schema column. Rejected
stale writes append no audit. Independent concurrent-PG proof remains lead-owned.

Timeline uses edited comment time/text and actual editor attribution where an
edit audit exists. `source` remains "comment"; additive `comment_source` is
string|null ("internal" or "hubspot_note" for comments). `kind` becomes "edited"
for edited comments, retaining the original source separately. Current schemas
use ApprovalPackage.submitted_at and SowVersion.uploaded_at/version_no; timeline
no longer reads nonexistent historical alias columns or labels submission as an
observed status-transition timestamp. Latest comment considers edited activity.

## Checkpoint Evidence

Tests authored before implementation. Runtime was initially held; service work
was partly authored before permission arrived. First execution64031 observed
nine failures while routers still lacked the new fields/access boundaries; this
is not claimed as a pristine-baseline red. Intermediate42007 passed8/failed1
(CRM read-only409 precedence), corrected without changing assertions. Expanded
session36816 passes **13 focused HTTP/service/SQLite cases**, exit0. They cover
revisions, pin ABA, missing/stale tokens/no audit, stale identity-map reread,
author/capabilities, scoped options, forbidden mutations and fixture/global/timeline
boundaries. Plain comment content remains JSON text; actual UI escaping is lead proof.

```sh
env -u DEALGATE_POSTGRES_URL PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/srikanthparimi/OfficeApp/dealgate-s21-qa/api/.venv/bin/python -m pytest -p no:cacheprovider tests/test_s21_tracking_boundaries.py -q
```

Run from this worktree's api directory; private SQLite and read-only dependencies,
no installs/shared DB/providers. Slot released after finite run. Existing direct
service/HTTP tests omit newly required revisions: lead has now authorized narrow
request-setup adaptation preserving all old business assertions. That bounded
regression is pending the next runtime slot, not falsely green at this checkpoint.
No T11/S21-13/staging closure is claimed.

## Contract-Aware Legacy Regression

Lead explicitly expanded test ownership to `test_deal_comment.py` and
`test_next_action.py` for request setup only. Session57137 ran the unchanged17
legacy cases: nine failures/eight passes. Seven failures omitted the now-required
revision; two exposed genuine same-second comment ordering ambiguity under
SQLite server-default timestamps. New internal comments now receive explicit UTC
microsecond creation timestamps. Existing latest/pinned assertions were preserved,
not changed to tolerate the wrong comment. No role policy or schema change.

Direct service test calls now pass their actual `comment_revision`/`action_revision`;
the HTTP test carries the returned POST revision into PATCH. All existing business
assertions remain intact, including forbidden third-party edits, CRM read-only
notes and refusal to complete approval-linked actions outside approval decisions.

Session1819: **30 passed** (13 new plus17 legacy), exit0, two inherited FastAPI
startup deprecation warnings. Same isolated command plus
`tests/test_deal_comment.py tests/test_next_action.py`. Runtime released after run.
Independent PostgreSQL concurrency and connected browser remain lead-owned.

Read-only residual outside worker ownership: Pipeline's latest-comment subquery
in `services/hubspot_pipeline.py` still orders pinned/created_at rather than edited
activity. Dedicated comments `latest` and timeline are repaired here; no claim
that every Pipeline activity reader is reconciled. Lead notified before integration.
