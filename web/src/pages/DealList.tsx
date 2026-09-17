import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { DealListResponse, DealRow, ListDealsQuery } from "../api/client";
import { getDeals } from "../api/client";
import { EmptyState } from "../ui/EmptyState";
import { ErrorState } from "../ui/ErrorState";
import { PageHeader } from "../ui/PageHeader";
import { StatusChip } from "../ui/StatusChip";
import { Table, type Column } from "../ui/Table";

type OwnerFilter = "me" | "all";

function statusTone(status: string): "ok" | "warn" | "block" | "neutral" {
  if (status === "Approved" || status === "Signed") return "ok";
  if (status === "Blocked" || status === "Rejected") return "block";
  if (status === "Intake" || status === "Coverage") return "warn";
  return "neutral";
}

function coverageTone(coverage: string): "ok" | "warn" | "block" | "neutral" {
  if (coverage === "Complete") return "ok";
  if (coverage.includes("expired")) return "block";
  if (coverage.includes("missing") || coverage.includes("No client")) return "warn";
  return "neutral";
}

export function DealListPage() {
  const navigate = useNavigate();
  const [owner, setOwner] = useState<OwnerFilter>("me");
  const [status, setStatus] = useState<string>("");
  const [data, setData] = useState<DealListResponse | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const query: ListDealsQuery = {};
    if (owner === "me") query.owner = "me";
    if (status) query.status = status;
    getDeals(query)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        setError(err);
        setData(null);
      })
      .finally(() => setLoading(false));
  }, [owner, status]);

  useEffect(() => {
    load();
  }, [load]);

  const columns: Column<DealRow>[] = [
    { key: "hubspot", header: "Deal", render: (r) => r.hubspot_deal_id },
    { key: "engagement", header: "Engagement", render: (r) => r.engagement_type ?? "—" },
    { key: "stage", header: "Sales stage", render: (r) => r.sales_stage ?? "—" },
    {
      key: "governance",
      header: "Governance",
      render: (r) => <StatusChip tone={statusTone(r.governance_status)}>{r.governance_status}</StatusChip>,
    },
    {
      key: "next",
      header: "Next action",
      render: (r) => (
        <span>
          <div>{r.next_client_action ?? "—"}</div>
          <div style={{ color: "#6b7280", fontSize: 12 }}>{r.next_client_date ?? ""}</div>
        </span>
      ),
    },
    {
      key: "coverage",
      header: "Coverage",
      render: (r) => <StatusChip tone={coverageTone(r.coverage_state)}>{r.coverage_state}</StatusChip>,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Deals"
        subtitle="Governance status, next client action, coverage state."
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <select
              aria-label="Owner filter"
              value={owner}
              onChange={(e) => setOwner(e.target.value as OwnerFilter)}
            >
              <option value="me">My deals</option>
              <option value="all">All deals</option>
            </select>
            <select
              aria-label="Governance status filter"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Any status</option>
              <option value="Intake">Intake</option>
              <option value="Coverage">Coverage</option>
              <option value="SOWDraft">SOWDraft</option>
              <option value="Approved">Approved</option>
              <option value="Signed">Signed</option>
              <option value="Blocked">Blocked</option>
            </select>
          </div>
        }
      />
      {error ? (
        <ErrorState error={error} retry={load} />
      ) : loading && !data ? (
        <EmptyState title="Loading" hint="Fetching your deals." />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="No deals yet"
          hint="Newly synced HubSpot deals show up here."
        />
      ) : (
        <Table
          ariaLabel="Deals"
          columns={columns}
          rows={data.items}
          onRowClick={(row) => navigate(`/deals/${row.id}`)}
        />
      )}
    </div>
  );
}
