# CRM Source Integration Review

Read-only application review at `9cf1e8a`, branch `s21/crm-source-review`.
Only this report changed. No provider/network, AWS, tests, installs, database,
browser or other worktrees were used. Findings below are static-code evidence,
not newly observed live failures. Lead owns contracts, migration and integration.

## Reuse Versus Gaps

| Area | Existing implementation worth preserving | Remaining gap |
| --- | --- | --- |
| Owner mirror | `services/hubspot_owners.py:42` already stores external string IDs, names/email, active/archived state and source times. `:172` ingests both owner populations; `:279` resolves a label without requiring a login. Migration 0045 already creates this table. Four owner-mirror tests cover ingestion/idempotency/archive transition/unknown ID. | Deal/company records do not store source owner IDs. Pipeline still joins `User` by local UUID (`hubspot_pipeline.py:240`, `:338`); client labels are explicitly `None` at `:1852`. `_resolve_owner` (`hubspot_intake.py:87`) creates local users from email and falls back to Sales leader/sentinel on absence, 404 or other error, conflating three different source states. Existing user names are not refreshed (`:77`). |
| Property discovery | `hubspot_properties.py:57` and migration 0045 provide the mapping/options table. Six discovery tests cover deal/company enumeration, absence and option changes. Reuse this module. | `:185` catches metadata errors and continues, so forbidden/unavailable becomes `business_unit_not_found`; `:148` treats malformed responses as empty. First regex hit wins (`:195`), even when multiple properties match. Existing mapping remains after a later absent/error result; no persisted explicit availability state/reason. No configured selection/settings path invokes the mapping read service outside its own module. |
| Source adapter | One `HubSpotClient` and shared `_upsert_opportunity` serve backfill/intake. Standard amount/date/identity fields and company upsert exist. | `_DEAL_PROPERTIES` (`integrations/hubspot.py:107`) cannot add discovered BU; company fetch (`:155`) asks only name/domain, not owner or mapped BU. Neither Client nor Opportunity has BU columns; Client lacks source owner/timestamps. `services/clients.py:47` ignores company owner/BU. |
| Metadata refresh | Backfill calls stage, owner and property mirrors before scanning (`hubspot_backfill.py:275`). Pipeline/stage tables already store names and metadata. | Contrary to module comments, only backfill invokes these refresh services. Webhook ingestion calls `_upsert_opportunity` without `stage_map` (`hubspot_intake.py:772`), so `:349` falls back to raw stage ID and false closed flags. `StageMap` keys stage alone (`hubspot_stage_mirror.py:42`); stage PK is also stage alone (`models/hubspot_pipeline.py:35`). Won/lost uses labels/order (`hubspot_stage_mirror.py:62`), while chips use probability, allowing inconsistent classification. |
| Event durability | Dedupe and processed watermark commit with record/audit effects (`hubspot_intake.py:791`); four intake-dedupe tests include dropped-ack replay. Keep that transaction boundary. | No comparison prevents an older fetched `hs_lastmodifieddate` from overwriting a newer mirror. Re-reading source reduces event-order risk but is not a concurrency/version fence. Currency/activity clears are ignored by `if value is not None` / truthy updates (`:482`). Missing activity is fabricated from last-modified time (`:357`). |
| Scan safety | Existing scan generation/timestamps and cursor in SyncStatus; partial-page failures skip archive. Four scan tests cover healthy scan, page failure, next healthy scan and records created mid-scan. | `run_backfill` starts `after=None` and holds seen IDs only in memory (`:256`, `:318`); cursor is not checkpointed. `_archive_missing` runs before generation validation (`:355`), then `touch_source` writes the old generation again (`:372`). `claim_scan_generation` is unlocked read/increment (`sync_status.py:166`); `mark_scan_completed` only checks after the dangerous write. Concurrent/old scans can archive current data despite comments claiming safety. |

Additional correctness details: `_extract_company_id` chooses the first raw
association (`hubspot_intake.py:168`) while `_dedup_company_ids` reorders labeled
ones (`:268`); then backfill takes `[1:]` for secondary IDs. Select primary once
and derive secondary by identity, not inconsistent list positions. Backfill
`owners_matched` counts any nonempty raw owner ID (`hubspot_backfill.py:167`), not
successful resolution. Owner mirror active-fetch errors return counts rather
than raise, and archived-fetch errors are suppressed (`hubspot_owners.py:203`);
backfill ignores `owner_counts.errors`, potentially reporting a healthy scan.

