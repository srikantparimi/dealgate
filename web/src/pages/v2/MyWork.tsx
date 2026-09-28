/**
 * My work (`/work`) — spec §6.
 *
 * Four tabs: Assigned to me / Waiting on others / Overdue / Completed.
 * Filters: task type (category), client, owner, due-range, priority.
 * Header action: Create task (drafts a scaffold locally — a full
 * create endpoint arrives with the Task authoring story).
 *
 * Row click opens the right Sheet drawer defined in
 * `./work/TaskDrawer`. The drawer decides which action buttons render
 * — approval + signature tasks route to the workflow, never a generic
 * checkbox.
 *
 * All time-sensitive logic (overdue split, due-range filter) is
 * captured in `./work/taskDisplay` so it stays deterministic under
 * test.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import {
  ApiError,
  listTasks,
  patchTask,
  reassignTask,
  type TaskInboxRow,
} from "../../api/client";
import { EmptyState } from "../../ui-v2/EmptyState";
import { ErrorState } from "../../ui-v2/ErrorState";
import { PageHeader } from "../../ui-v2/PageHeader";
import { StatusBadge } from "../../ui-v2/StatusBadge";
import { Button } from "../../ui-v2/primitives/button";
import { Checkbox } from "../../ui-v2/primitives/checkbox";
import { Input } from "../../ui-v2/primitives/input";
import { Label } from "../../ui-v2/primitives/label";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../../ui-v2/primitives/tabs";
import { TaskDrawer } from "./work/TaskDrawer";
import {
  DEFAULT_FILTERS,
  TASK_CATEGORIES,
  WORK_TABS,
  canCheckboxComplete,
  isOverdue,
  matchesFilters,
  nextActionLabel,
  overdueDays,
  statusLabel,
  statusTone,
  tabForRow,
  type Filters,
  type WorkTabId,
} from "./work/taskDisplay";

export function MyWorkPage() {
  const [rows, setRows] = useState<TaskInboxRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [tab, setTab] = useState<WorkTabId>("assigned");
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [detail, setDetail] = useState<TaskInboxRow | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [now] = useState<Date>(() => new Date());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // The server accepts owner/status query params. We pull the full
      // set with `owner=me` + `include_snoozed` so the four tabs can
      // split client-side; that keeps the tab counts consistent with
      // what the drawer sees without extra round-trips.
      const res = await listTasks({ owner: "me", include_snoozed: true });
      setRows(res.items);
    } catch (err) {
      setError(err);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const counts = useMemo(() => {
    const c: Record<WorkTabId, number> = {
      assigned: 0,
      waiting: 0,
      overdue: 0,
      completed: 0,
    };
    for (const r of rows) c[tabForRow(r, now)] += 1;
    return c;
  }, [rows, now]);

  const filtered = useMemo(
    () =>
      rows.filter(
        (r) => tabForRow(r, now) === tab && matchesFilters(r, filters, now),
      ),
    [rows, tab, filters, now],
  );

  async function completeTask(row: TaskInboxRow) {
    if (!canCheckboxComplete(row)) return;
    setBusy(true);
    try {
      await patchTask(row.id, { status: "done" });
      setNotice(`Marked "${row.subject}" complete.`);
      await load();
      setDetail(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      setNotice(`Complete failed — ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function reopenTask(row: TaskInboxRow) {
    setBusy(true);
    try {
      await patchTask(row.id, { status: "open" });
      setNotice(`Reopened "${row.subject}".`);
      await load();
      setDetail(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      setNotice(`Reopen failed — ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  async function reassign(row: TaskInboxRow, newOwnerId: string) {
    setBusy(true);
    try {
      await reassignTask(row.id, { new_owner_id: newOwnerId });
      setNotice(`Reassigned "${row.subject}".`);
      await load();
      setDetail(null);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : String(err);
      setNotice(`Reassign failed — ${msg}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="My work"
        subtitle="Tasks routed to you. Overdue rows escalate to your manager per the configured rule; approval and signature tasks complete through their own workflow."
        actions={
          <Button
            variant="primary"
            onClick={() =>
              setNotice(
                "Create task opens once the task-authoring story ships — for now, tasks arrive from the workflow scheduler.",
              )
            }
            aria-label="Create task"
          >
            <Plus className="h-4 w-4" aria-hidden />
            Create task
          </Button>
        }
      />

      {notice ? (
        <div
          role="status"
          className="mb-4 rounded-panel border border-primary/30 bg-primary-subtle px-4 py-3 text-body text-text"
        >
          {notice}
        </div>
      ) : null}

      <FilterRow filters={filters} onChange={setFilters} />

      <Tabs value={tab} onValueChange={(v) => setTab(v as WorkTabId)}>
        <TabsList aria-label="Task views">
          {WORK_TABS.map((t) => (
            <TabsTrigger key={t.id} value={t.id}>
              {t.label} ({counts[t.id]})
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value={tab} forceMount>
          {loading ? (
            <div
              role="status"
              className="rounded-panel border border-divider p-6 text-body text-text-secondary"
            >
              Loading tasks…
            </div>
          ) : error ? (
            <ErrorState
              title="We couldn't load your tasks"
              description={
                error instanceof ApiError ? error.message : String(error)
              }
              onRetry={() => {
                void load();
              }}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              title="Nothing in this view."
              description={emptyCopy(tab)}
            />
          ) : (
            <div className="overflow-x-auto rounded-panel border border-divider">
              <table
                className="w-full text-body"
                aria-label="My tasks"
                data-testid="work-table"
              >
                <thead className="bg-primary-subtle/40">
                  <tr className="text-left text-secondary text-text-secondary">
                    <th className="px-3 py-2 font-medium w-8">
                      <span className="sr-only">Complete</span>
                    </th>
                    <th className="px-3 py-2 font-medium">Task · record</th>
                    <th className="px-3 py-2 font-medium">Type</th>
                    <th className="px-3 py-2 font-medium">Assignee</th>
                    <th className="px-3 py-2 font-medium">Due · overdue</th>
                    <th className="px-3 py-2 font-medium">Status</th>
                    <th className="px-3 py-2 font-medium">Next action</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((row) => (
                    <TaskRow
                      key={row.id}
                      row={row}
                      now={now}
                      busy={busy}
                      onOpen={() => setDetail(row)}
                      onCheckboxComplete={() => completeTask(row)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      <TaskDrawer
        task={detail}
        now={now}
        busy={busy}
        onClose={() => setDetail(null)}
        onComplete={(t) => void completeTask(t)}
        onReopen={(t) => void reopenTask(t)}
        onReassign={(t, id) => void reassign(t, id)}
      />
    </div>
  );
}

function emptyCopy(tab: WorkTabId): string {
  if (tab === "assigned")
    return "You have no open tasks assigned to you right now.";
  if (tab === "waiting")
    return "No tasks are waiting on someone else at the moment.";
  if (tab === "overdue")
    return "Nothing is overdue — the scheduler will surface a task here as soon as one slips past due.";
  return "No completed tasks yet in this window.";
}

interface TaskRowProps {
  row: TaskInboxRow;
  now: Date;
  busy: boolean;
  onOpen: () => void;
  onCheckboxComplete: () => void;
}

function TaskRow({
  row,
  now,
  busy,
  onOpen,
  onCheckboxComplete,
}: TaskRowProps) {
  const canCheckbox = canCheckboxComplete(row);
  const overdue = isOverdue(row, now);
  const overdueBy = overdueDays(row, now);

  return (
    <tr
      data-testid={`task-row-${row.id}`}
      className="cursor-pointer border-t border-divider hover:bg-primary-subtle/30"
      onClick={onOpen}
    >
      <td
        className="px-3 py-3 align-top"
        // Stop the row click from firing when the user targets the
        // checkbox itself — otherwise the drawer opens on top of the
        // completion toast.
        onClick={(e) => e.stopPropagation()}
      >
        {canCheckbox ? (
          <Checkbox
            aria-label={`Mark "${row.subject}" complete`}
            checked={row.status === "done"}
            disabled={busy}
            onCheckedChange={(v) => {
              if (v) onCheckboxComplete();
            }}
          />
        ) : (
          <span
            aria-label="Workflow task — completes through its screen"
            title="Approval and signature tasks complete through the underlying workflow"
            className="inline-block h-4 w-4 rounded-[4px] border border-dashed border-divider"
          />
        )}
      </td>
      <td className="px-3 py-3 align-top">
        <div className="text-text">{row.subject}</div>
        <div className="text-secondary text-text-secondary">
          Task {row.id.slice(0, 8)}
        </div>
      </td>
      <td className="px-3 py-3 align-top text-text-secondary">
        {row.category ?? "General"}
      </td>
      <td className="px-3 py-3 align-top text-text-secondary tnum">
        {row.owner_name ?? "Unassigned"}
      </td>
      <td className="px-3 py-3 align-top tnum">
        <div className="text-text">{row.due_date ?? "No due date"}</div>
        {overdue ? (
          <div className="text-danger text-secondary">
            {overdueBy}d overdue
          </div>
        ) : null}
      </td>
      <td className="px-3 py-3 align-top">
        <StatusBadge
          tone={statusTone(row.status)}
          label={statusLabel(row.status)}
        />
      </td>
      <td className="px-3 py-3 align-top text-text">{nextActionLabel(row)}</td>
    </tr>
  );
}

interface FilterRowProps {
  filters: Filters;
  onChange: (next: Filters) => void;
}

function FilterRow({ filters, onChange }: FilterRowProps) {
  return (
    <div className="mb-4 grid grid-cols-1 gap-3 rounded-panel border border-divider bg-surface p-3 sm:grid-cols-2 lg:grid-cols-5">
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-category">Task type</Label>
        <select
          id="filter-category"
          className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
          value={filters.category}
          onChange={(e) => onChange({ ...filters, category: e.target.value })}
        >
          <option value="">Any</option>
          {TASK_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-client">Client</Label>
        <Input
          id="filter-client"
          type="search"
          placeholder="Client name"
          value={filters.client}
          onChange={(e) => onChange({ ...filters, client: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-owner">Owner</Label>
        <Input
          id="filter-owner"
          type="search"
          placeholder="Owner name or email"
          value={filters.owner}
          onChange={(e) => onChange({ ...filters, owner: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-due">Due range</Label>
        <select
          id="filter-due"
          className="h-10 rounded-control border border-input-border bg-surface px-3 text-body text-text focus-visible:outline-focus"
          value={filters.dueRange}
          onChange={(e) =>
            onChange({ ...filters, dueRange: e.target.value as Filters["dueRange"] })
          }
        >
          <option value="any">Any due date</option>
          <option value="week">Next 7 days</option>
          <option value="month">Next 30 days</option>
          <option value="quarter">Next 90 days</option>
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <Label htmlFor="filter-priority">Priority</Label>
        <Input
          id="filter-priority"
          type="search"
          placeholder="e.g. high"
          value={filters.priority}
          onChange={(e) => onChange({ ...filters, priority: e.target.value })}
        />
      </div>
    </div>
  );
}
