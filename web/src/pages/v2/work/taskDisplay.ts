/**
 * Task view helpers — spec §6.
 *
 * The API returns raw `status`, `category`, `due_date` and
 * `escalation_level`. These helpers translate those primitives into the
 * four workspace tabs and the humane row copy the spec calls for. All
 * time math happens against `now` passed in, so tests are deterministic.
 */
import type { TaskInboxRow } from "../../../api/client";
import type { StatusTone } from "../../../ui-v2/StatusBadge";

export type WorkTabId = "assigned" | "waiting" | "overdue" | "completed";

export interface WorkTabDef {
  id: WorkTabId;
  label: string;
}

export const WORK_TABS: WorkTabDef[] = [
  { id: "assigned", label: "Assigned to me" },
  { id: "waiting", label: "Waiting on others" },
  { id: "overdue", label: "Overdue" },
  { id: "completed", label: "Completed" },
];

/**
 * The category taxonomy from the API. `approval` and `signature` are
 * the two categories that MUST NOT expose the manual-complete checkbox
 * (spec §6 — completion happens through the underlying workflow).
 */
export const TASK_CATEGORIES: string[] = [
  "intake",
  "coverage",
  "approval",
  "signature",
  "expiry",
  "followup",
];

const WORKFLOW_ONLY_CATEGORIES = new Set(["approval", "approval.awaiting", "approval.routing", "signature"]);

/** Row → tab mapping. `Completed` includes `done` + `cancelled`; a
 * snoozed or blocked task lives under "Waiting on others". */
export function tabForRow(row: TaskInboxRow, now: Date): WorkTabId {
  if (row.status === "done" || row.status === "cancelled") return "completed";
  if (isOverdue(row, now)) return "overdue";
  if (row.status === "snoozed" || row.status === "blocked") return "waiting";
  return "assigned";
}

export function isOverdue(row: TaskInboxRow, now: Date): boolean {
  if (!row.due_date) return false;
  if (row.status === "done" || row.status === "cancelled") return false;
  // Compare on YYYY-MM-DD to keep the boundary honest across time zones.
  const today = now.toISOString().slice(0, 10);
  return row.due_date < today;
}

/** Days a task is past due; 0 when not overdue. */
export function overdueDays(row: TaskInboxRow, now: Date): number {
  if (!isOverdue(row, now)) return 0;
  const due = new Date(`${row.due_date}T00:00:00Z`).getTime();
  const today = new Date(now.toISOString().slice(0, 10) + "T00:00:00Z").getTime();
  return Math.max(0, Math.round((today - due) / 86400000));
}

/** True when a plain checkbox is allowed to move a task to `done`
 * (spec §6). Approval + signature tasks always route through the
 * underlying workflow. */
export function canCheckboxComplete(row: TaskInboxRow): boolean {
  if (row.status !== "open") return false;
  if (!row.category) return true;
  return !WORKFLOW_ONLY_CATEGORIES.has(row.category);
}

export function statusTone(status: string): StatusTone {
  if (status === "done") return "ok";
  if (status === "cancelled") return "neutral";
  if (status === "snoozed" || status === "blocked") return "warn";
  return "primarySubtle";
}

export function statusLabel(status: string): string {
  if (status === "open") return "Open";
  if (status === "done") return "Complete";
  if (status === "cancelled") return "Cancelled";
  if (status === "snoozed") return "Snoozed";
  if (status === "blocked") return "Blocked";
  return status;
}

/** The primary next action shown in the last row cell — a short,
 * verb-first phrase per category (spec §6). Never fabricates a due
 * date or an owner. */
export function nextActionLabel(row: TaskInboxRow): string {
  const c = row.category ?? "";
  if (c === "approval" || c === "approval.awaiting") return "Review package";
  if (c === "approval.routing") return "Resolve routing blocker";
  if (c === "signature") return "Prepare signature";
  if (c === "coverage") return "Resolve agreement";
  if (c === "expiry") return "Confirm renewal";
  if (c === "followup") return "Log client follow-up";
  if (c === "intake") return "Complete intake";
  return "Open task";
}

export interface Filters {
  category: string;
  client: string;
  owner: string;
  priority: string;
  dueRange: "any" | "week" | "month" | "quarter";
}

export const DEFAULT_FILTERS: Filters = {
  category: "",
  client: "",
  owner: "",
  priority: "",
  dueRange: "any",
};

export function matchesFilters(
  row: TaskInboxRow,
  f: Filters,
  now: Date,
): boolean {
  if (f.category && (row.category ?? "") !== f.category) return false;
  if (f.dueRange !== "any") {
    if (!row.due_date) return false;
    const due = new Date(`${row.due_date}T00:00:00Z`).getTime();
    const today = new Date(now.toISOString().slice(0, 10) + "T00:00:00Z").getTime();
    const days = Math.round((due - today) / 86400000);
    if (f.dueRange === "week" && (days < -30 || days > 7)) return false;
    if (f.dueRange === "month" && (days < -30 || days > 30)) return false;
    if (f.dueRange === "quarter" && (days < -60 || days > 90)) return false;
  }
  // client/owner/priority are captured but not yet indexed on the row
  // shape returned by /tasks. We keep the filter available in the UI so
  // future backend enrichment does not require a shell change; today
  // they act as fuzzy text matches against the subject.
  const needle = [f.client, f.owner, f.priority].filter(Boolean).join(" ").toLowerCase();
  if (needle && !row.subject.toLowerCase().includes(needle)) return false;
  return true;
}