## Proposed 0054 Contract

Extend existing models, not a competing CRM service. Types below are PostgreSQL
types; all external IDs remain strings. This is a proposal for lead review, not
permission to apply infrastructure or inferred live metadata configuration.

1. `opportunity.hubspot_owner_id VARCHAR(64) NULL` and
   `client.hubspot_owner_id VARCHAR(64) NULL`, indexed. Do not FK to owner mirror:
   an unresolved external owner must remain representable. Keep `owner_id` as
   legacy local-user linkage until callers migrate; add explicit
   `opportunity.local_assignee_id UUID NULL REFERENCES user(id) ON DELETE SET NULL`
   for new local assignment. Never populate CRM IDs from uploader/leader/email.
   Existing local `owner_id` is not evidence sufficient to backfill CRM IDs.
2. Both `opportunity` and `client`:
   `hubspot_business_unit VARCHAR(255) NULL` (raw option value),
   `hubspot_business_unit_mapping_version INTEGER NULL` and
   `hubspot_business_unit_observed_at TIMESTAMPTZ NULL`. Client additionally needs
   `hubspot_last_modified_at TIMESTAMPTZ NULL`, `hubspot_last_seen_at TIMESTAMPTZ NULL`.
   Preserve source values independently; if mapping object is company, join the
   canonical reporting account, never OR deal and company values indiscriminately.
3. Extend `hubspot_property_mapping`: `state VARCHAR(24) NOT NULL DEFAULT 'unknown'`
   checked against `unknown/configured/absent/unavailable/ambiguous`,
   `reason VARCHAR(512) NULL`, `checked_at TIMESTAMPTZ NULL`,
   `last_success_at TIMESTAMPTZ NULL`, `version INTEGER NOT NULL DEFAULT 1`,
   `evidence JSONB NULL`, `selected_by UUID NULL REFERENCES user(id) ON DELETE SET NULL`.
   Allow existing internal_name/object_type/label/field_type to be NULL for an
   absent/unavailable row; retain last-good metadata on errors but mark it stale.
   Last-good options are not proof that a currently inaccessible property exists.
   Seed old rows `unknown`, not verified configured; refresh explicitly.
4. Make `hubspot_stage` identity `(pipeline_id, id)` with a composite PK; retain
   the existing pipeline/order index. No current declared FK references stage
   alone. Update `session.get`, StageMap keys, selects and mapper calls together.
   No new duplicated pipeline-name column is needed: join the existing mirror.
5. Add `opportunity.hubspot_seen_scan_generation BIGINT NULL` with an index on
   `(source, hubspot_seen_scan_generation)`. Reuse `sync_status.cursor`, generation
   and scan timestamps. Add `scan_lease_token UUID NULL`,
   `scan_lease_expires_at TIMESTAMPTZ NULL`, `scan_context JSONB NULL` to SyncStatus
   for bounded worker ownership and frozen mapping/source configuration at resume.
   Keep a documented same-generation resume path; starting a new scan is distinct.

Legacy ordinary CRM tables have no tenant/portal discriminator. These additions
do not magically provide multi-portal tenancy: bind this existing single-source
mirror to an explicit configured portal and reject mismatch. Multi-portal support
would require scoped composite external keys across all related tables and is not
an incidental migration assumption. Downgrade must refuse loss of populated source
facts/checkpoints or duplicate stage IDs; rehearse upgrade/parity before deployment.

## Minimal Integration Order

1. Define additive response fields: source owner `{id,label,state,archived}`
   separately for company/deal, local assignee UUID separately; pipeline ID/name;
   BU `{value,label,state,reason,object_type,mapping_version,observed_at}`; source
   as-of metadata. Existing local-UUID owner filter cannot silently become an
   external string filter: add `crm_owner`/`crm_account_owner` axes, migrate UI
   and saved-view schema explicitly, retain legacy compatibility until audited.
2. Extend discovery to collect candidates and permissions/errors. Unique verified
   candidate can bind; ambiguity needs authorized selection from actual metadata.
   Add SystemAdmin read/select/refresh under existing settings/integration routes,
   audited locally; no HubSpot property creation. Absent requires successful
   relevant metadata reads. Configured empty value means Not provided; access,
   unknown option or mapping-version mismatch means Unavailable with a reason.
