import { useEffect, useState } from "react";
import type { UserRow } from "../api/client";
import { ApiError, patchUserGroups } from "../api/client";
import { Drawer } from "../ui/Drawer";
import { StatusChip } from "../ui/StatusChip";
import { RoleHistoryPanel } from "./RoleHistoryPanel";

/**
 * Slide-out editor for one user's groups. The admin picks groups to add /
 * remove; the save button calls `patchUserGroups` and surfaces the API
 * message inline on 409/422 (e.g. "cannot remove the last SystemAdmin").
 *
 * History for the same user renders inside the drawer so the admin sees the
 * trail their change is about to add to.
 */
export function EditGroupsDrawer({
  user,
  allowedGroups,
  open,
  onClose,
  onSaved,
}: {
  user: UserRow | null;
  allowedGroups: string[];
  open: boolean;
  onClose: () => void;
  onSaved: (user: UserRow) => void;
}) {
  const [add, setAdd] = useState<string[]>([]);
  const [remove, setRemove] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setAdd([]);
    setRemove([]);
    setError(null);
    setSaving(false);
  }, [user?.id, open]);

  if (!user) return null;

  const current = new Set(user.groups);
  const addable = allowedGroups.filter((g) => !current.has(g));

  function toggleAdd(group: string) {
    setAdd((cur) =>
      cur.includes(group) ? cur.filter((g) => g !== group) : [...cur, group],
    );
  }
  function toggleRemove(group: string) {
    setRemove((cur) =>
      cur.includes(group) ? cur.filter((g) => g !== group) : [...cur, group],
    );
  }

  async function save() {
    if (!user) return;
    setError(null);
    setSaving(true);
    try {
      const updated = await patchUserGroups(user.id, { add, remove });
      onSaved(updated);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else if (err instanceof Error) setError(err.message);
      else setError("Failed to update groups");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      title={`Edit groups — ${user.email}`}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            style={{
              background: "white",
              color: "#374151",
              border: "1px solid #e5e7eb",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || (add.length === 0 && remove.length === 0)}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: saving ? "wait" : "pointer",
              opacity: saving || (add.length === 0 && remove.length === 0) ? 0.6 : 1,
            }}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </>
      }
    >
      <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
            Current groups
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {user.groups.length === 0 ? (
              <span style={{ color: "#6b7280", fontSize: 14 }}>None</span>
            ) : (
              user.groups.map((g) => <StatusChip key={g}>{g}</StatusChip>)
            )}
          </div>
        </div>

        <fieldset
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 4,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <legend style={{ fontSize: 12, color: "#6b7280", padding: "0 6px" }}>
            Add
          </legend>
          {addable.length === 0 ? (
            <span style={{ color: "#6b7280", fontSize: 14 }}>
              This user already has every allowed group.
            </span>
          ) : (
            addable.map((group) => (
              <label
                key={group}
                style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}
              >
                <input
                  type="checkbox"
                  aria-label={`Add ${group}`}
                  checked={add.includes(group)}
                  onChange={() => toggleAdd(group)}
                />
                {group}
              </label>
            ))
          )}
        </fieldset>

        <fieldset
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 4,
            padding: 12,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <legend style={{ fontSize: 12, color: "#6b7280", padding: "0 6px" }}>
            Remove
          </legend>
          {user.groups.length === 0 ? (
            <span style={{ color: "#6b7280", fontSize: 14 }}>
              Nothing to remove.
            </span>
          ) : (
            user.groups.map((group) => (
              <label
                key={group}
                style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}
              >
                <input
                  type="checkbox"
                  aria-label={`Remove ${group}`}
                  checked={remove.includes(group)}
                  onChange={() => toggleRemove(group)}
                />
                {group}
              </label>
            ))
          )}
        </fieldset>

        {error ? (
          <div
            role="alert"
            style={{
              background: "#fef2f2",
              color: "#991b1b",
              border: "1px solid #fecaca",
              padding: 8,
              borderRadius: 4,
              fontSize: 14,
            }}
          >
            {error}
          </div>
        ) : null}

        <div>
          <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>
            Role history
          </div>
          <RoleHistoryPanel userId={user.id} />
        </div>
      </section>
    </Drawer>
  );
}
