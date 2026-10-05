# T23 Publication, Restricted Readers And Planning Boundaries

Baseline188adf3. Lead owns tests/e2e/local/s21-publication-boundaries.spec.ts,
integration, private runtime and ledger. Governance owns only
scripts/s21_publication_boundary_fixture.py and lanes/publication-boundary-fixture.md
in /Users/srikanthparimi/OfficeApp/dealgate-s21-publication-boundary-fixture,
branchs21/publication-boundary-fixture. Author-only; no runtime/installs.
Independent QA owns read-only review, no shared edits.

Reuse T22 half-time business oracle, but synthetic source must contain actual
financial values so cost-disclosure checks are nonvacuous. Initial2US/5India,
Nov1-Apr30,0.5allocation:7heads/3.5required/2.5matched/1gap. Real API revision
changes US2->3 and startDec1 preservingApr30end:8heads/4required/2.5matched/
1.5gap; USgap2people/1FTE, India1/0.5. Visible stale -> republish -> new sourcing
draft, exactOct17/Nov1 deadlines; old publication/draft immutable.

Use private s21_pub_<32hex> DB/tenant, literal owned localhost55421/user s21.
Lead switches one API serially from Admin/HR/Delivery to Sales-only (same owner)
for actual restricted browser/HTTP proof, then restores retained s21_journey.
No parallel heavy runtimes, no mock feature responses. Source date/quantity edit
is API-authored: current UI edits assumptions only; disclose this boundary.

Reject valid publication/draft requests plus reserve/hire/person_id/status extras,
exact422 and unchanged publication/draft/audit/workforce counts. Successful drafts
also leave workforce intervals unchanged. HR imports of observed reserved/hired
commitments remain supported; these are not operational hire commands.
Sales demand must be nonempty yet omit costs/rates/inputs/named matches; supply,
import history and sourcing are403 and UI has no financial values.
Other T23 conditions use mapped existing separate-worker replay/history evidence;
no whole FC-07/10/staging promotion from this bounded scenario.