3. Extend adapter fetch arguments with validated property names from the stored
   mapping; share projection in intake/backfill/company upsert. Persist explicit
   null clears only from a successfully requested property, not omitted payload
   fields. Resolve owners from the mirror in batches; never require or create a
   login for display. Refresh missing/stale owner metadata outside read requests.
4. Reuse stage/owner/property refresh at the consumer boundary with bounded
   freshness policy; pass the same qualified StageMap/mapping into both paths.
   Publish metadata errors separately from successful record consumption. Resolve
   stage labels in read joins or reconcile every affected cached deal atomically.
   Use declared closed/probability metadata, not name/order guesses.
5. Lock SyncStatus when claiming/resuming generation. For each page, commit its
   record effects, per-record seen generation and next cursor atomically; restart
   from persisted cursor. Before archive, lock and compare generation/lease,
   require final page and zero unresolved errors, then archive only unseen old
   rows and stamp completion in that same transaction. An obsolete worker must
   write neither archive state nor generation. Preserve new/concurrently modified
   rows and source-version ordering; deletion events need their own version fence.
6. Pipeline/detail/search/export/Forecast share mapped labels and filters, not
   UI-only aliases. Measure source counts by absent/unresolved/active/archived
   company owner and deal owner independently, plus BU availability/value buckets.

## Red Tests To Write First

- Owner A (company) and B (deal), both absent from User: both names resolve from
  mirror, local assignee remains C; archived B remains named after refresh.
  Blank source ID differs from unknown nonblank ID and a 403 lookup. Enabling a
  Sales-leader fallback must not alter source-owner identity or owner counts.
- Metadata configured with nonstandard internal name and option labels: adapter
  requests that exact field, persists raw value/version, and list/chip/export/
  Forecast grouping agrees. Deal and company mappings follow their declared
  object, including a configured empty value and later explicit clear.
- Property 403, malformed results, ambiguous candidates, formerly configured now
  absent, and unknown option must not become absence/zero or reuse a stale value
  without warning. Settings reload retains exact reason and version.
- Same stage ID in two pipelines; rename, reorder and non-English closed labels
  with declared probability. Source webhook through normal consumer preserves
  pipeline, label and closed metadata across deal detail and stage chips.
- Reassociation with labeled primary not first, association removal, and company
  rename: exact canonical and secondary IDs/counts after both intake and backfill.
- Two interleaved generations: older finalizer cannot archive or reset newer
  generation. Process kill after page commit resumes same cursor/generation;
  kill before commit reprocesses without duplicate effects. Assert exact all-page
  coverage and no false archive, not merely eventual row count.
- Stale fetched payload finishing after a newer write, explicit currency/activity
  clears, deletion versus newer recreation, and owner-mirror partial errors:
  source state never regresses and completion/freshness does not claim success.

## Evidence Boundaries

S20 code/tests exist; this review did not execute them. `docs/reports/s20/scoreboard.md:141`
still marks BU discovery missing; `:142` records 7 pass / 1 crash-resume xfail;
`:143` leaves staging mid-batch chaos deferred. `docs/s21/s20-carryover.md:20`
through `:22` correctly carries those into CO-07/08. Historical Venetian parity
`docs/reports/s20/t03-parity/venetian_60275608921/comparison.md:42` reports absent BU;
that is not current permission-aware portal verification. T43/T44, configured-
provider parity and human T36 remain separate from adapter tests. No requirement
is promoted to verified staging by this report.

## Phased Contract Refinement

This refinement follows another read of v3 and `docs/s21/contracts.md`; it does
not change scope. `docs/blueprint.md` is still a short legacy policy stub and
`docs/build-guide.md` points outside the repository. Its old agreement signature
gate and post-approval wording must not silently override v3's already recorded
agreement-store/amendment corrections. CRM changes do not alter GM floors,
financial approval, immutable submitted versions, or infrastructure controls.
Lead should reference existing decisions when publishing the implementation
contract, not rewrite financial policy as part of this work.

### Model And Migration Manifest

The earlier five numbered schema groups remain proposed, with these exact
defaults and activation refinements. `0054` denotes the lead-reserved family;
check actual Alembic head before assigning subsequent expand/contract revisions.

