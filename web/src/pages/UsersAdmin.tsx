import { useCallback, useEffect, useState } from "react";
import type { ListUsersQuery, UserRow } from "../api/client";
import { listUsers } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { FilterBar } from "../ui/FilterBar";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { EditGroupsDrawer } from "./EditGroupsDrawer";
import { InviteUserModal } from "./InviteUserModal";

/**
 * Users & roles admin page. Every mutation goes through the API — the
 * client-side gate on the SystemAdmin nav link is UX only; the server still
 * checks `require_role`.
 */
export function UsersAdminPage() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [allowedGroups, setAllowedGroups] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [group, setGroup] = useState<string>("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [editing, setEditing] = useState<UserRow | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query: ListUsersQuery = {};
    if (search.trim()) query.search = search.trim();
    if (group) query.group = group;
    listUsers(query)
      .then((res) => {
        setRows(res.items);
        setAllowedGroups(res.allowed_groups);
      })
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [search, group]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<UserRow>[] = [
    { key: "email", header: "Email", render: (u) => u.email },
    { key: "name", header: "Name", render: (u) => u.name },
    {
      key: "groups",
      header: "Groups",
      render: (u) => (
        <span style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
          {u.groups.length === 0 ? (
            <span style={{ color: "#6b7280" }}>—</span>
          ) : (
            u.groups.map((g) => <StatusChip key={g}>{g}</StatusChip>)
          )}
        </span>
      ),
    },
    {
      key: "last_login",
      header: "Last login",
      render: (u) => (
        <span style={{ fontSize: 12, color: u.last_login ? "#111827" : "#6b7280" }}>
          {u.last_login ?? "never"}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Users & roles"
        subtitle="Invite people, change group membership. Admin never approves packages."
        right={
          <button
            type="button"
            onClick={() => setInviteOpen(true)}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Invite user
          </button>
        }
      />
      <FilterBar>
        <input
          type="text"
          aria-label="Search users"
          placeholder="Search email or name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4, minWidth: 220 }}
        />
        <select
          aria-label="Group filter"
          value={group}
          onChange={(e) => setGroup(e.target.value)}
          style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
        >
          <option value="">Any group</option>
          {allowedGroups.map((g) => (
            <option key={g} value={g}>
              {g}
            </option>
          ))}
        </select>
      </FilterBar>
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching users." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No users found"
          hint="Invite the first teammate to get started."
        />
      ) : (
        <Table
          ariaLabel="Users"
          columns={columns}
          rows={rows}
          onRowClick={(row) => setEditing(row)}
        />
      )}
      <InviteUserModal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        allowedGroups={allowedGroups}
        onInvited={() => load()}
      />
      <EditGroupsDrawer
        user={editing}
        open={editing !== null}
        allowedGroups={allowedGroups}
        onClose={() => setEditing(null)}
        onSaved={() => load()}
      />
    </div>
  );
}
