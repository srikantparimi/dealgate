# S7 — NDA + MSA hard block + cost-field response filtering + SLA timers

## User story A: NDA + MSA gate
As Legal, no approval package can be submitted for a client that lacks an
Executed NDA AND an Executed MSA on any of its legal entities. The blueprint
§2 hard rule "No valid NDA + MSA → SOW cannot move to signature" was tracked
in coverage_state but never enforced at `submit_package`. Ship the gate.

## Acceptance A
- Given a client has NO agreements, `POST /approvals/packages/{opp_id}` → 409 with `detail = "MSA + NDA required (missing: NDA, MSA)"`. No audit row.
- Given only an Executed NDA (no MSA), → 409 with `detail = "MSA + NDA required (missing: MSA)"`.
- Given an Executed NDA + an Executed MSA, submission proceeds.
- Given an MSA in state `expired`, → 409 (expired ≠ valid).
- Given a client has multiple legal_entities, the check passes if the specific legal_entity linked to the opportunity has both, OR the client has both across entities (Legal's coverage model: entity-level; blueprint §6.2). Take the entity-level path first, then fall back to client-level for legacy.
- Test asserts no audit row on 409 (nothing partial written).

## User story B: cost-field response filtering
As a Sales user, when I read a shared resource that includes cost fields
(e.g. deal detail's gm_model summary, adviser estimate), the API response
strips `hourly_cost`, `cost_low`, `cost_base`, `cost_high`, and any similar
compensation-derived cost. Endpoint-level role gates already cover most
places; this closes the gap where a Sales user can read a container that
happens to embed a cost field.

## Acceptance B
- Given a Sales user hits `GET /deals/{id}` and the deal has a gm_model summary,
  the response's gm_model section omits `hourly_cost`, `cost_us`, `cost_india`
  (renders only `revenue_us`, `revenue_india`, `governance_status`, `blended_gm`).
- Given a Finance user hits the same endpoint, all cost fields are present.
- Filter is centralized in `api/app/services/redact.py` as a role-aware
  pydantic serializer; any new endpoint that returns cost must go through it.
- Test: parametrized across all governance roles for `/deals/{id}`, `/clients/{id}`,
  `/adviser/estimates/{id}` (public views), and `/delivery-model/{opp_id}`.

## User story C: approval SLA hard timer
As any approver, if an approval decision on a package sits with me for
> 2 business days without action, the escalation_level bumps and my
function head is notified. Blueprint §4 SLA: "one business day to accept
ownership, two business days per approval".

## Acceptance C
- Given a package moves to `pending_delivery_hr` at day T, the assigned Delivery + HR approvers each get a task with `due_date = T + 2 business days`.
- At T + 1 biz day, an approver-nudge notification is queued.
- At T + 2 biz days without decision, escalation_level → 1 + `escalation` notification to function head.
- At T + 3 biz days, escalation_level → 2.
- All time-travel via `DEALGATE_NOW`.
- Runs inside the existing `worker/alert_scheduler.py`.

## Data touched
- No new tables.
- `approval_package.status` transitions unchanged; `task.due_date` set on approver-task creation.

## Roles
- The gates and filters are read/write pass-through; no new role.

## Notes
- Blueprint §2 (NDA+MSA hard rule) — currently only tracked, not enforced.
- Blueprint §3 (Sales cannot see individual salary or contractor cost).
- Blueprint §4 (2-business-day SLA per approval).