| Addition/change | Initial data/default and backfill | Validation / downgrade refusal |
| --- | --- | --- |
| Opportunity and Client `hubspot_owner_id VARCHAR(64) NULL` | No server default. NULL on upgrade means **not observed**, not confirmed absent. Only a successful authoritative fetch may populate or explicitly clear it. | Add `hubspot_owner_observed_at TIMESTAMPTZ NULL` on both records, no default, to distinguish those states. Reject empty strings at writer boundary. Refuse column removal after source facts/observations exist. |
| Opportunity `local_assignee_id UUID NULL` FK User, SET NULL | No default or automatic copy from `owner_id`: that field currently conflates CRM and local identity. Preserve legacy linkage until an explicit migration rule identifies a local assignment. | Do not drop populated local assignments. Reader compatibility exposes legacy owner separately, never relabels it a confirmed source owner. |
| Both BU value/version/observed-at triples | All NULL initially, no fabricated label or source value. After a configured-property fetch, write value (including explicit NULL), current positive mapping version and observation time together. | CHECK version NULL or > 0. Writer requires version+observation together; old rows remain unresolved. Refuse loss of populated source observations on downgrade. |
| Client source modified/seen times | Both NULL, then set from provider source timestamp / committed observation respectively. Do not copy DealGate created_at to source timestamps. | Missing source timestamp leaves a record-version fence unresolved; it cannot authorize destructive reconciliation. |
| Mapping state/reason/check times/version/evidence/selected_by | Existing mapping rows receive state `unknown`, version 1; no last_success_at is inferred from old updated_at. Metadata identity columns become nullable so absence can be represented without dummy names. | Positive version; state check from previous proposal; configured requires nonempty object/type/internal name and validated options. Restore NOT NULL only if all rows satisfy old shape. Refuse dropping selected configuration, new states or evidence until an approved backup/forward recovery exists. |
| Scan generation marker on Opportunity | `BIGINT NULL`, no synthetic generation 0; existing rows are unobserved until an actual successful page commit. | Marker only advances, including an idempotent reread whose source facts do not change. Never reset it to make archive tests pass. Active scan or non-NULL markers block lossy downgrade. |
| SyncStatus lease/context fields | NULL initially. Add `scan_phase VARCHAR(16) NOT NULL DEFAULT 'idle'` with `idle/scanning/finalizing/completed/failed`; add `scan_failure_count INTEGER NOT NULL DEFAULT 0 CHECK >= 0`. This removes cursor-NULL ambiguity between not started and end reached. | Widen existing scan_generation to BIGINT in the family. Refuse downgrade if generation exceeds INTEGER, a scan is active/recoverable, or context/lease/failure evidence would be lost. Do not assume old in-progress generation is resumable: it lacks page checkpoints. |

`scan_context` schema v1 must include explicit configured portal identifier,
environment/tenant binding, query/property fingerprint, mapping version,
source-adapter schema version, scan start bound, page size and source coverage
mode. It contains no credentials or document payloads. Keep lease duration an
operator setting with a validated positive bounded value; changing it is not a
business decision and must not change record-membership semantics.

Migration backfill is deliberately two different operations: (a) SQL expansion
and structural validation, with zero provider calls; (b) an audited resumable
application job re-reading actual CRM records. Retain measured totals for each
stage: records expected/observed/resolved/absent/unavailable/rejected/remaining.
Do not fill external IDs by matching names or emails, create source values from
local owners, or purge dirty records to make a constraint pass. Lead-owned
migration rehearsals include a representative restored isolated database and
concurrent writers. An application rollback keeps the expanded schema/data;
database downgrade is conditional, never an automatic business-data deletion.

### Metadata State Machine

Global mapping availability and individual record completeness are different
axes; do not place record-level `empty` into the global mapping state enum.

| Input / event | Persisted mapping transition | Record/UI consequence |
| --- | --- | --- |
| No successful metadata observation | any initial legacy row -> unknown | Unavailable, reason metadata not checked. No inference of absence. |
| Relevant metadata responses succeed, valid shape, zero candidates and no selected property | unknown/configured/ambiguous -> absent | Not configured in HubSpot; filter disabled with reason; prepare CRM-owner request, not automatic property creation. |
| Exactly one valid candidate, no contradictory explicit selection | unknown/absent/unavailable -> configured | Save actual object/name/type/options and provenance. Only subsequently observed matching-version values count as classified. |
| Multiple valid candidates without explicit selection | any -> ambiguous | Unavailable, reason selection required; admin selects from returned definitions, not arbitrary free text. |
| Explicit authorized selection succeeds against current metadata | unknown/ambiguous/configured -> configured | Compare-and-swap expected version; audit actor and before/after. Reject stale writes 409. |
| Timeout/403/429 exhaustion/schema error, or selected property not readable | any -> unavailable | Preserve last-good identity/options separately as stale evidence; do not relabel as absent or silently switch to another object/property. |
| Previously selected property successfully confirmed deleted or wrong type | configured -> unavailable | Reason selected property removed/type changed. A deliberate admin re-selection/clear may then discover absence; never auto-bind a similarly named replacement. |
| Same valid metadata response | configured -> configured, same version | Update checked/success time; no invalidation churn. |
| Option labels/options/type or selected object/name change | configured -> configured or unavailable, version + 1 | Immutable audit identifies version change; affected projections invalidate. Re-read/revalidate values before declaring current-version parity. |

