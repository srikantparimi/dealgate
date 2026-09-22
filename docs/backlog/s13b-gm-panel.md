# S13b: Finance GM presentation and direct costs

Source: [product directive](../directives/s13b-gm-panel.md).

## Acceptance

- Given a $50,000 US fixed-price plan with 80 and 160 hours at $120, Confirm
  shows Cost /hr $120.00, a fixed-price bill-rate label, whole hours and 100% allocation.
- Given $1,000 of non-reimbursable costs, the server computes $29,800 delivery
  cost, $20,200 gross profit, 40.4% GM, and 2.0% direct cost as a share of price.
- Given $2,300 reimbursable travel, those GM results do not change; the amount
  appears as client-reimbursed pass-through outside GM.
- Given a percentage basis or proportional geography, the server resolves
  the amount and labor-weighted allocation using Decimal arithmetic.
- Given a saved GM version, its direct-cost amount, basis, provenance and
  reimbursement state survive reload and export, and reviewers see the pinned version.
- Given no resources in India, its row is not applicable and the chip tests
  only US. A mixed plan retains both independent floor checks.
- Given an incomplete cost plan, the panel cannot claim that the GM passes.
- Given expense terms without a stated budget, extraction proposes an unpriced
  draft. Human save is required, and removing a proposal remains removed.
- Given Finance or SystemAdmin access, category choices can be configured
  under Settings. Cost visibility remains subject to existing role rules.
- Given an internal identity stored as a UUID placeholder, signatories and
  People use the same display-name helper as client owners.

## Manual Inputs

The SOW can describe expense obligations without specifying the delivery
budget. Amounts, category refinements, geography and reimbursement overrides
are therefore human inputs when no reliable extracted value exists. Proposed
expense wording, source references and stated amounts are retained. Percentage
amounts, allocation and GM results are calculated on the server.

## Verification

See [implementation report](../reports/s13b.md) for automated evidence and the
remaining browser/staging acceptance step.
