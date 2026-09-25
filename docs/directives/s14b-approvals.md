# Directive S14b: approval groups, the submit path, and the pending-with stream

From: Kanna Parimi, product owner. Commit as `docs/directives/s14b-approvals.md`. Evidence: on the SOW workspace (SOW 5921506c, Peppermill), after clicking "Complete scope" there is no next action anywhere — the Approvals tab shows only "No approval package submitted" with no button, and the user is stranded. There is also no way to define who approves for each function. This slice makes the approval flow usable end to end. The governance rules themselves (order, freezing, versions, CEO gate) are already in the blueprint and build guide and do not change here.

## 1. The header CTA is a state machine, never a dead end

The workspace header has exactly one primary action, derived from the record's state, always present:

| State | Primary action | If blocked |
| --- | --- | --- |
| Scope draft | Complete scope | — |
| Scope confirmed, GM complete | **Submit for approval** | — |
| Scope confirmed, GM incomplete | Open Staffing & GM | names the missing inputs |
| Submitted | View review status (jumps to Approvals tab) | — |
| Changes requested | Resolve review | names the function and reason |
| All approved, floors met | Prepare signature | — |
| Floor failed | Awaiting CEO decision (link) | — |
| Approved + conditions unmet | Blocked: <condition> | names owner and evidence needed |

"Complete scope" completing and then showing nothing is the defect. Also fix the status contradiction visible now: the stepper shows step 2 checked while the chip and readiness panel say "Scope draft" — all three read the same state field; a checked step with a draft chip must be impossible. Per the blueprint, missing NDA/MSA does **not** block submitting for functional review — it blocks signature. The readiness panel should say so: "NDA missing — blocks signature, not review."

## 2. Approval groups

Settings → People & access → **Groups** tab. Five system groups, not deletable: Delivery, HR, Finance, Legal, Executive. Each group: members (picked from the user list), one **default approver**, optional backups, per-business-unit override later (not this slice). Executive holds the CEO and any recorded time-bound delegate (existing delegation model). Server-side: an approval for function X can only be assigned to, and decided by, a member of group X. Empty group = submission warns and the package cannot route that function; the gap appears on the command center as a blocker with an owner (admin).

## 3. Submit flow

"Submit for approval" opens one dialog: the frozen package identity (SOW v + GM v), and the four function rows, each pre-filled with the group's default approver, changeable only to another member of that group, with a due date defaulted from the SLA. If any floor fails, a fifth row appears: CEO (Executive group), not editable, marked "exception — brief will be generated". Confirm creates the package, assigns the approvals, notifies each approver, and the header CTA flips to "View review status". Separation of duties: the submitter cannot be an approver on the same package even if they are in a group; the dialog shows why their name is filtered out.

## 4. The pending-with stream

The Approvals tab becomes a live timeline, newest at top:

- Entry per event: submitted (by, at), each function's card — **Pending with <name>** (avatar, due date, aging "2d"), then Approved / Changes requested / Rejected (by, at, reason), CEO decision, resubmissions. Exact package versions on every entry.
- The four function cards keep the D/H/F/L mark row in sync everywhere it already appears (board card, command center preview).
- "Pending with" also surfaces: on the board card (already shows next action — make it the approver's name), in each approver's My Work as an actionable item, and in the readiness panel.
- Live updates: poll every 20s while the tab is open (no websocket infra this slice); an approver acting in one browser is visible in another within one poll cycle. Show "updated 12s ago".
- Approvers act from the stream: Approve / Request changes / Reject with mandatory reason, permission-checked server-side, exactly the existing package rules. Acting from the emailed deep link lands here.

## 5. Header hygiene (same screens, same slice)

- Owner shows a raw UUID on the SOW header — wire OwnerRef here too; grep the workspace header components for any remaining id-rendered-as-text.
- Breadcrumb shows the raw opportunity UUID — render client name → SOW title.
- The SOW title renders as a version hash ("SOW · 5921506c"). Title = extracted SOW title (or client + engagement type fallback); the hash stays in the meta line only.
- "Type —" and "Delivery —" with real values (they exist on the record: Fixed price, delivery model) or omit the field.

## Definition of done — browser-proven on staging with two real users

Using two e2e users (submitter + an approver seeded into the Delivery group; reuse the Cognito fixture pattern):

1. Groups screen: create members, set default approver; empty-group warning works.
2. Peppermill SOW: Complete scope → header immediately shows "Submit for approval" → dialog shows pre-filled approvers, submitter filtered out with explanation → submit succeeds.
3. Approvals tab shows "Pending with <approver>" with due date; board card and approver's My Work show the same.
4. Log in as the approver in a second context, approve with a note → submitter's open tab reflects it within one poll cycle (screenshot both browsers).
5. Below-floor fixture: CEO row auto-added, stream shows the exception entry.
6. Stepper, chips and readiness panel agree with each other in every state traversed; NDA-missing message names signature, not review.
7. Report `docs/reports/s14b.md`: screenshots, test IDs, files added/deleted. Existing suites stay green.
