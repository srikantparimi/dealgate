# T40 / CO-04 Independent Static Review

## Scope And Evidence

- Reviewed integration `cb53eb850d9dc8f4bfc06b8a1f52254fd477b332` and the
  read-only reviewer-registration change in
  `tests/e2e/local/s21-approval-card.spec.ts` on 2026-10-02.
- Owned output: this report only, on `s21/ocr-evidence`. The unmerged OCR
  checkpoint is preserved. No application/test edits, test execution,
  application imports, browser, database, provider calls or installs occurred.
- Requirement: original T40 requires exact distinct current in-review SOW
  package membership and count across card and destination. Multiple reviewers
  must not multiply a SOW; two SOWs under one deal remain two. CO-04 also requires
  correct visibility and an honest destination, not assignment counts.
- All source line numbers below refer to `cb53eb8`, not subsequent dirty repairs.
  Findings are static deductions with proposed reproductions, not executed
  failures. This report does not close T40 or claim staging verification.

## Findings

### P2: Equal-Count Membership Changes Can Produce A Mixed Board

References: `web/src/pages/v2/SowApprovals.tsx:89`,
`api/app/services/approvals.py:1145`,
`api/app/routers/approvals.py:262`,
`web/src/pages/v2/CommandCenter.tsx:232`.

The destination accepts pages when their totals agree, identities are distinct,
and collected length reaches total. Each request independently recomputes the
current authorized population. Neither the response nor subsequent requests
bind membership to a population revision. Equal totals and no duplicate IDs
therefore do not establish a consistent population. The card also links only
`status=in_review`, without binding the destination to its observed population.

Minimal API schedule: with ordered current packages `[A, B]`, request page 1,
size 1, obtaining `A`, total 2. In one transaction, remove both A and B from the
current population and create current packages C and D, ordered `[C, D]`.
Request page 2, size 1, obtaining D, total 2. The existing client checks accept
`[A, D]`, although those packages never belonged to one current population.
The same schedule works at the UI's size 100 by replacing both 100-row pages
between requests; this is not dependent on accepting a malformed page size.
An equal-count replacement after card load also breaks exact card/destination
membership without any pagination at all.

Minimal assertions: bind a real API page to a population revision, replace
membership without changing total, and require an explicit stale response on
the next page. At the UI boundary, assert that a same-total/different-revision
page yields an error and no partial cards; assert that the card's revision is
sent on destination load. Explicit refresh may acquire a new revision, but must
not silently combine pages or automatically retry until a green snapshot occurs.
Authorization loss between pages should likewise invalidate the old population.

Existing `web/src/__tests__/v2/S21ApprovalCard.test.tsx:37` changes total from 2
to 4, so it does not falsify this case. The reviewed connected browser reads
size-1 pages of a stable two-package population; it does not mutate membership
between them. Those assertions remain useful but do not establish snapshot
consistency.

### P2: Global First-30 Preview Can Hide An Entire Pending Lane

References: `web/src/pages/v2/CommandCenter.tsx:580`,
`web/src/pages/v2/CommandCenter.tsx:592`,
`web/src/pages/v2/CommandCenter.tsx:279`,
`web/src/pages/v2/CommandCenter.tsx:442`,
`web/src/pages/v2/command/ApprovalPreview.tsx:170`.

The change replaces per-status preview queries with one newest-first canonical
page of 30, then filters that page into the three lanes. Reproduction: 30 newer
pending Delivery/HR packages and one older pending CEO package, all current and
visible to the same reader. The scalar correctly reports 31, but the CEO preview
array is empty and its lane count becomes zero. When the separate CEO dashboard
does not provide an exception, the fallback priority signal also disappears.
The same starvation affects Finance/Legal. This is a presentation regression,
not an error in the canonical scalar or an authorization bypass.

Minimal assertion: use that 31-package population and assert the older CEO's
exact identity remains in the CEO preview, with the fallback decision signal
when no separate dashboard exception exists. Repeat with Finance/Legal if the
loading paths differ. Include more than one API page when verifying a repair
that loads the whole population, and retain revision consistency. The reviewed
two-package browser fixture and total-only card unit test cannot detect this.

## Checks Without A New Finding

- Canonical status selection ranks nonvoided packages per SOW before filtering
  pending states (`api/app/services/approvals.py:1098`). A newer approved package
  therefore does not reveal an older pending one. The three pending states,
  source relationship, archive, discarded and superseded checks are explicit
  at line 1118. Two separate SOWs under one opportunity remain separate.
