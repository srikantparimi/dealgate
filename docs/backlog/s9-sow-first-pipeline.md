# S9 — SOW-first pipeline: extract → classify → derive → confirm

## Story
Rebuild the SOW ingestion path so a well-formed SOW reaches "submitted
for approval" in **under ten minutes of human time**. Every field on the
confirmation screen carries a `provenance` tag. No blank form on open.

## Backend deliverables

### 1. Provenance metadata
- Extend `sow_version.extracted_fields` JSONB shape to carry per-field
  provenance: `{value, provenance: "extracted"|"looked_up"|"calculated"|"defaulted"|"manual", page_ref?, source_id?, confidence?, warning?}`.
- Every field extracted by Bedrock or Textract must include `provenance:
  "extracted"` + `page_ref` + `confidence`. Fields the system looks up
  (client entity, owner, past-SOW similar match) get `provenance:
  "looked_up"` + `source_id`. Fields computed by the GM engine get
  `provenance: "calculated"` + `formula_version`.

### 2. Engagement-type classifier
- New service `api/app/services/engagement_classifier.py`:
  - Rules first: monthly fee + service hours/SLA → managed service;
    named roles + hourly/daily rates + hours → staff aug (one role = single_resource); fixed fee + deliverables/milestones → fixed_price; "Assessment" + 2–6 week term + workshops → assessment; T&M / not-to-exceed → tm; placement fee → permanent_placement.
  - Model second: Bedrock scores the top-2 candidates for anything the
    rules didn't lock in. Confidence returned per candidate.
  - Threshold from config: default 0.85. Above → auto-classify. Below →
    two-candidate picker on the confirmation screen.

### 3. Auto-staffing
- New service `api/app/services/auto_staffing.py`:
  - `staff_aug`: read the resource table straight from the SOW extraction
    (roles + hours + rates).
  - `single_resource`: same, one row.
  - `managed_service`: `coverage_hours ÷ FTE capacity per shift` →
    headcount by role. Deterministic.
  - `fixed_price` + `assessment`: deliverables → roles + hours proposed
    from the capability catalog + closest approved past SOWs (via
    pgvector `sow_embedding` + `capability_catalog`). Cite the source
    SOW ids.
  - `tm`: rate card × forecast utilization.
- Every staffed line has provenance (`extracted` from the SOW table,
  `looked_up` from a past SOW, `calculated` from coverage math, or
  `defaulted` from the capability catalog).

### 4. Auto-GM
- Wire `services/auto_staffing` → `services/delivery_model.create_gm_model_version`
  automatically at extract time. The resulting `gm_model` opens as a
  Draft; every resource_line has provenance. Cost comes from `lookup_cost`
  (HR cost bands); revenue rate from `resolve_bill_rate` (client card).
- Mixed fixed-fee default allocation: cost-weighted effort. Finance can
  override with a recorded basis; the override stores its basis text.

### 5. Auto approver routing
- Existing `submit_package` already routes by role. Extend to:
  - Resolve the specific accountable user per function from a
    `function_owner` table (new; simple map role → user for a business
    unit; falls back to the group's first member if nothing configured).
  - Pre-draft the CEO exception brief the moment the auto-GM run
    predicts a below-floor package — before submit — so the Sales user
    sees "Will trigger" on the CEO gate.

### 6. Renewal + notice scheduling
- Already wired in Sprint 5 renewals scheduler. Extension: honor
  `notice_period` extracted from the SOW; schedule that Legal task at
  `notice_deadline - 60` per the manifesto.

### 7. Confirmation endpoint
- `GET /sow/{opportunity_id}/confirmation` — one call that returns the
  full derived package: extracted fields + confidence, classified
  engagement + top-2 candidates, resolved client rate card + warning if
  fallback, staffed grid with provenance, computed GM per component +
  floor result, proposed approvers, projected renewal/notice tasks, and
  a `needs_you` list of fields still requiring human input.
- `POST /sow/{opportunity_id}/confirmation/submit` — commits the
  confirmed values, transitions the opportunity + package. Idempotent.

## Frontend deliverables
- `web/src/pages/v2/SowStudio.tsx` — rebuild as a **confirmation
  screen**. The five spec §13 steps become the *structure of one
  page*, not five blank forms. Every field renders with its provenance
  chip and a "change" affordance. `manual` badges (there should be ≤ 3
  for a well-formed SOW) are highlighted. Submit disabled until every
  `needs_you` slot is resolved.
- `web/src/pages/v2/SowWorkspace.tsx` staffing grid — pre-populated
  from the auto-staffing output. Provenance chip per row. "Editing is
  the review."
- Every provenance chip uses the v2.1 tokens (`primarySubtle` for
  `extracted`, `success` for `calculated`, `warning` for `defaulted` +
  `manual`, `neutral` for `looked_up`).

## Tests
- Backend service tests for classifier + auto-staffing + confirmation
  endpoint.
- E2E tests in `tests/e2e/specs/`:
  - `11-sow-first-happy-path.spec.ts` — upload → confirmation screen
    shows engagement type auto-selected, staffing populated, GM
    computed, approvers assigned; submit works with ≤ 3 `needs_you`
    fields; measured completion < 10 min.
  - `12-sow-first-below-floor.spec.ts` — below-floor SOW auto-drafts
    the CEO brief; gate step reads "Will trigger" pre-submit.
  - `13-sow-first-no-client-card.spec.ts` — first SOW for a new client
    triggers exactly one inline rate-card request + fallback warning.

## Six fixture SOWs
Under `fixtures/sample_sows/`:
- `01_staff_aug_us.pdf` — well-formed staff aug in US, at policy.
- `02_managed_service_india.pdf` — managed service India, at policy.
- `03_fixed_price_mixed.pdf` — mixed fixed-fee, both floors pass.
- `04_assessment_4week.pdf` — 4-week assessment.
- `05_tm_capped.pdf` — T&M with a cap.
- `06_below_floor.pdf` — deliberately below both floors, drives the
  CEO gate.

Each PDF is generated deterministically by a Python script + `reportlab`
(add as dev dep) so the fixtures re-produce identically. No real client
data.

## Notes
- `sow-first-principles.md` is the authoritative acceptance spec.
- CLAUDE.md rule 10 gates review.
