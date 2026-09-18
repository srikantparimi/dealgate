import { useCallback, useEffect, useState } from "react";
import type { RateCardVersionSummary } from "../api/client";
import { listRateCards } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { PublishRateCardModal } from "./PublishRateCardModal";

/**
 * Finance's rate card admin: list published versions, highlight the active
 * one, publish a new version via the modal. Reads are Finance/Delivery/HR/
 * SystemAdmin (server-enforced); the client-side nav gate only hides the
 * link from other roles.
 */
export function RateCardsPage() {
  const [rows, setRows] = useState<RateCardVersionSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listRateCards()
      .then((res) => {
        setRows(res.items);
        setActiveId(res.active_id);
      })
      .catch((err) => {
        setError(err);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<RateCardVersionSummary>[] = [
    {
      key: "effective_from",
      header: "Effective from",
      render: (v) => (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          {v.effective_from}
          {v.is_active ? <StatusChip tone="ok">Active</StatusChip> : null}
        </span>
      ),
    },
    {
      key: "row_count",
      header: "Rows",
      render: (v) => <span>{v.row_count}</span>,
    },
    {
      key: "published_at",
      header: "Published",
      render: (v) => (
        <span style={{ fontSize: 12, color: "#374151" }}>
          {new Date(v.published_at).toLocaleString()}
        </span>
      ),
    },
    {
      key: "notes",
      header: "Notes",
      render: (v) => (
        <span style={{ color: v.notes ? "#111827" : "#9ca3af" }}>
          {v.notes ?? "—"}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Rate cards"
        subtitle="Finance-owned planning cost bands. Every publish creates a new immutable version tied to an effective date."
        right={
          <button
            type="button"
            onClick={() => setModalOpen(true)}
            style={{
              background: "#111827",
              color: "white",
              border: "none",
              padding: "8px 16px",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            Publish new version
          </button>
        }
      />
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching rate cards." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No rate cards yet"
          hint="Publish the first version to unlock GM calculations."
        />
      ) : (
        <Table
          ariaLabel="Rate card versions"
          columns={columns}
          rows={rows}
        />
      )}
      <PublishRateCardModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onPublished={load}
      />
      {activeId ? null : null /* activeId used indirectly via row.is_active */}
    </div>
  );
}
