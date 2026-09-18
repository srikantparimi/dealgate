# S4 E7 — Approval packages, sequential + parallel review, change-voids-approval

## User story
As Sales, I submit the approval package for a deal (frozen SOW version + GM
model version). Delivery + HR approve first (feasibility + staffing), then
Finance + Legal approve in parallel (economics + terms). Any change to
scope, price, cost, staffing or allocation voids all approvals and restarts
review. When every floor is met and all four functions approve, the package
becomes Ready to Sign. If any floor is missed, the package escalates to
the CEO with a generated brief.

## Acceptance tests (Given/When/Then)
- Given a deal has a confirmed sow_version and complete gm_model, when I POST
  `/approvals/packages`, then a frozen `approval_package` is created (sha256
  of sow_version + gm_model contents; package_hash stored).
- Given a package is `pending_delivery_hr`, when Delivery approves, then the
  package waits for HR; when both approve, it moves to `pending_finance_legal`.
- Given a package is `pending_finance_legal`, when Finance approves, then
  the package still waits for Legal; when both approve, it moves to
  `ready_to_sign` (if floors pass) or `pending_ceo_exception` (if any floor
  fails).
- Given a package is any pending state, when the underlying sow_version or
  gm_model changes, then the package is voided (audit `package.voided`),
  all approvals invalidated, and a new package must be submitted.
- Given I try to approve my own submission, then 403 (separation of duties).
- Given I hold two roles (e.g. Finance AND Delivery), then I can approve
  only one function per package (recorded).
- Given a package is `ready_to_sign`, when Sales tries to change anything,
  then 409 (package is frozen); to change, submit a new one.

## Data touched
- New: `approval_package` (id, opportunity_id, sow_version_id, gm_model_id,
  package_hash, status, submitted_by, submitted_at, released_at nullable).
- New: `approval` (id, package_id, function ENUM(delivery|hr|finance|legal),
  approver_id, decision ENUM(approve|reject|request_changes), reason,
  decided_at).

## Roles
- Submit: account owner + SystemAdmin.
- Approve delivery: Delivery role.
- Approve hr: HR role.
- Approve finance: Finance role.
- Approve legal: Legal role.
- Read: all governance roles.

## Out of scope
- CEO exception UI (separate story in same wave).
- HubSpot write-back (separate story).
- Signed SOW distribution (Sprint 5).

## Notes
- Blueprint §4 (workflow diagram) + §6.5 + §6.6.
- Every approval writes audit_event `approval.<function>.<decision>`.
