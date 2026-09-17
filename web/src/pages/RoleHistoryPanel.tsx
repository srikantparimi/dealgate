import { useEffect, useState } from "react";
import type { RoleHistoryRow, UUID } from "../api/client";
import { getRoleHistory } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { Table, type Column } from "../ui/Table";

/**
 * Read-only slice of `audit_event` rows scoped to one user, filtered to
 * `user.*` actions. Rendered inside the edit-groups drawer so the admin can
 * see the trail without navigating away.
 */
export function RoleHistoryPanel({ userId }: { userId: UUID }) {
  const [rows, setRows] = useState<RoleHistoryRow[] | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setRows(null);
    getRoleHistory(userId)
      .then((res) => {
        if (!cancelled) setRows(res.items);
      })
      .catch((err) => {
        if (!cancelled) setError(err);
      });
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (error) return <ErrorState error={error} />;
  if (rows === null) return <EmptyState title="Loading role history" />;
  if (rows.length === 0)
    return <EmptyState title="No role changes yet" hint="Group changes will appear here." />;

  const columns: Column<RoleHistoryRow>[] = [
    {
      key: "when",
      header: "When",
      render: (r) => <span style={{ fontSize: 12 }}>{r.ts}</span>,
    },
    {
      key: "action",
      header: "Action",
      render: (r) => <span style={{ fontSize: 12 }}>{r.action}</span>,
    },
    {
      key: "summary",
      header: "Change",
      render: (r) => <span style={{ fontSize: 12 }}>{summarise(r)}</span>,
    },
    {
      key: "actor",
      header: "Actor",
      render: (r) => (
        <span style={{ fontSize: 12, color: "#6b7280" }}>
          {r.actor_id ?? "system"}
        </span>
      ),
    },
  ];

  return <Table ariaLabel="Role history" columns={columns} rows={rows} />;
}

function summarise(row: RoleHistoryRow): string {
  const after = row.after ?? {};
  const added = Array.isArray((after as Record<string, unknown>).added)
    ? ((after as Record<string, unknown>).added as string[])
    : [];
  const removed = Array.isArray((after as Record<string, unknown>).removed)
    ? ((after as Record<string, unknown>).removed as string[])
    : [];
  const parts: string[] = [];
  if (added.length) parts.push(`+ ${added.join(", ")}`);
  if (removed.length) parts.push(`- ${removed.join(", ")}`);
  if (parts.length === 0) {
    // Fallback for `user.invited` and other actions that don't carry the diff.
    const groups = (after as Record<string, unknown>).groups;
    if (Array.isArray(groups) && groups.length > 0) {
      return `groups: ${(groups as string[]).join(", ")}`;
    }
    return row.action;
  }
  return parts.join(" ");
}
