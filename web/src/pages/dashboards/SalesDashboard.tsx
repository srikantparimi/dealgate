/**
 * Sales dashboard — scoped to the caller. My deals, next client actions,
 * missing contracts, adviser estimates, approval statuses.
 */

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  getSalesDashboard,
  type SalesDashboard,
} from "../../api/client";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { PageHeader } from "../../ui/PageHeader";
import { StatusChip } from "../../ui/StatusChip";
import { Table, type Column } from "../../ui/Table";
import { DashboardCard } from "./shared";

export function SalesDashboardPage() {
  const [data, setData] = useState<SalesDashboard | null>(null);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(() => {
    setError(null);
    getSalesDashboard()
      .then(setData)
      .catch(setError);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error && !data) return <ErrorState error={error} retry={load} />;
  if (!data)
    return <EmptyState title="Loading" hint="Fetching Sales dashboard." />;

  const dealCols: Column<{ id: string } & SalesDashboard["my_deals"][number]>[] = [
    {
      key: "deal",
      header: "Deal",
      render: (r) => (
        <Link to={`/sows/${r.id}`} style={{ color: "#1d4ed8" }}>
          {r.hubspot_deal_id}
        </Link>
      ),
    },
    { key: "stage", header: "Sales stage", render: (r) => r.sales_stage ?? "—" },
    { key: "gov", header: "Governance", render: (r) => r.governance_status },
    { key: "next", header: "Next action", render: (r) => r.next_client_action ?? "—" },
    { key: "date", header: "Next date", render: (r) => r.next_client_date ?? "—" },
  ];
  const dealRows = data.my_deals.map((r) => ({ ...r, id: r.id }));

  const nextCols = dealCols;
  const nextRows = data.next_client_actions.map((r) => ({ ...r, id: r.id }));

  const missingCols: Column<{ id: string } & SalesDashboard["missing_contracts"][number]>[] = [
    {
      key: "client",
      header: "Client",
      render: (r) => (
        <Link to={`/clients/${r.client_id}`} style={{ color: "#1d4ed8" }}>
          {r.client_name ?? r.client_id}
        </Link>
      ),
    },
    { key: "state", header: "Coverage", render: (r) => r.coverage_state },
  ];
  const missingRows = data.missing_contracts.map((r) => ({
    ...r,
    id: r.client_id,
  }));

  const estCols: Column<{ id: string } & SalesDashboard["adviser_estimates"][number]>[] = [
    { key: "id", header: "Estimate", render: (r) => r.id.slice(0, 8) + "…" },
    { key: "submitted", header: "Submitted", render: (r) => r.submitted_at ?? "—" },
    {
      key: "reviewed",
      header: "Reviewed",
      render: (r) =>
        r.reviewed ? (
          <StatusChip tone="ok">yes</StatusChip>
        ) : (
          <StatusChip tone="warn">no</StatusChip>
        ),
    },
  ];
  const estRows = data.adviser_estimates.map((r) => ({ ...r, id: r.id }));

  const apCols: Column<{ id: string } & SalesDashboard["approval_statuses"][number]>[] = [
    { key: "id", header: "Package", render: (r) => r.id.slice(0, 8) + "…" },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "submitted", header: "Submitted", render: (r) => r.submitted_at ?? "—" },
  ];
  const apRows = data.approval_statuses.map((r) => ({ ...r, id: r.id }));

  return (
    <div>
      <PageHeader title="Sales dashboard" subtitle="Your deals and their state." />

      <DashboardCard title="My deals">
        {dealRows.length === 0 ? (
          <EmptyState title="No deals owned" />
        ) : (
          <Table ariaLabel="My deals" columns={dealCols} rows={dealRows} />
        )}
      </DashboardCard>

      <DashboardCard title="Next client actions">
        {nextRows.length === 0 ? (
          <EmptyState title="No next actions logged" />
        ) : (
          <Table ariaLabel="Next actions" columns={nextCols} rows={nextRows} />
        )}
      </DashboardCard>

      <DashboardCard title="Missing contracts">
        {missingRows.length === 0 ? (
          <EmptyState title="Every client has complete coverage" />
        ) : (
          <Table
            ariaLabel="Missing contracts"
            columns={missingCols}
            rows={missingRows}
          />
        )}
      </DashboardCard>

      <DashboardCard title="Adviser estimates">
        {estRows.length === 0 ? (
          <EmptyState title="No estimates yet" />
        ) : (
          <Table ariaLabel="Adviser estimates" columns={estCols} rows={estRows} />
        )}
      </DashboardCard>

      <DashboardCard title="Approval statuses">
        {apRows.length === 0 ? (
          <EmptyState title="No packages submitted" />
        ) : (
          <Table ariaLabel="Approval statuses" columns={apCols} rows={apRows} />
        )}
      </DashboardCard>
    </div>
  );
}
