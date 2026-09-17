# Open questions

The lead answers these before the sprint that depends on them starts. Do not
guess. Each question names the sprint it blocks.

## Blocks Sprint 1

- [ ] **HubSpot edition, private-app scopes, sandbox URL.** Which HubSpot
  edition is licensed? Sandbox for staging? What scopes should the private app
  have? (Design: build-guide §11.)
- [ ] **Identity provider.** Entra ID or Google Workspace? Group name per role
  (Marketing, Sales, Presales, Delivery, HR, Finance, Legal, CEO, SystemAdmin)?
  (Design: build-guide §3.)
- [ ] **Build-guide §10 mirror.** The repo copy of `docs/build-guide.md` only
  contains the section list — §10 (data model) columns are not yet mirrored
  from the Claude Doc. Sprint 1 migration implements the columns named in the
  story files plus minimal skeletons for `client`, `legal_entity`, `agreement`
  (see `api/alembic/versions/20260917_0001_initial.py`). Mirror §10 and confirm
  or flag columns to add / rename. (Design: build-guide §10.)
- [ ] **`audit_event` DB grants in infra.** Migration adds a length CHECK on
  `row_hash` but the real append-only guarantee (no UPDATE/DELETE for the app
  role) must be granted in CDK/psql, not the app migration. Who owns adding
  that to `infra/`? (Design: blueprint §12.)
- [ ] **Task-to-opportunity linkage.** `task` has no `opportunity_id` column in
  the S1 schema (see `api/app/models/task.py`). The HubSpot intake service
  currently records the linkage inside `audit_event.after` (`opportunity_id`,
  `kind="intake"`) and reuses that trail for idempotency checks. Should the
  next migration add a proper FK column on `task`, or is the audit-only
  linkage the intended shape through S1? (Story: s1-e2.)
- [ ] **HubSpot v3 signed URI.** The v3 signature includes the full HTTPS URL.
  Behind the ALB the app sees `http://` and the internal host; the router
  reads `HUBSPOT_WEBHOOK_URL` to reconstruct what HubSpot signed. Confirm
  the staging/prod public URL and whether ALB will preserve query strings
  verbatim. (Story: s1-e2.)
- [ ] **Opportunity → client linkage.** `opportunity` has no `client_id` or
  `legal_entity_id` today, so the S1-E2 coverage helper cannot derive NDA/MSA
  state from a deal — it returns "No client linked" for every row (see
  `api/app/services/deals.py::coverage_state_summary`). Which column owns the
  association (deal-level `client_id`, `legal_entity_id`, or a join table),
  and which sprint adds the migration? (Design: build-guide §10, §6.2.)

## Blocks Sprint 2

- [ ] **GM definition (Finance).** What is inside `delivery_cost`? Burden,
  bench, tools, travel, subcontractors, PM overhead — in or out? (Design: §7.)
- [ ] **Mixed fixed-fee allocation (Finance).** How is one fee split between US
  and India work — by work package, by hours, by an approved method? (Design: §7.)
  Current `fixed_price` template takes `revenue_us` / `revenue_india` as
  explicit inputs and validates only that they sum to `total_price`.
- [ ] **Rate cards v1 (Finance + HR).** Planning cost bands by role, seniority
  and location. FX convention (fixed at SOW date? monthly?). (Design: §7.)
- [ ] **Alert channel.** Teams or Slack, plus email? Webhook URL for the
  incoming channel. (Design: §9.)
- [ ] **PBU (paid-but-unbilled) time in staff-aug (Delivery + Finance).** The
  §7 line "PBU time" currently modeled as extra hours per resource that add
  to cost at `hourly_cost` and add zero revenue (holidays, ramp, absorbed
  PTO). Confirm this is the intended shape, and whether replacement
  obligation should add a bench-cost reserve rather than being a policy
  flag only. (Design: §7 staff aug.)
- [ ] **T&M cap treatment (Finance).** Current `tm` template scores GM at
  forecast hours; when a revenue cap is set below forecast, revenue is
  clipped to the cap while cost stays at forecast. Confirm this is the
  expected pessimistic view for approvals. (Design: §7 T&M.)
- [ ] **Managed service term basis (Finance).** GM computed over the full
  contracted term (`monthly_fee * term_months`) vs. steady-state month.
  Current library uses full term. (Design: §7 managed service.)

## Blocks Sprint 4

- [ ] **CEO delegate policy and approval SLAs.** Named delegate window,
  business-day SLAs per approver role. (Design: §3, §4.)

## Blocks Sprint 6 / rollout

- [ ] **E-signature tool.** Manual upload for pilot; which tool afterwards
  (DocuSign, Adobe Sign, other)? Authorized signatories list. (Design: §6.7.)
- [ ] **Source for actuals.** Timesheets + cost system. CSV import for pilot;
  integration target after. (Design: §9.)
- [ ] **Executive sponsor and process owner.** Named owner of rate cards,
  approver changes, and failed integrations after go-live.

## Ambient

- [ ] **Search API for the adviser.** Tavily vs Brave — verify pricing and
  data-residency. (Design: §5, §11.)
- [ ] **Bedrock model access.** Which Claude models are enabled in the AWS
  account and region?
