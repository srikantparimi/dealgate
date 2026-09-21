# E2E: full approval-package journey (from S13a follow-up)

Kanna, product owner. 21 September 2026. Follows S13a. Deferred out of S13a
because scripting the four role-scoped submits through the browser is a
first-class story of its own, not a sub-task of delete-and-archive.

## Why

S13a proves that the delete-with-governance UI refuses hard-deletes on
approved records and offers Archive instead — but the test used
`/dev/seed-approved-package` (test-only, staging-gated) to reach the
approved state instead of driving the real S12 approval ceremony. The
seed endpoint bypasses:

- the extractor's field-by-field confirmation on the SOW Studio page,
- the S12 signatories picker + confirmation-submit,
- the four separation-of-duties decisions (Delivery, HR, Finance, Legal),
- the CEO exception path where applicable.

Every one of those is real behaviour the product depends on, and none of
them has an end-to-end Playwright proof yet.

## Definition of done

Given a fresh fixture SOW, a Playwright spec drives the full journey to
`released` in the browser, and asserts separation-of-duties along the way:

1. **Auth**: four role-scoped e2e users exist in the staging Cognito pool
   plus a fifth for the CEO exception path:
   - `e2e-sales@smartek21.com`         → Sales (submits the package)
   - `e2e-delivery@smartek21.com`      → Delivery + SystemAdmin-free
   - `e2e-hr@smartek21.com`            → HR
   - `e2e-finance@smartek21.com`       → Finance
   - `e2e-legal@smartek21.com`         → Legal
   - `e2e-ceo@smartek21.com`           → CEO (for the exception path)
   Passwords in `officeapp-dev-e2e-user-<role>` secrets, rotated the same
   way the existing e2e user is.

2. **Field confirmation**: the spec uploads the fixture, walks through
   the confirm grid (or the API PATCH loop that mirrors it), and lands
   the version at `sow_version.confirmed_at`.

3. **Signatories**: pick the two S12 signatories (client + internal),
   submit the confirmation. Assert `governance_status = SOWDraft.confirmed`
   and a `sow_confirmation.submitted` audit row exists.

4. **Package**: Sales submits the approval package via the UI. Assert an
   `ApprovalPackage` row is created in status `pending_delivery_hr`.

5. **Separation of duties (the load-bearing case)**: the submitting Sales
   user tries the four decisions in the UI. Each is refused with a 403;
   the button either isn't rendered or the API rejects. Screenshot the
   refusal.

6. **Sequenced approvals**: Delivery approves → HR approves → status
   flips to `pending_finance`; Finance approves → status flips to
   `pending_legal`; Legal approves → status flips to `released`. Assert
   the audit chain after each step.

7. **CEO exception path**: replay with a fixture whose GM breaches the
   floor. Delivery approve fires the CEO brief; CEO approves; then the
   normal Finance/Legal steps follow. Screenshot the CEO decision.

8. **Delete-refusal after release** (regression against S13a): once
   released, a portal Delete on the client shows the same Archive-instead
   dialog S13a proves for the seeded case. This closes the loop — S13a's
   seed-endpoint stand-in is retired for this fixture.

9. **Zero residue**: the `afterAll` cleans up every client the spec
   created via the S13a DELETE endpoint (or Archive for the released
   ones, since delete is refused after step 8).

## Acceptance tests (Given/When/Then)

```
Given a fresh fixture SOW uploaded by e2e-sales
When e2e-sales submits the approval package
Then an ApprovalPackage row is created in status pending_delivery_hr
 And the "decide" button is not visible in the UI for e2e-sales
 And POST /approvals/packages/{id}/decisions/delivery from e2e-sales returns 403

Given the package is in status pending_delivery_hr
When e2e-delivery clicks Approve and e2e-hr clicks Approve
Then the status flips to pending_finance
 And two audit rows record the decisions

Given the package is in status pending_finance
When e2e-finance approves
Then the status flips to pending_legal

Given the package is in status pending_legal
When e2e-legal approves
Then the status flips to released
 And a POST /clients/{id} DELETE from e2e-sales returns 409
 And the Delete dialog on that client shows "Archive instead"
```

## Non-goals

- Signed-SOW upload after release (that's the S5 signed-sow story; a
  separate spec covers it).
- HubSpot writeback (already covered by the S4 wave 3 integration test).
- The retracted / voided package path.

## Files this will touch (approx.)

- `tests/e2e/fixtures/staging-auth.ts` — per-role token minting.
- `tests/e2e/specs/21-approval-journey.spec.ts` — new spec (est. 350 LOC).
- Terraform + secrets: add four new Cognito users + secrets manager rows.
- `docs/reports/e2e-approval-journey.md` — proof report.
