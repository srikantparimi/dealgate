# S7 — Delivery Model Builder: WBS phases + reusable templates

## User story A: Work-breakdown-structure phases
As Delivery, the model has a first-class `phase` (workstream) row that
groups resource lines and links to SOW deliverables. Blueprint §8 lists
"Work breakdown" as an explicit input.

## Acceptance A
- Migration adds `gm_model_phase` (id, gm_model_id FK, name, order INT,
  sow_deliverable_ref VARCHAR nullable, description). Resource_line and
  cost_line get `phase_id` nullable FK.
- Builder UI shows an accordion per phase; resource + cost rows nest
  under a phase (fall back to "Ungrouped" for legacy rows).
- Reordering supported via `PATCH /delivery-model/{opp}/phases/reorder`.
- GM computation groups revenue+cost per phase for a summary widget in
  the right panel; overall model GM unchanged (sum across phases).

## User story B: Save-as-template
As Delivery, after a model is approved I can save it as a reusable
template. On a new opportunity, I pick a template and it seeds the
phase/resource/cost grid.

## Acceptance B
- New table `gm_model_template` (id, name, engagement_type, created_by,
  created_at, template_json JSONB) — captures phases + resource_lines
  (with role/seniority/location/allocation + relative hours) + cost_lines.
- `POST /delivery-model/templates` from any Delivery user; only saves the
  model shape, not the specific SOW or numbers.
- `POST /delivery-model/{opp}/from-template/{template_id}` seeds a new
  draft gm_model version from the template.
- Builder UI: `Save as template` button on the model; template picker in
  the header for a new deal.
- Tests: template round-trip preserves phase/role/allocation; loading a
  template into a fresh opp respects the current rate cards for cost
  band suggestions (does NOT hardcode cost).

## Notes
- Blueprint §8 explicit inputs.
- Templates never carry cost — cost always comes from active rate cards.