Record presentation: observed nonempty known option at current configured
version -> named BU; observed explicit NULL/empty -> Not provided; absent
mapping -> Not configured in HubSpot; not fetched, inaccessible, stale mapping,
unknown option or invalid value -> Unavailable with reason. Always retain the
raw unknown option as source evidence, never hide it in a numeric zero bucket.
Company/deal owner presentation follows the same observation distinction:
observed blank -> No account owner / Unassigned deal owner; nonblank missing
mirror -> Owner details unavailable; valid active or archived mirror -> name,
even without a DealGate user. Metadata errors must not erase last-good facts.

When discovery checks deals before companies, a failed deal-definition read
cannot establish that company fallback is authoritative. Mark unavailable unless
an explicit previously verified company mapping is independently refreshed;
never report full absence until all relevant reads succeed. Matching candidates
by label is discovery evidence, not an excuse to guess internal property names.

### Pipeline-Stage Compatibility

Replace stage identity coherently, not only StageMap's dictionary key. Existing
rows already carry non-NULL pipeline_id; validate that relationship and count
duplicate/colliding metadata before activation. A safe expansion sequence is:

1. Add unique `(pipeline_id,id)` while retaining existing PK(id). Deploy readers
   and writers that always use both values, including pipeline queries, stage
   chips, source adapter, StageMap, fixtures, reports and admin metadata refresh.
2. While legacy workers remain, reject rather than overwrite a conflicting
   stage ID from another pipeline; record unavailable metadata. This temporary
   fail-closed behavior is **not** completed multi-pipeline support.
3. After exact API/worker revisions are verified compatible, lead changes PK
   to `(pipeline_id,id)` and removes global uniqueness. Only then ingest both
   stages with the same ID. This is a gated contract step, not safe for an old
   worker using `session.get(HubspotStage, sid)`.
4. `StageMap.resolve(pipeline_id, stage_id)` is authoritative. A legacy stage-only
   wrapper may resolve only if exactly one candidate exists; ambiguous/missing
   keys return unavailable, never select the first pipeline. Pipeline name is
   read from HubspotPipeline even when there is one pipeline in the portal.

Downgrade to global stage uniqueness refuses if duplicate stage IDs exist; no
delete/dedup operation is an acceptable rollback. The old unique constraint can
be restored only after explicit validation that every ID is unique. Source
closed classification uses declared metadata: closed+probability 1 -> won,
closed+probability 0 -> lost; closed with unavailable/contradictory probability
is unresolved, not guessed from ordering/name. Lead must confirm the supported
provider payload semantics before claiming live classification parity.

### Atomic Scan Protocol

Use the existing backfill service and SyncStatus row, not another ingestion
engine. The following is the required transaction contract for CO-07:

1. **Acquire**: lock/create the source SyncStatus row transactionally. An
   unexpired foreign lease refuses work. A resumable same-context failed/scanning
   generation with expired lease keeps its generation/cursor/seen markers and
   gets a fresh unpredictable lease token. A genuinely new scan increments
   generation, clears cursor/failures, records context/start, sets scanning.
   Commit before provider I/O; only the job owner renews its lease.
2. **Fetch**: read one bounded page using persisted cursor and frozen properties
   outside a DB transaction. Validate response schema, continuation token and
   explicit end-of-list. Repeated/nonadvancing cursor is failure, not completion.
   A timeout or invalid body must not become an empty successful page.
3. **Commit page**: lock SyncStatus again and require exact generation/token,
   scanning phase, same context and valid lease using database wall time.
   Compare each source version against the current row before effects. Persist
   record/audit/outbox effects, monotonic seen-generation markers and next cursor
   in the SAME transaction. Empty final page changes phase to finalizing;
   nonempty final page does so after all its records succeed. Renew lease and
   recheck ownership/expiry before commit; failure rolls the whole page back.
   No provider calls while holding the DB lock. A row error cannot be skipped
   while advancing the cursor or setting finalizing.
