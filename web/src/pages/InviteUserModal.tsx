import { useState } from "react";
import type { InviteUserBody, UserRow } from "../api/client";
import { ApiError, inviteUser } from "../api/client";
import { Modal } from "../ui/Modal";

/**
 * Invite-user modal. Submit calls `inviteUser`, closes on success, shows an
 * inline error on 409 (duplicate) or 422 (bad group). Reset on open/close so
 * the form doesn't remember partial input across sessions.
 */
export function InviteUserModal({
  open,
  onClose,
  onInvited,
  allowedGroups,
}: {
  open: boolean;
  onClose: () => void;
  onInvited: (user: UserRow) => void;
  allowedGroups: string[];
}) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [groups, setGroups] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function toggleGroup(group: string) {
    setGroups((current) =>
      current.includes(group)
        ? current.filter((g) => g !== group)
        : [...current, group],
    );
  }

  function reset() {
    setEmail("");
    setName("");
    setGroups([]);
    setError(null);
    setSubmitting(false);
  }

  function handleClose() {
    reset();
    onClose();
  }

  async function submit() {
    setError(null);
    setSubmitting(true);
    try {
      const body: InviteUserBody = { email: email.trim(), name: name.trim(), groups };
      const created = await inviteUser(body);
      onInvited(created);
      reset();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to invite user");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Invite user"
      onClose={handleClose}
      footer={
        <>
          <button
            type="button"
            onClick={handleClose}
            disabled={submitting}
            style={{
              background: "white",
              color: "#374151",
              border: "1px solid #e5e7eb",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={submitting || !email.trim() || !name.trim()}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: submitting ? "wait" : "pointer",
              opacity: submitting || !email.trim() || !name.trim() ? 0.6 : 1,
            }}
          >
            {submitting ? "Inviting…" : "Invite"}
          </button>
        </>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Email</span>
          <input
            aria-label="Email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 12, color: "#6b7280" }}>Name</span>
          <input
            aria-label="Name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ padding: 6, border: "1px solid #e5e7eb", borderRadius: 4 }}
          />
        </label>
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
            Groups
          </legend>
          {allowedGroups.map((group) => (
            <label
              key={group}
              style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14 }}
            >
              <input
                type="checkbox"
                aria-label={`Group ${group}`}
                checked={groups.includes(group)}
                onChange={() => toggleGroup(group)}
              />
              {group}
            </label>
          ))}
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
      </div>
    </Modal>
  );
}