- Router role/owner/assignment context is passed to the service
  (`api/app/routers/approvals.py:271`). Owner/assignment SQL filtering and
  `allowed_for_package` run before both pagination and count
  (`api/app/services/approvals.py:1134`). No concrete new authorization bypass
  was identified in this canonical path. This is not a review of every legacy
  exact-status or detail endpoint.
- Existing `api/tests/test_s21_approval_card.py` covers current-versus-old
  packages, archive/supersession, owner/assignment restrictions, valid fixture
  participants, unissued siblings, and damaged grants/provenance. Source
  inspection does not independently establish their execution results.
- The connected fixture has two included SOWs under one deal, five distinct
  assigned reviewers per included package, an excluded ready-to-sign package,
  an unsubmitted draft and another fixture's hidden package. Its exact-identity
  assertions address the literal T40 membership/count case. Synthetic ORM
  package setup is disclosed; it is not proof of approval transitions.
- The dirty reviewer fix registers each local test identity through
  `POST /dev/test-fixtures`, asserts 201, then reads `/me`. It addresses missing
  persisted users rather than weakening reviewer validation. The earlier 422
  is a fixture-setup failure, not a demonstrated T40 application failure.

## Repair And Acceptance Boundary

The lead reports population-revision repair `1e74402` with 24 passing worker
tests, and plans a shared complete-population loader for previews and destination.
These are lead-reported repairs pending independent verification, not findings
retested here. New dirty revision assertions seen during review were not treated
as executed proof. Browser session 76427 was owned by the lead; this review did
not execute or independently establish its result. T40 acceptance remains the
lead's evidence decision, with local and staging evidence kept separate.

## Repair Verification At 205d51a

Bounded static follow-up reviewed integration
`205d51aadec743eb613fdb3ceb184520eacb79bb`, including canonical revision backend
`7c984ab`. Only this section was appended; the original findings and evidence
limits above remain unchanged. No test, browser or application runtime was run.

**Finding 1: statically resolved.**
`api/app/services/approvals.py:1150` hashes the complete authorized ordered list
of package identities, states and source-version identities, bound to actor,
reader and opportunity-filter context. It compares the supplied revision before
slicing and raises 409 on mismatch. Equal-count replacement therefore changes
the revision; it no longer relies on count or overlap to identify stale pages.
The router forwards the supplied revision and returns the computed revision
(`api/app/routers/approvals.py:270`). Authorization still precedes both revision
and pagination; the token does not substitute for access checks.

`web/src/api/approvalPopulation.ts:10` adopts the first canonical revision when
unpinned, sends it on every subsequent page, and rejects absent or different
response revisions. Existing total, empty-page and duplicate guards remain.
The Command Center retains the revision and encodes it into the card destination
(`web/src/pages/v2/CommandCenter.tsx:233`). The board reads that URL parameter,
passes it into the loader and reloads when it changes
(`web/src/pages/v2/SowApprovals.tsx:73`). On failure it clears partial cards and
shows an error. Explicit Reload removes the old URL revision and starts a new
load; tab changes similarly abandon the old pin. There is no automatic
retry-to-success path. These controls address both the inter-page schedule and
the card-to-destination replacement in the original finding.

**Finding 2: statically resolved.** Command Center now calls the same complete
population loader (`web/src/pages/v2/CommandCenter.tsx:581`). Only after every
page succeeds does it derive and slice each status lane (line 593). An older CEO
or Finance package can no longer disappear solely because another lane fills
the first global page. The populated CEO array also reaches the existing
fallback priority-signal path.

The inspected test source adds equal-total/different-revision rejection and
100 newer Delivery packages plus an older CEO package in
`web/src/__tests__/v2/S21ApprovalCard.test.tsx:69`, and backend same-count
replacement, pending-state change and viewer/filter binding cases in
`api/tests/test_s21_approval_card.py:236`. The connected spec now asserts token
propagation, stale 409, no stale cards and explicit refresh. These are meaningful
assertions for the two repairs, not independent execution evidence.

Lead-reported evidence: UI session 61712, five passed; backend session 62974,
47 affected tests passed; typecheck session 55907, exit 0. The repaired connected
browser run was pending at this review. No remaining concrete defect was found
within the two findings and token/refresh scope. Static closure of these two
findings is not whole T40 acceptance, a database-isolation proof, or staging
verification.
