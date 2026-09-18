import { useCallback, useEffect, useState } from "react";
import type {
  ActivePolicy,
  FxConvention,
  PolicyVersionRow,
} from "../api/client";
import { listPolicies } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";
import { PublishPolicyModal } from "./PublishPolicyModal";

/**
 * Finance-owned margin policy admin: US/India floors + FX convention. The
 * "current policy" card at the top always shows the effective values —
 * either the latest published version or the blueprint sentinel (US 0.35 /
 * India 0.50) if Finance has not published one yet.
 */
export function PolicyAdminPage() {
  const [rows, setRows] = useState<PolicyVersionRow[]>([]);
  const [active, setActive] = useState<ActivePolicy | null>(null);
  const [allowedFx, setAllowedFx] = useState<FxConvention[]>([
    "fixed_at_sow_date",
    "monthly_average",
  ]);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    listPolicies()
      .then((res) => {
        setRows(res.items);
        setActive(res.active);
        setAllowedFx(res.allowed_fx_conventions);
      })
      .catch((err) => {
        setError(err);
        setRows([]);
        setActive(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<PolicyVersionRow>[] = [
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
    { key: "us_floor", header: "US floor", render: (v) => v.us_floor },
    { key: "india_floor", header: "India floor", render: (v) => v.india_floor },
    {
      key: "fx_convention",
      header: "FX",
      render: (v) => v.fx_convention,
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
        title="Margin policy"
        subtitle="Finance-owned US/India floors and FX convention. Each publish creates a new immutable version."
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
            Publish new policy
          </button>
        }
      />
      {active ? (
        <div
          aria-label="Active policy"
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: 16,
            marginBottom: 16,
            display: "flex",
            gap: 24,
            alignItems: "center",
            background: "#f9fafb",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <StatusChip tone={active.is_default ? "warn" : "ok"}>
              {active.is_default ? "Defaults" : "Active"}
            </StatusChip>
            <span style={{ fontSize: 12, color: "#6b7280" }}>
              {active.effective_from
                ? `Effective ${active.effective_from}`
                : "No version published — blueprint defaults in effect"}
            </span>
          </div>
          <div style={{ display: "flex", gap: 24, fontSize: 14 }}>
            <span>
              <strong>US:</strong> {active.us_floor}
            </span>
            <span>
              <strong>India:</strong> {active.india_floor}
            </span>
            <span>
              <strong>FX:</strong> {active.fx_convention}
            </span>
          </div>
        </div>
      ) : null}
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && rows.length === 0 ? (
        <EmptyState title="Loading" hint="Fetching policy versions." />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No policy versions yet"
          hint="Finance can publish the first version above. Blueprint defaults are in effect until then."
        />
      ) : (
        <Table
          ariaLabel="Policy versions"
          columns={columns}
          rows={rows}
        />
      )}
      <PublishPolicyModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onPublished={load}
        allowedFxConventions={allowedFx}
      />
    </div>
  );
}