4. **Failure/restart**: retain last committed cursor and scan context, set failed
   with sanitized error and increment failure count through owner-checked CAS.
   Process death may leave scanning with an expired lease; restart acquires a
   new token on the same generation. Before-page-commit kill repeats that page;
   after-commit kill resumes next page. Existing source/event IDs and versions
   deduplicate external effects. A stale failed worker cannot write failure
   state over its successor either.
5. **Finalize**: lock source row, compare generation/token/context/lease and
   require finalizing plus zero unresolved page/record errors. Candidate removal
   requires last-seen-generation < current (or NULL), record predates scan and
   no later source observation/concurrent webhook update. Archive approved
   candidates, their audit effects and completed watermark atomically; release
   lease only after success. Never call generic touch_source with an unchecked
   generation. A superseded worker returns stale-worker refusal with no writes.
6. **Concurrent events**: webhook writes keep their existing atomic dedupe/effect
   commit and source-version fence. When a full scan holds a finalization lock,
   coordinate event writes with the same guard or lock/update candidates so a
   later committed event cannot be overwritten by an older scan snapshot.
   Reassociation/remote deletion must not bypass deletion tombstones or recreate
   deliberately removed local subjects from stale events.

Material source ambiguity: a paginated live CRM list is not necessarily a
snapshot, and this review has not verified durable cursor validity or an
authoritative deletion token. Therefore **absence from one completed list alone
does not prove deletion**. Conservative implementation revalidates candidate
absence through the existing authorized source adapter and requires explicit
authoritative absent/deleted evidence; 403, timeout and malformed data prohibit
archive. If the provider cannot establish that evidence, keep the row stale/
unavailable and report reconciliation unresolved. If a stored cursor expires,
mark that generation failed and start an explicitly new full generation; never
claim same-generation resume succeeded. T43 must cover the normal valid-cursor
restart plus this fallback separately. Finalization candidate I/O happens before
the final locked transaction and is checked against current row versions there.

### Independent Increments And Gates

| Increment | Ownership/dependency | Tests and exit gate |
| --- | --- | --- |
| A1: availability/identity contracts + pure response classification | Lead freezes schema/API names; no provider access required | State matrix above, explicit NULL versus unobserved, unknown option, archived owner/no login, malformed metadata, stale admin version. Pure tests do not close provider parity. |
| A2: metadata discovery and owner mirror | Existing hubspot_properties/owners modules; can run beside A3 after contracts | Adapter 403/429/malformed/ambiguous/deleted-property tests; preserve last-good facts, exact option labels and error counts, no synthetic login, audit/CAS of selection. |
| A3: lease/checkpoint engine | Existing hubspot_backfill/sync_status; depends only on lead's scan columns | Real isolated PostgreSQL concurrent acquisition, stale lease CAS, two generations, page rollback, process kill before/after commit, same generation/cursor resume, safe finalization. No SQLite-only concurrency claim. |
| A4: source projection wiring | A1/A2 plus expanded fields; existing intake/client/deal upsert | Actual adapter-shaped fetches include selected property; both webhook and backfill share mapping/qualified stage metadata; explicit clears and older payload race; exact association identity and measured source counts. |
| A5: source-facing UI and exports | Additive API contract, A4 populated data; UI owner separate | Real browser owner labels, metadata reasons, pipeline name on detail, filter chips/URL/persistence/export IDs and Forecast account/company grouping; no live-response mocks for acceptance. |
| A6: composite-key activation + integrated recovery | A2/A4 compatible API and every worker revision; lead contract migration | Two pipelines share stage ID without mutation; old-writer refusal before activation; downgrade refusal; metadata rename event updates all surfaces without raw-ID labels. |
| A7: combined parity and T43/T44/T36 | Approved infrastructure/provider access, isolated fixtures, human canary authorization | Fresh permission-aware metadata discovery, source-to-display report, deployed crash/queue recovery and nonduplicate side effects, 10k-deal load (or greater measured volume), exact source revisions and screenshots. |

These increments are independently schedulable only within the agreed worker
capacity/file ownership. A2 and A3 have different production files; the lead
alone integrates shared schema, consumer orchestration and deployments. A5 can
build against the frozen additive contract but cannot claim acceptance until
A4 persists real data. No current snapshot, targeted count or report text
establishes that any of these remaining gates is complete.
