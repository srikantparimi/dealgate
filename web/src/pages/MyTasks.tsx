import { useCallback, useEffect, useState } from "react";
import type {
  ListTasksQuery,
  TaskInboxRow,
} from "../api/client";
import {
  ApiError,
  listTasks,
  patchTask,
  reassignTask,
} from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { Drawer } from "../ui/Drawer";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { FilterBar } from "../ui/FilterBar";
import { Modal } from "../ui/Modal";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

const LEADER_ROLES = new Set(["SalesLeader", "HR", "SystemAdmin"]);

// Categories the API accepts; kept in one place so the filter and any new
// category badge use the same list.
const CATEGORIES = ["intake", "coverage", "approval", "expiry"] as const;

function statusTone(status: string): "ok" | "warn" | "block" | "neutral" {
  if (status === "done") return "ok";
  if (status === "cancelled") return "block";
  if (status === "snoozed") return "warn";
  return "neutral";
}

/**
 * "My tasks" inbox. Owner defaults to `me`; leaders may broaden the scope by
 * toggling the "All owners" filter. Row actions call PATCH /tasks/{id} for
 * transitions and POST /tasks/{id}/reassign for reassignment.
 */
export function MyTasksPage() {
  const { user } = useAuth();
  const isLeader = (user?.groups ?? []).some((g) => LEADER_ROLES.has(g));

  const [rows, setRows] = useState<TaskInboxRow[]>([]);
  const [status, setStatus] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [owner, setOwner] = useState<"me" | "all">("me");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [snoozeTarget, setSnoozeTarget] = useState<TaskInboxRow | null>(null);
  const [reassignTarget, setReassignTarget] = useState<TaskInboxRow | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query: ListTasksQuery = {};
    if (owner === "me") query.owner = "me";
    if (status) query.status = status;
    if (category) query.category = category;
    if (owner === "all") query.include_snoozed = true;
    listTasks(query)
      .then((res) => setRows(res.items))
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [status, category, owner]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(t);
  }, [toast]);

  async function transition(row: TaskInboxRow, next: string) {
    try {
      await patchTask(row.id, { status: next });
      setToast(`Task ${next}`);
      load();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Transition failed";
      setToast(msg);
    }
  }

  const columns: Column<TaskInboxRow>[] = [
    { key: "subject", header: "Subject", render: (r) => r.subject },
    {
      key: "category",
      header: "Category",
      render: (r) => (
        <span style={{ color: r.category ? "#111827" : "#6b7280" }}>
          {r.category ?? "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (r) => <StatusChip tone={statusTone(r.status)}>{r.status}</StatusChip>,
    },
    {
      key: "due",
      header: "Due",
      render: (r) => (
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          {r.due_date ?? "—"}
        </span>
      ),
    },
    {
      key: "escalation",
      header: "Esc.",
      render: (r) =>
        r.escalation_level > 0 ? (
          <StatusChip tone="warn">L{r.escalation_level}</StatusChip>
        ) : (
          <span style={{ color: "#6b7280" }}>—</span>
        ),
    },
    {
      key: "actions",
      header: "Actions",
      render: (r) => (
        <span style={{ display: "flex", gap: 6 }}>
          {r.status === "assigned" ? (
            <button
              type="button"
              aria-label={`Start ${r.subject}`}
              onClick={(e) => {
                e.stopPropagation();
                transition(r, "in_progress");
              }}
              style={buttonStyle}
            >
              Start
            </button>
          ) : null}
          {r.status === "in_progress" || r.status === "assigned" ? (
            <button
              type="button"
              aria-label={`Complete ${r.subject}`}
              onClick={(e) => {
                e.stopPropagation();
                transition(r, "done");
              }}
              style={buttonStyle}
            >
              Complete
            </button>
          ) : null}
          {r.status !== "done" && r.status !== "cancelled" ? (
            <button
              type="button"
              aria-label={`Snooze ${r.subject}`}
              onClick={(e) => {
                e.stopPropagation();
                setSnoozeTarget(r);
              }}
              style={buttonStyle}
            >
              Snooze
            </button>
          ) : null}
          {isLeader ? (
            <button
              type="button"
              aria-label={`Reassign ${r.subject}`}
              onClick={(e) => {
                e.stopPropagation();
                setReassignTarget(r);
              }}
              style={buttonStyle}
            >
              Reassign
            </button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="My tasks"
        subtitle="Everything assigned to you, ordered by due date."
      />
      <FilterBar>
        <select
          aria-label="Status filter"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">Any status</option>
          <option value="assigned">assigned</option>
          <option value="in_progress">in_progress</option>
          <option value="snoozed">snoozed</option>
          <option value="done">done</option>
          <option value="cancelled">cancelled</option>
        </select>
        <select
          aria-label="Category filter"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">Any category</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        {isLeader ? (
          <select
            aria-label="Owner filter"
            value={owner}
            onChange={(e) => setOwner(e.target.value as "me" | "all")}
          >
            <option value="me">Mine</option>
            <option value="all">All owners</option>
          </select>
        ) : null}
      </FilterBar>
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching your tasks." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No tasks"
          hint="You're clear. New tasks show up here as they're assigned."
        />
      ) : (
        <Table ariaLabel="My tasks" columns={columns} rows={rows} />
      )}

      {toast ? (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            bottom: 24,
            right: 24,
            background: "#111827",
            color: "white",
            padding: "8px 12px",
            borderRadius: 6,
            fontSize: 14,
          }}
        >
          {toast}
        </div>
      ) : null}

      <SnoozeModal
        task={snoozeTarget}
        onClose={() => setSnoozeTarget(null)}
        onSnoozed={() => {
          setSnoozeTarget(null);
          setToast("Task snoozed");
          load();
        }}
      />
      <ReassignDrawer
        task={reassignTarget}
        onClose={() => setReassignTarget(null)}
        onReassigned={() => {
          setReassignTarget(null);
          setToast("Task reassigned");
          load();
        }}
      />
    </div>
  );
}

