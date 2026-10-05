# Independent Extraction Review

Baseline: `646419bccbbc7984c77801091954881e9dc3b8f2`, branch
`s21/qa-extraction-review`. Bounded static review of `e75af5c` and `0cbb530`,
their callers, and the final extraction/currency contract sections. This report
is the only changed file. No tests, application runtime, database, browser,
installs or cloud calls were run. Findings below are code-derived, not executed
reproductions. Existing focused/browser results do not establish these cases.

## Findings

### 1. P1: Submission Can Freeze A Newly Conflicted Version

`api/app/services/sow_confirmation.py:759` builds and checks scope without the
parent/version lock, then stamps confirmation at line 770. The legacy path at
`api/app/services/sow_extract.py:648` likewise reads fields and checks conflicts
before an unlocked confirmation write. Replay obtains parent/version locks and
refreshes JSON at `sow_extract.py:363`, but these submission paths do not join
that protocol or recheck after waiting.

Reproduction schedule: start with complete, human-confirmed field envelopes,
no conflicts, an existing GM and no version-level confirmation. Session A runs
a same-document replay producing a different price candidate, holds its locks
and leaves the conflict uncommitted. Session B submits scope or legacy SOW:
its plain reads see the old, conflict-free committed JSON. Its confirmation
write waits for A. Commit A, then allow B to continue and commit. B does not
reload/revalidate the conflict, leaving `confirmed_at` set alongside an
unresolved conflict. Subsequent review fails the immutable gate at
`sow_extract.py:372`, so the normal correction flow is now unavailable.

Expected: submission waits and rechecks the locked current source, refusing the
conflict without confirmation/audit success. Missing proof: separate PostgreSQL
sessions with an observed wait for both submission entry points. The current
scope/legacy tests only submit after a conflict is already visible.

Parent-first locking does **not currently protect latest-version selection**:
`build_confirmation` selects the latest version at `sow_confirmation.py:655`
through the plain query at `sow_extract.py:729`. The replay helper's parent lock
protects an explicitly supplied version, not that earlier selection. A lock
added only after selecting/loading the version would not establish that it is
still the selected current source. The regression boundary must include a new
version arriving while confirmation waits: select/refresh under the shared
parent lock and verify the intended source identity. This also depends on new
version writers participating in that protocol; this review does not claim
that every upload writer already does so.

### 2. P1: Ownership Is Not Rechecked After Acquiring The Source Lock

`api/app/routers/sow.py:410` authorizes through `_conflict_editor` before
`api/app/services/extraction_conflicts.py:43` acquires the mutable-source lock.
The locked opportunity is refreshed at `sow_extract.py:363`, but neither the
service nor route rechecks `can_mutate_deal` on that refreshed row. The service
receives an actor ID, not the authority needed for that check.

Reproduction schedule: a Sales owner obtains a current review token. Another
transaction changes the opportunity owner while holding its row lock. The old
owner's POST reads the still-committed old owner and passes authorization, then
blocks on the row lock. Commit the transfer. The POST refreshes the new owner
but still accepts the old owner's decision and records its audit. No token
change occurs because owner identity is not part of the token.

Expected: 403/no field or audit mutation when the locked authoritative row no
longer permits the caller. Missing proof: a transfer-versus-review schedule
with the old owner lacking SalesLeader/SystemAdmin. The existing foreign-editor
test only tests a caller who was already unauthorized before the request.

### 3. P1: Valued But Disputed Currency Does Not Block Scope

`api/app/services/sow_confirmation.py:383` checks missing values and, at line
388, unconfirmed `defaulted` currency. A valid extraction envelope such as
`{"value":"USD","provenance":"extracted","status":"disputed","page_ref":2}`
matches neither condition. This is a supported extractor state: the validator
accepts disputed values at `api/app/integrations/bedrock_sow_extract.py:191`, and
the prompt explicitly uses disputed for contradictory evidence at line 262.

Reproduction: document clauses disagree between USD and CAD; preserve the
extractor's nonempty disputed currency, with other scope prerequisites valid.
`scope_blockers` omits currency and `submit_confirmation` stamps the version
without an explicit currency confirmation. This violates the missing/ambiguous
currency contract, not merely a preferred UI warning.

Expected: a currency blocker and 422 until explicit human confirmation.
Missing test: a nonempty disputed currency envelope. The new parameterized
currency test includes disputed currency only with `value=None`, so it exercises
the existing missing-value branch instead. Preserve the existing positive
historical confirmed-default case when closing this gap.

### 4. P2: A Remaining Field's Draft Is Silently Rebound To A New Token

`web/src/components/ExtractionConflicts.tsx:47` replaces all returned items but
retains `choices` and `reasons`, which are indexed only by field name. A later
save takes the updated item's token at line 44 and the old draft at line 45.
The parent keeps the same component/version mounted while conflicts remain
(`web/src/pages/v2/SowStudio.tsx:656`).

Reproduction: display conflicts A and B. Select "accept" and type a reason for
B. Another editor re-extracts, changing only B's candidate while leaving A's
current/candidate/model/prompt unchanged. Save A with its still-valid token.
The successful response contains B's new candidate and token; B's old choice
and reason remain selected. Saving B now accepts the new candidate using a
decision drafted against the old candidate, rather than requiring its review.

Expected: retain drafts only while their exact field review token is unchanged;
changed candidates require a new explicit choice. Missing test: two fields,
successful A response containing a changed B token, and no accepted B POST
until a new decision. Existing UI tests use one conflict and cover a rejected
stale save, not this successful-response transition.

## Boundaries And Evidence

Static positives: the review token includes document/version, both envelopes
and extractor revisions; conflict review refreshes locked JSON; keep preserves
the current envelope; accept retains candidate evidence and stamps confirmed;
decision and audit share the caller transaction. Error clearing is restricted
to the conflict-derived prefix, and the provider-failure preservation case is
covered by an existing focused test. These observations are not fresh pass
claims or proof of all interleavings.

Inspected focused tests: `api/tests/test_s21_extraction_conflicts.py`,
`api/tests/test_s21_currency_confirmation.py`,
`web/src/__tests__/v2/ExtractionConflicts.test.tsx`, and
`tests/e2e/local/s21-extraction-conflicts.spec.ts`. No independent tests were
authored because this task owns the report only. Proposed assertions above
must be established unchanged before production corrections are accepted.

| Numbered contract slice | State | Evidence |
| --- | --- | --- |
| FC-09 / S21-18 / T16 / T24 conflict review | missing | Static findings 1, 2 and 4; independent execution and fixes absent |
| S21-04 / S21-18 / FC-09 ambiguous currency | missing | Static finding 3; independent execution and fix absent |

This is not whole-requirement acceptance, staging verification, a report on the
held-out seven-profile corpus, or an authorization to waive remaining work.
