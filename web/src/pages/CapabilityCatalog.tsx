import { useCallback, useEffect, useState } from "react";
import type {
  CapabilityRow,
  CreateCapabilityBody,
  PatchCapabilityBody,
} from "../api/client";
import {
  ApiError,
  createCapability,
  deleteCapability,
  listCapabilities,
  patchCapability,
} from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { Modal } from "../ui/Modal";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

/**
 * Delivery / SystemAdmin capability catalog admin.
 *
 * Read is broader (Delivery / Presales / Marketing / Sales / SystemAdmin)
 * so the page is visible to everyone who might want to browse the
 * catalog. Writes are gated to Delivery / SystemAdmin server-side; the
 * client hides the "Add" and per-row action buttons for anyone else.
 */
export function CapabilityCatalogPage({
  canWrite = true,
  canDelete = true,
}: {
  canWrite?: boolean;
  canDelete?: boolean;
} = {}) {
  const [rows, setRows] = useState<CapabilityRow[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [modal, setModal] = useState<null | { mode: "create" } | { mode: "edit"; row: CapabilityRow }>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listCapabilities({ search: search || undefined })
      .then((res) => {
        setRows(res.items);
      })
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [search]);

  useEffect(() => {
    load();
  }, [load]);

  async function onDelete(row: CapabilityRow) {
    if (!canDelete) return;
    if (!window.confirm(`Delete capability "${row.name}"?`)) return;
    try {
      await deleteCapability(row.id);
      load();
    } catch (err) {
      setError(err);
    }
  }

  const columns: Column<CapabilityRow>[] = [
    { key: "name", header: "Name", render: (v) => <strong>{v.name}</strong> },
    {
      key: "description",
      header: "Description",
      render: (v) => (
        <span style={{ color: "#374151" }}>
          {v.description.length > 160
            ? `${v.description.slice(0, 159)}…`
            : v.description}
        </span>
      ),
    },
    {
      key: "tags",
      header: "Tags",
      render: (v) =>
        v.tags.length ? (
          <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }}>
            {v.tags.map((t) => (
              <span
                key={t}
                style={{
                  padding: "2px 8px",
                  borderRadius: 999,
                  background: "#eef2ff",
                  fontSize: 12,
                  color: "#3730a3",
                }}
              >
                {t}
              </span>
            ))}
          </span>
        ) : (
          <span style={{ color: "#9ca3af" }}>—</span>
        ),
    },
    {
      key: "has_embedding",
      header: "Embedding",
      render: (v) =>
        v.has_embedding ? (
          <StatusChip tone="ok">Indexed</StatusChip>
        ) : (
          <StatusChip tone="warn">Pending</StatusChip>
        ),
    },
    {
      key: "actions",
      header: "",
      render: (v) => (
        <span style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          {canWrite ? (
            <button
              type="button"
              aria-label={`Edit ${v.name}`}
              onClick={() => setModal({ mode: "edit", row: v })}
              style={buttonSecondaryStyle}
            >
              Edit
            </button>
          ) : null}
          {canDelete ? (
            <button
              type="button"
              aria-label={`Delete ${v.name}`}
              onClick={() => onDelete(v)}
              style={{ ...buttonSecondaryStyle, color: "#b91c1c" }}
            >
              Delete
            </button>
          ) : null}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Capabilities"
        subtitle="Delivery-owned catalog of what DealGate has actually delivered. The adviser retrieves against this list when proposing a team."
        right={
          canWrite ? (
            <button
              type="button"
              onClick={() => setModal({ mode: "create" })}
              style={buttonPrimaryStyle}
            >
              Add capability
            </button>
          ) : null
        }
      />

      <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
        <input
          aria-label="Search capabilities"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search name or description…"
          style={{
            flex: 1,
            border: "1px solid #d1d5db",
            borderRadius: 6,
            padding: "8px 10px",
          }}
        />
      </div>

      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching capabilities." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No capabilities yet"
          hint={
            canWrite
              ? "Add the first capability to unlock adviser retrieval."
              : "The Delivery team has not curated any capabilities yet."
          }
        />
      ) : (
        <Table
          ariaLabel="Capability catalog"
          columns={columns}
          rows={rows}
        />
      )}

      {modal ? (
        <CapabilityModal
          initial={modal.mode === "edit" ? modal.row : null}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null);
            load();
          }}
        />
      ) : null}
    </div>
  );
}


const buttonPrimaryStyle: React.CSSProperties = {
  background: "#111827",
  color: "white",
  border: "none",
  padding: "8px 16px",
  borderRadius: 6,
  cursor: "pointer",
};

const buttonSecondaryStyle: React.CSSProperties = {
  background: "white",
  color: "#111827",
  border: "1px solid #d1d5db",
  padding: "4px 10px",
  borderRadius: 6,
  cursor: "pointer",
  fontSize: 13,
};


function CapabilityModal({
  initial,
  onClose,
  onSaved,
}: {
  initial: CapabilityRow | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [tags, setTags] = useState((initial?.tags ?? []).join(", "));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit() {
    setSubmitting(true);
    setError(null);
    const tagList = tags
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean);
    try {
      if (initial) {
        const patch: PatchCapabilityBody = {
          name: name !== initial.name ? name : undefined,
          description:
            description !== initial.description ? description : undefined,
          tags: JSON.stringify(tagList) !== JSON.stringify(initial.tags)
            ? tagList
            : undefined,
        };
        await patchCapability(initial.id, patch);
      } else {
        const body: CreateCapabilityBody = {
          name,
          description,
          tags: tagList,
        };
        await createCapability(body);
      }
      onSaved();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={initial ? "Edit capability" : "Add capability"}
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            style={buttonSecondaryStyle}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSubmit}
            disabled={submitting || !name.trim() || !description.trim()}
            style={{
              ...buttonPrimaryStyle,
              opacity:
                submitting || !name.trim() || !description.trim() ? 0.5 : 1,
            }}
          >
            {initial ? "Save" : "Add"}
          </button>
        </>
      }
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        style={{ display: "flex", flexDirection: "column", gap: 12 }}
      >
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, color: "#374151" }}>Name</span>
          <input
            aria-label="Capability name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{
              border: "1px solid #d1d5db",
              borderRadius: 6,
              padding: "8px 10px",
            }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, color: "#374151" }}>Description</span>
          <textarea
            aria-label="Capability description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            style={{
              border: "1px solid #d1d5db",
              borderRadius: 6,
              padding: "8px 10px",
              fontFamily: "inherit",
            }}
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, color: "#374151" }}>
            Tags (comma separated)
          </span>
          <input
            aria-label="Capability tags"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="salesforce, crm, integration"
            style={{
              border: "1px solid #d1d5db",
              borderRadius: 6,
              padding: "8px 10px",
            }}
          />
        </label>
        {error ? (
          <div
            role="alert"
            style={{
              background: "#fef2f2",
              border: "1px solid #fecaca",
              color: "#991b1b",
              padding: 8,
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            {error}
          </div>
        ) : null}
      </form>
    </Modal>
  );
}