const buttonStyle: React.CSSProperties = {
  background: "white",
  border: "1px solid #e5e7eb",
  padding: "4px 8px",
  borderRadius: 4,
  fontSize: 12,
  cursor: "pointer",
};

function SnoozeModal({
  task,
  onClose,
  onSnoozed,
}: {
  task: TaskInboxRow | null;
  onClose: () => void;
  onSnoozed: () => void;
}) {
  const [wakeAt, setWakeAt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setWakeAt("");
    setError(null);
    setSaving(false);
  }, [task?.id]);

  async function save() {
    if (!task || !wakeAt) return;
    setSaving(true);
    setError(null);
    try {
      // <input type=datetime-local> returns a local time string without tz.
      const iso = new Date(wakeAt).toISOString();
      await patchTask(task.id, { status: "snoozed", wake_at: iso });
      onSnoozed();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Snooze failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={task !== null}
      title={task ? `Snooze — ${task.subject}` : "Snooze"}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} style={buttonStyle}>
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!wakeAt || saving}
            style={{ ...buttonStyle, background: "#111827", color: "white" }}
          >
            {saving ? "Saving…" : "Snooze"}
          </button>
        </>
      }
    >
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, color: "#6b7280" }}>Wake at</span>
        <input
          aria-label="Wake at"
          type="datetime-local"
          value={wakeAt}
          onChange={(e) => setWakeAt(e.target.value)}
          style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
        />
      </label>
      {error ? (
        <div role="alert" style={errorStyle}>
          {error}
        </div>
      ) : null}
    </Modal>
  );
}

function ReassignDrawer({
  task,
  onClose,
  onReassigned,
}: {
  task: TaskInboxRow | null;
  onClose: () => void;
  onReassigned: () => void;
}) {
  const [newOwnerId, setNewOwnerId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setNewOwnerId("");
    setError(null);
    setSaving(false);
  }, [task?.id]);

  async function save() {
    if (!task || !newOwnerId) return;
    setSaving(true);
    setError(null);
    try {
      await reassignTask(task.id, { new_owner_id: newOwnerId });
      onReassigned();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reassign failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={task !== null}
      title={task ? `Reassign — ${task.subject}` : "Reassign"}
      onClose={onClose}
      footer={
        <>
          <button type="button" onClick={onClose} style={buttonStyle}>
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={!newOwnerId || saving}
            style={{ ...buttonStyle, background: "#111827", color: "white" }}
          >
            {saving ? "Saving…" : "Reassign"}
          </button>
        </>
      }
    >
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, color: "#6b7280" }}>New owner user id</span>
        <input
          aria-label="New owner id"
          type="text"
          value={newOwnerId}
          onChange={(e) => setNewOwnerId(e.target.value)}
          placeholder="uuid"
          style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
        />
      </label>
      <p style={{ fontSize: 12, color: "#6b7280", marginTop: 8 }}>
        Paste the target user's id. A picker lands in a follow-up story.
      </p>
      {error ? (
        <div role="alert" style={errorStyle}>
          {error}
        </div>
      ) : null}
    </Drawer>
  );
}

const errorStyle: React.CSSProperties = {
  background: "#fef2f2",
  color: "#991b1b",
  border: "1px solid #fecaca",
  padding: 8,
  borderRadius: 4,
  fontSize: 14,
  marginTop: 12,
};
